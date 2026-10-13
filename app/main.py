from __future__ import annotations

from typing import Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from .logic import ALL_TYPES, compare_teams
from .pokeapi import NotFound, analyze, get_profile, list_by_type, list_generation, list_megas

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


@app.post("/teams/compare")
def compare(req: CompareRequest):
    return compare_teams(req.teamA.model_dump(), req.teamB.model_dump())
