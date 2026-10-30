"""Aplicação FastAPI."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import ClientDisconnect

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
from app.ui import render


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=NOME_PRODUTO, docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.exception_handler(404)
def nao_encontrado(request: Request, _):
    return render(request, "nao_encontrado.html", status_code=404, titulo="Página não encontrada")


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(request: Request, erro: RequestValidationError):
    """Id que não é número na URL é um endereço incorreto, não um erro de API."""
    if any(detalhe["loc"][0] == "path" for detalhe in erro.errors()):
        return nao_encontrado(request, erro)
    return await request_validation_exception_handler(request, erro)


@app.exception_handler(ClientDisconnect)
async def cliente_desconectou(_: Request, __: ClientDisconnect):
    """Envio interrompido pelo navegador: não há a quem responder, e não é erro do sistema."""
    return Response(status_code=400)


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
