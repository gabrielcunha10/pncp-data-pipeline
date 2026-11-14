import csv
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from prefect import flow, task
from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    delete,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import declarative_base, sessionmaker

import pncp_etl


def obter_logger(nome: str = "load_db") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger(nome)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = RotatingFileHandler(
            os.path.join("logs", "pipeline.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
        logger.propagate = False
    return logger


logger = obter_logger()

Base = declarative_base()


# ==============================================================================
# MODELAGEM DIMENSIONAL (STAR SCHEMA) - POSTGRESQL (NEON TECH)
# ==============================================================================

class DimEstado(Base):
    __tablename__ = "dim_estados"

    uf = Column(CHAR(2), primary_key=True)
    nome_estado = Column(String(50), nullable=False)
    regiao = Column(String(30), nullable=False)
    capital = Column(String(60), nullable=False)
    ano_pib = Column(Integer, nullable=False)
    populacao = Column(BigInteger, nullable=False)
    pib_reais = Column(Numeric(18, 2), nullable=False)
    pib_per_capita_reais = Column(Numeric(12, 2), nullable=False)
    crescimento_real_anual_pct = Column(Numeric(5, 2), nullable=True)


class DimMunicipio(Base):
    __tablename__ = "dim_municipios"

    codigo_ibge = Column(CHAR(7), primary_key=True)
    uf = Column(CHAR(2), ForeignKey("dim_estados.uf"), nullable=False, index=True)
    municipio = Column(String(120), nullable=False)
    eh_capital = Column(Boolean, nullable=False)
    ano_pib = Column(Integer, nullable=False)
    populacao = Column(BigInteger, nullable=False)
    pib_reais = Column(Numeric(18, 2), nullable=False)
    pib_per_capita_reais = Column(Numeric(12, 2), nullable=False)
    faixa_pib_per_capita = Column(String(60), nullable=False)


class DimOrgao(Base):
    __tablename__ = "dim_orgaos"

    cnpj_orgao = Column(String(18), primary_key=True)
    nome_orgao = Column(String(255), nullable=False)
    esfera = Column(String(50), nullable=False)
    poder = Column(String(30), nullable=False)


class FatoEdital(Base):
    __tablename__ = "fato_editais"

    id_contratacao_pncp = Column(String(60), primary_key=True)
    codigo_ibge = Column(CHAR(7), ForeignKey("dim_municipios.codigo_ibge"), nullable=False)
    cnpj_orgao = Column(String(18), ForeignKey("dim_orgaos.cnpj_orgao"), nullable=False)
    uf = Column(CHAR(2), nullable=False)
    numero_edital = Column(String(60), nullable=True)
    tipo_instrumento = Column(String(80), nullable=True)
    situacao = Column(String(50), nullable=False)
    modalidade_contratacao = Column(String(80), nullable=True)
    modo_disputa = Column(String(80), nullable=True)
    tipo_compra = Column(String(50), nullable=False)
    srp = Column(Boolean, nullable=False)
    unidade_compradora = Column(String(255), nullable=True)
    setor_area = Column(String(80), nullable=False)
    motivo_proposta = Column(String(100), nullable=True)
    palavras_chave = Column(Text, nullable=True)
    objeto = Column(Text, nullable=False)
    valor_estimado = Column(Numeric(16, 2), nullable=True)
    status_valor = Column(String(40), nullable=False)
    ano_publicacao = Column(Integer, nullable=True)
    ano_mes_publicacao = Column(CHAR(7), nullable=True)
    data_divulgacao = Column(DateTime, nullable=True)
    data_inicio_propostas = Column(DateTime, nullable=True)
    data_fim_propostas = Column(DateTime, nullable=True)
    ultima_atualizacao = Column(DateTime, nullable=True)
    link_pncp = Column(Text, nullable=True)
    link_sistema_origem = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_fato_editais_uf", "uf"),
        Index("ix_fato_editais_codigo_ibge", "codigo_ibge"),
        Index("ix_fato_editais_cnpj_orgao", "cnpj_orgao"),
        Index("ix_fato_editais_setor_area", "setor_area"),
        Index("ix_fato_editais_data_divulgacao", "data_divulgacao"),
    )


# ==============================================================================
# FUNÇÕES AUXILIARES DE CONVERSÃO E UPSERT
# ==============================================================================

def normalizar_database_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _parse_datetime_br(valor: str) -> Optional[datetime]:
    v = (valor or "").strip()
    if not v:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _parse_float(valor: Any) -> Optional[float]:
    v = str(valor if valor is not None else "").strip()
    if not v:
        return None
    return float(v)


def _parse_int(valor: Any) -> Optional[int]:
    v = str(valor if valor is not None else "").strip()
    if not v:
        return None
    return int(float(v))


def _extrair_nome_orgao(orgao_str: str) -> str:
    if " - " in orgao_str:
        return orgao_str.split(" - ", 1)[1].strip()
    return orgao_str.strip()


def _upsert_lote(session, model, pk_nome: str, registros: List[Dict[str, Any]], chunk_size: int = 500) -> int:
    if not registros:
        return 0

    dialect = session.bind.dialect.name
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
    colunas_update = [c.name for c in model.__table__.columns if c.name != pk_nome]

    for i in range(0, len(registros), chunk_size):
        lote = registros[i : i + chunk_size]
        stmt = insert_fn(model).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=[pk_nome],
            set_={col: getattr(stmt.excluded, col) for col in colunas_update},
        )
        session.execute(stmt)

    return len(registros)


# ==============================================================================
# LEITURA E PREPARAÇÃO DOS DADOS (ANO MAIS RECENTE DINÂMICO)
# ==============================================================================

def preparar_dim_estados(caminho_csv: str) -> List[Dict[str, Any]]:
    with open(caminho_csv, "r", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))

    if not linhas:
        return []

    ano_recente = max(int(r["Ano_PIB"]) for r in linhas if str(r.get("Ano_PIB", "")).isdigit())
    registros = []
    for r in linhas:
        if int(r.get("Ano_PIB", 0) or 0) == ano_recente:
            registros.append({
                "uf": r["UF"].strip().upper(),
                "nome_estado": r["Nome_Estado"].strip(),
                "regiao": r["Regiao"].strip(),
                "capital": r["Capital"].strip(),
                "ano_pib": ano_recente,
                "populacao": int(r["Populacao"]),
                "pib_reais": float(r["PIB_Reais"]),
                "pib_per_capita_reais": float(r["PIB_per_Capita_Reais"]),
                "crescimento_real_anual_pct": _parse_float(r.get("Crescimento_Real_Anual_Pct")),
            })
    return registros


def preparar_dim_municipios(caminho_csv: str) -> List[Dict[str, Any]]:
    with open(caminho_csv, "r", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))

    if not linhas:
        return []

    ano_recente = max(int(r["Ano_PIB"]) for r in linhas if str(r.get("Ano_PIB", "")).isdigit())
    registros = []
    for r in linhas:
        if int(r.get("Ano_PIB", 0) or 0) == ano_recente:
            pib_pc = float(r["PIB_per_Capita_Reais"])
            registros.append({
                "codigo_ibge": r["Codigo_Municipio_IBGE"].strip(),
                "uf": r["UF"].strip().upper(),
                "municipio": r["Municipio"].strip(),
                "eh_capital": r.get("É Capital", "").strip().lower() == "sim",
                "ano_pib": ano_recente,
                "populacao": int(r["Populacao"]),
                "pib_reais": float(r["PIB_Reais"]),
                "pib_per_capita_reais": pib_pc,
                "faixa_pib_per_capita": pncp_etl.classificar_faixa_pib_per_capita(pib_pc),
            })
    return registros


def preparar_dim_orgaos_e_fato_editais(caminho_csv: str):
    with open(caminho_csv, "r", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))

    orgaos_map: Dict[str, Dict[str, Any]] = {}
    editais: List[Dict[str, Any]] = []

    for r in linhas:
        cnpj = r["CNPJ do Órgão"].strip()
        if cnpj and cnpj not in orgaos_map:
            orgaos_map[cnpj] = {
                "cnpj_orgao": cnpj,
                "nome_orgao": _extrair_nome_orgao(r.get("Órgão", "")),
                "esfera": r.get("Nível de Governo (Esfera)", "").strip(),
                "poder": r.get("Poder", "").strip(),
            }

        editais.append({
            "id_contratacao_pncp": r["ID Contratação PNCP"].strip(),
            "codigo_ibge": r["Código IBGE do Município"].strip(),
            "cnpj_orgao": cnpj,
            "uf": r["UF"].strip().upper(),
            "numero_edital": r.get("Número do Edital", "").strip(),
            "tipo_instrumento": r.get("Tipo de Instrumento", "").strip(),
            "situacao": r.get("Situação", "").strip(),
            "modalidade_contratacao": r.get("Modalidade de Contratação", "").strip(),
            "modo_disputa": r.get("Modo de Disputa", "").strip(),
            "tipo_compra": r.get("Tipo de Compra", "").strip(),
            "srp": r.get("SRP", "").strip().lower() == "sim",
            "unidade_compradora": r.get("Unidade Compradora", "").strip(),
            "setor_area": r.get("Setor / Área", "").strip(),
            "motivo_proposta": r.get("Motivo da Proposta", "").strip(),
            "palavras_chave": r.get("Palavras-Chave do Objeto", "").strip(),
            "objeto": r.get("Objeto", "").strip(),
            "valor_estimado": _parse_float(r.get("Valor Estimado Numérico")),
            "status_valor": r.get("Status do Valor", "").strip(),
            "ano_publicacao": _parse_int(r.get("Ano Publicação")),
            "ano_mes_publicacao": r.get("Ano/Mês Publicação", "").strip() or None,
            "data_divulgacao": _parse_datetime_br(r.get("Data de Divulgação PNCP", "")),
            "data_inicio_propostas": _parse_datetime_br(r.get("Data Início Recebimento Propostas", "")),
            "data_fim_propostas": _parse_datetime_br(r.get("Data Fim Recebimento Propostas", "")),
            "ultima_atualizacao": _parse_datetime_br(r.get("Última Atualização", "")),
            "link_pncp": r.get("Link PNCP", "").strip(),
            "link_sistema_origem": r.get("Link Sistema Origem", "").strip(),
        })

    return list(orgaos_map.values()), editais


# ==============================================================================
# TASK E FLOW DE CARGA NO BANCO DE DADOS (PREFECT)
# ==============================================================================

@task(name="Carregar Data Warehouse PostgreSQL (Neon)", retries=2, retry_delay_seconds=5, log_prints=True)
def carregar_banco_dados(
    database_url: Optional[str] = None,
    csv_ufs: str = os.path.join("data", "dados_ibge_ufs.csv"),
    csv_municipios: str = os.path.join("data", "dados_ibge_municipios.csv"),
    csv_editais: str = os.path.join("data", "editais_pncp_PB_PE.csv"),
):
    load_dotenv()
    raw_url = database_url or os.getenv("DATABASE_URL")
    if not raw_url:
        raise ValueError("Variável DATABASE_URL não encontrada no .env ou nos parâmetros.")

    db_url = normalizar_database_url(raw_url)
    engine = create_engine(db_url, pool_pre_ping=True)

    logger.info("=" * 70)
    logger.info("   CARGA NO DATA WAREHOUSE (POSTGRESQL / NEON TECH)")
    logger.info("=" * 70)

    # Cria tabelas e índices caso ainda não existam
    Base.metadata.create_all(engine)
    logger.info("Esquema Star Schema verificado/criado com sucesso.")

    estados = preparar_dim_estados(csv_ufs)
    municipios = preparar_dim_municipios(csv_municipios)
    orgaos, editais = preparar_dim_orgaos_e_fato_editais(csv_editais)

    Session = sessionmaker(bind=engine)
    with Session() as session:
        qtd_estados = _upsert_lote(session, DimEstado, "uf", estados)
        qtd_municipios = _upsert_lote(session, DimMunicipio, "codigo_ibge", municipios)
        qtd_orgaos = _upsert_lote(session, DimOrgao, "cnpj_orgao", orgaos)
        qtd_editais = _upsert_lote(session, FatoEdital, "id_contratacao_pncp", editais)

        # Sincronizar exclusões (ex: editais revogados/suspensos removidos do CSV)
        ids_ativos = {e["id_contratacao_pncp"] for e in editais}
        ids_no_banco = {row[0] for row in session.query(FatoEdital.id_contratacao_pncp).all()}
        ids_para_remover = list(ids_no_banco - ids_ativos)
        if ids_para_remover:
            session.execute(
                delete(FatoEdital).where(FatoEdital.id_contratacao_pncp.in_(ids_para_remover))
            )

        session.commit()

    ano_ibge = municipios[0]["ano_pib"] if municipios else "-"
    logger.info(f"dim_estados    (Ano IBGE {ano_ibge}): {qtd_estados} registros sincronizados")
    logger.info(f"dim_municipios (Ano IBGE {ano_ibge}): {qtd_municipios} registros sincronizados")
    logger.info(f"dim_orgaos:                          {qtd_orgaos} registros sincronizados")
    logger.info(f"fato_editais:                        {qtd_editais} registros sincronizados")
    logger.info(f"fato_editais (removidos/inativos):   {len(ids_para_remover)} registros removidos")
    logger.info("=" * 70)

    return {
        "dim_estados": qtd_estados,
        "dim_municipios": qtd_municipios,
        "dim_orgaos": qtd_orgaos,
        "fato_editais": qtd_editais,
        "removidos": len(ids_para_remover),
    }


@flow(name="Flow 3 - Carga no Banco PostgreSQL (Neon)", log_prints=True)
def flow_carga_banco():
    return carregar_banco_dados()


if __name__ == "__main__":
    flow_carga_banco()
