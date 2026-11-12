import os
import json
import csv
import re
import logging
from logging.handlers import RotatingFileHandler
import unicodedata
from datetime import datetime
from typing import Any, Optional, Tuple
from dateutil import parser as date_parser
from prefect import flow, task


def obter_logger(nome: str = "pncp_etl") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger(nome)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh = RotatingFileHandler(
            os.path.join("logs", "pipeline.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
        logger.propagate = False
    return logger


logger = obter_logger()

def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).lower()

def limpar_descricao_objeto(texto: Any) -> str:
    """
    Higieniza a descrição do Objeto:
    - Remove tags de sistemas na frente do texto (ex: '[Portal de Compras Públicas] - ', '[LICITANET] - ').
    - Remove quebras de linha (\r, \n), tabulações e espaços invisíveis (\xa0).
    - Padroniza espaços múltiplos em um único espaço.
    """
    if not texto:
        return ""
    limpo = re.sub(r"^\s*\[[^\]]+\]\s*[-–—]?\s*", "", str(texto))
    limpo = re.sub(r"[\r\n\t\xa0]+", " ", limpo)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo

def format_cnpj(cnpj: Any) -> str:
    if not cnpj:
        return ""
    cnpj_str = "".join(filter(str.isdigit, str(cnpj)))
    if len(cnpj_str) == 14:
        return f"{cnpj_str[:2]}.{cnpj_str[2:5]}.{cnpj_str[5:8]}/{cnpj_str[8:12]}-{cnpj_str[12:]}"
    return str(cnpj)

def format_datetime(dt_str: Optional[str]) -> str:
    if not dt_str:
        return ""
    try:
        dt = date_parser.isoparse(dt_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt_str)

def format_currency(val: Any) -> str:
    if val is None or val == "":
        return ""
    try:
        val_float = float(val)
        return f"R$ {val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)

# 1ª Prioridade: O que está sendo adquirido (Item, Serviço ou Insumo específico)
_REGRAS_SETOR_ITEM = [
    ("Obras e Infraestrutura", r"\b(obra|paviment|asfalt|reforma|constru|engenharia|drenagem|calcamento|edifica|ponte|praca|iluminacao|luminaria|luz publica|urbanizacao|saneamento|terraplanagem|postes|materiais eletricos|materiais hidraulicos|pre-moldados|cimento|brita|granito)"),
    ("Informática (TI)", r"\b(informatica|software|computador|computadores|notebook|notebooks|tecnologia da informacao|ti\b|internet|fibra optica|licenca de uso|licenciamento|datacenter|hardware|sistema informatizado|sistema de gestao|nuvem|cftv|biometrico|ged|impressora|impressoras|impressao corporativa|rede movel|voz e dados|telecomunicac)\b"),
    ("Transporte, Frota e Combustíveis", r"\b(transporte|veiculo|combustivel|combustiveis|frota|onibus|gasolina|diesel|etanol|ambulanc|locacao de veiculo|pneu|automovel|caminhao|caminhoes|carroceria|passagens aereas|agenciamento de passagens|lubrificante|servicos mecanicos)"),
    ("Saúde", r"\b(medic|remedio|farmac|enferm|odontol|vacin|leito|cirurg|laborat|exame|biomedic|fisioterap|psicolog|nutricion|seringa|dieta enteral|dietas enterais|formula lactea|formulas lacteas|hemodialise|ortoped|oftalmol|oxigenio medicinal|insumos hospitalares|material medico)"),
    ("Educação", r"\b(merenda|pedagog|didatico|livro|fardamento|kit escolar|kits escolares)"),
    ("Segurança Pública e Vigilância", r"\b(seguranca|vigilancia|vigia|policia|militar|bombeiro|bombeiros|guarda-vidas|guarda municipal|defesa social|armada|desarmada|extintor|extintores|incendio|cjm|penitenciar|prisional|delegacia|drone|aeronave|aeronaves)"),
    ("Cultura, Esporte e Eventos", r"\b(cultura|cultural|culturais|artista|artistas|banda|bandas|musica|musical|musicais|musicos|show|shows|evento|eventos|festa|festividades|carnaval|sao joao|natalin|esporte|esportivo|esportivos|lazer|trofeu|trofeus|medalha|medalhas|playground|brinquedo|brinquedos|academia ao ar livre|academias ao ar livre|turismo|hospedagem|sonorizacao|palco)"),
    ("Assistência Social e Cidadania", r"\b(cesta basica|cestas basicas|vulnerabilidade|kit natalidade|funerari|urnas|familias carentes|sem fome|doacao|oculos de grau)"),
    ("Meio Ambiente, Agro e Serviços Urbanos", r"\b(meio ambiente|ambiental|residuo|residuos|aterro|coleta de lixo|limpeza urbana|poda|paisagismo|jardinagem|muda|mudas|arborea|bioma|caatinga|icmbio|desassoreamento|recursos hidricos|poco|pocos|agropecuar|agricultura|rural|embrapa|racao|racoes|animal|animais|caes e gatos|veterinar|matadouro|abatedouro|escavadeira|retroescavadeira|maquinas pesadas|trator)"),
    ("Alimentação, Copa e Suprimentos", r"\b(generos alimenticios|alimentacao|alimento|alimentos|refeicao|refeicoes|marmitex|quentinha|quentinhas|almoco|almocos|buffet|coffee break|coquetel|lanches|salgados|padaria|padarias|panificados|paes|bolos|cafe|agua mineral|agua adicionada|agua para consumo|garrafoes|glp|gas liquefeito|gas de cozinha|botijao|utensilios de cozinha|utensilos de cozinha|copa|cantina|aves e pescados|carnes|hortifruti)"),
    ("Mobiliário, Climatização e Estrutura Predial", r"\b(mobiliario|mobiliarios|cadeiras|mesas|armarios|ar-condicionado|ar condicionado|climatizacao|refrigeracao|eletrodomesticos|material permanente|materiais permanentes|persianas|lampadas|vidros|marcenaria|bens imoveis|instalacoes)"),
    ("Limpeza, Conservação e Expediente", r"\b(limpeza|higiene|conservacao|papel a4|papel oficio|papel sulfite|materiais de expediente|material de expediente|almoxarifado|copos|descartaveis|lixeiras|tecidos|roupa)"),
    ("Comunicação, Gráfica e Publicidade", r"\b(comunicacao|publicidade|marketing|servicos graficos|materiais graficos|sites e blogs|audio visual|audiovisual|divulgacao|publicacao de avisos|promocionais)"),
]

# 2ª Prioridade (Fallback): Palavras genéricas de secretaria/órgão/local quando o item é genérico
_REGRAS_SETOR_DESTINO = [
    ("Saúde", r"\b(saude|hospit|clinic|upa|fms|sus|samu|ubs|caps)"),
    ("Educação", r"\b(educa|escol|colegio|ensino|creche|aluno|profess|fnde|universidad|estudant)"),
    ("Assistência Social e Cidadania", r"\b(assistencia social|desenvolvimento social|cras|creas)"),
]


def _buscar_regras(texto: str, regras: list) -> Optional[str]:
    texto_norm = remover_acentos(texto)
    for setor, padrao in regras:
        if re.search(padrao, texto_norm):
            return setor
    return None


def classificar_setor(objeto: str, unidade: str = "", orgao: str = "") -> str:
    """
    Classifica nas áreas temáticas priorizando o que está sendo adquirido (objeto).
    Palavras genéricas de secretaria/local (ex: 'Secretaria de Educação', 'Hospital')
    só são usadas como fallback quando o objeto não especifica o item/serviço.
    """
    # 1. Verifica o item/serviço específico no Objeto
    setor_item = _buscar_regras(objeto, _REGRAS_SETOR_ITEM)
    if setor_item:
        return setor_item

    # 2. Fallback: verifica menção de destino/pasta no Objeto ou na Unidade/Órgão
    setor_destino = _buscar_regras(f"{objeto} {unidade} {orgao}", _REGRAS_SETOR_DESTINO)
    if setor_destino:
        return setor_destino

    # 3. Fallback final: verifica se a Unidade/Órgão indica algum setor específico
    setor_unidade = _buscar_regras(f"{unidade} {orgao}", _REGRAS_SETOR_ITEM)
    if setor_unidade:
        return setor_unidade

    return "Gestão Financeira, Patrimonial e Administrativa"

def classificar_motivo_e_palavras_chave(objeto: str) -> Tuple[str, str]:
    """
    Analisa a descrição limpa da proposta (Objeto), extrai as palavras-chave
    e classifica o motivo/natureza da proposta sem falsos positivos.
    """
    t = remover_acentos(objeto)

    regras = [
        (
            "Obras e Engenharia",
            r"\b(obra|obras|pavimentacao|asfalto|asfaltica|reforma|construcao|ampliacao|engenharia|drenagem|calcamento|edificacao|ponte|praca|urbanizacao|terraplanagem|saneamento|recapeamento|reestruturacao)\b"
        ),
        (
            "Credenciamento de Serviços / Profissionais",
            r"\b(credenciamento|credenciar|chamamento publico)\b"
        ),
        (
            "Locação de Bens, Veículos e Estruturas",
            r"\b(locacao|aluguel|locar|horas maquinas)\b"
        ),
        (
            "Eventos, Cultura e Festividades",
            r"\b(evento|eventos|show|shows|festividade|festividades|palco|sonorizacao|decoracao natalina|iluminacao natalina|carnaval|sao joao|festa|artistico|artisticos)\b"
        ),
        (
            "Transporte e Logística",
            r"\b(transporte escolar|transporte de estudantes|transporte de alunos|transporte de pacientes|frete|transporte rodoviario)\b"
        ),
        (
            "Tecnologia da Informação e Sistemas",
            r"\b(software|sistema informatizado|sistema de gestao|solucao integrada|licenca|licencas|licenciamento|informatica|computador|computadores|notebook|notebooks|internet|fibra optica|datacenter|cftv|biometrico|ged)\b"
        ),
        (
            "Concessão, Permissão de Uso e Alienação",
            r"\b(concessao|permissao de uso|cessao de uso|alienacao|leilao)\b"
        ),
        (
            "Aquisição de Bens, Materiais e Insumos",
            r"\b(aquisicao|fornecimento|compra de|materiais|material|suprimentos|insumos|instrumentais|equipamentos|medicamentos|merenda|combustivel|combustiveis|gasolina|diesel|glp|botijao|agua mineral|generos alimenticios|fardamento|uniforme|mobiliario|eletrodomesticos|utensilios|pecas|pneus|racoes)\b"
        ),
        (
            "Prestação de Serviços Especializados",
            r"\b(prestacao de servico|prestacao de servicos|prestacao dos servicos|servicos de|servico de|servico continuo|servicos graficos|manutencao|vigilancia|vigia|limpeza|assessoria|consultoria|coleta|residuos|residuo|exames|servicos medicos|fisioterapeuticos|seguro|publicidade|comunicacao|impressao|dedetizacao|capacitacao|treinamento|concurso|folha de pagamento|instituicao financeira|regularizacao fundiaria)\b"
        )
    ]

    for cat, pattern in regras:
        matches = re.findall(pattern, t)
        if matches:
            kw_unicas = sorted(list(set(matches)))
            return cat, ", ".join(kw_unicas)

    return "Outros / Diversos", "não identificada"

def classificar_tipo_compra(modalidade_nome: str, modo_disputa_nome: str = "") -> str:
    """Classifica em Compra Direta (Sem Disputa), Disputa Aberta ou Credenciamento."""
    mod = remover_acentos(modalidade_nome)
    disp = remover_acentos(modo_disputa_nome)
    if "dispensa" in mod or "inexigibilidade" in mod or "direta" in mod:
        return "Compra Direta (Sem Disputa)"
    if "pregao" in mod or "concorrencia" in mod or "leilao" in mod or "dialogo" in mod:
        return "Disputa Aberta (Com Disputa)"
    if "credenciamento" in mod or "chamamento" in mod:
        return "Credenciamento"
    if "aberto" in disp or "fechado" in disp:
        return "Disputa Aberta (Com Disputa)"
    return "Outros"

def mapear_esfera(esfera_id: Any) -> str:
    m = {"M": "Municipal (Prefeitura)", "E": "Estadual", "F": "Federal", "D": "Distrital"}
    return m.get(str(esfera_id).upper(), "Não informada")

def mapear_poder(poder_id: Any) -> str:
    m = {"E": "Executivo", "L": "Legislativo", "J": "Judiciário"}
    return m.get(str(poder_id).upper(), "Não informado")

def is_capital(municipio: str, uf: str) -> str:
    m = remover_acentos(municipio).strip()
    u = str(uf).upper().strip()
    if (u == "PB" and "joao pessoa" in m) or (u == "PE" and "recife" in m):
        return "Sim"
    return "Não"

def status_valor_transparencia(valor: Any) -> str:
    if valor is None or valor == "":
        return "Não Informado / Sigiloso"
    try:
        val_float = float(valor)
        return "Valor Zerado (R$ 0,00)" if val_float <= 0.0 else "Informado"
    except Exception:
        return "Não Informado / Sigiloso"

def classificar_faixa_pib_per_capita(pib_per_capita: Any) -> str:
    if pib_per_capita is None or pib_per_capita == "":
        return "Não Informado"
    try:
        val = float(pib_per_capita)
        if val <= 12500.0:
            return "Até R$ 12,5 mil (Baixo)"
        elif val <= 15000.0:
            return "De R$ 12,5 mil a R$ 15 mil (Médio-Baixo)"
        elif val <= 20000.0:
            return "De R$ 15 mil a R$ 20 mil (Médio-Alto)"
        else:
            return "Acima de R$ 20 mil (Alto)"
    except Exception:
        return "Não Informado"

def carregar_dados_ibge_municipios(
    caminho_csv: str = os.path.join("data", "dados_ibge_municipios.csv")
) -> dict:
    """
    Carrega data/dados_ibge_municipios.csv e retorna um dicionário mapeando tanto
    o código IBGE de 7 dígitos quanto a tupla (municipio_normalizado, uf) para os
    dados socioeconômicos mais recentes do IBGE.
    """
    mapa = {"por_codigo": {}, "por_nome": {}}
    if not os.path.exists(caminho_csv):
        return mapa
    try:
        with open(caminho_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            # Ordenar por ano para que a última iteração guarde o ano mais recente (ex: 2023)
            linhas = sorted(list(reader), key=lambda r: int(r.get("Ano_PIB", 0) or 0))
            for r in linhas:
                cod_ibge = str(r.get("Codigo_Municipio_IBGE", "")).strip()
                m_norm = remover_acentos(r.get("Municipio", ""))
                uf = r.get("UF", "").strip().upper()
                info = {
                    "Codigo_IBGE": cod_ibge,
                    "Populacao": r.get("Populacao", ""),
                    "PIB_Reais": r.get("PIB_Reais", ""),
                    "PIB_Formatado": r.get("PIB_Formatado", ""),
                    "PIB_per_Capita_Reais": r.get("PIB_per_Capita_Reais", ""),
                    "Faixa_PIB_per_Capita": classificar_faixa_pib_per_capita(r.get("PIB_per_Capita_Reais", ""))
                }
                if cod_ibge:
                    mapa["por_codigo"][cod_ibge] = info
                if m_norm and uf:
                    mapa["por_nome"][(m_norm, uf)] = info
    except Exception as e:
        logger.warning(f"Não foi possível carregar dados IBGE de municípios: {e}")
    return mapa

def obter_dados_ibge(mapa_ibge: dict, codigo_ibge: Any, municipio: str, uf: str) -> dict:
    """
    Prioriza o cruzamento pelo código IBGE oficial (7 dígitos) vindo da API do PNCP
    e utiliza o par (município normalizado, UF) como fallback.
    """
    cod_str = str(codigo_ibge or "").strip()
    if cod_str and cod_str in mapa_ibge.get("por_codigo", {}):
        return mapa_ibge["por_codigo"][cod_str]
    m_norm = remover_acentos(municipio or "")
    uf_norm = (uf or "").strip().upper()
    return mapa_ibge.get("por_nome", {}).get((m_norm, uf_norm), {})

def is_recebendo_proposta(item: dict, ref_dt: datetime) -> bool:
    situacao = str(item.get("situacaoCompraNome", "")).strip().lower()
    if situacao in ["revogada", "anulada", "suspensa", "cancelada"]:
        return False

    dt_enc_str = item.get("dataEncerramentoProposta")
    if dt_enc_str:
        try:
            dt_enc = date_parser.isoparse(dt_enc_str)
            if dt_enc.tzinfo and ref_dt.tzinfo is None:
                ref_dt_norm = ref_dt.astimezone(dt_enc.tzinfo)
            else:
                ref_dt_norm = ref_dt.replace(tzinfo=None)
                dt_enc = dt_enc.replace(tzinfo=None)
            if dt_enc < ref_dt_norm:
                return False
        except Exception:
            pass
    return True

@task(name="Transformar e Enriquecer Editais PNCP", log_prints=True)
def executar_etl(
    input_json: str = os.path.join("data", "dados_brutos_pncp.json"),
    output_csv: str = os.path.join("data", "editais_pncp_PB_PE.csv")
):
    """
    Fase de Transformação e Carga Incremental e Idempotente (Transform & Load):
    Lê os registros já processados em data/editais_pncp_PB_PE.csv, processa o ETL
    apenas para editais inéditos ou atualizados (Upsert por 'ID Contratação PNCP')
    e mantém os registros inalterados sem reprocessamento desnecessário.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)

    logger.info("=" * 70)
    logger.info("   PNCP - ETL INCREMENTAL E IDEMPOTENTE (UPSERT)")
    logger.info(f"   Origem: {input_json} -> Destino: {output_csv}")
    logger.info("=" * 70)

    try:
        with open(input_json, "r", encoding="utf-8") as f:
            itens_brutos = json.load(f)
    except FileNotFoundError:
        logger.error(f"Arquivo '{input_json}' não encontrado. Execute o 'download_pncp.py' primeiro.")
        return

    # 1. Carregar base CSV já existente para evitar reprocessamento de editais inalterados
    registros_por_id = {}
    if os.path.exists(output_csv):
        try:
            with open(output_csv, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=";")
                for r in reader:
                    chave = r.get("ID Contratação PNCP", "").strip()
                    if chave:
                        registros_por_id[chave] = r
        except Exception:
            registros_por_id = {}

    logger.info(f"Total de registros brutos lidos: {len(itens_brutos)}")
    logger.info(f"Total de editais já existentes no CSV: {len(registros_por_id)}")

    dados_ibge_mun = carregar_dados_ibge_municipios()
    logger.info(f"Total de municípios carregados da base do IBGE: {len(dados_ibge_mun.get('por_codigo', {}))}")

    # Enriquecer registros já existentes e atualizar classificação de Setor/Área se necessário
    enriquecidos_ibge = 0
    for chave, r in registros_por_id.items():
        novo_setor = classificar_setor(
            r.get("Objeto", ""),
            r.get("Unidade Compradora", ""),
            r.get("Órgão", "")
        )
        mudou_setor = r.get("Setor / Área") != novo_setor
        if mudou_setor:
            r["Setor / Área"] = novo_setor

        if (
            mudou_setor
            or "PIB do Município" not in r or not r.get("PIB do Município")
            or "Código IBGE do Município" not in r or not r.get("Código IBGE do Município")
            or "Faixa de PIB per Capita" not in r or not r.get("Faixa de PIB per Capita")
        ):
            ibge_info = obter_dados_ibge(
                dados_ibge_mun,
                r.get("Código IBGE do Município", ""),
                r.get("Município", ""),
                r.get("UF", "")
            )
            r["Código IBGE do Município"] = ibge_info.get("Codigo_IBGE", "")
            r["População do Município"] = ibge_info.get("Populacao", "")
            r["PIB do Município"] = ibge_info.get("PIB_Formatado", "")
            r["PIB do Município Numérico"] = ibge_info.get("PIB_Reais", "")
            r["PIB per Capita Municipal"] = ibge_info.get("PIB_per_Capita_Reais", "")
            r["Faixa de PIB per Capita"] = ibge_info.get("Faixa_PIB_per_Capita", "")
            enriquecidos_ibge += 1

    if enriquecidos_ibge > 0:
        logger.info(f"Editais existentes enriquecidos com Código IBGE, PIB e Faixa de Renda: {enriquecidos_ibge}")

    now_dt = datetime.now()
    mantidos_sem_reprocessar = 0
    novos_inseridos = 0
    atualizados = 0
    removidos_inativos = 0

    for item in itens_brutos:
        num_controle = str(item.get("numeroControlePNCP") or "").strip()
        if not num_controle:
            continue

        situacao = str(item.get("situacaoCompraNome", "")).strip().lower()
        if situacao in ["revogada", "anulada", "suspensa", "cancelada"]:
            if num_controle in registros_por_id:
                del registros_por_id[num_controle]
                removidos_inativos += 1
            continue

        ultima_atualizacao_fmt = format_datetime(item.get("dataAtualizacao"))

        # Se o edital já está no CSV e não sofreu alteração no portal, pula o reprocessamento do ETL
        if num_controle in registros_por_id:
            if registros_por_id[num_controle].get("Última Atualização") == ultima_atualizacao_fmt:
                mantidos_sem_reprocessar += 1
                continue
            eh_atualizacao = True
        else:
            if not is_recebendo_proposta(item, ref_dt=now_dt):
                continue
            eh_atualizacao = False

        uf_consulta = item.get("_uf_consulta", "")
        orgao = item.get("orgaoEntidade") or {}
        cnpj = orgao.get("cnpj", "")
        razao_social = orgao.get("razaoSocial", "")
        cnpj_fmt = format_cnpj(cnpj)
        orgao_str = f"{cnpj_fmt} - {razao_social}" if cnpj_fmt else razao_social

        unidade = item.get("unidadeOrgao") or {}
        unidade_cod = unidade.get("codigoUnidade", "")
        unidade_nome = unidade.get("nomeUnidade", "")
        unidade_str = f"{unidade_cod} - {unidade_nome}" if unidade_cod else unidade_nome

        municipio = unidade.get("municipioNome", "")
        uf_sigla = unidade.get("ufSigla") or uf_consulta
        localidade = f"{municipio}/{uf_sigla}" if municipio else uf_sigla
        codigo_ibge_api = unidade.get("codigoIbge")
        ibge_info = obter_dados_ibge(dados_ibge_mun, codigo_ibge_api, municipio, uf_sigla)
        cod_ibge_final = ibge_info.get("Codigo_IBGE") or (str(codigo_ibge_api).strip() if codigo_ibge_api else "")

        modalidade = item.get("modalidadeNome", "")
        modo_disputa = item.get("modoDisputaNome", "")
        objeto_limpo = limpar_descricao_objeto(item.get("objetoCompra", ""))
        val_estimado = item.get("valorTotalEstimado")

        # Classificação por motivo e extração de palavras-chave da proposta
        motivo_proposta, palavras_chave = classificar_motivo_e_palavras_chave(objeto_limpo)

        ano = item.get("anoCompra")
        seq = item.get("sequencialCompra")
        link_pncp = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if (cnpj and ano and seq) else ""

        dt_pub_str = item.get("dataPublicacaoPncp")
        ano_mes_pub = ""
        ano_pub = ""
        if dt_pub_str:
            try:
                dt_p = date_parser.isoparse(dt_pub_str)
                ano_mes_pub = dt_p.strftime("%Y-%m")
                ano_pub = dt_p.strftime("%Y")
            except Exception:
                pass

        amparo = item.get("amparoLegal") or {}
        amparo_str = amparo.get("nome") or amparo.get("descricao") or ""

        fontes = item.get("fontesOrcamentarias") or []
        fontes_nomes = []
        for f in fontes:
            if isinstance(f, dict):
                fontes_nomes.append(f.get("nome") or f.get("descricao") or str(f))
            elif f:
                fontes_nomes.append(str(f))
        fontes_str = ", ".join(fontes_nomes) if fontes_nomes else "Não informada"

        link_origem = str(item.get("linkSistemaOrigem") or "").strip()
        link_origem_str = link_origem if link_origem else "Publicado diretamente no PNCP"

        row = {
            "UF": uf_sigla,
            "Número do Edital": item.get("numeroCompra", ""),
            "Tipo de Instrumento": item.get("tipoInstrumentoConvocatorioNome", ""),
            "ID Contratação PNCP": num_controle,
            "Situação": item.get("situacaoCompraNome", ""),
            "Modalidade de Contratação": modalidade,
            "Modo de Disputa": modo_disputa,
            "Tipo de Compra": classificar_tipo_compra(modalidade, modo_disputa),
            "Amparo Legal": amparo_str,
            "SRP": "Sim" if item.get("srp") else "Não",
            "Fonte Orçamentária": fontes_str,
            "Órgão": orgao_str,
            "CNPJ do Órgão": cnpj_fmt,
            "Nível de Governo (Esfera)": mapear_esfera(orgao.get("esferaId")),
            "Poder": mapear_poder(orgao.get("poderId")),
            "Unidade Compradora": unidade_str,
            "Localidade": localidade,
            "Município": municipio,
            "Código IBGE do Município": cod_ibge_final,
            "É Capital": is_capital(municipio, uf_sigla),
            "População do Município": ibge_info.get("Populacao", ""),
            "PIB do Município": ibge_info.get("PIB_Formatado", ""),
            "PIB do Município Numérico": ibge_info.get("PIB_Reais", ""),
            "PIB per Capita Municipal": ibge_info.get("PIB_per_Capita_Reais", ""),
            "Faixa de PIB per Capita": ibge_info.get("Faixa_PIB_per_Capita", ""),
            "Setor / Área": classificar_setor(objeto_limpo, unidade_nome, razao_social),
            "Motivo da Proposta": motivo_proposta,
            "Palavras-Chave do Objeto": palavras_chave,
            "Objeto": objeto_limpo,
            "Valor Total Estimado": format_currency(val_estimado),
            "Valor Estimado Numérico": val_estimado if val_estimado is not None else "",
            "Status do Valor": status_valor_transparencia(val_estimado),
            "Ano Publicação": ano_pub,
            "Ano/Mês Publicação": ano_mes_pub,
            "Data de Divulgação PNCP": format_datetime(dt_pub_str),
            "Data Início Recebimento Propostas": format_datetime(item.get("dataAberturaProposta")),
            "Data Fim Recebimento Propostas": format_datetime(item.get("dataEncerramentoProposta")),
            "Última Atualização": ultima_atualizacao_fmt,
            "Link PNCP": link_pncp,
            "Link Sistema Origem": link_origem_str
        }
        registros_por_id[num_controle] = row
        if eh_atualizacao:
            atualizados += 1
        else:
            novos_inseridos += 1

    linhas_finais = sorted(
        registros_por_id.values(),
        key=lambda r: (r.get("UF", ""), r.get("ID Contratação PNCP", ""))
    )

    if linhas_finais:
        houve_mudanca = (
            novos_inseridos > 0 
            or atualizados > 0 
            or removidos_inativos > 0 
            or enriquecidos_ibge > 0 
            or not os.path.exists(output_csv)
        )
        if houve_mudanca:
            fieldnames = [
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
            with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
                writer.writeheader()
                writer.writerows(linhas_finais)

        logger.info("=" * 70)
        logger.info("   ETL Incremental Concluído!")
        logger.info(f"   - Editais mantidos (sem reprocessar): {mantidos_sem_reprocessar}")
        logger.info(f"   - Novos editais inseridos:            {novos_inseridos}")
        logger.info(f"   - Editais atualizados (retificados):  {atualizados}")
        logger.info(f"   - Editais revogados/suspensos remov.: {removidos_inativos}")
        logger.info(f"   - Total único consolidado no CSV:     {len(linhas_finais)}")
        logger.info(f"   Arquivo salvo: {output_csv}")
        logger.info("=" * 70)
    else:
        logger.warning("Nenhum registro aprovado no filtro.")


@flow(name="Flow 2 - Transformação e Limpeza ETL PNCP", log_prints=True)
def flow_etl_pncp():
    executar_etl()


if __name__ == "__main__":
    flow_etl_pncp()
