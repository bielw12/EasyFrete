"""Cadastro de rotas."""
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.forms import UFS, Form
from app.models import Rota
from app.routers._comum import contem, excluir_ou_bloquear, obter_ou_404, ordenar_por_nome, redirecionar
from app.services.alertas import salvar_e_reavaliar
from app.ui import render

router = APIRouter(prefix="/rotas")


def _ler_ufs_passagem(form: Form) -> str:
    """Aceita "mg, pr" ou "MG PR" e grava "MG,PR"."""
    ufs = [uf.upper() for uf in re.split(r"[,;\s]+", form.valores.get("ufs_passagem") or "") if uf]
    invalidas = [uf for uf in ufs if uf not in UFS]
    if invalidas:
        form.erros["ufs_passagem"] = f"UF inválida: {', '.join(invalidas)}. Separe por vírgula, como MG,PR."
    return ",".join(dict.fromkeys(ufs))


def _ler(form: Form) -> dict:
    return dict(
        nome=form.texto("nome", maximo=120),
        origem_cidade=form.texto("origem_cidade", maximo=80),
        origem_uf=form.uf("origem_uf"),
        destino_cidade=form.texto("destino_cidade", maximo=80),
        destino_uf=form.uf("destino_uf"),
        ufs_passagem=_ler_ufs_passagem(form),
        distancia_km=form.positivo("distancia_km"),
        pedagio_estimado=form.numero("pedagio_estimado"),
        tempo_estimado_h=form.positivo("tempo_estimado_h"),
        frete_tabela=form.numero("frete_tabela"),
    )


def _tela_form(request: Request, form: Form | None = None, rota: Rota | None = None, status_code: int = 200):
    return render(
        request,
        "rotas/form.html",
        status_code=status_code,
        titulo=f"Editar {rota.nome}" if rota else "Nova rota",
        form=form,
        r=rota,
    )


@router.get("")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    rotas = ordenar_por_nome(db.scalars(select(Rota)))
    q = q.strip()
    if q:
        rotas = [r for r in rotas if contem(q, r.nome, r.origem_cidade, r.destino_cidade, r.origem_uf, r.destino_uf)]
    return render(request, "rotas/lista.html", titulo="Rotas", rotas=rotas, q=q)


@router.get("/novo")
def novo(request: Request):
    return _tela_form(request)


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db)):
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, status_code=422)
    db.add(Rota(**dados))
    salvar_e_reavaliar(db)
    return redirecionar("/rotas", msg=f"Rota {dados['nome']} cadastrada.")


@router.get("/{rota_id}")
def ficha(request: Request, rota_id: int, db: Session = Depends(get_db)):
    rota = obter_ou_404(db, Rota, rota_id)
    return render(request, "rotas/ficha.html", titulo=rota.nome, r=rota)


@router.get("/{rota_id}/editar")
def editar(request: Request, rota_id: int, db: Session = Depends(get_db)):
    return _tela_form(request, rota=obter_ou_404(db, Rota, rota_id))


@router.post("/{rota_id}/editar")
async def salvar(request: Request, rota_id: int, db: Session = Depends(get_db)):
    rota = obter_ou_404(db, Rota, rota_id)
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, rota, status_code=422)
    for campo, valor in dados.items():
        setattr(rota, campo, valor)
    salvar_e_reavaliar(db)
    return redirecionar("/rotas", msg=f"Rota {rota.nome} atualizada.")


@router.post("/{rota_id}/excluir")
def excluir(rota_id: int, db: Session = Depends(get_db)):
    rota = obter_ou_404(db, Rota, rota_id)
    nome = rota.nome
    return excluir_ou_bloquear(
        db, rota, "/rotas",
        ok=f"Rota {nome} excluída.",
        bloqueado=f"A rota {nome} tem viagens registradas e não pode ser excluída: isso apagaria o histórico de margem.",
    )
