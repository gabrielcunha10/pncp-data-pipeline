import csv
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

import atualizar_ibge
import download_pncp
import pncp_etl


# ==============================================================================
# FIXTURES COMPARTILHADAS (PYTEST)
# ==============================================================================

@pytest.fixture(scope="module")
def dados_editais_csv():
    """Carrega as linhas de data/editais_pncp_PB_PE.csv uma única vez para os testes."""
    caminho = os.path.join("data", "editais_pncp_PB_PE.csv")
    assert os.path.exists(caminho), f"Arquivo '{caminho}' não encontrado."
    with open(caminho, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


@pytest.fixture(scope="module")
def dados_ibge_municipios_csv():
    """Carrega as linhas de data/dados_ibge_municipios.csv uma única vez para os testes."""
    caminho = os.path.join("data", "dados_ibge_municipios.csv")
    assert os.path.exists(caminho), f"Arquivo '{caminho}' não encontrado."
    with open(caminho, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


# ==============================================================================
# 1. TESTES DO MÓDULO: download_pncp.py
# ==============================================================================

def test_download_pncp_upsert_sem_duplicatas(tmp_path, monkeypatch):
    """Garante que baixar_dados_brutos realiza Upsert por numeroControlePNCP sem duplicar."""
    json_path = tmp_path / "dados_brutos_pncp.json"

    # Pré-popular cache com 1 edital existente
    edital_antigo = {
        "numeroControlePNCP": "00000000000191-1-000001/2026",
        "objetoCompra": "Versao Antiga",
        "_uf_consulta": "PB"
    }
    json_path.write_text(json.dumps([edital_antigo]), encoding="utf-8")

    # Simular resposta da API para PB (atualiza 000001 e insere 000002) e PE (insere 000003)
    resp_pb = MagicMock(status_code=200)
    resp_pb.json.return_value = {
        "totalPaginas": 1,
        "data": [
            {"numeroControlePNCP": "00000000000191-1-000001/2026", "objetoCompra": "Versao Atualizada"},
            {"numeroControlePNCP": "00000000000191-1-000002/2026", "objetoCompra": "Edital Novo PB"}
        ]
    }
    resp_pe = MagicMock(status_code=200)
    resp_pe.json.return_value = {
        "totalPaginas": 1,
        "data": [
            {"numeroControlePNCP": "11111111000191-1-000003/2026", "objetoCompra": "Edital Novo PE"}
        ]
    }

    monkeypatch.setattr(download_pncp.time, "sleep", lambda _: None)
    monkeypatch.setattr(download_pncp.requests.Session, "get", MagicMock(side_effect=[resp_pb, resp_pe]))

    download_pncp.baixar_dados_brutos.fn(
        ufs=("PB", "PE"),
        data_final="20261231",
        output_json=str(json_path)
    )

    resultado = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(resultado) == 3, "Deve conter exatamente 3 registros únicos após o Upsert."

    mapa = {r["numeroControlePNCP"]: r for r in resultado}
    assert mapa["00000000000191-1-000001/2026"]["objetoCompra"] == "Versao Atualizada"
    assert mapa["00000000000191-1-000002/2026"]["_uf_consulta"] == "PB"
    assert mapa["11111111000191-1-000003/2026"]["_uf_consulta"] == "PE"


def test_integridade_json_bruto_pncp():
    """Valida a estrutura e unicidade de chaves do arquivo real data/dados_brutos_pncp.json."""
    caminho = os.path.join("data", "dados_brutos_pncp.json")
    if not os.path.exists(caminho):
        pytest.skip("Arquivo data/dados_brutos_pncp.json não encontrado localmente.")

    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    assert isinstance(dados, list)
    assert len(dados) > 0, "O JSON bruto do PNCP não pode estar vazio."

    ids = [item.get("numeroControlePNCP") for item in dados]
    assert None not in ids, "Todos os itens brutos devem possuir numeroControlePNCP."
    assert len(ids) == len(set(ids)), "Não deve haver numeroControlePNCP duplicado no JSON bruto."


# ==============================================================================
# 2. TESTES DO MÓDULO: atualizar_ibge.py
# ==============================================================================

def test_atualizar_dados_ibge_ufs_calculo_pib_estadual(tmp_path, monkeypatch):
    """Testa atualizar_dados_ibge_ufs na consolidação de PIB e população estadual."""
    csv_ufs = tmp_path / "dados_ibge_ufs.csv"

    resp_censo = MagicMock(status_code=200)
    resp_censo.json.return_value = [
        {"D1C": "Código", "V": "Valor"},
        {"D1C": "25", "V": "3974687"},
        {"D1C": "26", "V": "9058931"}
    ]
    resp_pop = MagicMock(status_code=200)
    resp_pop.json.return_value = [{"D1C": "Código", "D3C": "Ano", "V": "Valor"}]
    resp_pib = MagicMock(status_code=200)
    resp_pib.json.return_value = [
        {"D1C": "Código", "D3C": "Ano", "V": "Valor"},
        {"D1C": "25", "D3C": "2023", "V": "96947000"},
        {"D1C": "26", "D3C": "2023", "V": "245828000"}
    ]

    monkeypatch.setattr(
        atualizar_ibge.requests.Session,
        "get",
        MagicMock(side_effect=[resp_censo, resp_pop, resp_pib])
    )

    atualizar_ibge.atualizar_dados_ibge_ufs.fn(ano_inicial=2023, output_csv=str(csv_ufs))

    assert csv_ufs.exists()
    with open(csv_ufs, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert len(rows) == 2
    pb = next(r for r in rows if r["UF"] == "PB")
    assert int(pb["PIB_Reais"]) == 96947000 * 1000


def test_atualizar_dados_ibge_municipios_calculo_pib_per_capita(tmp_path, monkeypatch):
    """Testa a conversão de Mil Reais para Reais e o cálculo do PIB per capita municipal."""
    csv_mun = tmp_path / "dados_ibge_municipios.csv"

    resp_censo = MagicMock(status_code=200)
    resp_censo.json.return_value = [
        {"D1C": "Código", "V": "Valor"},
        {"D1C": "2507507", "V": "833932"},   # João Pessoa - PB
        {"D1C": "2611606", "V": "1488920"}   # Recife - PE
    ]
    resp_pop = MagicMock(status_code=200)
    resp_pop.json.return_value = [{"D1C": "Código", "D3C": "Ano", "V": "Valor"}]
    resp_pib = MagicMock(status_code=200)
    resp_pib.json.return_value = [
        {"D1C": "Código", "D1N": "Município", "D3C": "Ano", "V": "Valor"},
        {"D1C": "2507507", "D1N": "João Pessoa - PB", "D3C": "2023", "V": "28418202"},
        {"D1C": "2611606", "D1N": "Recife - PE", "D3C": "2023", "V": "66351621"}
    ]

    monkeypatch.setattr(
        atualizar_ibge.requests.Session,
        "get",
        MagicMock(side_effect=[resp_censo, resp_pop, resp_pib])
    )

    atualizar_ibge.atualizar_dados_ibge_municipios.fn(ano_inicial=2023, output_csv=str(csv_mun))

    assert csv_mun.exists()
    with open(csv_mun, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    assert len(rows) == 2
    jp = next(r for r in rows if r["Codigo_Municipio_IBGE"] == "2507507")
    assert jp["UF"] == "PB"
    assert jp["É Capital"] == "Sim"
    assert int(jp["PIB_Reais"]) == 28418202 * 1000
    assert float(jp["PIB_per_Capita_Reais"]) == pytest.approx(round((28418202 * 1000) / 833932, 2), rel=1e-4)


def test_integridade_base_ibge_municipios_real(dados_ibge_municipios_csv):
    """Valida se data/dados_ibge_municipios.csv cobre os 408 municípios de PB e PE."""
    rows_2023 = [r for r in dados_ibge_municipios_csv if r.get("Ano_PIB") == "2023"]
    assert len(rows_2023) == 408, "Devem existir exatamente 408 municípios (223 PB + 185 PE) no ano de referência 2023."

    for r in rows_2023:
        assert len(r["Codigo_Municipio_IBGE"]) == 7
        assert r["UF"] in ("PB", "PE")
        assert int(r["Populacao"]) > 0
        assert float(r["PIB_Reais"]) > 0
        assert float(r["PIB_per_Capita_Reais"]) > 0


# ==============================================================================
# 3. TESTES UNITÁRIOS E DE INTEGRAÇÃO DO MÓDULO: pncp_etl.py
# ==============================================================================

def test_limpar_descricao_objeto():
    sujo = "[Portal de Compras Públicas] -   Aquisição de\nmedicamentos\t hospitalares.  "
    assert pncp_etl.limpar_descricao_objeto(sujo) == "Aquisição de medicamentos hospitalares."


def test_format_cnpj():
    assert pncp_etl.format_cnpj("08778268000160") == "08.778.268/0001-60"


@pytest.mark.parametrize(
    "modalidade,modo_disputa,esperado",
    [
        ("Dispensa", "Não se aplica", "Compra Direta (Sem Disputa)"),
        ("Inexigibilidade", "Não se aplica", "Compra Direta (Sem Disputa)"),
        ("Pregão - Eletrônico", "Aberto", "Disputa Aberta (Com Disputa)"),
        ("Credenciamento", "Não se aplica", "Credenciamento"),
    ],
    ids=["dispensa_direta", "inexigibilidade_direta", "pregao_eletronico", "credenciamento"]
)
def test_classificar_tipo_compra(modalidade, modo_disputa, esperado):
    assert pncp_etl.classificar_tipo_compra(modalidade, modo_disputa) == esperado


@pytest.mark.parametrize(
    "objeto,unidade,esperado",
    [
        ("Aquisição de medicamentos e insumos odontológicos", "Fundo Municipal de Saúde", "Saúde"),
        ("Pavimentação em paralelepípedos de vias urbanas", "Secretaria de Infraestrutura", "Obras e Infraestrutura"),
        ("Licenciamento de software em nuvem e computadores", "Diretoria de TI", "Informática (TI)"),
        ("Aquisição de gasolina e óleo diesel para ambulâncias", "Fundo Municipal de Saúde", "Transporte, Frota e Combustíveis"),
        ("Aquisição de notebook para atender as necessidades das escolas da rede de ensino", "Secretaria de Educação", "Informática (TI)"),
        ("Obra de reforma e ampliação da creche municipal", "Secretaria de Educação", "Obras e Infraestrutura"),
        ("Aquisição de ar condicionado para atender a Secretaria Municipal de Educação", "Secretaria de Educação", "Mobiliário, Climatização e Estrutura Predial"),
    ],
    ids=[
        "saude_medicamentos",
        "obras_pavimentacao",
        "ti_software",
        "frota_combustivel_ambulancia",
        "ti_notebook_escola",
        "obras_reforma_creche",
        "climatizacao_ar_condicionado",
    ]
)
def test_classificar_setor(objeto, unidade, esperado):
    assert pncp_etl.classificar_setor(objeto, unidade, "") == esperado


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (15000.50, "Informado"),
        (0, "Valor Zerado (R$ 0,00)"),
        (None, "Não Informado / Sigiloso"),
    ],
    ids=["valor_informado", "valor_zerado", "valor_sigiloso_nulo"]
)
def test_status_valor_transparencia(valor, esperado):
    assert pncp_etl.status_valor_transparencia(valor) == esperado


@pytest.mark.parametrize(
    "pib_pc,esperado",
    [
        (10000, "Até R$ 12,5 mil (Baixo)"),
        (14000, "De R$ 12,5 mil a R$ 15 mil (Médio-Baixo)"),
        (18000, "De R$ 15 mil a R$ 20 mil (Médio-Alto)"),
        (35000, "Acima de R$ 20 mil (Alto)"),
    ],
    ids=["faixa_baixo", "faixa_medio_baixo", "faixa_medio_alto", "faixa_alto"]
)
def test_classificar_faixa_pib_per_capita(pib_pc, esperado):
    assert pncp_etl.classificar_faixa_pib_per_capita(pib_pc) == esperado


def test_executar_etl_upsert_e_remocao_inativos(tmp_path):
    """Testa o pipeline completo de ETL em ambiente isolado (inserção, atualização e remoção de revogados)."""
    json_in = tmp_path / "brutos.json"
    csv_out = tmp_path / "editais.csv"
    futuro = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%dT23:59:59")

    # 1ª Execução: 2 editais ativos
    lote_1 = [
        {
            "numeroControlePNCP": "ID-1",
            "situacaoCompraNome": "Divulgada no PNCP",
            "dataAtualizacao": "2026-04-01T10:00:00",
            "dataPublicacaoPncp": "2026-04-01T09:00:00",
            "dataEncerramentoProposta": futuro,
            "modalidadeNome": "Pregão - Eletrônico",
            "modoDisputaNome": "Aberto",
            "objetoCompra": "[LICITANET] - Compra de computadores",
            "valorTotalEstimado": 50000.0,
            "orgaoEntidade": {"cnpj": "08778268000160", "razaoSocial": "Prefeitura de João Pessoa", "esferaId": "M", "poderId": "E"},
            "unidadeOrgao": {"codigoUnidade": "1", "nomeUnidade": "Sec TI", "municipioNome": "João Pessoa", "ufSigla": "PB", "codigoIbge": "2507507"}
        },
        {
            "numeroControlePNCP": "ID-2",
            "situacaoCompraNome": "Divulgada no PNCP",
            "dataAtualizacao": "2026-04-01T10:00:00",
            "dataPublicacaoPncp": "2026-04-01T09:00:00",
            "dataEncerramentoProposta": futuro,
            "modalidadeNome": "Dispensa",
            "modoDisputaNome": "Não se aplica",
            "objetoCompra": "Aquisição de merenda escolar",
            "valorTotalEstimado": 0.0,
            "orgaoEntidade": {"cnpj": "10565000000192", "razaoSocial": "Prefeitura do Recife", "esferaId": "M", "poderId": "E"},
            "unidadeOrgao": {"codigoUnidade": "2", "nomeUnidade": "Sec Educação", "municipioNome": "Recife", "ufSigla": "PE", "codigoIbge": "2611606"}
        }
    ]
    json_in.write_text(json.dumps(lote_1), encoding="utf-8")

    pncp_etl.executar_etl.fn(input_json=str(json_in), output_csv=str(csv_out))

    with open(csv_out, "r", encoding="utf-8-sig") as f:
        rows_1 = list(csv.DictReader(f, delimiter=";"))
    assert len(rows_1) == 2

    # 2ª Execução: ID-2 foi revogado no portal e ID-1 teve valor retificado
    lote_2 = [
        {**lote_1[0], "dataAtualizacao": "2026-04-02T12:00:00", "valorTotalEstimado": 75000.0},
        {**lote_1[1], "situacaoCompraNome": "Revogada"}
    ]
    json_in.write_text(json.dumps(lote_2), encoding="utf-8")

    pncp_etl.executar_etl.fn(input_json=str(json_in), output_csv=str(csv_out))

    with open(csv_out, "r", encoding="utf-8-sig") as f:
        rows_2 = list(csv.DictReader(f, delimiter=";"))

    assert len(rows_2) == 1, "O edital revogado (ID-2) deve ser removido do CSV."
    assert rows_2[0]["ID Contratação PNCP"] == "ID-1"
    assert float(rows_2[0]["Valor Estimado Numérico"]) == 75000.0
    assert rows_2[0]["Código IBGE do Município"] == "2507507"


# ==============================================================================
# 4. TESTES DE QUALIDADE DE DADOS PRÉ-BANCO (DATA QUALITY)
# ==============================================================================

def test_qualidade_esquema_colunas_obrigatorias(dados_editais_csv):
    """Verifica se todas as 40 colunas esperadas pelo modelo de dados estão presentes."""
    colunas_esperadas = [
        "UF", "Número do Edital", "Tipo de Instrumento", "ID Contratação PNCP",
        "Situação", "Modalidade de Contratação", "Modo de Disputa", "Tipo de Compra",
        "Amparo Legal", "SRP", "Fonte Orçamentária", "Órgão", "CNPJ do Órgão",
        "Nível de Governo (Esfera)", "Poder", "Unidade Compradora", "Localidade",
        "Município", "Código IBGE do Município", "É Capital", "População do Município",
        "PIB do Município", "PIB do Município Numérico", "PIB per Capita Municipal",
        "Faixa de PIB per Capita", "Setor / Área", "Motivo da Proposta",
        "Palavras-Chave do Objeto", "Objeto", "Valor Total Estimado",
        "Valor Estimado Numérico", "Status do Valor", "Ano Publicação",
        "Ano/Mês Publicação", "Data de Divulgação PNCP",
        "Data Início Recebimento Propostas", "Data Fim Recebimento Propostas",
        "Última Atualização", "Link PNCP", "Link Sistema Origem"
    ]
    assert len(dados_editais_csv) > 0, "O CSV de editais não pode estar vazio."
    assert list(dados_editais_csv[0].keys()) == colunas_esperadas


def test_qualidade_unicidade_chave_primaria(dados_editais_csv):
    """Garante que 'ID Contratação PNCP' não possui nulos nem duplicatas (Primary Key)."""
    ids = [r["ID Contratação PNCP"].strip() for r in dados_editais_csv]
    assert all(ids), "Nenhum edital pode ter 'ID Contratação PNCP' vazio."
    assert len(ids) == len(set(ids)), "Foram encontrados IDs de contratação duplicados no CSV!"


def test_qualidade_integridade_referencial_foreign_key_ibge(dados_editais_csv, dados_ibge_municipios_csv):
    """Garante que 100% dos editais possuem 'Código IBGE do Município' válido na tabela do IBGE."""
    codigos_validos = {
        r["Codigo_Municipio_IBGE"].strip()
        for r in dados_ibge_municipios_csv
        if r.get("Codigo_Municipio_IBGE")
    }
    orfaos = [
        (r["ID Contratação PNCP"], r["Município"], r["UF"], r.get("Código IBGE do Município"))
        for r in dados_editais_csv
        if r.get("Código IBGE do Município", "").strip() not in codigos_validos
    ]
    assert len(orfaos) == 0, f"Editais sem correspondência de Foreign Key no IBGE: {orfaos[:5]}"


def test_qualidade_tipagem_numerica_para_sql(dados_editais_csv):
    """Verifica se todas as colunas numéricas podem ser convertidas para FLOAT/INT sem erro no banco."""
    for r in dados_editais_csv:
        id_pncp = r["ID Contratação PNCP"]
        val_est = r.get("Valor Estimado Numérico", "")
        if val_est != "":
            assert float(val_est) >= 0.0, f"Valor negativo no edital {id_pncp}"

        assert int(r["População do Município"]) > 0, f"População inválida no edital {id_pncp}"
        assert float(r["PIB do Município Numérico"]) > 0.0, f"PIB inválido no edital {id_pncp}"
        assert float(r["PIB per Capita Municipal"]) > 0.0, f"PIB per capita inválido no edital {id_pncp}"


def test_qualidade_regras_negocio_deilas(dados_editais_csv):
    """Garante que apenas PB e PE estão na base, sem editais inativos e com dimensões preenchidas."""
    situacoes_proibidas = {"revogada", "anulada", "suspensa", "cancelada"}
    faixas_validas = {
        "Até R$ 12,5 mil (Baixo)",
        "De R$ 12,5 mil a R$ 15 mil (Médio-Baixo)",
        "De R$ 15 mil a R$ 20 mil (Médio-Alto)",
        "Acima de R$ 20 mil (Alto)"
    }
    status_validos = {"Informado", "Valor Zerado (R$ 0,00)", "Não Informado / Sigiloso"}

    for r in dados_editais_csv:
        assert r["UF"] in ("PB", "PE")
        assert r["Situação"].strip().lower() not in situacoes_proibidas
        assert r["É Capital"] in ("Sim", "Não")
        assert r["Tipo de Compra"].strip() != ""
        assert r["Nível de Governo (Esfera)"].strip() != ""
        assert r["Poder"].strip() != ""
        assert r["Setor / Área"].strip() != ""
        assert r["Status do Valor"] in status_validos
        assert r["Faixa de PIB per Capita"] in faixas_validas


def test_orquestracao_prefect_flows_e_tasks():
    """Garante que os módulos do pipeline estão devidamente decorados com @flow e @task do Prefect."""
    from prefect.flows import Flow
    from prefect.tasks import Task

    assert isinstance(download_pncp.baixar_dados_brutos, Task)
    assert isinstance(download_pncp.flow_extracao_pncp, Flow)

    assert isinstance(atualizar_ibge.atualizar_dados_ibge_ufs, Task)
    assert isinstance(atualizar_ibge.atualizar_dados_ibge_municipios, Task)
    assert isinstance(atualizar_ibge.atualizar_tudo, Flow)

    assert isinstance(pncp_etl.executar_etl, Task)
    assert isinstance(pncp_etl.flow_etl_pncp, Flow)


def test_sistema_de_logs_persistente():
    """Verifica se os módulos geram e registram eventos estruturados em logs/pipeline.log."""
    caminho_log = os.path.join("logs", "pipeline.log")
    pncp_etl.logger.info("Validação de teste automatizado do sistema de logs.")
    assert os.path.exists(caminho_log), "O arquivo logs/pipeline.log deve ser criado automaticamente."
    with open(caminho_log, "r", encoding="utf-8") as f:
        conteudo = f.read()
    assert "pncp_etl" in conteudo
    assert "INFO" in conteudo


