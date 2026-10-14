# PokéTeam — Pokédex

Microservice **sans état** (FastAPI) : façade de PokéAPI (*Anti-Corruption Layer*) et **seule
source des règles Pokémon** — faiblesses et résistances, formule d'affrontement, boss de la
semaine, règles du mode Capture. Aucune base de données : un cache mémoire devant PokéAPI et un
référentiel statique (`app/data/capture.json`).

| | |
|---|---|
| Stack | Python 3.12, FastAPI, httpx |
| Port interne | 8000 |
| Appelé par | la gateway (`/pokeapi/*`) et le service Équipes (appels internes) |
| Dépend de | PokéAPI (internet) |

## Routes principales

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/generation/{n}`, `/megas`, `/type/{type}/pokemon` | Listes pour la création d'équipe |
| GET | `/pokemon/{id}` | Profil : stats, types, faiblesses, résistances |
| POST | `/teams/analyze` | Profils + summary + couverture + suggestions d'une équipe |
| POST | `/teams/compare` | Affrontement de deux équipes |
| GET · POST | `/boss`, `/boss/fight` | Boss de la semaine |
| GET · POST | `/capture/*` | Règles du mode Capture (starters, état, rencontres, combat, verrouillage) |

Documentation interactive : `http://localhost:8000/docs` en local.

## Variables d'environnement

| Variable | Défaut |
|---|---|
| `POKEAPI_URL` | `https://pokeapi.co/api/v2` |

## Lancer seul

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pip install -r requirements.txt pytest
python -m pytest -v          # 43 tests, PokéAPI simulée
```

Le référentiel du mode Capture se régénère avec `python scripts/build_capture_data.py`.

## Fait partie de PokéTeam

Ce dépôt est un des composants de l'organisation [poketeam-luco7](https://github.com/poketeam-luco7).
Pour lancer l'application complète (gateway, 3 services, 2 bases), voir le dépôt
d'orchestration [`poketeam`](https://github.com/poketeam-luco7/poketeam) : `docker-compose.yml`,
architecture (C4) et décisions d'architecture (ADR).
