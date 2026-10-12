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
