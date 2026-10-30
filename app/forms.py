"""Leitura e validação de formulários, com mensagens em português por campo."""
from datetime import date, datetime
from math import isfinite

from fastapi import Request


class Form:
    """Lê campos de um formulário. Erros ficam em `erros`; o texto digitado, em `valores` (para reexibir)."""

    def __init__(self, dados: dict):
        self.valores = {k: (v.strip() if isinstance(v, str) else v) for k, v in dados.items()}
        self.erros: dict[str, str] = {}

    @classmethod
    async def de(cls, request: Request) -> "Form":
        return cls(dict(await request.form()))

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
        """Aceita 1234.56, 1234,56 e 1.234,56."""
        bruto = self._bruto(nome, obrigatorio)
        if not bruto:
            return None
        texto = bruto.replace(".", "").replace(",", ".") if "," in bruto else bruto
        try:
            valor = float(texto)
        except ValueError:
            valor = None
        if valor is None or not isfinite(valor):
            self.erros[nome] = "Informe um número válido."
            return None
        if minimo is not None and valor < minimo:
            self.erros[nome] = "O valor não pode ser negativo." if minimo == 0 else f"O valor mínimo é {minimo:g}."
            return None
        if maximo is not None and valor > maximo:
            self.erros[nome] = f"O valor máximo é {maximo:g}."
            return None
        return valor

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
