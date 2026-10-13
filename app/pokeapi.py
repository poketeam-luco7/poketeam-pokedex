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
    data = await get_json(f"/pokemon/{str(id_or_name).lower()}")
    types = [t["type"]["name"] for t in sorted(data["types"], key=lambda t: t["slot"])]
    relations = await asyncio.gather(*(_type_relations(t) for t in types))

    stats = {STAT_NAMES[s["stat"]["name"]]: s["base_stat"] for s in data["stats"]}
    weak, resist = weaknesses_and_resistances(list(relations))

    return {
        "id": data["id"],
        "name": data["name"],
        "isMega": is_mega(data["name"]),
        "baseSpecies": base_species(data["name"]),
        "sprite": data["sprites"]["front_default"] or SPRITE_URL.format(id=data["id"]),
        "types": types,
        "stats": stats,
        "statTotal": sum(stats.values()),
        "weaknesses": weak,
        "resistances": resist,
    }


def is_mega(name: str) -> bool:
    """Formes Méga dans PokéAPI : 'charizard-mega-x', 'gyarados-mega'...
    ('meganium' ou 'yanmega' ne contiennent pas '-mega')."""
    return "-mega" in name


def base_species(name: str) -> str:
    return name.split("-mega")[0] if is_mega(name) else name


async def _pokemon_index() -> dict[int, dict]:
    """Tous les Pokémon utiles (formes de base + Méga), avec leurs types.

    Construit uniquement à partir des 18 pages de types (déjà en cache) :
    aucune requête par Pokémon. Les autres formes alternatives (Alola, Gigamax...)
    ont un id > 10000 sans '-mega' et sont ignorées.
    """
    type_pages = await asyncio.gather(*(get_json(f"/type/{t}") for t in ALL_TYPES))
    index: dict[int, dict] = {}
    for type_name, page in zip(ALL_TYPES, type_pages):
        for entry in page["pokemon"]:
            pid = _id_from_url(entry["pokemon"]["url"])
            name = entry["pokemon"]["name"]
            if pid >= 10000 and not is_mega(name):
                continue
            p = index.setdefault(pid, {
                "id": pid,
                "name": name,
                "sprite": SPRITE_URL.format(id=pid),
                "isMega": is_mega(name),
                "baseSpecies": base_species(name),
                "_slots": [],
            })
            p["_slots"].append((entry["slot"], type_name))
    for p in index.values():
        p["types"] = [t for _, t in sorted(p["_slots"])]
    return index


def _public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


async def list_generation(num: int) -> list[dict]:
    """Liste des Pokémon d'une génération : id, nom, sprite, types.

    L'ancien monolithe faisait un appel par Pokémon, les uns après les autres
    (~150 appels pour la génération 1). Ici : 1 appel pour la génération +
    18 appels pour les types, en parallèle et mis en cache.
    """
    gen = await get_json(f"/generation/{num}")
    index = await _pokemon_index()

    result = []
    for species in gen["pokemon_species"]:
        pid = _id_from_url(species["url"])  # id de l'espèce = id de la forme par défaut
        p = index.get(pid, {"types": []})
        result.append({
            "id": pid,
            "name": species["name"],
            "sprite": SPRITE_URL.format(id=pid),
            "types": p["types"],
            "isMega": False,
            "baseSpecies": species["name"],
        })
    return sorted(result, key=lambda p: p["id"])


async def list_megas() -> list[dict]:
    """Toutes les Méga-Évolutions, rangées après leur forme de base."""
    index = await _pokemon_index()
    base_ids = {p["name"]: p["id"] for p in index.values() if not p["isMega"]}
    megas = [p for p in index.values() if p["isMega"]]
    megas.sort(key=lambda p: (base_ids.get(p["baseSpecies"], 99999), p["id"]))
    return [_public(p) for p in megas]


async def list_by_type(type_name: str) -> list[dict]:
    """Tous les Pokémon d'un type, toutes générations confondues, puis les Méga."""
    index = await _pokemon_index()
    found = [p for p in index.values() if type_name in p["types"]]
    found.sort(key=lambda p: (p["isMega"], p["id"]))
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
