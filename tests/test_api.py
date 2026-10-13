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


def type_page(name):
    rel = TYPES.get(name, {"double_damage_from": [], "half_damage_from": [], "no_damage_from": []})
    pokemon = []
    if name == "fire":
        pokemon = [{"slot": 1, "pokemon": {"name": "charizard", "url": "https://x/pokemon/6/"}}]
    if name == "flying":
        pokemon = [{"slot": 2, "pokemon": {"name": "charizard", "url": "https://x/pokemon/6/"}}]
    if name == "grass":
        pokemon = [{"slot": 1, "pokemon": {"name": "bulbasaur", "url": "https://x/pokemon/1/"}}]
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
