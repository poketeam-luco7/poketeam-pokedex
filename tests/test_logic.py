from app.logic import (
    compare_teams,
    defensive_multipliers,
    weaknesses_and_resistances,
)

# damage_relations réelles de PokéAPI, simplifiées
FIRE = {"double": ["water", "ground", "rock"],
        "half": ["fire", "grass", "ice", "bug", "steel", "fairy"], "none": []}
FLYING = {"double": ["electric", "ice", "rock"],
          "half": ["grass", "fighting", "bug"], "none": ["ground"]}
WATER = {"double": ["electric", "grass"],
         "half": ["fire", "water", "ice", "steel"], "none": []}
GROUND = {"double": ["water", "grass", "ice"],
          "half": ["poison", "rock"], "none": ["electric"]}


def test_double_type_se_multiplie_immunite():
    # Eau/Sol (Laggron) : Électrik = 2 x 0 = immunité, pas une faiblesse
    m = defensive_multipliers([WATER, GROUND])
    assert m["electric"] == 0
    assert m["grass"] == 4


def test_double_type_se_compense():
    # Feu/Vol (Dracaufeu) : Glace = 0.5 x 2 = neutre
    weak, resist = weaknesses_and_resistances([FIRE, FLYING])
    assert "ice" not in weak and "ice" not in resist
    assert "rock" in weak          # x4 compte comme UNE faiblesse
    assert "ground" in resist      # immunité comptée comme résistance


def test_dracaufeu_contre_tortank():
    charizard = {
        "name": "A", "statTotal": 534, "offensiveTypes": ["fire", "flying"],
        "weak": {"water": 1, "rock": 1, "electric": 1},
        "resist": {t: 1 for t in ["fire", "grass", "bug", "steel", "fairy", "fighting", "ground"]},
    }
    blastoise = {
        "name": "B", "statTotal": 530, "offensiveTypes": ["water"],
        "weak": {"electric": 1, "grass": 1},
        "resist": {"fire": 1, "water": 1, "ice": 1, "steel": 1},
    }
    r = compare_teams(charizard, blastoise)
    assert r["teamA"]["typeAdvantage"] == -2
    assert r["teamA"]["score"] == 427.2
    assert r["teamB"]["score"] == 636.0
    assert r["winner"] == "B"


def test_multiplicateur_borne():
    a = {"statTotal": 100, "offensiveTypes": ["water"], "weak": {},
         "resist": {"fire": 20}}
    b = {"statTotal": 100, "offensiveTypes": ["fire"], "weak": {}, "resist": {}}
    r = compare_teams(a, b)
    assert r["teamA"]["multiplier"] == 1.5
    assert r["teamB"]["multiplier"] == 0.5


def test_egalite():
    t = {"statTotal": 300, "offensiveTypes": ["normal"], "weak": {}, "resist": {}}
    assert compare_teams(t, dict(t))["winner"] == "draw"


# --- Analyse et suggestions ---------------------------------------------------
from app.logic import ALL_TYPES as _T, build_summary, coverage_by_type, suggest_types

NO_REL = {"double": [], "half": [], "none": []}
GRASS = {"double": ["fire", "ice", "poison", "flying", "bug"],
         "half": ["water", "electric", "grass", "ground"], "none": []}
RELATIONS = {t: NO_REL for t in _T} | {"fire": FIRE, "water": WATER, "grass": GRASS,
                                        "ground": GROUND, "flying": FLYING}

ARCANINE = {"types": ["fire"], "statTotal": 555,
            "weaknesses": ["water", "ground", "rock"],
            "resistances": ["fire", "grass", "ice", "bug", "steel", "fairy"]}


def test_summary_compte_chaque_membre():
    s = build_summary([ARCANINE, ARCANINE])
    assert s["weak"]["water"] == 2 and s["resist"]["fire"] == 2
    assert s["statTotal"] == 1110 and s["offensiveTypes"] == ["fire"]


def test_couverture_sur_les_18_types():
    rows = coverage_by_type(build_summary([ARCANINE]))
    assert len(rows) == 18
    eau = next(r for r in rows if r["type"] == "water")
    assert eau == {"type": "water", "weak": 1, "resist": 0, "net": -1}


def test_suggestion_pour_une_equipe_feu():
    # Équipe Feu faible à Eau, Sol et Roche : Plante résiste à Eau et Sol, elle sort en tête
    sugg = suggest_types(build_summary([ARCANINE, ARCANINE]), RELATIONS)
    assert sugg[0]["type"] == "grass"
    assert set(sugg[0]["covers"]) == {"water", "ground"}


def test_aucune_suggestion_si_rien_a_couvrir():
    solide = {"types": ["steel"], "statTotal": 500, "weaknesses": [], "resistances": ["fire"]}
    assert suggest_types(build_summary([solide]), RELATIONS) == []
