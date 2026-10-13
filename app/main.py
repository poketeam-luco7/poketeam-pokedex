from __future__ import annotations

from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from .logic import compare_teams
from .pokeapi import NotFound, get_profile, list_generation

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


@app.get("/pokemon/{id_or_name}")
async def pokemon(id_or_name: str):
    try:
        return await get_profile(id_or_name)
    except NotFound:
        raise HTTPException(404, f"Pokémon inconnu : {id_or_name}")
    except httpx.HTTPError:
        raise HTTPException(503, "PokéAPI indisponible")


@app.post("/teams/compare")
def compare(req: CompareRequest):
    return compare_teams(req.teamA.model_dump(), req.teamB.model_dump())
