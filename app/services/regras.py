"""Cálculos de negócio puros: recebem objetos com atributos e nada de banco.

Interpretações das regras em docs/DECISOES.md. `hoje` aceita date ou datetime.
"""
import math
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

STATUS_REALIZADOS = ("em_transito", "entregue", "faturada")

JANELA_PRECO_DIAS = 30
JANELA_FRETE_DIAS = 90
SEPARACAO_JORNADA_H = 4.0
PAUSA_DIRECAO_H = 0.5


def _data(valor) -> date:
    return valor.date() if isinstance(valor, datetime) else valor


def _na_janela(valor, hoje, dias: int) -> bool:
    """Janela fechada nas duas pontas: de hoje − dias até hoje."""
    hoje = _data(hoje)
    return hoje - timedelta(days=dias) <= _data(valor) <= hoje


def _razao(numerador: float, denominador: float) -> float | None:
    return numerador / denominador if denominador else None


def realizada(viagem) -> bool:
    return viagem.status in STATUS_REALIZADOS


# ---------- Viagem ----------

def km_total(viagem) -> float:
    return viagem.km_carregado + viagem.km_vazio


def pct_km_vazio(viagem) -> float | None:
    """Percentual 0–100; None se a viagem não tem km."""
    total = km_total(viagem)
    return viagem.km_vazio / total * 100 if total else None


def dias_viagem(viagem, rota=None) -> int:
    """Dias inteiros para cima, mínimo 1. Sem chegada, usa o tempo estimado da rota."""
    if viagem.chegada_em:
        horas = (viagem.chegada_em - viagem.saida_em).total_seconds() / 3600
    else:
        horas = rota.tempo_estimado_h if rota else 0
    return max(1, math.ceil(horas / 24))


def custo_km_manutencao(ordens, viagens_do_veiculo, hoje, janela_dias: int) -> float | None:
    """Σ custo das OS na janela ÷ km das viagens realizadas na janela. None sem km."""
    custo = sum(o.custo for o in ordens if _na_janela(o.data, hoje, janela_dias))
    km = sum(
        km_total(v)
        for v in viagens_do_veiculo
        if realizada(v) and _na_janela(v.saida_em, hoje, janela_dias)
    )
    return _razao(custo, km)


def preco_medio_recente(abastecimentos, hoje, padrao: float, janela_dias: int = JANELA_PRECO_DIAS) -> float:
    """Σ R$ ÷ Σ litros na janela (ponderado por litros); `padrao` sem dados."""
    valor = litros = 0.0
    for a in abastecimentos:
        if _na_janela(a.data_hora, hoje, janela_dias):
            valor += a.valor_total
            litros += a.litros
    return valor / litros if litros else padrao


@dataclass(slots=True)
class DRE:
    receita: float
    combustivel: float
    combustivel_estimado: bool
    pedagio: float
    diarias: float
    comissao: float
    manutencao: float
    pneus: float
    custo_fixo: float
    outros: float
    custo_total: float
    margem: float
    margem_pct: float | None  # 0–100
    custo_km: float | None
    receita_km: float | None
    pct_vazio: float | None  # 0–100
    km_total: float
    dias: int


def dre_viagem(
    viagem,
    veiculo,
    rota,
    motorista,
    abastecimentos,
    custo_km_manut: float | None,
    preco_medio: float,
    custo_pneu_por_km: float,
) -> DRE:
    """`abastecimentos` são os vinculados à viagem; `custo_km_manut` None vira custo zero."""
    km = km_total(viagem)
    dias = dias_viagem(viagem, rota)
    receita = viagem.frete_valor

    estimado = not abastecimentos
    if estimado:
        combustivel = km / veiculo.consumo_ref_kmpl * preco_medio if veiculo.consumo_ref_kmpl else 0.0
    else:
        combustivel = sum(a.valor_total for a in abastecimentos)

    comissao = receita * motorista.comissao_pct / 100
    manutencao = (custo_km_manut or 0.0) * km
    pneus = km * custo_pneu_por_km
    custo_fixo = veiculo.custo_fixo_mensal / 30 * dias
    custo_total = (
        combustivel + viagem.pedagio_real + viagem.diarias_valor + comissao
        + manutencao + pneus + custo_fixo + viagem.outros_custos
    )
    margem = receita - custo_total
    return DRE(
        receita=receita,
        combustivel=combustivel,
        combustivel_estimado=estimado,
        pedagio=viagem.pedagio_real,
        diarias=viagem.diarias_valor,
        comissao=comissao,
        manutencao=manutencao,
        pneus=pneus,
        custo_fixo=custo_fixo,
        outros=viagem.outros_custos,
        custo_total=custo_total,
        margem=margem,
        margem_pct=margem / receita * 100 if receita else None,
        custo_km=_razao(custo_total, km),
        receita_km=_razao(receita, km),
        pct_vazio=pct_km_vazio(viagem),
        km_total=km,
        dias=dias,
    )


# ---------- Agregações ----------

@dataclass(slots=True)
class Agregado:
    viagens: int = 0
    receita: float = 0.0
    custo_total: float = 0.0
    margem: float = 0.0
    km_total: float = 0.0
    km_vazio: float = 0.0

    @property
    def margem_pct(self) -> float | None:
        return self.margem / self.receita * 100 if self.receita else None

    @property
    def custo_km(self) -> float | None:
        return _razao(self.custo_total, self.km_total)

    @property
    def receita_km(self) -> float | None:
        return _razao(self.receita, self.km_total)

    @property
    def pct_vazio(self) -> float | None:
        return self.km_vazio / self.km_total * 100 if self.km_total else None


def agregar_por(viagens, dres: dict, chave) -> dict:
    """Agrupa as viagens realizadas por `chave(viagem)`, ex.: attrgetter("rota_id")."""
    grupos = defaultdict(Agregado)
    for v in viagens:
        if not realizada(v):
            continue
        dre = dres[v.id]
        g = grupos[chave(v)]
        g.viagens += 1
        g.receita += dre.receita
        g.custo_total += dre.custo_total
        g.margem += dre.margem
        g.km_total += dre.km_total
        g.km_vazio += v.km_vazio
    return dict(grupos)


def agregar(viagens, dres: dict) -> Agregado:
    """Total das viagens realizadas (KPIs)."""
    return agregar_por(viagens, dres, lambda _: None).get(None, Agregado())


# ---------- Consumo ----------

@dataclass(slots=True)
class IntervaloConsumo:
    abastecimento: object  # o tanque cheio que fecha o intervalo
    km: float
    litros: float
    kmpl: float


def intervalos_consumo(abastecimentos_do_veiculo) -> list[IntervaloConsumo]:
    """Intervalos entre tanques cheios consecutivos, em ordem cronológica.

    Parciais somam litros ao intervalo. Odômetro regressivo descarta o intervalo e, se a
    leitura seguinte mostrar que foi erro de digitação (e não troca de odômetro), também
    o intervalo vizinho à leitura errada, que teria km absurdo.
    """
    intervalos: list[IntervaloConsumo] = []
    anterior = None
    teto = None  # odômetro antes da última regressão
    litros = 0.0
    for a in sorted(abastecimentos_do_veiculo, key=lambda x: x.data_hora):
        if anterior is None:
            anterior = a if a.tanque_cheio else None
            continue
        litros += a.litros
        if not a.tanque_cheio:
            continue
        km = a.odometro_km - anterior.odometro_km
        if km > 0 and litros > 0 and (teto is None or a.odometro_km < teto):
            intervalos.append(IntervaloConsumo(a, km, litros, km / litros))
        if km < 0:
            # A leitura anterior era alta demais: voltamos ao início do seu intervalo ou depois dele.
            ultimo = intervalos[-1] if intervalos else None
            if (
                ultimo
                and ultimo.abastecimento.odometro_km == anterior.odometro_km
                and a.odometro_km >= anterior.odometro_km - ultimo.km
            ):
                intervalos.pop()
            teto = anterior.odometro_km
        elif km > 0:  # leitura repetida não prova nada: mantém o teto
            teto = None
        anterior = a
        litros = 0.0
    return intervalos


def consumo_medio(intervalos) -> float | None:
    """Σ km ÷ Σ litros dos intervalos."""
    return _razao(sum(i.km for i in intervalos), sum(i.litros for i in intervalos))


# ---------- Manutenção ----------

def frete_medio_diario(viagens, hoje, janela_dias: int = JANELA_FRETE_DIAS) -> float:
    """Frete das viagens realizadas do veículo na janela ÷ dias da janela."""
    total = sum(v.frete_valor for v in viagens if realizada(v) and _na_janela(v.saida_em, hoje, janela_dias))
    return total / janela_dias


def custo_parada(dias_parado: float, frete_medio: float) -> float:
    return dias_parado * frete_medio


@dataclass(slots=True)
class SituacaoPlano:
    status: str  # vencido | a_vencer | ok
    km_restantes: float | None
    dias_restantes: int | None
    vence_km: float | None
    vence_em: date | None


def situacao_plano(plano, odometro_atual: float, hoje, avencer_pct: float, avencer_dias: int) -> SituacaoPlano:
    """Vencido só com saldo negativo; saldo zero (vence agora) ainda é a vencer."""
    vence_km = km_restantes = vence_em = dias_restantes = None
    if plano.intervalo_km:
        vence_km = plano.ultima_km + plano.intervalo_km
        km_restantes = vence_km - odometro_atual
    if plano.intervalo_dias:
        vence_em = plano.ultima_data + timedelta(days=plano.intervalo_dias)
        dias_restantes = (vence_em - _data(hoje)).days

    if (km_restantes is not None and km_restantes < 0) or (dias_restantes is not None and dias_restantes < 0):
        status = "vencido"
    elif (km_restantes is not None and km_restantes <= plano.intervalo_km * avencer_pct / 100) or (
        dias_restantes is not None and dias_restantes <= avencer_dias
    ):
        status = "a_vencer"
    else:
        status = "ok"
    return SituacaoPlano(status, km_restantes, dias_restantes, vence_km, vence_em)


# ---------- Documentos ----------

@dataclass(slots=True)
class SituacaoDocumento:
    status: str  # vencido | a_vencer | ok
    dias_restantes: int


def situacao_documento(vencimento: date | None, hoje, avencer_dias: int) -> SituacaoDocumento | None:
    """None quando o documento não se aplica (ex.: motorista sem MOPP). Vence hoje = a vencer."""
    if vencimento is None:
        return None
    dias = (vencimento - _data(hoje)).days
    status = "vencido" if dias < 0 else "a_vencer" if dias <= avencer_dias else "ok"
    return SituacaoDocumento(status, dias)


# ---------- Retorno ----------

def normalizar_cidade(nome: str) -> str:
    """Sem acentos, maiúsculas nem espaços sobrando."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def _casamento(cidade_a: str, uf_a: str, cidade_b: str, uf_b: str) -> str | None:
    """"cidade", "uf" ou None. Mesmo nome em outra UF é outra cidade."""
    if uf_a.strip().upper() != uf_b.strip().upper():
        return None
    return "cidade" if normalizar_cidade(cidade_a) == normalizar_cidade(cidade_b) else "uf"


@dataclass(slots=True)
class OportunidadeRetorno:
    viagem: object
    carga: object
    casa_origem: str  # cidade | uf
    casa_destino: str  # cidade | uf
    ganho_potencial: float


def oportunidades_retorno(viagem, rota, veiculo, cargas) -> list[OportunidadeRetorno]:
    """Cargas abertas que levam o veículo do destino da viagem de volta à base.

    Melhores casamentos primeiro (cidade antes de UF), depois maior ganho. Sem km vazio, lista vazia.
    """
    if viagem.km_vazio <= 0:
        return []
    achadas = []
    for c in cargas:
        if c.status != "aberta":
            continue
        origem = _casamento(c.origem_cidade, c.origem_uf, rota.destino_cidade, rota.destino_uf)
        destino = _casamento(c.destino_cidade, c.destino_uf, veiculo.cidade_base, veiculo.uf_base)
        if origem and destino:
            achadas.append(OportunidadeRetorno(viagem, c, origem, destino, c.valor))
    return sorted(
        achadas,
        key=lambda o: ((o.casa_origem, o.casa_destino).count("cidade"), o.casa_origem == "cidade", o.ganho_potencial),
        reverse=True,
    )


# ---------- Jornada ----------

def _horas(inicio: datetime, fim: datetime) -> float:
    return (fim - inicio).total_seconds() / 3600


def _tempo_novo(registro, coberto_ate: datetime) -> timedelta:
    """Parte do registro depois de `coberto_ate`, para não somar sobreposição em dobro."""
    return max(registro.fim - max(registro.inicio, coberto_ate), timedelta())


@dataclass(slots=True)
class Jornada:
    inicio: datetime
    fim: datetime
    direcao: timedelta  # soma em timedelta: somar horas em float viola limites exatos
    registros: list

    @property
    def direcao_h(self) -> float:
        return self.direcao.total_seconds() / 3600


def agrupar_jornadas(registros) -> list[Jornada]:
    """Direção e espera separadas por menos de 4 h formam uma jornada; só direção conta nas horas.

    Tempo de direção sobreposto conta uma vez só.
    """
    jornadas: list[Jornada] = []
    trabalho = sorted((r for r in registros if r.tipo in ("direcao", "espera")), key=lambda r: r.inicio)
    direcao_ate = None
    for r in trabalho:
        if not jornadas or _horas(jornadas[-1].fim, r.inicio) >= SEPARACAO_JORNADA_H:
            jornadas.append(Jornada(r.inicio, r.fim, timedelta(), []))
            direcao_ate = r.inicio
        j = jornadas[-1]
        j.fim = max(j.fim, r.fim)
        j.registros.append(r)
        if r.tipo == "direcao":
            j.direcao += _tempo_novo(r, direcao_ate)
            direcao_ate = max(direcao_ate, r.fim)
    return jornadas


@dataclass(slots=True)
class TrechoDirecao:
    inicio: datetime
    fim: datetime
    duracao: timedelta  # só tempo dirigindo, sem as pausas curtas

    @property
    def horas(self) -> float:
        return self.duracao.total_seconds() / 3600


def trechos_direcao(registros) -> list[TrechoDirecao]:
    """Funde registros de direção separados por menos de 30 min; sobreposição conta uma vez só."""
    trechos: list[TrechoDirecao] = []
    for r in sorted((r for r in registros if r.tipo == "direcao"), key=lambda r: r.inicio):
        if trechos and _horas(trechos[-1].fim, r.inicio) < PAUSA_DIRECAO_H:
            t = trechos[-1]
            t.duracao += _tempo_novo(r, t.fim)
            t.fim = max(t.fim, r.fim)
        else:
            trechos.append(TrechoDirecao(r.inicio, r.fim, r.fim - r.inicio))
    return trechos


@dataclass(slots=True)
class ViolacaoJornada:
    tipo: str  # direcao_continua | descanso | jornada_diaria
    severidade: str  # atencao | critico
    inicio: datetime
    fim: datetime
    horas: float
    limite_h: float


def violacoes_jornada(registros_do_motorista, direcao_h: float, descanso_h: float, diaria_h: float) -> list[ViolacaoJornada]:
    """Violações de um motorista em ordem cronológica. Valor exatamente no limite não viola."""
    violacoes = [
        ViolacaoJornada("direcao_continua", "atencao", t.inicio, t.fim, t.horas, direcao_h)
        for t in trechos_direcao(registros_do_motorista)
        if t.horas > direcao_h
    ]
    jornadas = agrupar_jornadas(registros_do_motorista)
    for j in jornadas:
        if j.direcao_h > diaria_h:
            violacoes.append(ViolacaoJornada("jornada_diaria", "critico", j.inicio, j.fim, j.direcao_h, diaria_h))
    for anterior, seguinte in zip(jornadas, jornadas[1:]):
        descanso = _horas(anterior.fim, seguinte.inicio)
        if descanso < descanso_h:
            violacoes.append(ViolacaoJornada("descanso", "atencao", anterior.fim, seguinte.inicio, descanso, descanso_h))
    return sorted(violacoes, key=lambda v: v.inicio)
