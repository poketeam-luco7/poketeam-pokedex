"""Façade vers PokéAPI (Anti-Corruption Layer) avec cache en mémoire.

Le format brut de PokéAPI ne sort jamais de ce fichier : le reste du système
ne voit que des profils simplifiés.
"""
from __future__ import annotations

import asyncio
import os

import httpx

from .logic import ALL_TYPES, weaknesses_and_resistances

POKEAPI_URL = os.getenv("POKEAPI_URL", "https://pokeapi.co/api/v2")
SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"

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
        "sprite": data["sprites"]["front_default"],
        "types": types,
        "stats": stats,
        "statTotal": sum(stats.values()),
        "weaknesses": weak,
        "resistances": resist,
    }


async def list_generation(num: int) -> list[dict]:
    """Liste des Pokémon d'une génération : id, nom, sprite, types.

    L'ancien monolithe faisait un appel par Pokémon, les uns après les autres
    (~150 appels pour la génération 1). Ici : 1 appel pour la génération +
    18 appels pour les types, en parallèle et mis en cache.
    """
    gen = await get_json(f"/generation/{num}")
    type_pages = await asyncio.gather(*(get_json(f"/type/{t}") for t in ALL_TYPES))

    # id du Pokémon -> [(slot, type)]
    types_by_id: dict[int, list[tuple[int, str]]] = {}
    for type_name, page in zip(ALL_TYPES, type_pages):
        for entry in page["pokemon"]:
            pid = _id_from_url(entry["pokemon"]["url"])
            types_by_id.setdefault(pid, []).append((entry["slot"], type_name))

    result = []
    for species in gen["pokemon_species"]:
        pid = _id_from_url(species["url"])  # id de l'espèce = id de la forme par défaut
        result.append({
            "id": pid,
            "name": species["name"],
            "sprite": SPRITE_URL.format(id=pid),
            "types": [t for _, t in sorted(types_by_id.get(pid, []))],
        })
    return sorted(result, key=lambda p: p["id"])
