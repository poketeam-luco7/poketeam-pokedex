from __future__ import annotations

from typing import Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from . import capture
from .logic import ALL_TYPES, compare_teams
from .pokeapi import (NotFound, analyze, current_boss, get_profile, list_by_type, list_generation,
                      list_megas)

app = FastAPI(
    title="Pokédex",
    description="Service sans état : façade PokéAPI et calcul des affrontements",
)


class TeamSummary(BaseModel):
    name: Optional[str] = None
    statTotal: int
    weak: Dict[str, int] = Field(default_factory=dict)
    resist: Dict[str, int] = Field(default_factory=dict)
    offensiveTypes: List[str]


class AnalyzeRequest(BaseModel):
    pokemonIds: List[Union[int, str]] = Field(min_length=1, max_length=6)


class BossFightRequest(BaseModel):
    team: TeamSummary


class CaptureState(BaseModel):
    unlocked: List[Union[int, str]] = Field(default_factory=list)
    victories: Dict[str, int] = Field(default_factory=dict)


class EncounterRequest(BaseModel):
    tier: int = Field(ge=0, le=20)
    unlocked: List[Union[int, str]] = Field(default_factory=list)
    exclude: List[int] = Field(default_factory=list)


class CaptureAnalyzeRequest(BaseModel):
    pokemonIds: List[Union[int, str]] = Field(min_length=1, max_length=6)
    unlocked: List[Union[int, str]] = Field(default_factory=list)


class CaptureFightRequest(BaseModel):
    team: TeamSummary
    wildId: int
    teamSize: int = Field(ge=1, le=6)


class CompareRequest(BaseModel):
    teamA: TeamSummary
    teamB: TeamSummary


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/generation/{num}")
async def generation(num: int = Path(ge=1, le=9)):
    try:
        return await list_generation(num)
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.get("/megas")
async def megas():
    try:
        return await list_megas()
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.get("/type/{type_name}/pokemon")
async def pokemon_by_type(type_name: str):
    if type_name not in ALL_TYPES:
        raise HTTPException(404, f"Type inconnu : {type_name}")
    try:
        return await list_by_type(type_name)
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.get("/pokemon/{id_or_name}")
async def pokemon(id_or_name: str):
    try:
        return await get_profile(id_or_name)
    except NotFound:
        raise HTTPException(404, f"Pokémon inconnu : {id_or_name}")
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.post("/teams/analyze")
async def analyze_route(req: AnalyzeRequest):
    """Analyse d'une équipe (en création ou à l'enregistrement)."""
    try:
        return await analyze(req.pokemonIds)
    except NotFound as e:
        pid = str(e).rsplit("/", 1)[-1]
        raise HTTPException(404, f"Pokémon inconnu : {pid}")
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.get("/boss")
async def boss():
    """Boss de la semaine (public)."""
    try:
        return await current_boss()
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.post("/boss/fight")
async def boss_fight(req: BossFightRequest):
    """Affrontement d'une équipe contre le boss : même formule que le versus."""
    try:
        b = await current_boss()
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")
    result = compare_teams(req.team.model_dump(), b["summary"])
    public = {k: v for k, v in b.items() if k != "summary"}
    return {**result, "boss": public}


@app.post("/teams/compare")
def compare(req: CompareRequest):
    return compare_teams(req.teamA.model_dump(), req.teamB.model_dump())


# --- Mode Capture -------------------------------------------------------------------
# Le Pokédex applique les règles ; la progression du dresseur est fournie par Équipes.

@app.get("/capture/starters")
def capture_starters():
    return capture.starters()


@app.post("/capture/state")
def capture_state(req: CaptureState):
    """Collection, paliers, évolutions possibles pour une progression donnée."""
    return {
        "collection": capture.collection(req.unlocked),
        "unlockedSpecies": capture.unlocked_species_names(req.unlocked),
        "progression": capture.progression(req.unlocked, req.victories),
        "tiers": capture.tiers(req.unlocked),
    }


@app.post("/capture/encounters")
def capture_encounters(req: EncounterRequest):
    """3 Pokémon sauvages tirés au hasard dans le palier, parmi les lignes non possédées."""
    return capture.draw_encounters(req.tier, req.unlocked, req.exclude)


@app.post("/capture/analyze")
async def capture_analyze(req: CaptureAnalyzeRequest):
    """Analyse d'une équipe du mode Capture + Pokémon non débloqués."""
    try:
        result = await analyze(req.pokemonIds)
    except NotFound as e:
        raise HTTPException(404, f"Pokémon inconnu : {str(e).rsplit('/', 1)[-1]}")
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")
    result["forbidden"] = [m["name"] for m in result["members"] if not capture.is_allowed(m, req.unlocked)]
    return result


@app.post("/capture/fight")
async def capture_fight(req: CaptureFightRequest):
    """Combat contre un Pokémon sauvage qui s'adapte à la taille de l'équipe."""
    if req.wildId not in capture.REF["species"]:
        raise HTTPException(404, "Pokémon sauvage inconnu")
    try:
        wild = await get_profile(req.wildId)
    except NotFound:
        raise HTTPException(404, "Pokémon sauvage inconnu")
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")
    result = compare_teams(req.team.model_dump(), capture.wild_summary(wild, req.teamSize))
    return {**result, "wild": {**capture.entry(req.wildId), "sprite": wild["sprite"]}}
