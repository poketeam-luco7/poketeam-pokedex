"""Règles du mode Capture, sur le vrai référentiel (data/capture.json)."""
import random

from app import capture as c

ID = c.REF["by_name"]


def test_referentiel_charge():
    assert len(c.REF["species"]) >= 1025
    s = c.REF["species"][ID["charizard"]]
    assert s["stage"] == 3 and s["evolvesFrom"] == ID["charmeleon"]
    assert len(s["megas"]) >= 2                                 # Méga X et Y


def test_starters_des_9_generations():
    noms = [s["name"] for s in c.starters()]
    assert len(noms) == 27 and noms[0] == "bulbasaur" and noms[-1] == "quaxly"
    assert all(s["stage"] == 1 for s in c.starters())


def test_paliers_de_50():
    paliers = c.tiers([ID["charmander"]])
    assert all(p["max"] - p["min"] == 49 for p in paliers)
    assert sum(p["count"] for p in paliers) == len(c.REF["species"])
    p300 = next(p for p in paliers if p["min"] == 300)
    assert p300["owned"] >= 1                                   # Salamèche (309)


def test_rencontres_hors_lignes_possedees():
    # Possédant Salamèche, on ne rencontre ni Reptincel ni Dracaufeu
    pool = c.encounter_pool(c.tier_index(534), [ID["charmander"]])
    assert ID["charizard"] not in pool and pool
    pool_libre = c.encounter_pool(c.tier_index(534), [])
    assert ID["charizard"] in pool_libre


def test_tirage_de_3_dans_le_palier():
    tirage = c.draw_encounters(6, [], rng=random.Random(1))
    rencontres = tirage["candidates"]
    assert not tirage["training"] and len(rencontres) == 3
    assert all(300 <= r["statTotal"] <= 349 for r in rencontres)


def test_battre_dracaufeu_donne_salameche():
    assert c.entry(ID["charizard"])["firstStage"]["name"] == "charmander"
    assert c.entry(ID["raichu"])["firstStage"]["name"] == "pichu"   # le bébé est le 1er stade


def test_evolution_a_10_puis_30_victoires():
    owned = [ID["charmander"]]
    assert c.progression(owned, {"charmander": 9})["unlock"] == []
    assert c.progression(owned, {"charmander": 10})["unlock"] == [ID["charmeleon"]]
    owned.append(ID["charmeleon"])
    p = c.progression(owned, {"charmander": 10, "charmeleon": 29})
    assert p["unlock"] == [] and p["progress"]["charmeleon"]["threshold"] == 30
    assert c.progression(owned, {"charmeleon": 30})["unlock"] == [ID["charizard"]]


def test_evoli_choix_puis_10_victoires_par_branche():
    owned = [ID["eevee"]]
    p = c.progression(owned, {"eevee": 10})
    assert p["unlock"] == [] and len(p["choices"][0]["options"]) == 8
    owned.append(ID["vaporeon"])                                   # 1re branche choisie
    assert c.progression(owned, {"eevee": 19})["choices"] == []
    assert len(c.progression(owned, {"eevee": 20})["choices"][0]["options"]) == 7


def test_mega_apres_50_victoires_avec_la_forme_finale():
    owned = [ID["charmander"], ID["charmeleon"], ID["charizard"]]
    assert c.progression(owned, {"charizard": 49})["unlock"] == []
    megas = c.progression(owned, {"charizard": 50})["unlock"]
    assert set(megas) == set(c.REF["species"][ID["charizard"]]["megas"])


def test_sauvage_adapte_a_la_taille_equipe():
    pika = {"name": "pikachu", "statTotal": 320, "types": ["electric"],
            "weaknesses": ["ground"], "resistances": ["electric", "flying", "steel"]}
    s = c.wild_summary(pika, 4)
    assert s["statTotal"] == 1280 and s["weak"]["ground"] == 4


def test_formes_et_mega_autorisees():
    owned = [ID["giratina"]]
    assert c.is_allowed({"id": 10007, "baseSpecies": "giratina", "isMega": False}, owned)
    assert not c.is_allowed({"id": 6, "baseSpecies": "charizard", "isMega": False}, owned)
    assert not c.is_allowed({"id": 10034, "baseSpecies": "charizard", "isMega": True}, [ID["charizard"]])
    assert c.is_allowed({"id": 10034, "baseSpecies": "charizard", "isMega": True}, [ID["charizard"], 10034])


def test_pokedex_par_generation():
    d = c.dex_progress([4, 5, 152, 10034])
    assert d["total"] == 1025 and d["captured"] == 3
    assert [g["total"] for g in d["generations"]][:2] == [151, 100]
    assert d["generations"][0]["captured"] == 2 and d["generations"][1]["captured"] == 1
    assert d["megas"]["captured"] == 1
    assert c.generation_of(1025) == 9


def test_palier_termine_devient_entrainement():
    tier = 3                                             # 150-199 : une dizaine d'espèces
    tout = c.tier_species(tier)
    assert not c.is_training(tier, [])
    possedes = [c.first_stage(sid) for sid in tout]      # on possède toutes les lignes du palier
    assert c.is_training(tier, possedes)
    assert next(t for t in c.tiers(possedes) if t["index"] == tier)["training"]
    tirage = c.draw_encounters(tier, possedes, rng=random.Random(2))
    assert tirage["training"] and len(tirage["candidates"]) == 3
    assert all(r["id"] in tout for r in tirage["candidates"])   # Pokémon déjà possédés compris


def test_entrainement_dans_un_petit_palier():
    tier = max(c.tier_index(s["statTotal"]) for s in c.REF["species"].values())
    tout = c.tier_species(tier)
    possedes = [c.first_stage(sid) for sid in tout]
    # tous déjà battus : on autorise les revanches plutôt que de bloquer la run
    tirage = c.draw_encounters(tier, possedes, exclude=tout)
    assert tirage["candidates"]


def test_trop_fort_deux_paliers_en_dessous():
    dracaufeu = {"name": "charizard", "statTotal": 534}   # palier 10
    assert c.too_strong([dracaufeu], 9) == []             # 1 palier en dessous : autorisé
    assert c.too_strong([dracaufeu], 8) == ["charizard"]  # 2 paliers en dessous : interdit
    assert c.too_strong([dracaufeu], 12) == []            # plus fort que lui : autorisé


def test_mega_avec_ses_propres_stats_et_types():
    m = c.mega_entry(10034)
    assert m["name"] == "charizard-mega-x" and m["statTotal"] == 634 and m["types"] == ["fire", "dragon"]
    assert m["tier"] == 12
