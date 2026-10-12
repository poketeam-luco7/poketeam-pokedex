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
