"""Cadastro de veículos."""
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import agora
from app.db import get_db
from app.forms import Form
from app.models import STATUS_VEICULO, TIPOS_VEICULO, Veiculo
from app.routers._comum import contem, excluir_ou_bloquear, obter_ou_404, redirecionar
from app.services.alertas import salvar_e_reavaliar
from app.ui import render, rotulo

router = APIRouter(prefix="/veiculos")

ANO_MINIMO = 1980
_PLACA = re.compile(r"([A-Z]{3})-?([0-9][A-Z0-9][0-9]{2})")


def normalizar_placa(texto: str) -> str | None:
    """Devolve ABC1D23 (Mercosul) ou ABC-1234 (antiga, hífen opcional na digitação). None se o formato for inválido."""
    casou = _PLACA.fullmatch(texto.upper().replace(" ", ""))
    if not casou:
        return None
    letras, resto = casou.groups()
    return f"{letras}-{resto}" if resto.isdigit() else letras + resto


def _ler(form: Form, db: Session, veiculo_id: int | None = None) -> dict:
    placa = form.texto("placa")
    if placa:
        placa = normalizar_placa(placa)
        if not placa:
            form.erros["placa"] = "Placa inválida. Use o formato ABC1D23 ou ABC-1234."
        elif db.scalar(select(Veiculo.id).where(Veiculo.placa == placa, Veiculo.id != veiculo_id)):
            form.erros["placa"] = f"Já existe um veículo com a placa {placa}."
    return dict(
        placa=placa,
        tipo=form.texto("tipo", opcoes=TIPOS_VEICULO),
        modelo=form.texto("modelo", maximo=80),
        ano=form.inteiro("ano", minimo=ANO_MINIMO, maximo=agora().year + 1),
        capacidade_kg=form.positivo("capacidade_kg"),
        tanque_l=form.positivo("tanque_l"),
        consumo_ref_kmpl=form.positivo("consumo_ref_kmpl"),
        odometro_km=form.numero("odometro_km"),
        custo_fixo_mensal=form.numero("custo_fixo_mensal"),
        venc_crlv=form.vencimento("venc_crlv"),
        venc_seguro=form.vencimento("venc_seguro"),
        cidade_base=form.texto("cidade_base", maximo=80),
        uf_base=form.uf("uf_base"),
        status=form.texto("status", opcoes=STATUS_VEICULO),
    )


def _tela_form(request: Request, form: Form | None = None, veiculo: Veiculo | None = None, status_code: int = 200):
    return render(
        request,
        "veiculos/form.html",
        status_code=status_code,
        titulo=f"Editar {veiculo.placa}" if veiculo else "Novo veículo",
        form=form,
        v=veiculo,
        tipos=[(t, rotulo(t)) for t in TIPOS_VEICULO],
        opcoes_status=[(s, rotulo(s)) for s in STATUS_VEICULO],
    )


@router.get("")
def lista(request: Request, q: str = "", db: Session = Depends(get_db)):
    veiculos = db.scalars(select(Veiculo).order_by(Veiculo.placa)).all()
    q = q.strip()
    if q:
        veiculos = [
            v for v in veiculos
            if contem(q, v.placa, v.placa.replace("-", ""), v.modelo, v.cidade_base, rotulo(v.tipo))
        ]
    return render(request, "veiculos/lista.html", titulo="Veículos", veiculos=veiculos, q=q)


@router.get("/novo")
def novo(request: Request):
    return _tela_form(request)


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db)):
    form = await Form.de(request)
    dados = _ler(form, db)
    if not form.ok:
        return _tela_form(request, form, status_code=422)
    db.add(Veiculo(**dados))
    salvar_e_reavaliar(db)
    return redirecionar("/veiculos", msg=f"Veículo {dados['placa']} cadastrado.")


@router.get("/{veiculo_id}")
def ficha(request: Request, veiculo_id: int, db: Session = Depends(get_db)):
    veiculo = obter_ou_404(db, Veiculo, veiculo_id)
    return render(request, "veiculos/ficha.html", titulo=veiculo.placa, v=veiculo)


@router.get("/{veiculo_id}/editar")
def editar(request: Request, veiculo_id: int, db: Session = Depends(get_db)):
    return _tela_form(request, veiculo=obter_ou_404(db, Veiculo, veiculo_id))


@router.post("/{veiculo_id}/editar")
async def salvar(request: Request, veiculo_id: int, db: Session = Depends(get_db)):
    veiculo = obter_ou_404(db, Veiculo, veiculo_id)
    form = await Form.de(request)
    dados = _ler(form, db, veiculo_id)
    if not form.ok:
        return _tela_form(request, form, veiculo, status_code=422)
    for campo, valor in dados.items():
        setattr(veiculo, campo, valor)
    salvar_e_reavaliar(db)
    return redirecionar("/veiculos", msg=f"Veículo {veiculo.placa} atualizado.")


@router.post("/{veiculo_id}/excluir")
def excluir(veiculo_id: int, db: Session = Depends(get_db)):
    veiculo = obter_ou_404(db, Veiculo, veiculo_id)
    placa = veiculo.placa
    return excluir_ou_bloquear(
        db, veiculo, "/veiculos",
        ok=f"Veículo {placa} excluído.",
        bloqueado=f"O veículo {placa} tem histórico (viagens, abastecimentos ou manutenção) e não pode ser excluído. "
                  "Para tirá-lo de uso, edite o cadastro e marque como Inativo.",
    )
