"""Façade vers PokéAPI (Anti-Corruption Layer) avec cache en mémoire.

Le format brut de PokéAPI ne sort jamais de ce fichier : le reste du système
ne voit que des profils simplifiés.
"""
from __future__ import annotations

import asyncio
import os

import httpx

from datetime import date, datetime, time, timedelta, timezone

from .logic import (ALL_TYPES, BOSS_STAT_MULTIPLIER, analyze_team, boss_of_week, boss_summary,
                    weaknesses_and_resistances)

POKEAPI_URL = os.getenv("POKEAPI_URL", "https://pokeapi.co/api/v2")
SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"
ARTWORK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png"

STAT_NAMES = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "spAtk",
    "special-defense": "spDef",
    "speed": "speed",
}

# Cache jetable : les données PokéAPI ne changent pas, et un redémarrage
# le vide simplement. Le service reste donc sans état.
_cache: dict[str, dict] = {}


class NotFound(Exception):
    pass


async def _fetch(path: str) -> dict:
    """Seul point de contact avec le réseau (remplacé dans les tests)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{POKEAPI_URL}{path}")
    if r.status_code == 404:
        raise NotFound(path)
    r.raise_for_status()
    return r.json()


async def get_json(path: str) -> dict:
    if path not in _cache:
        _cache[path] = await _fetch(path)
    return _cache[path]


def _id_from_url(url: str) -> int:
    return int(url.rstrip("/").split("/")[-1])


async def _type_relations(type_name: str) -> dict:
    rel = (await get_json(f"/type/{type_name}"))["damage_relations"]
    return {
        "double": [t["name"] for t in rel["double_damage_from"]],
        "half": [t["name"] for t in rel["half_damage_from"]],
        "none": [t["name"] for t in rel["no_damage_from"]],
    }


async def get_profile(id_or_name: str) -> dict:
    """Profil d'un Pokémon : stats, types, faiblesses et résistances."""
    key = str(id_or_name).lower()
    type_form = _parse_type_form(key)
    if type_form:
        return await _type_form_profile(*type_form)
    data = await get_json(f"/pokemon/{key}")
    types = [t["type"]["name"] for t in sorted(data["types"], key=lambda t: t["slot"])]
    relations = await asyncio.gather(*(_type_relations(t) for t in types))

    stats = {STAT_NAMES[s["stat"]["name"]]: s["base_stat"] for s in data["stats"]}
    weak, resist = weaknesses_and_resistances(list(relations))

    return {
        "id": data["id"],
        "name": data["name"],
        "isMega": is_mega(data["name"]),
        "isForm": data["id"] >= 10000 and not is_mega(data["name"]),
        "baseSpecies": data.get("species", {}).get("name") or base_species(data["name"]),
        "sprite": data["sprites"]["front_default"] or SPRITE_URL.format(id=data["id"]),
        "types": types,
        "stats": stats,
        "statTotal": sum(stats.values()),
        "weaknesses": weak,
        "resistances": resist,
    }


# --- Formes alternatives --------------------------------------------------------

# Arceus et Silvallié changent de type sans être des Pokémon distincts dans PokéAPI
# (ce sont des « pokemon-form »). Elles sont identifiées par leur nom, ex. "arceus-fire".
TYPE_FORM_SPECIES = {"arceus": 493, "silvally": 773}

# Variétés sans intérêt pour composer une équipe (cosmétiques ou spécifiques à un mode de jeu)
EXCLUDED_VARIETIES = ("-gmax", "-totem", "-starter", "pikachu-", "-power-construct",
                      "-battle-bond", "-own-tempo", "koraidon-", "miraidon-")


def _parse_type_form(name: str):
    for species, pid in TYPE_FORM_SPECIES.items():
        suffix = name.removeprefix(f"{species}-")
        if suffix != name and suffix in ALL_TYPES and suffix != "normal":
            return species, pid, suffix
    return None


def _type_form_entry(species: str, pid: int, type_name: str) -> dict:
    return {
        "id": f"{species}-{type_name}",
        "name": f"{species}-{type_name}",
        "sprite": f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}-{type_name}.png",
        "isMega": False,
        "isForm": True,
        "baseSpecies": species,
        "types": [type_name],
    }


async def _type_form_profile(species: str, pid: int, type_name: str) -> dict:
    """Mêmes stats que l'espèce de base, seul le type change."""
    base = await get_profile(species)
    relations = [await _type_relations(type_name)]
    weak, resist = weaknesses_and_resistances(relations)
    return {**base, **_type_form_entry(species, pid, type_name), "weaknesses": weak, "resistances": resist}


def _is_wanted_variety(name: str) -> bool:
    return not any(x in name for x in EXCLUDED_VARIETIES)


async def _species_names() -> dict[int, str]:
    """id d'espèce -> nom d'espèce, à partir des 9 générations (en cache)."""
    async def gen(n):
        try:
            return await get_json(f"/generation/{n}")
        except NotFound:  # génération absente : on mémorise une page vide
            _cache[f"/generation/{n}"] = {"pokemon_species": []}
            return _cache[f"/generation/{n}"]
    pages = await asyncio.gather(*(gen(n) for n in range(1, 10)))
    return {_id_from_url(s["url"]): s["name"] for page in pages for s in page["pokemon_species"]}


def _species_of(name: str, species: list[str]) -> str:
    """Espèce d'une variété : le plus long nom d'espèce qui préfixe son nom
    ('giratina-origin' -> 'giratina', 'mr-mime-galar' -> 'mr-mime')."""
    best = name
    for s in species:
        if (name == s or name.startswith(s + "-")) and (best == name or len(s) > len(best)):
            best = s
    return best


def is_mega(name: str) -> bool:
    """Formes Méga dans PokéAPI : 'charizard-mega-x', 'gyarados-mega'...
    ('meganium' ou 'yanmega' ne contiennent pas '-mega')."""
    return "-mega" in name


def base_species(name: str) -> str:
    return name.split("-mega")[0] if is_mega(name) else name


async def _pokemon_index() -> dict:
    """Tous les Pokémon utiles avec leurs types : formes de base, Méga, variétés
    (Giratina-Origine, Motisma...) et formes par type (Arceus, Silvallié).

    Construit à partir des 18 pages de types et des 9 générations, toutes en cache :
    aucune requête par Pokémon.
    """
    type_pages, species_by_id = await asyncio.gather(
        asyncio.gather(*(get_json(f"/type/{t}") for t in ALL_TYPES)),
        _species_names(),
    )
    species_list = list(species_by_id.values())
    index: dict = {}
    for type_name, page in zip(ALL_TYPES, type_pages):
        for entry in page["pokemon"]:
            pid = _id_from_url(entry["pokemon"]["url"])
            name = entry["pokemon"]["name"]
            if pid >= 10000 and not is_mega(name) and not _is_wanted_variety(name):
                continue
            p = index.setdefault(pid, {
                "id": pid,
                "name": name,
                "sprite": SPRITE_URL.format(id=pid),
                "isMega": is_mega(name),
                "isForm": pid >= 10000 and not is_mega(name),
                "baseSpecies": species_by_id.get(pid) or _species_of(base_species(name), species_list),
                "_slots": [],
            })
            p["_slots"].append((entry["slot"], type_name))
    for p in index.values():
        p["types"] = [t for _, t in sorted(p["_slots"])]
    for species, pid in TYPE_FORM_SPECIES.items():
        for t in ALL_TYPES:
            if t != "normal":
                entry = _type_form_entry(species, pid, t)
                index[entry["id"]] = entry
    return index


def _public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


async def list_generation(num: int) -> list[dict]:
    """Pokémon d'une génération, chacun suivi de ses formes alternatives
    (Raichu puis Raichu d'Alola, Giratina puis Giratina-Origine, Arceus puis Arceus Feu...).

    L'ancien monolithe faisait un appel par Pokémon, les uns après les autres
    (~150 appels pour la génération 1). Ici tout vient de pages en cache :
    la génération, les 18 types et les 9 générations pour les noms d'espèces.
    """
    gen = await get_json(f"/generation/{num}")
    index = await _pokemon_index()
    base_ids = _base_ids(index)

    forms_by_species: dict[str, list[dict]] = {}
    for p in index.values():
        if p.get("isForm"):
            forms_by_species.setdefault(p["baseSpecies"], []).append(p)

    result = []
    for species in sorted(gen["pokemon_species"], key=lambda s: _id_from_url(s["url"])):
        pid = _id_from_url(species["url"])  # id de l'espèce = id de la forme par défaut
        result.append({
            "id": pid,
            "name": species["name"],
            "sprite": SPRITE_URL.format(id=pid),
            "types": index.get(pid, {"types": []})["types"],
            "isMega": False,
            "isForm": False,
            "baseSpecies": species["name"],
        })
        forms = sorted(forms_by_species.get(species["name"], []), key=lambda p: _rank(p, base_ids))
        result.extend(_public(p) for p in forms)
    return result


async def list_megas() -> list[dict]:
    """Toutes les Méga-Évolutions, rangées après leur forme de base."""
    index = await _pokemon_index()
    base_ids = _base_ids(index)
    megas = [p for p in index.values() if p["isMega"]]
    megas.sort(key=lambda p: (base_ids.get(p["baseSpecies"], 99999), p["id"]))
    return [_public(p) for p in megas]


def _base_ids(index: dict) -> dict[str, int]:
    """Nom d'espèce -> id de sa forme de base (pour ranger les formes après elle)."""
    return {p["baseSpecies"]: p["id"] for p in index.values()
            if isinstance(p["id"], int) and p["id"] < 10000}


def _rank(p: dict, base_ids: dict) -> tuple:
    """Ordre d'affichage : formes de base, puis Méga, puis autres formes, par espèce."""
    group = 1 if p["isMega"] else 2 if p.get("isForm") else 0
    # formes par type (Arceus-Feu...) rangées dans l'ordre officiel des types
    type_order = ALL_TYPES.index(p["types"][0]) if isinstance(p["id"], str) else 0
    return (group, base_ids.get(p["baseSpecies"], 99999), type_order, str(p["id"]))


async def list_by_type(type_name: str) -> list[dict]:
    """Tous les Pokémon d'un type, toutes générations confondues, puis Méga et formes."""
    index = await _pokemon_index()
    base_ids = _base_ids(index)
    found = [p for p in index.values() if type_name in p["types"]]
    found.sort(key=lambda p: _rank(p, base_ids))
    return [_public(p) for p in found]


async def analyze(pokemon_ids: list) -> dict:
    """Profils des membres + summary + couverture + suggestions, en un seul appel."""
    profiles = await asyncio.gather(*(get_profile(pid) for pid in pokemon_ids))
    relations = dict(zip(ALL_TYPES, await asyncio.gather(*(_type_relations(t) for t in ALL_TYPES))))
    return analyze_team(list(profiles), relations)


async def current_boss(today: date | None = None) -> dict:
    """Boss de la semaine : profil, stats multipliées, et date du prochain changement."""
    today = today or datetime.now(timezone.utc).date()
    pick = boss_of_week(today)
    profile = await get_profile(pick["name"])
    next_monday = today + timedelta(days=7 - today.weekday())
    return {
        **profile,
        "artwork": ARTWORK_URL.format(id=profile["id"]),
        "week": pick["week"],
        "endsAt": datetime.combine(next_monday, time(0, 0), timezone.utc).isoformat(),
        "stats": {k: v * BOSS_STAT_MULTIPLIER for k, v in profile["stats"].items()},
        "statTotal": profile["statTotal"] * BOSS_STAT_MULTIPLIER,
        "baseStatTotal": profile["statTotal"],
        "summary": boss_summary(profile),
    }
