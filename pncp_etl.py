import os
import json
import csv
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional, Tuple
from dateutil import parser as date_parser

def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).lower()

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

def classificar_setor(objeto: str, unidade: str = "", orgao: str = "") -> str:
    """Classifica nas áreas do projeto: Saúde, Educação, Obras, Transporte, TI e Outros."""
    texto = remover_acentos(f"{objeto} {unidade} {orgao}")
    if re.search(r"\b(saude|medic|remedio|hospit|farmac|clinic|enferm|upa|fms|sus|odontol|vacin|leito|cirurg|laborat|exame|biomedic)", texto):
        return "Saúde"
    if re.search(r"\b(educa|escol|ensino|creche|merenda|pedagog|aluno|profess|didatico|fnde|livro|fardamento)", texto):
        return "Educação"
    if re.search(r"\b(obra|paviment|asfalt|reforma|constru|engenharia|drenagem|calcamento|edifica|ponte|praca|iluminacao|luz publica)", texto):
        return "Obras"
    if re.search(r"\b(transporte|veiculo|combustivel|frota|onibus|gasolina|diesel|locacao de veiculo|pneu|automovel|ambulancia)", texto):
        return "Transporte"
    if re.search(r"\b(informatica|software|computador|tecnologia|ti\b|internet|rede|licenca de software|datacenter|hardware|sistema|nuvem)", texto):
        return "Informática (TI)"
    return "Outros"

def classificar_motivo_e_palavras_chave(objeto: str) -> Tuple[str, str]:
    """
    Analisa o texto da proposta (Objeto), extrai as palavras-chave
    e classifica o motivo/natureza da proposta:
    - Aquisição de Bens e Materiais
    - Obras e Engenharia
    - Prestação de Serviços Contínuos / Especializados
    - Locação de Bens e Veículos
    - Credenciamento de Serviços / Profissionais
    - Tecnologia da Informação e Sistemas
    - Transporte e Logística
    - Eventos, Cultura e Festividades
    - Outros / Diversos
    """
    t = remover_acentos(objeto)

    regras = [
        ("Obras e Engenharia", r"\b(obra|obras|pavimentacao|asfalto|asfaltica|reforma|construcao|engenharia|drenagem|calcamento|edificacao|ponte|praca)\b"),
        ("Locação de Bens e Veículos", r"\b(locacao|aluguel|locar)\b"),
        ("Credenciamento de Serviços / Profissionais", r"\b(credenciamento|chamamento publico)\b"),
        ("Eventos, Cultura e Festividades", r"\b(evento|eventos|show|shows|festividade|festividades|palco|som|decoracao natalina|iluminacao natalina|carnaval|sao joao)\b"),
        ("Tecnologia da Informação e Sistemas", r"\b(software|sistema|sistemas|licenca|licenciamento|informatica|computador|computadores|internet|link de dados|datacenter)\b"),
        ("Transporte e Logística", r"\b(transporte escolar|transporte de estudantes|transporte de alunos|transporte de pacientes|frete|frota|onibus)\b"),
        ("Prestação de Serviços Contínuos / Especializados", r"\b(prestacao de servico|prestacao de servicos|servicos de|servico de|manutencao|vigilancia|limpeza|assessoria|consultoria|coleta)\b"),
        ("Aquisição de Bens e Materiais", r"\b(aquisicao|fornecimento|compra de|materiais|material|suprimentos|equipamentos|medicamentos|merenda|combustivel|combustiveis)\b")
    ]

    motivo = "Outros / Diversos"
    kw_encontradas = []

    for cat, pattern in regras:
        matches = re.findall(pattern, t)
        if matches:
            motivo = cat
            kw_encontradas = sorted(list(set(matches)))
            break

    if not kw_encontradas:
        generic_matches = re.findall(r"\b(gestao|capacitacao|treinamento|seguranca|apoio|uniforme|alimentacao)\b", t)
        if generic_matches:
            kw_encontradas = sorted(list(set(generic_matches)))

    kw_str = ", ".join(kw_encontradas) if kw_encontradas else "não identificada"
    return motivo, kw_str

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

def executar_etl(
    input_json: str = os.path.join("data", "dados_brutos_pncp.json"),
    output_csv: str = os.path.join("data", "editais_pncp_PB_PE.csv")
):
    """
    Fase de Transformação e Carga (Transform & Load):
    Lê o JSON com os dados brutos da pasta data/, aplica regras de negócio,
    limpeza, classificação temática e por motivo, gerando o CSV consolidado em data/.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)

    print("=" * 70)
    print("   PNCP - ETL: TRANSFORMAÇÃO E CARGA DOS DADOS")
    print(f"   Origem: {input_json} -> Destino: {output_csv}")
    print("=" * 70)

    try:
        with open(input_json, "r", encoding="utf-8") as f:
            itens_brutos = json.load(f)
    except FileNotFoundError:
        print(f"Erro: Arquivo '{input_json}' não encontrado. Execute o 'download_pncp.py' primeiro.")
        return

    print(f"\nTotal de registros brutos lidos: {len(itens_brutos)}")
    now_dt = datetime.now()
    linhas_tratadas = []

    for item in itens_brutos:
        if not is_recebendo_proposta(item, ref_dt=now_dt):
            continue

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

        modalidade = item.get("modalidadeNome", "")
        modo_disputa = item.get("modoDisputaNome", "")
        objeto = item.get("objetoCompra", "")
        val_estimado = item.get("valorTotalEstimado")

        # Classificação por motivo e extração de palavras-chave da proposta
        motivo_proposta, palavras_chave = classificar_motivo_e_palavras_chave(objeto)

        ano = item.get("anoCompra")
        seq = item.get("sequencialCompra")
        num_controle = item.get("numeroControlePNCP", "")
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
        fontes_str = ", ".join([str(f) for f in fontes]) if fontes else "Não informada"

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
            "É Capital": is_capital(municipio, uf_sigla),
            "Setor / Área": classificar_setor(objeto, unidade_nome, razao_social),
            "Motivo da Proposta": motivo_proposta,
            "Palavras-Chave do Objeto": palavras_chave,
            "Objeto": objeto,
            "Valor Total Estimado": format_currency(val_estimado),
            "Valor Estimado Numérico": val_estimado if val_estimado is not None else "",
            "Status do Valor": status_valor_transparencia(val_estimado),
            "Ano Publicação": ano_pub,
            "Ano/Mês Publicação": ano_mes_pub,
            "Data de Divulgação PNCP": format_datetime(dt_pub_str),
            "Data Início Recebimento Propostas": format_datetime(item.get("dataAberturaProposta")),
            "Data Fim Recebimento Propostas": format_datetime(item.get("dataEncerramentoProposta")),
            "Última Atualização": format_datetime(item.get("dataAtualizacao")),
            "Link PNCP": link_pncp,
            "Link Sistema Origem": item.get("linkSistemaOrigem", "")
        }
        linhas_tratadas.append(row)

    if linhas_tratadas:
        fieldnames = list(linhas_tratadas[0].keys())
        with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(linhas_tratadas)

        print("\n" + "=" * 70)
        print(f"   ETL Concluído!")
        print(f"   Total de editais tratados e salvos: {len(linhas_tratadas)}")
        print(f"   Arquivo gerado: {output_csv}")
        print("=" * 70)
    else:
        print("\nNenhum registro aprovado no filtro.")

executar_etl()
