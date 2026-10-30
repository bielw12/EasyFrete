"""Entidades do domínio. Custos e margem não são colunas: ver app/services/regras.py."""
from datetime import date, datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

TIPOS_VEICULO = ("cavalo+carreta", "truck", "toco", "VUC")
STATUS_VEICULO = ("ativo", "manutencao", "inativo")
STATUS_MOTORISTA = ("ativo", "inativo")
STATUS_VIAGEM = ("planejada", "em_transito", "entregue", "faturada", "cancelada")
CTE_STATUS = ("pendente", "emitido", "autorizado", "cancelado")
MDFE_STATUS = ("pendente", "emitido", "encerrado")
CANHOTO_STATUS = ("pendente", "recebido")
TIPOS_OS = ("preventiva", "corretiva")
TIPOS_JORNADA = ("direcao", "descanso", "espera")
STATUS_CARGA = ("aberta", "alocada")
SEVERIDADES = ("critico", "atencao", "info")
STATUS_ALERTA = ("aberto", "resolvido", "ignorado")


class Veiculo(Base):
    __tablename__ = "veiculo"

    id: Mapped[int] = mapped_column(primary_key=True)
    placa: Mapped[str] = mapped_column(String(8), unique=True)
    tipo: Mapped[str]
    modelo: Mapped[str]
    ano: Mapped[int]
    capacidade_kg: Mapped[float]
    tanque_l: Mapped[float]
    consumo_ref_kmpl: Mapped[float]
    odometro_km: Mapped[float]
    custo_fixo_mensal: Mapped[float]
    venc_crlv: Mapped[date]
    venc_seguro: Mapped[date]
    cidade_base: Mapped[str]
    uf_base: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(default="ativo")


class Motorista(Base):
    __tablename__ = "motorista"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    cpf: Mapped[str]
    cnh_categoria: Mapped[str]
    venc_cnh: Mapped[date]
    venc_mopp: Mapped[date | None]
    comissao_pct: Mapped[float]
    diaria_valor: Mapped[float]
    status: Mapped[str] = mapped_column(default="ativo")


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    cnpj: Mapped[str]


class Rota(Base):
    __tablename__ = "rota"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    origem_cidade: Mapped[str]
    origem_uf: Mapped[str] = mapped_column(String(2))
    destino_cidade: Mapped[str]
    destino_uf: Mapped[str] = mapped_column(String(2))
    # UFs atravessadas além de origem e destino, ex.: "MG,PR". Evita falso positivo no alerta de UF.
    ufs_passagem: Mapped[str] = mapped_column(default="")
    distancia_km: Mapped[float]
    pedagio_estimado: Mapped[float]
    tempo_estimado_h: Mapped[float]
    frete_tabela: Mapped[float]


class Viagem(Base):
    __tablename__ = "viagem"

    id: Mapped[int] = mapped_column(primary_key=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("veiculo.id"))
    motorista_id: Mapped[int] = mapped_column(ForeignKey("motorista.id"))
    rota_id: Mapped[int] = mapped_column(ForeignKey("rota.id"))
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    saida_em: Mapped[datetime]
    chegada_em: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(default="planejada")
    frete_valor: Mapped[float]
    km_carregado: Mapped[float] = mapped_column(default=0)
    km_vazio: Mapped[float] = mapped_column(default=0)
    carga_kg: Mapped[float] = mapped_column(default=0)
    pedagio_real: Mapped[float] = mapped_column(default=0)
    diarias_valor: Mapped[float] = mapped_column(default=0)
    outros_custos: Mapped[float] = mapped_column(default=0)
    cte_numero: Mapped[str | None]
    cte_status: Mapped[str] = mapped_column(default="pendente")
    mdfe_numero: Mapped[str | None]
    mdfe_status: Mapped[str] = mapped_column(default="pendente")
    canhoto_status: Mapped[str] = mapped_column(default="pendente")
    canhoto_recebido_em: Mapped[datetime | None]
    canhoto_arquivo: Mapped[str | None]
    observacoes: Mapped[str | None]

    veiculo: Mapped[Veiculo] = relationship()
    motorista: Mapped[Motorista] = relationship()
    rota: Mapped[Rota] = relationship()
    cliente: Mapped[Cliente] = relationship()
    abastecimentos: Mapped[list["Abastecimento"]] = relationship(back_populates="viagem")


class Abastecimento(Base):
    __tablename__ = "abastecimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("veiculo.id"))
    viagem_id: Mapped[int | None] = mapped_column(ForeignKey("viagem.id"))
    data_hora: Mapped[datetime]
    litros: Mapped[float]
    valor_total: Mapped[float]
    odometro_km: Mapped[float]
    posto: Mapped[str]
    cidade: Mapped[str]
    uf: Mapped[str] = mapped_column(String(2))
    tanque_cheio: Mapped[bool] = mapped_column(default=True)

    veiculo: Mapped[Veiculo] = relationship()
    viagem: Mapped[Viagem | None] = relationship(back_populates="abastecimentos")


class PlanoManutencao(Base):
    __tablename__ = "plano_manutencao"

    id: Mapped[int] = mapped_column(primary_key=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("veiculo.id"))
    descricao: Mapped[str]
    intervalo_km: Mapped[float | None]
    intervalo_dias: Mapped[int | None]
    ultima_km: Mapped[float]
    ultima_data: Mapped[date]

    veiculo: Mapped[Veiculo] = relationship()


class OrdemServico(Base):
    __tablename__ = "ordem_servico"

    id: Mapped[int] = mapped_column(primary_key=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("veiculo.id"))
    plano_id: Mapped[int | None] = mapped_column(ForeignKey("plano_manutencao.id"))
    tipo: Mapped[str]
    descricao: Mapped[str]
    data: Mapped[date]
    km: Mapped[float]
    custo: Mapped[float]
    dias_parado: Mapped[float] = mapped_column(default=0)

    veiculo: Mapped[Veiculo] = relationship()
    plano: Mapped[PlanoManutencao | None] = relationship()


class RegistroJornada(Base):
    __tablename__ = "registro_jornada"

    id: Mapped[int] = mapped_column(primary_key=True)
    motorista_id: Mapped[int] = mapped_column(ForeignKey("motorista.id"))
    viagem_id: Mapped[int | None] = mapped_column(ForeignKey("viagem.id"))
    inicio: Mapped[datetime]
    fim: Mapped[datetime]
    tipo: Mapped[str]

    motorista: Mapped[Motorista] = relationship()
    viagem: Mapped[Viagem | None] = relationship()


class CargaDisponivel(Base):
    __tablename__ = "carga_disponivel"

    id: Mapped[int] = mapped_column(primary_key=True)
    origem_cidade: Mapped[str]
    origem_uf: Mapped[str] = mapped_column(String(2))
    destino_cidade: Mapped[str]
    destino_uf: Mapped[str] = mapped_column(String(2))
    valor: Mapped[float]
    data_coleta: Mapped[date]
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"))
    status: Mapped[str] = mapped_column(default="aberta")

    cliente: Mapped[Cliente | None] = relationship()


class Alerta(Base):
    __tablename__ = "alerta"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str]
    severidade: Mapped[str]
    entidade: Mapped[str]
    entidade_id: Mapped[int]
    mensagem: Mapped[str]
    criado_em: Mapped[datetime]
    status: Mapped[str] = mapped_column(default="aberto")
    motivo: Mapped[str | None]
    chave_unica: Mapped[str] = mapped_column(unique=True)


class Config(Base):
    __tablename__ = "config"

    chave: Mapped[str] = mapped_column(primary_key=True)
    valor: Mapped[str]
