"""Casos numéricos conferidos à mão: a conta está no comentário de cada teste."""
from datetime import date, datetime, timedelta
from operator import attrgetter
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import event

from app.config import LIMIARES
from app.db import engine
from app.models import (
    Abastecimento,
    Cliente,
    Config,
    Motorista,
    OrdemServico,
    Rota,
    Veiculo,
    Viagem,
)
from app.services import consultas, regras
from app.services.consultas import carregar_config, dres_de_viagens

HOJE = date(2026, 10, 30)


def viagem(**campos):
    base = dict(
        id=1,
        status="entregue",
        frete_valor=10000.0,
        km_carregado=800.0,
        km_vazio=200.0,
        pedagio_real=300.0,
        diarias_valor=200.0,
        outros_custos=100.0,
        saida_em=datetime(2026, 10, 1, 8, 0),
        chegada_em=datetime(2026, 10, 3, 8, 0),
    )
    return NS(**{**base, **campos})


VEICULO = NS(custo_fixo_mensal=9000.0, consumo_ref_kmpl=2.5)
ROTA = NS(tempo_estimado_h=30.0)
MOTORISTA = NS(comissao_pct=8.0)


def dre(v, abastecimentos=(), veiculo=VEICULO, custo_km_manut=0.5, preco=6.0, pneu=0.35):
    return regras.dre_viagem(v, veiculo, ROTA, MOTORISTA, list(abastecimentos), custo_km_manut, preco, pneu)


# ---------- Viagem realizada ----------

@pytest.mark.parametrize("status", ["em_transito", "entregue", "faturada"])
def test_status_que_contam_como_realizada(status):
    # 1000 km, frete 9000, saída dentro das janelas de 90 e 180 dias
    v = viagem(status=status, frete_valor=9000.0)
    assert regras.realizada(v) is True
    # OS 500 / 1000 km = R$ 0,50/km
    assert regras.custo_km_manutencao([NS(data=HOJE, custo=500.0)], [v], HOJE, 180) == pytest.approx(0.5)
    # 9000 / 90 dias = R$ 100/dia
    assert regras.frete_medio_diario([v], HOJE) == pytest.approx(100)
    dres = {v.id: NS(receita=9000.0, custo_total=6000.0, margem=3000.0, km_total=1000.0)}
    assert regras.agregar_por([v], dres, attrgetter("status"))[status].viagens == 1
    assert regras.agregar([v], dres).receita == 9000


@pytest.mark.parametrize("status", ["planejada", "cancelada"])
def test_status_que_nao_contam_como_realizada(status):
    assert regras.realizada(viagem(status=status)) is False


# ---------- DRE ----------

def test_dre_com_combustivel_real():
    # km = 800 + 200 = 1000; dias = 48 h = 2
    # combustível 1000 + 500 = 1500 | pedágio 300 | diárias 200 | comissão 8% de 10000 = 800
    # manutenção 0,50 × 1000 = 500 | pneus 0,35 × 1000 = 350 | fixo 9000/30 × 2 = 600 | outros 100
    # custo = 1500+300+200+800+500+350+600+100 = 4350; margem = 5650 = 56,5%
    # custo/km = 4,35; receita/km = 10; vazio = 200/1000 = 20%
    d = dre(viagem(), [NS(valor_total=1000.0), NS(valor_total=500.0)])
    assert d.receita == 10000
    assert d.combustivel == 1500
    assert d.combustivel_estimado is False
    assert d.pedagio == 300
    assert d.diarias == 200
    assert d.comissao == pytest.approx(800)
    assert d.manutencao == pytest.approx(500)
    assert d.pneus == pytest.approx(350)
    assert d.custo_fixo == pytest.approx(600)
    assert d.outros == 100
    assert d.custo_total == pytest.approx(4350)
    assert d.margem == pytest.approx(5650)
    assert d.margem_pct == pytest.approx(56.5)
    assert d.custo_km == pytest.approx(4.35)
    assert d.receita_km == pytest.approx(10)
    assert d.pct_vazio == pytest.approx(20)
    assert d.km_total == 1000
    assert d.dias == 2


def test_dre_com_combustivel_estimado():
    # Sem abastecimento: 1000 km / 2,5 km/l = 400 l × R$ 6 = 2400
    # custo = 2400+300+200+800+500+350+600+100 = 5250; margem = 4750 = 47,5%
    d = dre(viagem())
    assert d.combustivel == pytest.approx(2400)
    assert d.combustivel_estimado is True
    assert d.custo_total == pytest.approx(5250)
    assert d.margem == pytest.approx(4750)
    assert d.margem_pct == pytest.approx(47.5)


def test_dre_margem_negativa():
    # Frete 1000: comissão 80; custo = 1500+300+200+80+500+350+600+100 = 3630
    # margem = 1000 − 3630 = −2630 = −263%
    d = dre(viagem(frete_valor=1000.0), [NS(valor_total=1500.0)])
    assert d.custo_total == pytest.approx(3630)
    assert d.margem == pytest.approx(-2630)
    assert d.margem_pct == pytest.approx(-263)


def test_dre_divisao_por_zero_devolve_none():
    # Sem frete e sem km, sem chegada: rota de 30 h = 2 dias; só o custo fixo 9000/30 × 2 = 600
    v = viagem(
        frete_valor=0.0, km_carregado=0.0, km_vazio=0.0, pedagio_real=0.0, diarias_valor=0.0,
        outros_custos=0.0, chegada_em=None,
    )
    d = dre(v)
    assert d.custo_total == pytest.approx(600)
    assert d.margem == pytest.approx(-600)
    assert d.margem_pct is None
    assert d.custo_km is None
    assert d.receita_km is None
    assert d.pct_vazio is None


def test_dre_sem_consumo_de_referencia_nem_taxa_de_manutencao():
    d = dre(viagem(), veiculo=NS(custo_fixo_mensal=0.0, consumo_ref_kmpl=0.0), custo_km_manut=None)
    assert d.combustivel == 0
    assert d.combustivel_estimado is True
    assert d.manutencao == 0


# ---------- Dias, km vazio ----------

@pytest.mark.parametrize(
    "horas, dias",
    [(0, 1), (1, 1), (24, 1), (24 + 1 / 60, 2), (48, 2), (49, 3), (-5, 1)],
)
def test_dias_viagem_com_chegada(horas, dias):
    saida = datetime(2026, 10, 1, 8, 0)
    assert regras.dias_viagem(viagem(saida_em=saida, chegada_em=saida + timedelta(hours=horas))) == dias


@pytest.mark.parametrize("tempo, dias", [(0, 1), (24, 1), (25, 2), (72, 3)])
def test_dias_viagem_sem_chegada_usa_tempo_da_rota(tempo, dias):
    assert regras.dias_viagem(viagem(chegada_em=None), NS(tempo_estimado_h=tempo)) == dias


def test_pct_km_vazio():
    # 250 / (750 + 250) = 25%
    assert regras.pct_km_vazio(viagem(km_carregado=750.0, km_vazio=250.0)) == 25
    assert regras.pct_km_vazio(viagem(km_carregado=100.0, km_vazio=0.0)) == 0
    assert regras.pct_km_vazio(viagem(km_carregado=0.0, km_vazio=0.0)) is None


# ---------- Manutenção rateada e preço ----------

def test_custo_km_manutencao_borda_da_janela_e_so_realizadas():
    # Janela de 180 dias até 30/10/2026 começa em 03/05/2026.
    # OS: 1000 (na borda) + 500 (hoje) = 1500; a de 02/05 e a futura ficam fora.
    # Viagens: 1000 km (borda) + 2000 km = 3000 km; planejada e a de 02/05 ficam fora.
    # 1500 / 3000 = R$ 0,50/km
    inicio = date(2026, 5, 3)
    ordens = [
        NS(data=inicio, custo=1000.0),
        NS(data=HOJE, custo=500.0),
        NS(data=inicio - timedelta(days=1), custo=9000.0),
        NS(data=HOJE + timedelta(days=1), custo=9000.0),
    ]
    viagens = [
        viagem(saida_em=datetime(2026, 5, 3, 0, 0), km_carregado=1000.0, km_vazio=0.0),
        viagem(saida_em=datetime(2026, 10, 1, 8, 0), km_carregado=1500.0, km_vazio=500.0),
        viagem(saida_em=datetime(2026, 5, 2, 23, 59), km_carregado=9000.0, km_vazio=0.0),
        viagem(status="planejada", km_carregado=9000.0),
        viagem(status="cancelada", km_carregado=9000.0),
    ]
    assert regras.custo_km_manutencao(ordens, viagens, HOJE, 180) == pytest.approx(0.5)


def test_custo_km_manutencao_sem_km_devolve_none():
    assert regras.custo_km_manutencao([NS(data=HOJE, custo=100.0)], [], HOJE, 180) is None


def test_custo_km_manutencao_sem_os_e_zero():
    assert regras.custo_km_manutencao([], [viagem(saida_em=datetime(2026, 10, 1))], HOJE, 180) == 0


def test_preco_medio_recente():
    # Ponderado por litros: (600 + 700) / (100 + 100) = 6,50. O de 31 dias atrás fica fora.
    abast = [
        NS(data_hora=datetime(2026, 9, 30, 0, 0), litros=100.0, valor_total=600.0),  # 30 dias: dentro
        NS(data_hora=datetime(2026, 10, 30, 23, 0), litros=100.0, valor_total=700.0),
        NS(data_hora=datetime(2026, 9, 29, 23, 59), litros=100.0, valor_total=9000.0),
    ]
    assert regras.preco_medio_recente(abast, HOJE, 6.2) == pytest.approx(6.5)
    assert regras.preco_medio_recente([], HOJE, 6.2) == 6.2
    assert regras.preco_medio_recente(abast[2:], HOJE, 6.2) == 6.2


# ---------- Consumo ----------

def abast(dia, odometro, litros, cheio=True):
    return NS(data_hora=datetime(2026, 10, dia, 8, 0), odometro_km=odometro, litros=litros, tanque_cheio=cheio)


def kms_por_litro(lista):
    return [(i.km, i.litros, i.kmpl) for i in regras.intervalos_consumo(lista)]


def test_consumo_entre_tanques_cheios():
    # (10500 − 10000) / 200 l = 2,5 km/l, usando só os litros do abastecimento atual
    assert kms_por_litro([abast(1, 10000.0, 999.0), abast(2, 10500.0, 200.0)]) == [(500.0, 200.0, 2.5)]


def test_consumo_ordena_por_data():
    assert kms_por_litro([abast(2, 10500.0, 200.0), abast(1, 10000.0, 100.0)]) == [(500.0, 200.0, 2.5)]


def test_consumo_com_parcial_no_meio():
    # 10000 cheio → 10300 parcial 50 l → 11000 cheio 150 l: 1000 km / 200 l = 5 km/l
    lista = [abast(1, 10000.0, 100.0), abast(2, 10300.0, 50.0, cheio=False), abast(3, 11000.0, 150.0)]
    assert kms_por_litro(lista) == [(1000.0, 200.0, 5.0)]


def test_consumo_ignora_parcial_antes_do_primeiro_cheio():
    # O parcial inicial não tem referência: 500 km / 100 l = 5 km/l
    lista = [abast(1, 9000.0, 70.0, cheio=False), abast(2, 10000.0, 100.0), abast(3, 10500.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_troca_de_odometro_descarta_so_o_intervalo_regressivo():
    # 100000 → 90000 descartado; 90000 → 90500 com 100 l = 5 km/l é válido
    lista = [abast(1, 100000.0, 100.0), abast(2, 90000.0, 100.0), abast(3, 90500.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_odometro_digitado_baixo_nao_gera_km_absurdo():
    # 90000 é erro: 100000→90000 e 90000→100500 são descartados; 100500→101000 = 5 km/l
    lista = [abast(1, 100000.0, 100.0), abast(2, 90000.0, 100.0), abast(3, 100500.0, 100.0), abast(4, 101000.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_odometro_digitado_alto_nao_gera_km_absurdo():
    # 200000 é erro: 100000→200000 sai quando a próxima leitura volta; 100500→101000 = 5 km/l
    lista = [abast(1, 100000.0, 100.0), abast(2, 200000.0, 100.0), abast(3, 100500.0, 100.0), abast(4, 101000.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_odometro_repetido_descarta_e_segue():
    # Mesmo odômetro: sem intervalo; 10000 → 10500 com 100 l = 5 km/l segue válido
    lista = [abast(1, 10000.0, 100.0), abast(2, 10000.0, 100.0), abast(3, 10500.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


@pytest.mark.parametrize(
    "odometros",
    [
        # Leitura seguinte igual à de antes da regressão: 90000 é erro, 10000 km em 100 l seria absurdo
        [100000.0, 90000.0, 100000.0, 100500.0],
        # Erro baixo repetido: 90000→100500 não pode entrar com 105 km/l
        [100000.0, 90000.0, 90000.0, 100500.0, 101000.0],
        # Erro alto repetido: 100000→200000 sai mesmo com a repetição no meio
        [100000.0, 200000.0, 200000.0, 100500.0, 101000.0],
        # Erro alto e volta exatamente à leitura de início do intervalo
        [100000.0, 200000.0, 100000.0, 100500.0],
    ],
)
def test_consumo_erro_de_odometro_com_igualdade_ou_repeticao(odometros):
    lista = [abast(dia, odo, 100.0) for dia, odo in enumerate(odometros, start=1)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_troca_de_odometro_preserva_o_intervalo_real_anterior():
    # 100000→100500 é real; 1000 fica abaixo do início dele, logo é troca: 1000→1500 também vale
    lista = [abast(1, 100000.0, 100.0), abast(2, 100500.0, 100.0), abast(3, 1000.0, 100.0), abast(4, 1500.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0), (500.0, 100.0, 5.0)]


def test_consumo_troca_de_odometro_com_leitura_repetida():
    # A repetição mantém o teto, mas 90500 continua abaixo dele: é troca e o intervalo vale
    lista = [abast(1, 100000.0, 100.0), abast(2, 90000.0, 100.0), abast(3, 90000.0, 100.0), abast(4, 90500.0, 100.0)]
    assert kms_por_litro(lista) == [(500.0, 100.0, 5.0)]


def test_consumo_sem_intervalos():
    assert regras.intervalos_consumo([]) == []
    assert regras.intervalos_consumo([abast(1, 10000.0, 100.0)]) == []
    assert regras.consumo_medio([]) is None


def test_consumo_medio_ponderado():
    # (500 + 500) km / (100 + 300) l = 2,5 km/l (a média simples daria 3,33)
    lista = [abast(1, 0.0, 1.0), abast(2, 500.0, 100.0), abast(3, 1000.0, 300.0)]
    assert regras.consumo_medio(regras.intervalos_consumo(lista)) == 2.5


# ---------- Agregações ----------

def test_agregar_por_e_sigma_margem_sobre_sigma_receita():
    # Rota 1: margem (2000 − 500) / receita (10000 + 5000) = 10%; custo (8000+5500)/(1000+500) = 9/km
    # Média simples daria (20% − 10%)/2 = 5%, por isso Σ/Σ.
    # Rota 2 só tem planejada: não aparece.
    viagens = [
        viagem(id=1, rota_id=1, km_carregado=800.0, km_vazio=200.0),
        viagem(id=2, rota_id=1, km_carregado=500.0, km_vazio=0.0, status="faturada"),
        viagem(id=3, rota_id=2, status="planejada"),
        viagem(id=4, rota_id=1, status="cancelada"),
    ]
    dres = {
        1: NS(receita=10000.0, custo_total=8000.0, margem=2000.0, km_total=1000.0),
        2: NS(receita=5000.0, custo_total=5500.0, margem=-500.0, km_total=500.0),
    }
    grupos = regras.agregar_por(viagens, dres, attrgetter("rota_id"))
    assert list(grupos) == [1]
    g = grupos[1]
    assert g.viagens == 2
    assert g.margem == 1500
    assert g.margem_pct == pytest.approx(10)
    assert g.custo_km == pytest.approx(9)
    assert g.receita_km == pytest.approx(10)
    # vazio: 200 / 1500
    assert g.pct_vazio == pytest.approx(200 / 1500 * 100)
    assert regras.agregar(viagens, dres).viagens == 2


def test_agregado_vazio_nao_divide_por_zero():
    total = regras.agregar([], {})
    assert total.viagens == 0
    assert total.margem_pct is None
    assert total.custo_km is None
    assert total.receita_km is None
    assert total.pct_vazio is None


# ---------- Custo de parada ----------

def test_custo_de_parada():
    # Fretes na janela de 90 dias: 6000 + 3000 = 9000; 9000 / 90 = R$ 100/dia; 3 dias = R$ 300
    borda = datetime(2026, 8, 1, 0, 0)  # 90 dias antes de 30/10
    viagens = [
        viagem(frete_valor=6000.0, saida_em=borda),
        viagem(frete_valor=3000.0, saida_em=datetime(2026, 10, 30, 8, 0)),
        viagem(frete_valor=9000.0, saida_em=datetime(2026, 7, 31, 23, 59)),
        viagem(frete_valor=9000.0, saida_em=datetime(2026, 10, 1), status="planejada"),
    ]
    medio = regras.frete_medio_diario(viagens, HOJE)
    assert medio == pytest.approx(100)
    assert regras.custo_parada(3, medio) == pytest.approx(300)
    assert regras.frete_medio_diario([], HOJE) == 0


# ---------- Plano de manutenção ----------

def plano(intervalo_km=20000.0, intervalo_dias=None, ultima_km=100000.0, ultima_data=date(2026, 1, 1)):
    return NS(intervalo_km=intervalo_km, intervalo_dias=intervalo_dias, ultima_km=ultima_km, ultima_data=ultima_data)


@pytest.mark.parametrize(
    "odometro, status, restantes",
    [
        # Vence em 120000; 10% de 20000 = 2000: a vencer a partir de 118000
        (117999.0, "ok", 2001.0),
        (118000.0, "a_vencer", 2000.0),
        (120000.0, "a_vencer", 0.0),
        (120001.0, "vencido", -1.0),
    ],
)
def test_plano_por_km(odometro, status, restantes):
    s = regras.situacao_plano(plano(), odometro, HOJE, 10.0, 15)
    assert (s.status, s.km_restantes, s.dias_restantes) == (status, restantes, None)
    assert s.vence_km == 120000


@pytest.mark.parametrize(
    "hoje, status, restantes",
    [
        # 01/01/2026 + 100 dias = 11/04/2026; 15 dias antes = 27/03
        (date(2026, 3, 26), "ok", 16),
        (date(2026, 3, 27), "a_vencer", 15),
        (date(2026, 4, 11), "a_vencer", 0),
        (date(2026, 4, 12), "vencido", -1),
    ],
)
def test_plano_por_data(hoje, status, restantes):
    s = regras.situacao_plano(plano(intervalo_km=None, intervalo_dias=100), 0.0, hoje, 10.0, 15)
    assert (s.status, s.dias_restantes, s.km_restantes) == (status, restantes, None)
    assert s.vence_em == date(2026, 4, 11)


def test_plano_vencido_por_data_com_km_folgado_e_vice_versa():
    p = plano(intervalo_dias=100)
    assert regras.situacao_plano(p, 100000.0, date(2026, 4, 12), 10.0, 15).status == "vencido"
    assert regras.situacao_plano(p, 120001.0, date(2026, 1, 2), 10.0, 15).status == "vencido"
    assert regras.situacao_plano(p, 119000.0, date(2026, 1, 2), 10.0, 15).status == "a_vencer"


def test_plano_sem_intervalos_fica_ok():
    s = regras.situacao_plano(plano(intervalo_km=None), 999999.0, HOJE, 10.0, 15)
    assert (s.status, s.km_restantes, s.dias_restantes) == ("ok", None, None)


# ---------- Documentos ----------

@pytest.mark.parametrize(
    "dias, status",
    [(-1, "vencido"), (0, "a_vencer"), (12, "a_vencer"), (30, "a_vencer"), (31, "ok")],
)
def test_situacao_documento_bordas(dias, status):
    s = regras.situacao_documento(HOJE + timedelta(days=dias), HOJE, 30)
    assert (s.status, s.dias_restantes) == (status, dias)


def test_documento_que_nao_se_aplica():
    assert regras.situacao_documento(None, HOJE, 30) is None


def test_documento_aceita_datetime_como_hoje():
    assert regras.situacao_documento(HOJE, datetime(2026, 10, 30, 23, 0), 30).dias_restantes == 0


# ---------- Retorno ----------

ROTA_RET = NS(destino_cidade="São Paulo", destino_uf="SP")
VEIC_RET = NS(cidade_base="Jundiaí", uf_base="SP")


def carga(origem, uf_o, destino, uf_d, valor=3000.0, status="aberta"):
    return NS(
        origem_cidade=origem, origem_uf=uf_o, destino_cidade=destino, destino_uf=uf_d, valor=valor, status=status
    )


def test_retorno_casa_cidade_sem_acento_nem_caixa():
    ops = regras.oportunidades_retorno(viagem(), ROTA_RET, VEIC_RET, [carga(" SAO  PAULO ", "sp", "jundiai", "SP")])
    assert len(ops) == 1
    assert (ops[0].casa_origem, ops[0].casa_destino, ops[0].ganho_potencial) == ("cidade", "cidade", 3000.0)


def test_retorno_usa_uf_como_alternativa_e_ordena_cidade_primeiro():
    uf = carga("Santos", "SP", "Campinas", "SP", valor=9000.0)
    so_origem = carga("São Paulo", "SP", "Campinas", "SP", valor=5000.0)
    so_destino = carga("Santos", "SP", "Jundiaí", "SP", valor=7000.0)
    cidade = carga("São Paulo", "SP", "Jundiaí", "SP", valor=1000.0)
    ops = regras.oportunidades_retorno(viagem(), ROTA_RET, VEIC_RET, [uf, so_destino, so_origem, cidade])
    assert [o.carga for o in ops] == [cidade, so_origem, so_destino, uf]
    assert (ops[3].casa_origem, ops[3].casa_destino) == ("uf", "uf")


def test_retorno_descarta_o_que_nao_casa():
    cargas = [
        carga("Rio de Janeiro", "RJ", "Jundiaí", "SP"),  # origem em outra UF
        carga("São Paulo", "SP", "Curitiba", "PR"),  # destino em outra UF
        carga("São Paulo", "SP", "Jundiaí", "SP", status="alocada"),
    ]
    assert regras.oportunidades_retorno(viagem(), ROTA_RET, VEIC_RET, cargas) == []


def test_retorno_cidade_homonima_em_outra_uf_nao_casa():
    assert regras.oportunidades_retorno(viagem(), ROTA_RET, VEIC_RET, [carga("São Paulo", "MG", "Jundiaí", "SP")]) == []


def test_retorno_sem_km_vazio_nao_sugere():
    c = [carga("São Paulo", "SP", "Jundiaí", "SP")]
    assert regras.oportunidades_retorno(viagem(km_vazio=0.0), ROTA_RET, VEIC_RET, c) == []


# ---------- Jornada ----------

def reg(ini, fim, tipo="direcao"):
    """Horas desde 00:00 de 01/10/2026."""
    base = datetime(2026, 10, 1)
    return NS(inicio=base + timedelta(hours=ini), fim=base + timedelta(hours=fim), tipo=tipo)


def violacoes(registros):
    return regras.violacoes_jornada(registros, direcao_h=5.5, descanso_h=11.0, diaria_h=10.0)


def tipos(registros):
    return [v.tipo for v in violacoes(registros)]


def test_direcao_continua_exatamente_no_limite_nao_viola():
    assert tipos([reg(6, 11.5)]) == []


def test_direcao_continua_um_minuto_acima_viola():
    v = violacoes([reg(6, 11.5 + 1 / 60)])
    assert [(x.tipo, x.severidade) for x in v] == [("direcao_continua", "atencao")]
    assert v[0].horas == pytest.approx(5.5 + 1 / 60)


def test_direcao_funde_pausa_menor_que_30_min_e_soma_so_tempo_dirigindo():
    # 3 h + 20 min de pausa + 2,75 h: 5,75 h dirigindo (> 5,5); a pausa não conta
    registros = [reg(6, 9), reg(9 + 1 / 3, 12 + 1 / 12)]
    trechos = regras.trechos_direcao(registros)
    assert len(trechos) == 1
    assert trechos[0].horas == pytest.approx(5.75)
    assert tipos(registros) == ["direcao_continua"]


def test_pausa_de_exatos_30_min_separa_a_direcao():
    registros = [reg(6, 9), reg(9.5, 12.25)]
    assert len(regras.trechos_direcao(registros)) == 2
    assert tipos(registros) == []


def test_jornada_diaria_exatamente_no_limite_nao_viola():
    # 5 h + pausa 1 h + 5 h = 10 h de direção
    assert tipos([reg(6, 11), reg(12, 17)]) == []


def test_jornada_diaria_acima_do_limite_e_critico():
    # 5 h + pausa 1 h + 5,5 h = 10,5 h de direção
    v = violacoes([reg(6, 11), reg(12, 17.5)])
    assert [(x.tipo, x.severidade) for x in v] == [("jornada_diaria", "critico")]
    assert v[0].horas == pytest.approx(10.5)


def test_espera_nao_conta_na_jornada_diaria_mas_mantem_a_jornada_unida():
    # 5 h direção + 5 h espera + 5 h direção: sem a espera, as 5 h de intervalo separariam a jornada
    registros = [reg(6, 11), reg(11, 16, "espera"), reg(16, 21)]
    jornadas = regras.agrupar_jornadas(registros)
    assert len(jornadas) == 1
    assert jornadas[0].direcao_h == 10
    assert tipos(registros) == []


def _sequencia(minutos, pausa):
    """Registros de direção com as durações dadas, separados por `pausa` minutos."""
    registros, inicio = [], 6.0
    for m in minutos:
        registros.append(reg(inicio, inicio + m / 60))
        inicio += (m + pausa) / 60
    return registros


@pytest.mark.parametrize("minutos", [[30, 215, 85], [10, 250, 70]])
def test_direcao_continua_somando_varios_trechos_ate_o_limite_nao_viola(minutos):
    # 330 min = 5 h 30; somando horas em float daria 5,500000000000001
    registros = _sequencia(minutos, pausa=10)
    assert regras.trechos_direcao(registros)[0].horas == 5.5
    assert regras.violacoes_jornada(registros, 5.5, 11.0, 99.0) == []


@pytest.mark.parametrize("minutos, pausa", [([30, 460, 110], 60), ([5, 485, 110], 40)])
def test_jornada_diaria_somando_varios_registros_ate_o_limite_nao_viola(minutos, pausa):
    # 600 min = 10 h; somando horas em float daria 10,000000000000002
    registros = _sequencia(minutos, pausa)
    assert regras.agrupar_jornadas(registros)[0].direcao_h == 10
    assert regras.violacoes_jornada(registros, 99.0, 11.0, 10.0) == []


def test_varios_trechos_um_minuto_acima_do_limite_violam():
    # 331 min de direção e 601 min na jornada
    assert [v.tipo for v in regras.violacoes_jornada(_sequencia([30, 215, 86], 10), 5.5, 11.0, 99.0)] == ["direcao_continua"]
    assert [v.tipo for v in regras.violacoes_jornada(_sequencia([30, 460, 111], 60), 99.0, 11.0, 10.0)] == ["jornada_diaria"]


def test_registro_contido_em_outro_nao_encurta_o_fim():
    # 06–12 contém 07–08. O próximo começa 15 min depois das 12h, e não 4 h 15 depois das 08h.
    trechos = regras.trechos_direcao([reg(6, 12), reg(7, 8), reg(12.25, 13)])
    assert len(trechos) == 1
    assert trechos[0].fim == datetime(2026, 10, 1, 13)
    # 06–18 contém 07–08. O próximo começa 3 h depois das 18h: mesma jornada, que termina às 22h.
    jornadas = regras.agrupar_jornadas([reg(6, 18), reg(7, 8), reg(21, 22)])
    assert len(jornadas) == 1
    assert jornadas[0].fim == datetime(2026, 10, 1, 22)
    # Sem registro seguinte, o fim continua sendo o do registro mais longo
    assert regras.trechos_direcao([reg(6, 12), reg(7, 8)])[0].fim == datetime(2026, 10, 1, 12)
    assert regras.agrupar_jornadas([reg(6, 12), reg(7, 8)])[0].fim == datetime(2026, 10, 1, 12)


@pytest.mark.parametrize(
    "registros, horas",
    [
        # Contido: 06–11 já cobre 07–08, são 5 h de relógio
        ([reg(6, 11), reg(7, 8)], 5),
        # Mesmo registro lançado duas vezes: 4 h
        ([reg(8, 12), reg(8, 12)], 4),
        # Sobreposição parcial: 06–12 = 6 h
        ([reg(6, 10), reg(9, 12)], 6),
        # Contido seguido de parcial: compara com 10h, não com o fim do contido: 06–12 = 6 h
        ([reg(6, 10), reg(7, 8), reg(9, 12)], 6),
        # Sobreposição mais pausa curta fundida: 06–10 + 10h15–11h = 4,75 h
        ([reg(6, 10), reg(8, 9), reg(10.25, 11)], 4.75),
    ],
)
def test_direcao_sobreposta_conta_uma_vez_so(registros, horas):
    assert [t.horas for t in regras.trechos_direcao(registros)] == [horas]
    assert [j.direcao_h for j in regras.agrupar_jornadas(registros)] == [horas]


@pytest.mark.parametrize(
    "registros",
    [
        [reg(6, 11), reg(7, 8)],  # 5 h reais, somava 6
        [reg(8, 12), reg(8, 12)],  # 4 h reais, somava 8
        [reg(6, 11.5), reg(6, 11.5)],  # 5,5 h reais, exatamente no limite
    ],
)
def test_direcao_sobreposta_nao_gera_violacao_falsa(registros):
    assert tipos(registros) == []


def test_direcao_sobreposta_acima_do_limite_ainda_viola():
    # 06–12 = 6 h reais, mesmo com o registro repetido
    v = violacoes([reg(6, 12), reg(6, 12)])
    assert [x.tipo for x in v] == ["direcao_continua"]
    assert v[0].horas == 6


def test_jornada_diaria_com_registro_duplicado_conta_uma_vez():
    # 5 h + pausa 1 h + 5 h = 10 h reais, no limite; a duplicata somava 15 h
    assert tipos([reg(6, 11), reg(6, 11), reg(12, 17)]) == []


def test_espera_sobreposta_nao_desconta_direcao():
    # Direção 06–08 e 09–10 = 3 h. A espera 07–12 estende a jornada, mas não cobre direção.
    jornadas = regras.agrupar_jornadas([reg(6, 8), reg(7, 12, "espera"), reg(9, 10)])
    assert jornadas[0].direcao_h == 3
    assert jornadas[0].fim == datetime(2026, 10, 1, 12)


def test_sobreposicao_nao_passa_de_uma_jornada_para_a_seguinte():
    # 06–09 (com sobreposição) = 3 h; depois de 5 h de intervalo, 14–16 = 2 h
    jornadas = regras.agrupar_jornadas([reg(6, 8), reg(7, 9), reg(14, 16)])
    assert [j.direcao_h for j in jornadas] == [3, 2]


def test_separacao_de_jornadas_na_borda_de_4h():
    # Intervalo de 3 h 59 min: mesma jornada. 4 h exatas: jornada nova.
    assert len(regras.agrupar_jornadas([reg(6, 8), reg(8 + 3 + 59 / 60, 13)])) == 1
    assert len(regras.agrupar_jornadas([reg(6, 8), reg(12, 13)])) == 2


def test_registro_de_descanso_nao_entra_na_jornada():
    assert regras.agrupar_jornadas([reg(0, 8, "descanso")]) == []


def test_descanso_exatamente_11h_nao_viola():
    assert tipos([reg(6, 10), reg(21, 25)]) == []


def test_descanso_abaixo_de_11h_viola():
    # Fim às 10:00, volta às 20:59: 10 h 59 min
    v = violacoes([reg(6, 10), reg(20 + 59 / 60, 25)])
    assert [(x.tipo, x.severidade) for x in v] == [("descanso", "atencao")]
    assert v[0].horas == pytest.approx(10 + 59 / 60)


def test_violacoes_em_ordem_cronologica():
    # Jornada 1 (00h–06h): 6 h seguidas, direção contínua às 00h. Descanso de 5 h, a partir das 06h.
    # Jornada 2 (11h–23h): 5 h + pausa de 1 h + 6 h = 11 h, jornada diária às 11h e direção contínua às 17h.
    registros = [reg(0, 6), reg(11, 16), reg(17, 23)]
    assert tipos(registros) == ["direcao_continua", "descanso", "jornada_diaria", "direcao_continua"]


def test_jornada_sem_registros():
    assert violacoes([]) == []


# ---------- Consultas ----------

def _cadastros(db):
    veiculo = Veiculo(
        placa="AAA0A00", tipo="truck", modelo="M", ano=2020, capacidade_kg=1000.0, tanque_l=500.0,
        consumo_ref_kmpl=2.5, odometro_km=0.0, custo_fixo_mensal=9000.0, venc_crlv=HOJE, venc_seguro=HOJE,
        cidade_base="Jundiaí", uf_base="SP",
    )
    motorista = Motorista(
        nome="M", cpf="0", cnh_categoria="E", venc_cnh=HOJE, comissao_pct=8.0, diaria_valor=0.0
    )
    cliente = Cliente(nome="C", cnpj="0")
    rota = Rota(
        nome="R", origem_cidade="A", origem_uf="SP", destino_cidade="B", destino_uf="SP", distancia_km=1000.0,
        pedagio_estimado=0.0, tempo_estimado_h=30.0, frete_tabela=0.0,
    )
    db.add_all([veiculo, motorista, cliente, rota])
    db.flush()
    return veiculo, motorista, cliente, rota


def _viagem_orm(cad, **campos):
    veiculo, motorista, cliente, rota = cad
    base = dict(
        veiculo_id=veiculo.id, motorista_id=motorista.id, cliente_id=cliente.id, rota_id=rota.id,
        saida_em=datetime(2026, 10, 1, 8, 0), chegada_em=datetime(2026, 10, 3, 8, 0), status="entregue",
        frete_valor=10000.0, km_carregado=800.0, km_vazio=200.0, pedagio_real=300.0, diarias_valor=200.0,
        outros_custos=100.0,
    )
    return Viagem(**{**base, **campos})


def _abast_orm(veiculo, viagem_id, valor, litros):
    return Abastecimento(
        veiculo_id=veiculo.id, viagem_id=viagem_id, data_hora=datetime(2026, 10, 2, 8, 0), litros=litros,
        valor_total=valor, odometro_km=0.0, posto="P", cidade="C", uf="SP",
    )


def test_dres_de_viagens_ponta_a_ponta(db):
    # Config: pneu 0,50/km. Taxa de manutenção do veículo: OS 2000 / km das realizadas (1000 + 1000) = 1,00/km.
    # A planejada de 9000 km não entra no denominador.
    # Viagem A (real): combustível 1000 | pedágio 300 | diárias 200 | comissão 800 | manutenção 1000
    #                  pneus 500 | fixo 600 | outros 100 = 4500; margem 5500 = 55%
    # Viagem B (sem abastecimento): preço médio = 1000 / 200 l = R$ 5; 1000/2,5 = 400 l × 5 = 2000
    #                  2000+300+200+800+1000+500+600+100 = 5500; margem 4500 = 45%
    cad = _cadastros(db)
    veiculo = cad[0]
    a = _viagem_orm(cad)
    b = _viagem_orm(cad)
    planejada = _viagem_orm(cad, status="planejada", km_carregado=9000.0)
    db.add_all([a, b, planejada])
    db.flush()
    db.add(_abast_orm(veiculo, a.id, 1000.0, 200.0))
    db.add(OrdemServico(veiculo_id=veiculo.id, tipo="corretiva", descricao="x", data=HOJE, km=0.0, custo=2000.0))
    db.add(Config(chave="custo_pneu_por_km", valor="0.50"))
    db.commit()

    dres = dres_de_viagens(db, hoje=HOJE)
    assert set(dres) == {a.id, b.id, planejada.id}
    assert dres[a.id].combustivel_estimado is False
    assert dres[a.id].custo_total == pytest.approx(4500)
    assert dres[a.id].margem_pct == pytest.approx(55)
    assert dres[b.id].combustivel_estimado is True
    assert dres[b.id].combustivel == pytest.approx(2000)
    assert dres[b.id].custo_total == pytest.approx(5500)
    assert dres[b.id].margem_pct == pytest.approx(45)

    # Só as pedidas; agregação ignora a planejada
    assert set(dres_de_viagens(db, [a], hoje=HOJE)) == {a.id}
    assert regras.agregar([a, b, planejada], dres).viagens == 2


def test_dres_de_viagens_com_banco_vazio(db):
    assert dres_de_viagens(db, hoje=HOJE) == {}


def test_dres_de_viagens_nao_faz_n_mais_1(db):
    cad = _cadastros(db)
    db.add_all([_viagem_orm(cad) for _ in range(30)])
    db.commit()
    consultas = []

    def contar(conn, cursor, statement, *_):
        consultas.append(statement)

    event.listen(engine, "before_cursor_execute", contar)
    try:
        dres = dres_de_viagens(db, hoje=HOJE)
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    assert len(dres) == 30
    assert len(consultas) <= 8


def test_dres_de_viagens_usa_janela_de_manutencao_configurada(db):
    # OS de 20 dias atrás, R$ 1000 sobre 1000 km: fora da janela de 10 dias, dentro da padrão (180)
    cad = _cadastros(db)
    v = _viagem_orm(cad, saida_em=datetime(2026, 10, 25, 8, 0), chegada_em=datetime(2026, 10, 27, 8, 0))
    db.add(v)
    db.add(OrdemServico(
        veiculo_id=cad[0].id, tipo="corretiva", descricao="x", data=HOJE - timedelta(days=20), km=0.0, custo=1000.0
    ))
    db.commit()
    assert dres_de_viagens(db, hoje=HOJE)[v.id].manutencao == pytest.approx(1000)
    db.add(Config(chave="manut_janela_dias", valor="10"))
    db.commit()
    assert dres_de_viagens(db, hoje=HOJE)[v.id].manutencao == 0


def test_dres_de_viagens_usa_preco_de_diesel_configurado(db):
    # Sem abastecimentos: 1000 km / 2,5 km/l = 400 l × R$ 7 = 2800
    cad = _cadastros(db)
    v = _viagem_orm(cad)
    db.add(v)
    db.add(Config(chave="preco_diesel_padrao", valor="7"))
    db.commit()
    assert dres_de_viagens(db, hoje=HOJE)[v.id].combustivel == pytest.approx(2800)


def test_dres_de_viagens_sem_hoje_usa_a_data_atual(db, monkeypatch):
    # OS de 30/10/2026: dentro da janela em HOJE, fora dela 1 ano depois
    cad = _cadastros(db)
    v = _viagem_orm(cad, saida_em=datetime(2026, 10, 25, 8, 0), chegada_em=datetime(2026, 10, 27, 8, 0))
    db.add(v)
    db.add(OrdemServico(veiculo_id=cad[0].id, tipo="corretiva", descricao="x", data=HOJE, km=0.0, custo=1000.0))
    db.commit()
    monkeypatch.setattr(consultas, "agora", lambda: datetime(2026, 10, 30, 12, 0))
    assert dres_de_viagens(db)[v.id].manutencao == pytest.approx(1000)
    monkeypatch.setattr(consultas, "agora", lambda: datetime(2027, 10, 30, 12, 0))
    assert dres_de_viagens(db)[v.id].manutencao == 0


@pytest.mark.parametrize("valor", ["inf", "-inf", "1e999", "nan", "lixo"])
@pytest.mark.parametrize("chave", ["canhoto_atencao_dias", "margem_meta_pct"])
def test_carregar_config_valor_invalido_volta_ao_padrao(db, chave, valor):
    db.add(Config(chave=chave, valor=valor))
    db.commit()
    assert carregar_config(db)[chave] == LIMIARES[chave][0]


def test_carregar_config_mescla_banco_e_padroes(db):
    db.add_all(
        [
            Config(chave="margem_meta_pct", valor="15"),
            Config(chave="canhoto_atencao_dias", valor="7.0"),
            Config(chave="jornada_direcao_h", valor="6,5"),
            Config(chave="consumo_janela", valor="lixo"),
            Config(chave="chave_desconhecida", valor="1"),
        ]
    )
    db.commit()
    config = carregar_config(db)
    assert set(config) == set(LIMIARES)
    assert config["margem_meta_pct"] == 15.0
    assert config["canhoto_atencao_dias"] == 7
    assert isinstance(config["canhoto_atencao_dias"], int)
    assert config["jornada_direcao_h"] == 6.5
    assert config["consumo_janela"] == LIMIARES["consumo_janela"][0]
    assert config["custo_pneu_por_km"] == LIMIARES["custo_pneu_por_km"][0]
