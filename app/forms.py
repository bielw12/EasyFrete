"""Leitura e validação de formulários, com mensagens em português por campo."""
import re
from datetime import date, datetime
from math import isfinite

from fastapi import Request

from app.config import agora

UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
    "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)
_COM_MILHAR = re.compile(r"[+-]?[1-9][0-9]{0,2}(\.[0-9]{3})+(,[0-9]*)?")
_SEM_MILHAR = re.compile(r"[+-]?([0-9]+([.,][0-9]*)?|[.,][0-9]+)")
ANOS_VENCIMENTO = 20


def _ler_numero(texto: str) -> float | None:
    if _COM_MILHAR.fullmatch(texto):
        texto = texto.replace(".", "")
    elif not _SEM_MILHAR.fullmatch(texto):
        return None
    valor = float(texto.replace(",", "."))
    return valor if isfinite(valor) else None


class Form:
    """Lê campos de um formulário. Erros ficam em `erros`; o texto digitado, em `valores` (para reexibir)."""

    def __init__(self, dados: dict):
        self.valores = {k: (v.strip() if isinstance(v, str) else v) for k, v in dados.items()}
        self.erros: dict[str, str] = {}

    @classmethod
    async def de(cls, request: Request) -> "Form":
        """Só campos de texto; arquivos enviados são lidos direto de `request.form()`."""
        return cls({k: v for k, v in (await request.form()).items() if isinstance(v, str)})

    @property
    def ok(self) -> bool:
        return not self.erros

    def _bruto(self, nome: str, obrigatorio: bool):
        valor = self.valores.get(nome) or ""
        if not valor and obrigatorio:
            self.erros[nome] = "Campo obrigatório."
        return valor

    def texto(self, nome: str, obrigatorio: bool = True, opcoes=None, maximo: int | None = None) -> str | None:
        valor = self._bruto(nome, obrigatorio)
        if valor and opcoes and valor not in opcoes:
            self.erros[nome] = "Opção inválida."
        if valor and maximo and len(valor) > maximo:
            self.erros[nome] = f"Use no máximo {maximo} caracteres."
        return valor or None

    def numero(self, nome: str, obrigatorio: bool = True, minimo: float | None = 0, maximo: float | None = None) -> float | None:
        """Aceita 1234.56, 1234,56 e 1.234,56. Ponto seguido de grupos de 3 dígitos é milhar: 1.234 vale 1234."""
        bruto = self._bruto(nome, obrigatorio)
        if not bruto:
            return None
        valor = _ler_numero(bruto)
        if valor is None:
            self.erros[nome] = "Informe um número válido."
            return None
        if minimo is not None and valor < minimo:
            self.erros[nome] = "O valor não pode ser negativo." if minimo == 0 else f"O valor mínimo é {minimo:g}."
            return None
        if maximo is not None and valor > maximo:
            self.erros[nome] = f"O valor máximo é {maximo:g}."
            return None
        return valor

    def positivo(self, nome: str, obrigatorio: bool = True) -> float | None:
        """Número maior que zero: para valores que entram em divisões ou que não fazem sentido zerados."""
        valor = self.numero(nome, obrigatorio)
        if valor == 0:
            self.erros[nome] = "Informe um valor maior que zero."
            return None
        return valor

    def uf(self, nome: str, obrigatorio: bool = True) -> str | None:
        """Sigla de UF válida, gravada em maiúsculas."""
        valor = self._bruto(nome, obrigatorio).upper()
        if valor and valor not in UFS:
            self.erros[nome] = "UF inválida. Use a sigla de 2 letras, como SP."
        return valor or None

    def inteiro(self, nome: str, obrigatorio: bool = True, minimo: float | None = 0, maximo: float | None = None) -> int | None:
        valor = self.numero(nome, obrigatorio, minimo, maximo)
        if valor is None:
            return None
        if valor != int(valor):
            self.erros[nome] = "Informe um número inteiro."
            return None
        return int(valor)

    def data(self, nome: str, obrigatorio: bool = True) -> date | None:
        bruto = self._bruto(nome, obrigatorio)
        if not bruto:
            return None
        try:
            return date.fromisoformat(bruto)
        except ValueError:
            self.erros[nome] = "Informe uma data válida."
            return None

    def vencimento(self, nome: str, obrigatorio: bool = True) -> date | None:
        """Data de vencimento de documento: barra anos implausíveis, como 0026 (ano digitado com 2 dígitos)."""
        valor = self.data(nome, obrigatorio)
        ano = agora().year
        if valor and abs(valor.year - ano) > ANOS_VENCIMENTO:
            self.erros[nome] = f"Ano improvável. Use 4 dígitos, entre {ano - ANOS_VENCIMENTO} e {ano + ANOS_VENCIMENTO}."
            return None
        return valor

    def datahora(self, nome: str, obrigatorio: bool = True) -> datetime | None:
        bruto = self._bruto(nome, obrigatorio)
        if not bruto:
            return None
        try:
            return datetime.fromisoformat(bruto)
        except ValueError:
            self.erros[nome] = "Informe data e hora válidas."
            return None

    def marcado(self, nome: str) -> bool:
        return bool(self.valores.get(nome))

    def registro(self, nome: str, db, modelo, obrigatorio: bool = True):
        """Valida uma chave estrangeira e devolve o id."""
        bruto = self._bruto(nome, obrigatorio)
        if not bruto:
            return None
        if not bruto.isdigit() or db.get(modelo, int(bruto)) is None:
            self.erros[nome] = "Selecione uma opção válida."
            return None
        return int(bruto)
