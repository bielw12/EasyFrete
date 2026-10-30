"""Cadastro de clientes."""
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.forms import Form
from app.models import Cliente
from app.routers._comum import contem, contem_documento, excluir_ou_bloquear, obter_ou_404, ordenar_por_nome, redirecionar
from app.services.alertas import salvar_e_reavaliar
from app.ui import render

router = APIRouter(prefix="/clientes")


def normalizar_cnpj(texto: str) -> str | None:
    """Só o formato (sem dígito verificador): 12 letras ou dígitos e 2 dígitos, com ou sem pontuação.

    Devolve em maiúsculas, como 00.000.000/0000-00 ou 12.ABC.345/01DE-35.
    """
    cnpj = re.sub(r"[./\-\s]", "", texto).upper()
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj):
        return None
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _ler(form: Form) -> dict:
    cnpj = form.texto("cnpj")
    if cnpj:
        cnpj = normalizar_cnpj(cnpj)
        if not cnpj:
            form.erros["cnpj"] = "CNPJ inválido. Use 14 caracteres, como 12.345.678/0001-90 ou 12.ABC.345/01DE-35."
    return dict(nome=form.texto("nome", maximo=120), cnpj=cnpj)


def _tela_form(request: Request, form: Form | None = None, cliente: Cliente | None = None, status_code: int = 200):
    return render(
        request,
        "clientes/form.html",
        status_code=status_code,
        titulo=f"Editar {cliente.nome}" if cliente else "Novo cliente",
        form=form,
        c=cliente,
    )


@router.get("")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    clientes = ordenar_por_nome(db.scalars(select(Cliente)))
    q = q.strip()
    if q:
        clientes = [c for c in clientes if contem(q, c.nome, c.cnpj) or contem_documento(q, c.cnpj)]
    return render(request, "clientes/lista.html", titulo="Clientes", clientes=clientes, q=q)


@router.get("/novo")
def novo(request: Request):
    return _tela_form(request)


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db)):
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, status_code=422)
    db.add(Cliente(**dados))
    salvar_e_reavaliar(db)
    return redirecionar("/clientes", msg=f"Cliente {dados['nome']} cadastrado.")


@router.get("/{cliente_id}")
def ficha(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = obter_ou_404(db, Cliente, cliente_id)
    return render(request, "clientes/ficha.html", titulo=cliente.nome, c=cliente)


@router.get("/{cliente_id}/editar")
def editar(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    return _tela_form(request, cliente=obter_ou_404(db, Cliente, cliente_id))


@router.post("/{cliente_id}/editar")
async def salvar(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = obter_ou_404(db, Cliente, cliente_id)
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, cliente, status_code=422)
    for campo, valor in dados.items():
        setattr(cliente, campo, valor)
    salvar_e_reavaliar(db)
    return redirecionar("/clientes", msg=f"Cliente {cliente.nome} atualizado.")


@router.post("/{cliente_id}/excluir")
def excluir(cliente_id: int, db: Session = Depends(get_db)):
    cliente = obter_ou_404(db, Cliente, cliente_id)
    nome = cliente.nome
    return excluir_ou_bloquear(
        db, cliente, "/clientes",
        ok=f"Cliente {nome} excluído.",
        bloqueado=f"O cliente {nome} tem viagens ou cargas registradas e não pode ser excluído: "
                  "isso apagaria o histórico de margem.",
    )
