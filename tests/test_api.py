"""Teste la façade et les routes sans réseau : PokéAPI est simulée."""
import pytest
from fastapi.testclient import TestClient

from app import pokeapi
from app.logic import ALL_TYPES
from app.main import app

TYPES = {
    "fire": {"double_damage_from": ["water", "ground", "rock"],
             "half_damage_from": ["fire", "grass", "ice", "bug", "steel", "fairy"],
             "no_damage_from": []},
    "flying": {"double_damage_from": ["electric", "ice", "rock"],
               "half_damage_from": ["grass", "fighting", "bug"],
               "no_damage_from": ["ground"]},
}


# Pokémon présents dans les fausses pages de types : (id, nom, [types par slot])
ALL_MONS = [
    (1, "bulbasaur", ["grass", "poison"]),
    (6, "charizard", ["fire", "flying"]),
    (9, "blastoise", ["water"]),
    (130, "gyarados", ["water", "flying"]),
    (10034, "charizard-mega-x", ["fire", "dragon"]),
    (10035, "charizard-mega-y", ["fire", "flying"]),
    (10041, "gyarados-mega", ["water", "dark"]),
    (10196, "charizard-gmax", ["fire", "flying"]),   # forme Gigamax : ignorée
    (487, "giratina-altered", ["ghost", "dragon"]),  # forme de base, nom différent de l'espèce
    (10007, "giratina-origin", ["ghost", "dragon"]),
    (479, "rotom", ["electric", "ghost"]),
    (10009, "rotom-wash", ["electric", "water"]),
    (10080, "pikachu-rock-star", ["electric"]),      # Pikachu cosplay : ignoré
    (493, "arceus", ["normal"]),
    (1007, "koraidon", ["fighting", "dragon"]),
    (10264, "koraidon-limited-build", ["fighting", "dragon"]),   # formes de Koraidon : ignorées
    (10268, "miraidon-low-power-mode", ["electric", "dragon"]),  # formes de Miraidon : ignorées
]


def type_page(name):
    rel = TYPES.get(name, {"double_damage_from": [], "half_damage_from": [], "no_damage_from": []})
    pokemon = [
        {"slot": types.index(name) + 1, "pokemon": {"name": n, "url": f"https://x/pokemon/{pid}/"}}
        for pid, n, types in ALL_MONS if name in types
    ]
    return {
        "damage_relations": {k: [{"name": t} for t in v] for k, v in rel.items()},
        "pokemon": pokemon,
    }


FAKE = {
    "/pokemon/charizard": {
        "id": 6, "name": "charizard",
        "sprites": {"front_default": "sprite6.png"},
        "types": [{"slot": 2, "type": {"name": "flying"}}, {"slot": 1, "type": {"name": "fire"}}],
        "stats": [{"base_stat": v, "stat": {"name": n}} for n, v in [
            ("hp", 78), ("attack", 84), ("defense", 78),
            ("special-attack", 109), ("special-defense", 85), ("speed", 100)]],
    },
    "/generation/1": {"pokemon_species": [
        {"name": "charizard", "url": "https://x/pokemon-species/6/"},
        {"name": "bulbasaur", "url": "https://x/pokemon-species/1/"},
    ]},
    "/generation/4": {"pokemon_species": [
        {"name": "giratina", "url": "https://x/pokemon-species/487/"},
        {"name": "rotom", "url": "https://x/pokemon-species/479/"},
        {"name": "arceus", "url": "https://x/pokemon-species/493/"},
    ]},
    "/pokemon/arceus": {
        "id": 493, "name": "arceus", "species": {"name": "arceus"},
        "sprites": {"front_default": "493.png"},
        "types": [{"slot": 1, "type": {"name": "normal"}}],
        "stats": [{"base_stat": 120, "stat": {"name": n}} for n in
                  ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]],
    },
    **{f"/type/{t}": type_page(t) for t in ALL_TYPES},
}

calls = []


@pytest.fixture(autouse=True)
def fake_pokeapi(monkeypatch):
    async def fake_fetch(path):
        calls.append(path)
        if path not in FAKE:
            raise pokeapi.NotFound(path)
        return FAKE[path]

    pokeapi._cache.clear()
    calls.clear()
    monkeypatch.setattr(pokeapi, "_fetch", fake_fetch)


client = TestClient(app)


def test_profil_dracaufeu():
    r = client.get("/pokemon/Charizard")
    assert r.status_code == 200
    p = r.json()
    assert p["types"] == ["fire", "flying"]  # trié par slot
    assert p["statTotal"] == 534
    assert "rock" in p["weaknesses"] and "water" in p["weaknesses"]
    assert "ground" in p["resistances"]      # immunité via Vol
    assert "ice" not in p["weaknesses"] + p["resistances"]


def test_pokemon_inconnu():
    assert client.get("/pokemon/missingno").status_code == 404


def test_profil_signale_les_mega():
    FAKE["/pokemon/charizard-mega-x"] = {**FAKE["/pokemon/charizard"], "id": 10034, "name": "charizard-mega-x",
                                         "types": [{"slot": 1, "type": {"name": "fire"}}, {"slot": 2, "type": {"name": "dragon"}}]}
    p = client.get("/pokemon/charizard-mega-x").json()
    assert p["isMega"] is True and p["baseSpecies"] == "charizard"
    assert client.get("/pokemon/charizard").json()["isMega"] is False


def test_megas_rangees_apres_leur_forme_de_base():
    megas = client.get("/megas").json()
    assert [m["name"] for m in megas] == ["charizard-mega-x", "charizard-mega-y", "gyarados-mega"]
    assert megas[0]["types"] == ["fire", "dragon"]
    assert all(m["isMega"] for m in megas)          # pas de Gigamax


def test_filtre_type_toutes_generations():
    eau = client.get("/type/water/pokemon").json()
    assert [p["name"] for p in eau] == ["blastoise", "gyarados", "gyarados-mega", "rotom-wash",
                                        "arceus-water", "silvally-water"]  # puis Méga, puis formes
    assert eau[1]["types"] == ["water", "flying"]
    assert client.get("/type/lumiere/pokemon").status_code == 404


def test_generation_triee_avec_types():
    r = client.get("/generation/1")
    assert r.status_code == 200
    gen = r.json()
    assert [p["id"] for p in gen] == [1, 6]
    assert gen[1]["types"] == ["fire", "flying"]
    assert gen[0]["sprite"].endswith("/1.png")


def test_cache_evite_les_appels_repetes():
    client.get("/generation/1")
    n = len(calls)
    client.get("/generation/1")
    assert len(calls) == n


def test_generation_hors_limite():
    assert client.get("/generation/10").status_code == 422


def test_route_compare():
    body = {
        "teamA": {"name": "Feu", "statTotal": 534, "offensiveTypes": ["fire", "flying"],
                  "weak": {"water": 1, "rock": 1, "electric": 1},
                  "resist": {"fire": 1, "grass": 1, "bug": 1, "steel": 1, "fairy": 1, "fighting": 1, "ground": 1}},
        "teamB": {"name": "Eau", "statTotal": 530, "offensiveTypes": ["water"],
                  "weak": {"electric": 1, "grass": 1},
                  "resist": {"fire": 1, "water": 1, "ice": 1, "steel": 1}},
    }
    r = client.post("/teams/compare", json=body)
    assert r.status_code == 200
    assert r.json()["winner"] == "B"


def test_route_analyze():
    r = client.post("/teams/analyze", json={"pokemonIds": ["charizard", "charizard"]})
    assert r.status_code == 200
    a = r.json()
    assert [m["name"] for m in a["members"]] == ["charizard", "charizard"]
    assert a["summary"]["weak"]["rock"] == 2 and a["summary"]["statTotal"] == 1068
    assert len(a["coverage"]) == 18
    assert isinstance(a["suggestions"], list)
    assert client.post("/teams/analyze", json={"pokemonIds": ["missingno"]}).status_code == 404
    assert client.post("/teams/analyze", json={"pokemonIds": []}).status_code == 422


def test_boss_de_la_semaine_et_combat(monkeypatch):
    from app import logic
    monkeypatch.setattr(logic, "BOSS_CATALOG", ["charizard"])
    b = client.get("/boss").json()
    assert b["name"] == "charizard"
    assert b["statTotal"] == 534 * 5 and b["baseStatTotal"] == 534
    assert b["artwork"].endswith("/official-artwork/6.png")
    assert "summary" in b and b["endsAt"].endswith("+00:00")

    team = {"name": "Eau", "statTotal": 3000, "offensiveTypes": ["water"],
            "weak": {"electric": 6}, "resist": {"fire": 6, "water": 6}}
    r = client.post("/boss/fight", json={"team": team}).json()
    assert r["boss"]["name"] == "charizard" and "summary" not in r["boss"]
    assert r["teamB"]["statTotal"] == 2670
    assert r["teamB"]["defensiveDetail"] == {"water": -3}   # le boss compte pour 3
    assert r["winner"] == "A"


def test_generation_avec_formes_a_cote_de_leur_espece():
    gen = client.get("/generation/4").json()
    noms = [p["name"] for p in gen]
    assert noms[:4] == ["rotom", "rotom-wash", "giratina", "giratina-origin"]
    assert noms[4] == "arceus" and noms[5] == "arceus-fire"        # ordre officiel des types
    assert sum(n.startswith("arceus-") for n in noms) == 17        # 18 types sauf Normal
    assert gen[3]["isForm"] and gen[3]["baseSpecies"] == "giratina"
    assert "charizard-mega-x" not in noms                          # les Méga gardent leur onglet


def test_formes_exclues():
    tous = [p["name"] for t in ("fighting", "electric", "fire") for p in client.get(f"/type/{t}/pokemon").json()]
    assert "koraidon" in tous
    assert not any(n.startswith(("koraidon-", "miraidon-")) for n in tous)
    assert "pikachu-rock-star" not in tous and "charizard-gmax" not in tous


def test_profil_forme_par_type():
    p = client.get("/pokemon/arceus-fire").json()
    assert p["id"] == "arceus-fire" and p["types"] == ["fire"]
    assert p["statTotal"] == 720 and p["baseSpecies"] == "arceus"   # stats d'Arceus
    assert "water" in p["weaknesses"] and "fire" in p["resistances"]
    assert p["sprite"].endswith("/493-fire.png")
    assert client.get("/pokemon/arceus-lumiere").status_code == 404


def test_routes_capture():
    FAKE["/pokemon/6"] = FAKE["/pokemon/charizard"]
    starters = client.get("/capture/starters").json()
    assert len(starters) == 27

    etat = client.post("/capture/state", json={"unlocked": [4], "victories": {"charmander": 10}}).json()
    assert etat["unlockedSpecies"] == ["charmander"]
    assert etat["progression"]["unlock"] == [5]                       # Reptincel débloqué
    assert any(p["owned"] for p in etat["tiers"])

    rencontres = client.post("/capture/encounters", json={"tier": 10, "unlocked": [4]}).json()["candidates"]
    assert len(rencontres) == 3 and all(r["firstStage"]["name"] != "charmander" for r in rencontres)

    equipe = {"name": "Eau", "statTotal": 530, "offensiveTypes": ["water"],
              "weak": {"electric": 1, "grass": 1}, "resist": {"fire": 1, "water": 1}}
    r = client.post("/capture/fight", json={"team": equipe, "wildId": 6, "teamSize": 1}).json()
    assert r["wild"]["name"] == "charizard" and r["wild"]["firstStage"]["name"] == "charmander"
    assert r["teamB"]["statTotal"] == 534

    a = client.post("/capture/analyze", json={"pokemonIds": ["charizard"], "unlocked": [4]}).json()
    assert a["forbidden"] == ["charizard"] and a["tooStrong"] == []
    a = client.post("/capture/analyze", json={"pokemonIds": ["charizard"], "unlocked": [4, 5, 6], "tier": 8}).json()
    assert a["tooStrong"] == ["charizard"]
    assert etat["pokedex"]["captured"] == 1 and etat["unlockedMegas"] == []

    locked = client.post("/capture/locked", json={"teams": {
        "t1": {"pokemonIds": [6], "unlocked": [4]},
        "t2": {"pokemonIds": [6], "unlocked": [4, 5, 6]}}}).json()
    assert locked == {"t1": ["charizard"], "t2": []}
