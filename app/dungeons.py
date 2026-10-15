"""Règles des donjons et du boss final (domaine pur, sans réseau).

Les légendaires, les fabuleux et les Méga ne se capturent pas en run : chacun a son donjon.
Le mode s'ouvre quand le Pokédex du dresseur est assez rempli ; chaque donjon exige une
équipe assez forte pour y entrer. Comme pour le mode Capture, le Pokédex reste sans état :
la progression du dresseur lui est fournie à chaque appel.
"""
from __future__ import annotations

from .capture import REF, SPRITE_URL, _species_ids, first_stage

DUNGEON_UNLOCK = 25        # Pokémon capturés pour ouvrir le mode Donjons
ENTRY_FACTOR = 3           # total des stats de l'équipe ≥ 3 × celles du Pokémon
STAT_MULTIPLIER = 4        # en combat, le Pokémon du donjon (et le boss final) a ses stats × 4
TYPE_WEIGHT = 3            # ses faiblesses et résistances comptent comme 3 Pokémon

ARTWORK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png"


def requirement(stat_total: int) -> int:
    return stat_total * ENTRY_FACTOR


def _species_dungeon(sid: int) -> dict:
    s = REF["species"][sid]
    reward = first_stage(sid)
    return {"id": sid, "name": s["name"], "kind": s["special"], "statTotal": s["statTotal"],
            "types": s["types"], "sprite": SPRITE_URL.format(id=sid),
            "requirement": requirement(s["statTotal"]),
            "reward": {"id": reward, "name": REF["species"][reward]["name"]}}


def _mega_dungeon(mid: int) -> dict:
    info, owner = REF["megas"][mid], REF["mega_owner"][mid]
    return {"id": mid, "name": info["name"], "kind": "mega", "statTotal": info["statTotal"],
            "types": info["types"], "sprite": SPRITE_URL.format(id=mid),
            "requirement": requirement(info["statTotal"]),
            "reward": {"id": mid, "name": info["name"]},
            "needs": {"id": owner, "name": REF["species"][owner]["name"]}}


def catalog() -> list[dict]:
    """Tous les donjons : un par légendaire ou fabuleux, un par Méga."""
    species = [_species_dungeon(sid) for sid, s in REF["species"].items() if s.get("special")]
    megas = [_mega_dungeon(mid) for mid in REF["megas"]]
    return sorted(species + megas, key=lambda d: (d["statTotal"], d["id"]))


def _owned(unlocked: list) -> set[int]:
    return {int(u) for u in unlocked if str(u).isdigit()}


def state(unlocked: list) -> dict:
    """Ouverture du mode et donjons visibles. Le donjon d'une Méga n'apparaît que si le dresseur
    possède l'espèce qui méga-évolue ; un donjon est conquis quand sa récompense est obtenue."""
    owned = _owned(unlocked)
    owned_chains = {REF["species"][sid]["chain"] for sid in _species_ids(unlocked)}
    captured = len(_species_ids(unlocked))
    dungeons = []
    for d in catalog():
        if d["kind"] == "mega" and d["needs"]["id"] not in owned:
            continue
        reward = d["reward"]["id"]
        conquered = (reward in owned if d["kind"] == "mega"
                     else REF["species"][reward]["chain"] in owned_chains)
        dungeons.append({**d, "conquered": conquered})
    return {"open": captured >= DUNGEON_UNLOCK, "captured": captured, "required": DUNGEON_UNLOCK,
            "dungeons": dungeons, "ultimate": ultimate()}


def check_entry(dungeon_id: int, unlocked: list, team_stat_total: int) -> tuple[dict | None, str | None]:
    """(donjon, None) si le dresseur peut y entrer avec cette équipe, sinon (None, raison)."""
    st = state(unlocked)
    if not st["open"]:
        return None, f"Capture {DUNGEON_UNLOCK} Pokémon pour ouvrir les donjons ({st['captured']}/{DUNGEON_UNLOCK})"
    dungeon = next((d for d in st["dungeons"] if d["id"] == dungeon_id), None)
    if dungeon is None:
        return None, "Ce donjon n'est pas accessible"
    if team_stat_total < dungeon["requirement"]:
        return None, f"Équipe trop faible : {team_stat_total} / {dungeon['requirement']} de stats requises"
    return dungeon, None


def boss_summary(profile: dict) -> dict:
    """Le Pokémon d'un donjon (ou le boss final) vu comme une « équipe » pour la formule."""
    return {
        "name": profile["name"],
        "statTotal": profile["statTotal"] * STAT_MULTIPLIER,
        "weak": {t: TYPE_WEIGHT for t in profile["weaknesses"]},
        "resist": {t: TYPE_WEIGHT for t in profile["resistances"]},
        "offensiveTypes": list(profile["types"]),
    }


# --- Boss final ------------------------------------------------------------------------

def ultimate() -> dict:
    """Éthernatos Infinimax : l'objectif de fin de jeu, accessible à toute équipe assez forte."""
    u = REF["ultimate"]
    return {**u, "requirement": requirement(u["statTotal"]),
            "sprite": SPRITE_URL.format(id=u["id"]), "artwork": ARTWORK_URL.format(id=u["id"])}


def check_ultimate(team_stat_total: int) -> str | None:
    need = ultimate()["requirement"]
    if team_stat_total < need:
        return f"Équipe trop faible pour Éthernatos Infinimax : {team_stat_total} / {need} de stats requises"
    return None

