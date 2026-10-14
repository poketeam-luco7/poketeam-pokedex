"""Règles du mode Capture (domaine pur, sans réseau).

Le référentiel data/capture.json (espèces, chaînes d'évolution, stades, stats, Méga)
est généré une fois par scripts/build_capture_data.py et chargé au démarrage.
Le Pokédex reste sans état : la progression de chaque dresseur est stockée par Équipes
et transmise à chaque appel.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "capture.json"

TIER_SIZE = 50                 # paliers de 50 points de stats de base
FIRST_EVOLUTION = 10           # victoires pour passer du 1er au 2e stade
SECOND_EVOLUTION = 30          # victoires pour passer du 2e au 3e stade
EXTRA_BRANCH = 10              # victoires supplémentaires pour choisir une autre branche (Évoli...)
MEGA_THRESHOLD = 50            # victoires avec la forme finale pour débloquer ses Méga
ENCOUNTERS_PER_ROUND = 3
ROUNDS_PER_RUN = 3
MAX_TIERS_BELOW = 1            # un Pokémon peut combattre 1 palier sous le sien, pas 2

# Dernier numéro national de chaque génération (1 à 9)
GENERATION_ENDS = (151, 251, 386, 493, 649, 721, 809, 905, 1025)

SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"


def _load() -> dict:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    species = {s["id"]: s for s in data["species"]}
    children: dict[int, list[int]] = {}
    for s in species.values():
        if s["evolvesFrom"]:
            children.setdefault(s["evolvesFrom"], []).append(s["id"])
    mega_owner = {m: s["id"] for s in species.values() for m in s["megas"]}
    return {"species": species, "children": children, "mega_owner": mega_owner,
            "starters": data["starters"], "by_name": {s["name"]: s["id"] for s in species.values()},
            "megas": {int(k): v for k, v in data.get("megas", {}).items()}}


REF = _load()


# --- Données de base -------------------------------------------------------------

def entry(sid: int) -> dict:
    """Fiche courte d'une espèce, enrichie de son premier stade."""
    s = REF["species"][sid]
    first = first_stage(sid)
    return {
        "id": sid, "name": s["name"], "types": s["types"], "statTotal": s["statTotal"],
        "stage": s["stage"], "sprite": SPRITE_URL.format(id=sid), "isMega": False,
        "tier": tier_index(s["statTotal"]),
        "firstStage": {"id": first, "name": REF["species"][first]["name"]},
    }


def mega_entry(mega_id: int) -> dict:
    owner = REF["species"][REF["mega_owner"][mega_id]]
    info = REF["megas"].get(mega_id, {})
    total = info.get("statTotal")
    return {"id": mega_id, "name": info.get("name", f"{owner['name']}-mega"),
            "types": info.get("types", owner["types"]), "statTotal": total,
            "tier": tier_index(total) if total else None, "stage": owner["stage"],
            "sprite": SPRITE_URL.format(id=mega_id), "isMega": True, "baseSpecies": owner["name"]}


def first_stage(sid: int) -> int:
    s = REF["species"][sid]
    return first_stage(s["evolvesFrom"]) if s["evolvesFrom"] else sid


def starters() -> list[dict]:
    return [entry(sid) for sid in REF["starters"]]


def tier_index(stat_total: int) -> int:
    return stat_total // TIER_SIZE


def tiers(unlocked: list[int] | None = None) -> list[dict]:
    """Paliers de 50 en stats de base, avec le nombre d'espèces et de lignes déjà possédées."""
    owned_chains = _owned_chains(unlocked or [])
    counts: dict[int, list[int]] = {}
    for s in REF["species"].values():
        c = counts.setdefault(tier_index(s["statTotal"]), [0, 0])
        c[0] += 1
        c[1] += s["chain"] in owned_chains
    # Palier terminé (plus rien à capturer) : il sert de terrain d'entraînement
    return [{"index": i, "min": i * TIER_SIZE, "max": i * TIER_SIZE + TIER_SIZE - 1,
             "count": c[0], "owned": c[1], "training": c[0] == c[1]} for i, c in sorted(counts.items())]


def _species_ids(unlocked: list) -> set[int]:
    return {int(u) for u in unlocked if str(u).isdigit() and int(u) in REF["species"]}


def _owned_chains(unlocked: list) -> set[int]:
    return {REF["species"][sid]["chain"] for sid in _species_ids(unlocked)}


# --- Rencontres --------------------------------------------------------------------

def encounter_pool(tier: int, unlocked: list, exclude: list | None = None) -> list[int]:
    """Espèces du palier dont on ne possède pas encore la ligne d'évolution."""
    owned = _owned_chains(unlocked)
    skip = {int(x) for x in (exclude or [])}
    return [sid for sid, s in REF["species"].items()
            if tier_index(s["statTotal"]) == tier and s["chain"] not in owned and sid not in skip]


def tier_species(tier: int) -> list[int]:
    return [sid for sid, s in REF["species"].items() if tier_index(s["statTotal"]) == tier]


def is_training(tier: int, unlocked: list) -> bool:
    """Plus aucune ligne à capturer dans ce palier : la run devient un entraînement."""
    return not encounter_pool(tier, unlocked)


def draw_encounters(tier: int, unlocked: list, exclude: list | None = None,
                    count: int = ENCOUNTERS_PER_ROUND, rng: random.Random | None = None) -> dict:
    """3 adversaires du palier. En capture : parmi les lignes non possédées.
    En entraînement : parmi toutes les espèces du palier (déjà battus évités si possible)."""
    training = is_training(tier, unlocked)
    if training:
        skip = {int(x) for x in (exclude or [])}
        pool = [sid for sid in tier_species(tier) if sid not in skip] or tier_species(tier)
    else:
        pool = encounter_pool(tier, unlocked, exclude)
    picks = (rng or random).sample(pool, min(count, len(pool)))
    return {"training": training,
            "candidates": [entry(sid) for sid in sorted(picks, key=lambda i: REF["species"][i]["statTotal"])]}


def too_strong(members: list[dict], tier: int) -> list[str]:
    """Pokémon trop forts pour le palier : interdits 2 paliers (ou plus) sous le leur,
    pour que les combats restent disputés."""
    return [m["name"] for m in members if tier_index(m["statTotal"]) - tier > MAX_TIERS_BELOW]


def wild_summary(profile: dict, team_size: int) -> dict:
    """Le Pokémon sauvage s'adapte à la taille de l'équipe : on compare la moyenne
    de l'équipe au Pokémon (stats et poids des types multipliés par la taille)."""
    n = max(1, team_size)
    return {
        "name": profile["name"],
        "statTotal": profile["statTotal"] * n,
        "weak": {t: n for t in profile["weaknesses"]},
        "resist": {t: n for t in profile["resistances"]},
        "offensiveTypes": list(profile["types"]),
    }


# --- Évolutions ----------------------------------------------------------------------

def evolution_threshold(sid: int, branches_owned: int) -> int:
    base = FIRST_EVOLUTION if REF["species"][sid]["stage"] == 1 else SECOND_EVOLUTION
    return base + EXTRA_BRANCH * branches_owned


def progression(unlocked: list, victories: dict[str, int]) -> dict:
    """Ce que la progression permet : évolutions automatiques (une seule branche),
    choix à faire (plusieurs branches), Méga à débloquer, et barres de progression."""
    owned = _species_ids(unlocked)
    owned_megas = {int(u) for u in unlocked if str(u).isdigit() and int(u) in REF["mega_owner"]}
    unlock, choices, progress = [], [], {}

    for sid in sorted(owned):
        s = REF["species"][sid]
        v = victories.get(s["name"], 0)
        kids = REF["children"].get(sid, [])
        missing = [k for k in kids if k not in owned]
        if missing:
            threshold = evolution_threshold(sid, len(kids) - len(missing))
            progress[s["name"]] = {"victories": v, "threshold": threshold, "next": [REF["species"][k]["name"] for k in missing]}
            if v >= threshold:
                if len(kids) == 1:
                    unlock.append(missing[0])
                else:
                    choices.append({"from": sid, "fromName": s["name"],
                                    "options": [entry(k) for k in missing]})
        elif not kids and s["megas"] and not set(s["megas"]) <= owned_megas:
            progress[s["name"]] = {"victories": v, "threshold": MEGA_THRESHOLD, "next": ["mega"]}
            if v >= MEGA_THRESHOLD:
                unlock.extend(m for m in s["megas"] if m not in owned_megas)
    return {"unlock": unlock, "choices": choices, "progress": progress}


def collection(unlocked: list) -> list[dict]:
    """Fiches des Pokémon débloqués (espèces puis Méga)."""
    owned = sorted(_species_ids(unlocked), key=lambda i: (REF["species"][i]["chain"], i))
    megas = sorted(int(u) for u in unlocked if str(u).isdigit() and int(u) in REF["mega_owner"])
    return [entry(sid) for sid in owned] + [mega_entry(m) for m in megas]


def unlocked_species_names(unlocked: list) -> list[str]:
    return sorted(REF["species"][sid]["name"] for sid in _species_ids(unlocked))


def is_allowed(profile: dict, unlocked: list) -> bool:
    """Un Pokémon est utilisable s'il est débloqué. Les formes alternatives suivent
    leur espèce ; une Méga doit avoir été débloquée elle-même."""
    if profile.get("isMega"):
        return str(profile["id"]) in {str(u) for u in unlocked}
    return profile["baseSpecies"] in set(unlocked_species_names(unlocked))


# --- Pokédex du dresseur ---------------------------------------------------------------

def generation_of(sid: int) -> int:
    return next(g for g, end in enumerate(GENERATION_ENDS, start=1) if sid <= end)


def dex_progress(unlocked: list) -> dict:
    """Espèces capturées sur le total, globalement et par génération (les Méga à part)."""
    owned = _species_ids(unlocked)
    gens = [{"num": g, "captured": 0, "total": 0} for g in range(1, len(GENERATION_ENDS) + 1)]
    for sid in REF["species"]:
        g = gens[generation_of(sid) - 1]
        g["total"] += 1
        g["captured"] += sid in owned
    owned_megas = {int(u) for u in unlocked if str(u).isdigit() and int(u) in REF["mega_owner"]}
    return {"captured": len(owned), "total": len(REF["species"]), "generations": gens,
            "megas": {"captured": len(owned_megas), "total": len(REF["mega_owner"])}}


def unlocked_megas(unlocked: list) -> list[int]:
    return sorted(int(u) for u in unlocked if str(u).isdigit() and int(u) in REF["mega_owner"])
