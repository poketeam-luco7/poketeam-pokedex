"""Règles des donjons et du boss final, sans réseau."""
from app import capture as c
from app import dungeons as d

ID = c.REF["by_name"]


def premiers(n):
    """n espèces possédées (hors légendaires), pour ouvrir le mode."""
    return [sid for sid in c.REF["species"] if c.in_capture(sid)][:n]


def test_un_donjon_par_legendaire_fabuleux_et_mega():
    cat = d.catalog()
    especes = [x for x in cat if x["kind"] in ("legendary", "mythical")]
    assert len(especes) == 94 and sum(x["kind"] == "mythical" for x in especes) == 23
    assert len([x for x in cat if x["kind"] == "mega"]) == len(c.REF["megas"])
    assert cat == sorted(cat, key=lambda x: (x["statTotal"], x["id"]))


def test_mode_ouvert_a_25_captures():
    assert not d.state(premiers(24))["open"]
    assert d.state(premiers(25))["open"]


def test_seuil_d_entree_trois_fois_les_stats():
    mewtwo = next(x for x in d.catalog() if x["name"] == "mewtwo")
    assert mewtwo["requirement"] == 680 * 3
    owned = premiers(25)
    assert d.check_entry(mewtwo["id"], owned, 2039)[1].startswith("Équipe trop faible")
    assert d.check_entry(mewtwo["id"], owned, 2040) == (next(x for x in d.state(owned)["dungeons"]
                                                              if x["id"] == mewtwo["id"]), None)
    assert "25" in d.check_entry(mewtwo["id"], premiers(3), 9999)[1]


def test_ligne_legendaire_recompense_le_premier_stade():
    solgaleo = next(x for x in d.catalog() if x["name"] == "solgaleo")
    assert solgaleo["reward"]["name"] == "cosmog"
    owned = premiers(25) + [ID["cosmog"]]
    st = {x["name"]: x for x in d.state(owned)["dungeons"]}
    assert st["solgaleo"]["conquered"] and st["cosmog"]["conquered"] and not st["mewtwo"]["conquered"]


def test_donjon_mega_visible_si_l_espece_est_possedee():
    sans = {x["id"] for x in d.state(premiers(25))["dungeons"]}
    avec = {x["id"] for x in d.state(premiers(25) + [ID["gyarados"]])["dungeons"]}
    assert 10041 not in sans and 10041 in avec
    owned = premiers(25) + [ID["gyarados"], 10041]
    assert next(x for x in d.state(owned)["dungeons"] if x["id"] == 10041)["conquered"]


def test_boss_final():
    u = d.ultimate()
    assert u["name"] == "eternatus-eternamax" and u["statTotal"] == 1125 and u["requirement"] == 3375
    assert d.check_ultimate(3374) and d.check_ultimate(3375) is None


def test_boss_summary_stats_x4_et_types_x3():
    ray = {"name": "rayquaza-mega", "types": ["dragon", "flying"], "statTotal": 780,
           "weaknesses": ["ice"], "resistances": ["ground"]}
    s = d.boss_summary(ray)
    assert s["statTotal"] == 3120 and s["weak"] == {"ice": 3} and s["resist"] == {"ground": 3}
