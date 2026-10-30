"""Apoio comum aos routers: redirecionamento com aviso, busca de registro, exclusão protegida, busca e ordenação textual."""
import re
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError

from app.services.alertas import salvar_e_reavaliar
from app.services.regras import normalizar_cidade


def redirecionar(url: str, msg: str | None = None, erro: str | None = None) -> RedirectResponse:
    parametros = {chave: valor for chave, valor in (("msg", msg), ("erro", erro)) if valor}
    return RedirectResponse(f"{url}?{urlencode(parametros)}" if parametros else url, status_code=303)


def obter_ou_404(db, modelo, registro_id: int):
    # Fora do INTEGER de 64 bits do SQLite, o driver levantaria OverflowError.
    registro = db.get(modelo, registro_id) if abs(registro_id) < 2**63 else None
    if registro is None:
        raise HTTPException(status_code=404)
    return registro


def excluir_ou_bloquear(db, registro, url: str, ok: str, bloqueado: str) -> RedirectResponse:
    """Exclui e redireciona com `ok`; se a chave estrangeira impedir (há histórico), redireciona com `bloqueado`."""
    db.delete(registro)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return redirecionar(url, erro=bloqueado)
    salvar_e_reavaliar(db)
    return redirecionar(url, msg=ok)


def contem(busca: str, *textos) -> bool:
    """Busca sem diferenciar maiúsculas nem acentos: "sao" encontra "São Paulo"."""
    alvo = normalizar_cidade(busca)
    return any(alvo in normalizar_cidade(texto) for texto in textos if texto)


def _sem_pontuacao(texto: str) -> str:
    return re.sub(r"[./\-\s]", "", texto)


def contem_documento(busca: str, documento: str) -> bool:
    """CPF/CNPJ com ou sem pontuação: "12345678900" encontra "123.456.789-00"."""
    alvo = _sem_pontuacao(busca)
    return bool(alvo) and contem(alvo, _sem_pontuacao(documento))


def ordenar_por_nome(registros) -> list:
    """Ordem alfabética de pt-BR, que o SQLite não faz: acentos e minúsculas ficariam depois do Z."""
    return sorted(registros, key=lambda registro: normalizar_cidade(registro.nome))
