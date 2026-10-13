"""Logique métier pure du Pokédex : aucune dépendance réseau, testable seule."""
from __future__ import annotations


ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

# Paramètres de la formule de comparaison (à justifier dans un ADR)
TYPE_WEIGHT = 0.1
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 1.5


def defensive_multipliers(type_relations: list[dict]) -> dict[str, float]:
    """Multiplicateur subi pour chaque type attaquant.

    type_relations : pour chaque type du Pokémon, ses damage_relations
    simplifiées {"double": [...], "half": [...], "none": [...]}.
    Les doubles types se MULTIPLIENT : Eau/Sol face à Électrik = 2 x 0 = 0.
    """
    result = {}
    for attacker in ALL_TYPES:
        mult = 1.0
        for rel in type_relations:
            if attacker in rel["none"]:
                mult *= 0
            elif attacker in rel["double"]:
                mult *= 2
            elif attacker in rel["half"]:
                mult *= 0.5
        result[attacker] = mult
    return result


def weaknesses_and_resistances(type_relations: list[dict]) -> tuple[list[str], list[str]]:
    """> 1 = faiblesse, < 1 (immunité incluse) = résistance, == 1 = neutre."""
    mults = defensive_multipliers(type_relations)
    weak = [t for t, m in mults.items() if m > 1]
    resist = [t for t, m in mults.items() if m < 1]
    return weak, resist


def defensive_score(defender: dict, attacker_types: list[str]) -> tuple[int, dict[str, int]]:
    """Somme de (résistances - faiblesses) du défenseur sur les types de l'adversaire."""
    detail = {}
    for t in attacker_types:
        detail[t] = defender["resist"].get(t, 0) - defender["weak"].get(t, 0)
    return sum(detail.values()), detail


def _multiplier(advantage: int) -> float:
    raw = 1 + TYPE_WEIGHT * advantage
    return max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, raw))


def compare_teams(a: dict, b: dict) -> dict:
    """a et b : {name, statTotal, weak, resist, offensiveTypes}."""
    def_a, detail_a = defensive_score(a, b["offensiveTypes"])
    def_b, detail_b = defensive_score(b, a["offensiveTypes"])

    adv_a = def_a - def_b
    adv_b = -adv_a
    mult_a, mult_b = _multiplier(adv_a), _multiplier(adv_b)
    score_a = round(a["statTotal"] * mult_a, 1)
    score_b = round(b["statTotal"] * mult_b, 1)

    if score_a > score_b:
        winner = "A"
    elif score_b > score_a:
        winner = "B"
    else:
        winner = "draw"

    def side(team, def_score, detail, adv, mult, score):
        return {
            "name": team.get("name"),
            "statTotal": team["statTotal"],
            "defensiveScore": def_score,
            "defensiveDetail": detail,  # contribution de chaque type adverse
            "typeAdvantage": adv,
            "multiplier": round(mult, 2),
            "score": score,
        }

    return {
        "winner": winner,
        "teamA": side(a, def_a, detail_a, adv_a, mult_a, score_a),
        "teamB": side(b, def_b, detail_b, adv_b, mult_b, score_b),
        "formula": {
            "typeWeight": TYPE_WEIGHT,
            "multiplierRange": [MULTIPLIER_MIN, MULTIPLIER_MAX],
            "description": "score = statTotal x clamp(1 + typeWeight x typeAdvantage)",
        },
    }


# --- Analyse d'une équipe en cours de création ---------------------------------

def build_summary(profiles: list[dict]) -> dict:
    """Chaque Pokémon ajoute +1 dans chacune de ses faiblesses et résistances.
    (Source unique de cette règle : le service Équipes s'en sert via /teams/analyze.)"""
    weak, resist, offensive = {}, {}, []
    for p in profiles:
        for t in p["weaknesses"]:
            weak[t] = weak.get(t, 0) + 1
        for t in p["resistances"]:
            resist[t] = resist.get(t, 0) + 1
        for t in p["types"]:
            if t not in offensive:
                offensive.append(t)
    return {
        "statTotal": sum(p["statTotal"] for p in profiles),
        "weak": weak,
        "resist": resist,
        "offensiveTypes": offensive,
    }


def coverage_by_type(summary: dict) -> list[dict]:
    """Pour chacun des 18 types attaquants : combien de membres sont faibles / résistent."""
    rows = []
    for t in ALL_TYPES:
        w, r = summary["weak"].get(t, 0), summary["resist"].get(t, 0)
        rows.append({"type": t, "weak": w, "resist": r, "net": r - w})
    return rows


def suggest_types(summary: dict, relations: dict[str, dict], limit: int = 3) -> list[dict]:
    """Types défensifs à ajouter pour couvrir les faiblesses de l'équipe.

    Un type candidat gagne des points pour chaque faiblesse non couverte de l'équipe
    qu'il résiste (pondérée par sa gravité) et en perd pour chaque faiblesse
    non couverte qu'il aggraverait.
    """
    coverage = {row["type"]: row["net"] for row in coverage_by_type(summary)}
    dangers = {t: -net for t, net in coverage.items() if net < 0}
    if not dangers:
        return []

    suggestions = []
    for candidate in ALL_TYPES:
        rel = relations[candidate]
        covers = [t for t in dangers if t in rel["half"] or t in rel["none"]]
        risks = [t for t in ALL_TYPES if t in rel["double"] and coverage[t] <= 0]
        score = sum(dangers[t] for t in covers) - len(risks)
        if score > 0:
            suggestions.append({"type": candidate, "score": score, "covers": covers, "risks": risks})

    suggestions.sort(key=lambda s: (-s["score"], ALL_TYPES.index(s["type"])))
    return suggestions[:limit]


def analyze_team(profiles: list[dict], relations: dict[str, dict]) -> dict:
    summary = build_summary(profiles)
    return {
        "members": profiles,
        "summary": summary,
        "coverage": coverage_by_type(summary),
        "suggestions": suggest_types(summary, relations),
    }


# --- Boss de la semaine --------------------------------------------------------
# Le boss est déduit de la date : aucun stockage, aucune tâche planifiée.
# Deux appels la même semaine renvoient le même boss, le service reste sans état.

BOSS_CATALOG = [
    "rayquaza-mega", "mewtwo-mega-y", "tyranitar-mega", "garchomp-mega",
    "metagross-mega", "gyarados-mega", "salamence-mega", "charizard-mega-x",
]
BOSS_STAT_MULTIPLIER = 5   # un boss a 5 fois les stats de base de son espèce
BOSS_TYPE_WEIGHT = 3       # ses faiblesses/résistances comptent comme 3 Pokémon


def boss_of_week(day) -> dict:
    """Boss de la semaine ISO contenant `day` (un objet date)."""
    year, week, _ = day.isocalendar()
    name = BOSS_CATALOG[(year * 100 + week) % len(BOSS_CATALOG)]
    return {"name": name, "week": f"{year}-W{week:02d}"}


def boss_summary(profile: dict) -> dict:
    """Le boss vu comme une « équipe » pour la formule d'affrontement."""
    return {
        "name": profile["name"],
        "statTotal": profile["statTotal"] * BOSS_STAT_MULTIPLIER,
        "weak": {t: BOSS_TYPE_WEIGHT for t in profile["weaknesses"]},
        "resist": {t: BOSS_TYPE_WEIGHT for t in profile["resistances"]},
        "offensiveTypes": list(profile["types"]),
    }
