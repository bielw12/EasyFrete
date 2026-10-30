"""Templates Jinja2: formatação pt-BR, menu lateral e render."""
from datetime import date, datetime
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.config import NOME_PRODUTO
from app.db import SessionLocal
from app.models import Alerta

MENU = [
    ("/", "Painel", "painel"),
    ("/viagens", "Viagens", "viagem"),
    ("/veiculos", "Veículos", "veiculo"),
    ("/motoristas", "Motoristas", "motorista"),
    ("/clientes", "Clientes", "cliente"),
    ("/rotas", "Rotas", "rota"),
    ("/combustivel", "Combustível", "combustivel"),
    ("/manutencao", "Manutenção", "manutencao"),
    ("/canhotos", "Canhotos e Fiscal", "canhoto"),
    ("/jornada", "Jornada", "jornada"),
    ("/cargas", "Retorno e Cargas", "carga"),
    ("/alertas", "Alertas", "alerta"),
    ("/configuracoes", "Configurações", "config"),
]

ROTULOS = {
    "em_transito": "Em trânsito",
    "manutencao": "Em manutenção",
    "critico": "Crítico",
    "atencao": "Atenção",
    "direcao": "Direção",
    "VUC": "VUC",
    "cavalo+carreta": "Cavalo + carreta",
}


def _milhar(texto: str) -> str:
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor) -> str:
    if valor is None:
        return "—"
    return f"{'-' if valor < -0.004 else ''}R$ {_milhar(f'{abs(valor):,.2f}')}"


def numero(valor, casas: int = 0) -> str:
    if valor is None:
        return "—"
    return _milhar(f"{valor:,.{casas}f}")


def pct(valor, casas: int = 1) -> str:
    """Recebe o percentual já em escala 0–100."""
    return "—" if valor is None else f"{numero(valor, casas)}%"


def data_br(valor) -> str:
    return valor.strftime("%d/%m/%Y") if isinstance(valor, (date, datetime)) else "—"


def datahora_br(valor) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if isinstance(valor, datetime) else "—"


def rotulo(valor) -> str:
    """Texto legível para valores de status/tipo guardados no banco."""
    if valor is None:
        return "—"
    return ROTULOS.get(valor, str(valor).replace("_", " ").capitalize())


def _globais(request: Request) -> dict:
    with SessionLocal() as sessao:
        criticos = sessao.scalar(
            select(func.count()).select_from(Alerta).where(Alerta.status == "aberto", Alerta.severidade == "critico")
        )
    return {
        "nome_produto": NOME_PRODUTO,
        "menu": MENU,
        "alertas_criticos": criticos,
        "msg": request.query_params.get("msg"),
        "erro_msg": request.query_params.get("erro"),
    }


templates = Jinja2Templates(directory=Path(__file__).parent / "templates", context_processors=[_globais])
templates.env.filters.update(brl=brl, numero=numero, pct=pct, data=data_br, datahora=datahora_br, rotulo=rotulo)


def render(request: Request, nome: str, status_code: int = 200, **contexto):
    return templates.TemplateResponse(request, nome, contexto, status_code=status_code)
