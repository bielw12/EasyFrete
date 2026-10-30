"""Cadastro de motoristas."""
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.forms import Form
from app.models import STATUS_MOTORISTA, Motorista
from app.routers._comum import contem, contem_documento, excluir_ou_bloquear, obter_ou_404, ordenar_por_nome, redirecionar
from app.services.alertas import salvar_e_reavaliar
from app.ui import render, rotulo

router = APIRouter(prefix="/motoristas")

CATEGORIAS_CNH = ("B", "C", "D", "E", "AB", "AC", "AD", "AE")


def normalizar_cpf(texto: str) -> str | None:
    """Só o formato (sem dígito verificador): 11 dígitos, com ou sem pontuação. Devolve 000.000.000-00."""
    digitos = re.sub(r"[.\-\s]", "", texto)
    if not re.fullmatch(r"[0-9]{11}", digitos):
        return None
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _ler(form: Form) -> dict:
    cpf = form.texto("cpf")
    if cpf:
        cpf = normalizar_cpf(cpf)
        if not cpf:
            form.erros["cpf"] = "CPF inválido. Use 11 dígitos, como 123.456.789-00."
    return dict(
        nome=form.texto("nome", maximo=120),
        cpf=cpf,
        cnh_categoria=form.texto("cnh_categoria", opcoes=CATEGORIAS_CNH),
        venc_cnh=form.vencimento("venc_cnh"),
        venc_mopp=form.vencimento("venc_mopp", obrigatorio=False),
        comissao_pct=form.numero("comissao_pct", maximo=100),
        diaria_valor=form.numero("diaria_valor"),
        status=form.texto("status", opcoes=STATUS_MOTORISTA),
    )


def _tela_form(request: Request, form: Form | None = None, motorista: Motorista | None = None, status_code: int = 200):
    return render(
        request,
        "motoristas/form.html",
        status_code=status_code,
        titulo=f"Editar {motorista.nome}" if motorista else "Novo motorista",
        form=form,
        m=motorista,
        categorias=[(c, c) for c in CATEGORIAS_CNH],
        opcoes_status=[(s, rotulo(s)) for s in STATUS_MOTORISTA],
    )


@router.get("")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    motoristas = ordenar_por_nome(db.scalars(select(Motorista)))
    q = q.strip()
    if q:
        motoristas = [m for m in motoristas if contem(q, m.nome, m.cpf) or contem_documento(q, m.cpf)]
    return render(request, "motoristas/lista.html", titulo="Motoristas", motoristas=motoristas, q=q)


@router.get("/novo")
def novo(request: Request):
    return _tela_form(request)


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db)):
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, status_code=422)
    db.add(Motorista(**dados))
    salvar_e_reavaliar(db)
    return redirecionar("/motoristas", msg=f"Motorista {dados['nome']} cadastrado.")


@router.get("/{motorista_id}")
def ficha(request: Request, motorista_id: int, db: Session = Depends(get_db)):
    motorista = obter_ou_404(db, Motorista, motorista_id)
    return render(request, "motoristas/ficha.html", titulo=motorista.nome, m=motorista)


@router.get("/{motorista_id}/editar")
def editar(request: Request, motorista_id: int, db: Session = Depends(get_db)):
    return _tela_form(request, motorista=obter_ou_404(db, Motorista, motorista_id))


@router.post("/{motorista_id}/editar")
async def salvar(request: Request, motorista_id: int, db: Session = Depends(get_db)):
    motorista = obter_ou_404(db, Motorista, motorista_id)
    form = await Form.de(request)
    dados = _ler(form)
    if not form.ok:
        return _tela_form(request, form, motorista, status_code=422)
    for campo, valor in dados.items():
        setattr(motorista, campo, valor)
    salvar_e_reavaliar(db)
    return redirecionar("/motoristas", msg=f"Motorista {motorista.nome} atualizado.")


@router.post("/{motorista_id}/excluir")
def excluir(motorista_id: int, db: Session = Depends(get_db)):
    motorista = obter_ou_404(db, Motorista, motorista_id)
    nome = motorista.nome
    return excluir_ou_bloquear(
        db, motorista, "/motoristas",
        ok=f"Motorista {nome} excluído.",
        bloqueado=f"{nome} tem histórico (viagens ou jornada) e não pode ser excluído. "
                  "Para tirá-lo de uso, edite o cadastro e marque como Inativo.",
    )
