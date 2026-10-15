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
    assert sum(p["count"] for p in paliers) == sum(c.in_capture(sid) for sid in c.REF["species"])
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


def test_mega_ne_se_gagne_plus_aux_victoires():
    owned = [ID["charmander"], ID["charmeleon"], ID["charizard"]]
    p = c.progression(owned, {"charizard": 500})
    assert p["unlock"] == [] and "charizard" not in p["progress"]   # elle a son donjon


def test_legendaires_hors_du_mode_capture():
    mewtwo, cosmog = c.REF["by_name"]["mewtwo"], c.REF["by_name"]["cosmog"]
    assert not c.in_capture(mewtwo) and not c.in_capture(cosmog)
    for tier in range(15):
        pool = c.encounter_pool(tier, [])
        assert mewtwo not in pool and cosmog not in pool
    assert all(c.in_capture(sid) for t in range(15) for sid in c.tier_species(t))


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
    tier = max(c.tier_index(s["statTotal"]) for sid, s in c.REF["species"].items() if c.in_capture(sid))
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


def test_ecart_de_palier_seulement_en_entrainement():
    dracaufeu = {"name": "charizard", "statTotal": 534}
    tier = 3
    assert c.too_strong_for_run([dracaufeu], tier, [ID["charmander"]]) == []        # capture : libre
    tout = [c.first_stage(sid) for sid in c.tier_species(tier)]
    assert c.too_strong_for_run([dracaufeu], tier, tout) == ["charizard"]           # entraînement


def test_mega_avec_ses_propres_stats_et_types():
    m = c.mega_entry(10034)
    assert m["name"] == "charizard-mega-x" and m["statTotal"] == 634 and m["types"] == ["fire", "dragon"]
    assert m["tier"] == 12


# --- Formes alternatives ---------------------------------------------------------------

def _form(name):
    return next(fid for fid, f in c.REF["forms"].items() if f["name"] == name)


def test_formes_equivalentes_et_ameliorees():
    assert c.REF["forms"][_form("urshifu-rapid-strike")]["kind"] == "equivalent"
    assert c.REF["forms"][_form("giratina-origin")]["kind"] == "equivalent"
    for name in ("palafin-hero", "rotom-wash", "zygarde-complete", "kyurem-black"):
        assert c.REF["forms"][_form(name)]["kind"] == "improved", name


def test_forme_equivalente_suit_son_espece():
    shifours = c.REF["by_name"]["urshifu"]
    rapide = {"id": _form("urshifu-rapid-strike"), "baseSpecies": "urshifu", "isMega": False}
    assert c.is_allowed(rapide, [shifours])
    assert any(e["name"] == "urshifu-rapid-strike" for e in c.collection([shifours]))


def test_superdofin_heros_apres_30_victoires():
    superdofin, heros = c.REF["by_name"]["palafin"], _form("palafin-hero")
    owned = [c.REF["by_name"]["finizen"], superdofin]
    profil = {"id": heros, "baseSpecies": "palafin", "isMega": False}
    assert not c.is_allowed(profil, owned)                       # plus de forme gratuite
    p = c.progression(owned, {"palafin": 29})
    assert p["unlock"] == [] and p["progress"]["palafin"]["threshold"] == 30
    assert c.progression(owned, {"palafin": 30})["unlock"] == [heros]
    assert c.is_allowed(profil, owned + [heros])
    assert any(e["id"] == heros for e in c.collection(owned + [heros]))


def test_formes_legendaires_et_fusions_hors_victoires():
    assert not c.earned_by_victories(_form("zygarde-complete"))     # donjon
    assert not c.earned_by_victories(_form("kyurem-black"))         # fusion : donjon
