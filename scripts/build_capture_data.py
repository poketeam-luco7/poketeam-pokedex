"""Génère app/data/capture.json, le référentiel du mode Capture.

Source : les CSV officiels publiés par PokéAPI sur GitHub (mêmes données que l'API).
Le fichier généré est commité : le Pokédex le charge au démarrage, sans aucun appel réseau.
À relancer seulement si de nouveaux Pokémon sortent :

    python scripts/build_capture_data.py            # télécharge les CSV
    python scripts/build_capture_data.py ./csv      # ou depuis un dossier local
"""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ULTIMATE = "eternatus-eternamax"

# Variétés ignorées (mêmes règles que la façade PokéAPI) ; les Méga sont traitées à part
EXCLUDED_FORMS = ("-gmax", "-totem", "-starter", "pikachu-", "-power-construct", "-battle-bond",
                  "-own-tempo", "koraidon-", "miraidon-", "-mega", ULTIMATE)
IMPROVED_GAP = 20          # au-delà de +20 de stats, une forme est « améliorée » et se mérite
FUSIONS = {                # forme fusionnée -> espèces partenaires à posséder
    "kyurem-black": ["zekrom"], "kyurem-white": ["reshiram"],
    "necrozma-dusk": ["solgaleo"], "necrozma-dawn": ["lunala"], "necrozma-ultra": ["solgaleo", "lunala"],
    "calyrex-ice": ["glastrier"], "calyrex-shadow": ["spectrier"],
}
BASE_URL = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
FILES = ["pokemon_species", "pokemon", "pokemon_stats", "pokemon_types", "types"]
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "capture.json"

# Premier stade des starters des 9 générations
STARTERS = [
    "bulbasaur", "charmander", "squirtle", "chikorita", "cyndaquil", "totodile",
    "treecko", "torchic", "mudkip", "turtwig", "chimchar", "piplup",
    "snivy", "tepig", "oshawott", "chespin", "fennekin", "froakie",
    "rowlet", "litten", "popplio", "grookey", "scorbunny", "sobble",
    "sprigatito", "fuecoco", "quaxly",
]


def load(source: str | None) -> dict[str, list[dict]]:
    tables = {}
    for name in FILES:
        if source:
            text = (Path(source) / f"{name}.csv").read_text(encoding="utf-8")
        else:
            with urllib.request.urlopen(BASE_URL + f"{name}.csv", timeout=60) as r:
                text = r.read().decode("utf-8")
        tables[name] = list(csv.DictReader(io.StringIO(text)))
    return tables


def build(t: dict[str, list[dict]]) -> dict:
    type_names = {r["id"]: r["identifier"] for r in t["types"]}
    totals: dict[int, int] = {}
    for r in t["pokemon_stats"]:
        totals[int(r["pokemon_id"])] = totals.get(int(r["pokemon_id"]), 0) + int(r["base_stat"])
    types: dict[int, list[tuple[int, str]]] = {}
    for r in t["pokemon_types"]:
        types.setdefault(int(r["pokemon_id"]), []).append((int(r["slot"]), type_names[r["type_id"]]))

    megas: dict[int, list[int]] = {}
    mega_info: dict[str, dict] = {}
    for r in t["pokemon"]:
        if "-mega" in r["identifier"]:
            mid = int(r["id"])
            megas.setdefault(int(r["species_id"]), []).append(mid)
            # stats et types propres à la Méga (Méga-Dracaufeu X est Feu/Dragon)
            mega_info[str(mid)] = {"name": r["identifier"], "statTotal": totals[mid],
                                   "types": [name for _, name in sorted(types[mid])]}

    rows = {int(r["id"]): r for r in t["pokemon_species"]}

    def stage(sid: int) -> int:
        parent = rows[sid]["evolves_from_species_id"]
        return 1 if not parent else 1 + stage(int(parent))

    species = []
    for sid, r in sorted(rows.items()):
        species.append({
            "id": sid,                                   # id d'espèce = id du Pokémon par défaut
            "name": r["identifier"],
            "chain": int(r["evolution_chain_id"]),
            "evolvesFrom": int(r["evolves_from_species_id"]) if r["evolves_from_species_id"] else None,
            "stage": stage(sid),
            "statTotal": totals[sid],
            "types": [name for _, name in sorted(types[sid])],
            "megas": sorted(megas.get(sid, [])),
            # légendaires et fabuleux : hors du mode Capture, gagnés dans les donjons
            "special": ("mythical" if r["is_mythical"] == "1"
                        else "legendary" if r["is_legendary"] == "1" else None),
        })
    by_name = {s["name"]: s["id"] for s in species}
    # Formes alternatives : équivalentes (suivent l'espèce) ou améliorées (à mériter)
    default_of = {int(r["species_id"]): int(r["id"]) for r in t["pokemon"] if r["is_default"] == "1"}
    forms = []
    for r in t["pokemon"]:
        if r["is_default"] == "1" or any(e in r["identifier"] for e in EXCLUDED_FORMS):
            continue
        fid, sid = int(r["id"]), int(r["species_id"])
        gain = totals[fid] - totals[default_of[sid]]
        forms.append({"id": fid, "name": r["identifier"], "species": sid, "statTotal": totals[fid],
                      "types": [name for _, name in sorted(types[fid])],
                      "kind": "improved" if gain > IMPROVED_GAP else "equivalent",
                      "partners": [by_name[n] for n in FUSIONS.get(r["identifier"], [])]})

    # Boss final : Éthernatos Infinimax (forme qui n'existe qu'en combat)
    ultimate = next(r for r in t["pokemon"] if r["identifier"] == ULTIMATE)
    uid = int(ultimate["id"])
    return {"species": species, "starters": [by_name[n] for n in STARTERS], "megas": mega_info, "forms": forms,
            "ultimate": {"id": uid, "name": ULTIMATE, "statTotal": totals[uid],
                         "types": [name for _, name in sorted(types[uid])]}}


if __name__ == "__main__":
    data = build(load(sys.argv[1] if len(sys.argv) > 1 else None))
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['species'])} espèces, {len(data['starters'])} starters -> {OUT}")
