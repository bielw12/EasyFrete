"""Aplicação FastAPI."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import NOME_PRODUTO
from app.db import init_db
from app.routers import (
    alertas,
    canhotos,
    cargas,
    clientes,
    combustivel,
    configuracoes,
    jornada,
    manutencao,
    motoristas,
    painel,
    rotas,
    veiculos,
    viagens,
)


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=NOME_PRODUTO, docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

for modulo in (
    painel,
    viagens,
    veiculos,
    motoristas,
    clientes,
    rotas,
    combustivel,
    manutencao,
    canhotos,
    jornada,
    cargas,
    alertas,
    configuracoes,
):
    app.include_router(modulo.router)
