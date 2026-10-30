"""Monta os dados do banco para as funções puras de regras.py."""
import math
from collections import defaultdict

from sqlalchemy import select

from app.config import LIMIARES, agora
from app.models import Abastecimento, Config, Motorista, OrdemServico, Rota, Veiculo, Viagem
from app.services import regras


def carregar_config(db) -> dict:
    """Todos os limiares: valor salvo em Config ou o padrão, sempre no tipo do padrão."""
    salvos = dict(db.execute(select(Config.chave, Config.valor)).all())
    config = {}
    for chave, (padrao, *_) in LIMIARES.items():
        try:
            valor = float(salvos[chave].replace(",", "."))
        except (KeyError, ValueError):
            valor = padrao
        config[chave] = type(padrao)(valor) if math.isfinite(valor) else padrao
    return config


def _por_id(db, *colunas) -> dict:
    return {linha.id: linha for linha in db.execute(select(*colunas))}


def dres_de_viagens(db, viagens=None, hoje=None) -> dict:
    """{viagem_id: DRE} de `viagens` (padrão: todas), com número fixo de consultas.

    Inclui planejadas e canceladas, para as telas de detalhe; agregar_por só conta as realizadas.
    """
    hoje = hoje or agora().date()
    config = carregar_config(db)
    if viagens is None:
        viagens = db.scalars(select(Viagem)).all()

    veiculos = _por_id(db, Veiculo.id, Veiculo.custo_fixo_mensal, Veiculo.consumo_ref_kmpl)
    rotas = _por_id(db, Rota.id, Rota.tempo_estimado_h)
    motoristas = _por_id(db, Motorista.id, Motorista.comissao_pct)

    abastecimentos = db.execute(
        select(Abastecimento.viagem_id, Abastecimento.data_hora, Abastecimento.litros, Abastecimento.valor_total)
    ).all()
    abast_por_viagem = defaultdict(list)
    for a in abastecimentos:
        abast_por_viagem[a.viagem_id].append(a)
    preco = regras.preco_medio_recente(abastecimentos, hoje, config["preco_diesel_padrao"])

    ordens_por_veiculo = defaultdict(list)
    for o in db.execute(select(OrdemServico.veiculo_id, OrdemServico.data, OrdemServico.custo)):
        ordens_por_veiculo[o.veiculo_id].append(o)
    viagens_por_veiculo = defaultdict(list)
    for v in db.execute(
        select(Viagem.veiculo_id, Viagem.saida_em, Viagem.status, Viagem.frete_valor, Viagem.km_carregado, Viagem.km_vazio)
    ):
        viagens_por_veiculo[v.veiculo_id].append(v)
    custo_km_manut = {
        veiculo_id: regras.custo_km_manutencao(
            ordens_por_veiculo[veiculo_id], viagens_por_veiculo[veiculo_id], hoje, config["manut_janela_dias"]
        )
        for veiculo_id in veiculos
    }

    return {
        v.id: regras.dre_viagem(
            v,
            veiculos[v.veiculo_id],
            rotas[v.rota_id],
            motoristas[v.motorista_id],
            abast_por_viagem[v.id],
            custo_km_manut[v.veiculo_id],
            preco,
            config["custo_pneu_por_km"],
        )
        for v in viagens
    }
