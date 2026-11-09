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

def classificar_setor(objeto: str, unidade: str = "", orgao: str = "") -> str:
    """
    Classifica nas áreas temáticas divididas por tipo de demanda e atuação pública.
    Evita falsos positivos como 'Sistema de Registro de Preços' ou 'Rede Municipal'.
    """
    texto = remover_acentos(f"{objeto} {unidade} {orgao}")

    # 1. Saúde
    if re.search(r"\b(saude|medic|remedio|hospit|farmac|clinic|enferm|upa|fms|sus|samu|ubs|caps|odontol|vacin|leito|cirurg|laborat|exame|biomedic|fisioterap|psicolog|nutricion|seringa|dieta enteral|dietas enterais|formula lactea|formulas lacteas|hemodialise|ortoped|oftalmol|ambulanc)", texto):
        return "Saúde"

    # 2. Educação
    if re.search(r"\b(educa|escol|colegio|ensino|creche|merenda|pedagog|aluno|profess|didatico|fnde|livro|fardamento|universidad|estudant)", texto):
        return "Educação"

    # 3. Obras e Infraestrutura
    if re.search(r"\b(obra|paviment|asfalt|reforma|constru|engenharia|drenagem|calcamento|edifica|ponte|praca|iluminacao|luminaria|luz publica|urbanizacao|saneamento|terraplanagem|postes|materiais eletricos|materiais hidraulicos|pre-moldados|cimento|brita|granito)", texto):
        return "Obras e Infraestrutura"

    # 4. Transporte, Frota e Combustíveis
    if re.search(r"\b(transporte|veiculo|combustivel|combustiveis|frota|onibus|gasolina|diesel|locacao de veiculo|pneu|automovel|caminhao|caminhoes|carroceria|passagens aereas|agenciamento de passagens|lubrificante|servicos mecanicos)", texto):
        return "Transporte, Frota e Combustíveis"

    # 5. Informática (TI)
    if re.search(r"\b(informatica|software|computador|computadores|notebook|notebooks|tecnologia da informacao|ti\b|internet|fibra optica|licenca de uso|licenciamento|datacenter|hardware|sistema informatizado|sistema de gestao|nuvem|cftv|biometrico|ged|impressora|impressoras|impressao corporativa|rede movel|voz e dados|telecomunicac)\b", texto):
        return "Informática (TI)"

    # 6. Segurança Pública e Vigilância
    if re.search(r"\b(seguranca|vigilancia|vigia|policia|militar|bombeiro|bombeiros|guarda-vidas|guarda municipal|defesa social|armada|desarmada|extintor|extintores|incendio|cjm|penitenciar|prisional|delegacia|drone|aeronave|aeronaves)", texto):
        return "Segurança Pública e Vigilância"

    # 7. Cultura, Esporte e Eventos
    if re.search(r"\b(cultura|cultural|culturais|artista|artistas|banda|bandas|musica|musical|musicais|musicos|show|shows|evento|eventos|festa|festividades|carnaval|sao joao|natalin|esporte|esportivo|esportivos|lazer|trofeu|trofeus|medalha|medalhas|playground|brinquedo|brinquedos|academia ao ar livre|academias ao ar livre|turismo|hospedagem|sonorizacao|palco)", texto):
        return "Cultura, Esporte e Eventos"

    # 8. Assistência Social e Cidadania
    if re.search(r"\b(assistencia social|desenvolvimento social|cesta basica|cestas basicas|vulnerabilidade|cras|creas|kit natalidade|funerari|urnas|familias carentes|sem fome|doacao|oculos de grau)", texto):
        return "Assistência Social e Cidadania"

    # 9. Meio Ambiente, Agro e Serviços Urbanos
    if re.search(r"\b(meio ambiente|ambiental|residuo|residuos|aterro|coleta de lixo|limpeza urbana|poda|paisagismo|jardinagem|muda|mudas|arborea|bioma|caatinga|icmbio|desassoreamento|recursos hidricos|poco|pocos|agropecuar|agricultura|rural|embrapa|racao|racoes|animal|animais|caes e gatos|veterinar|matadouro|abatedouro|escavadeira|retroescavadeira|maquinas pesadas|trator)", texto):
        return "Meio Ambiente, Agro e Serviços Urbanos"

    # 10. Alimentação, Copa e Suprimentos
    if re.search(r"\b(generos alimenticios|alimentacao|alimento|alimentos|refeicao|refeicoes|marmitex|quentinha|quentinhas|almoco|almocos|buffet|coffee break|coquetel|lanches|salgados|padaria|padarias|panificados|paes|bolos|cafe|agua mineral|agua adicionada|agua para consumo|garrafoes|glp|gas liquefeito|gas de cozinha|botijao|utensilios de cozinha|utensilos de cozinha|copa|cantina|aves e pescados|carnes|hortifruti)", texto):
        return "Alimentação, Copa e Suprimentos"

    # 11. Mobiliário, Climatização e Estrutura Predial
    if re.search(r"\b(mobiliario|mobiliarios|cadeiras|mesas|armarios|ar-condicionado|ar condicionado|climatizacao|refrigeracao|eletrodomesticos|material permanente|materiais permanentes|persianas|lampadas|vidros|marcenaria|bens imoveis|instalacoes)", texto):
        return "Mobiliário, Climatização e Estrutura Predial"

    # 12. Limpeza, Conservação e Expediente
    if re.search(r"\b(limpeza|higiene|conservacao|papel a4|papel oficio|papel sulfite|materiais de expediente|material de expediente|almoxarifado|copos|descartaveis|lixeiras|tecidos|roupa)", texto):
        return "Limpeza, Conservação e Expediente"

    # 13. Comunicação, Gráfica e Publicidade
    if re.search(r"\b(comunicacao|publicidade|marketing|servicos graficos|materiais graficos|sites e blogs|audio visual|audiovisual|divulgacao|publicacao de avisos|promocionais)", texto):
        return "Comunicação, Gráfica e Publicidade"

    # 14. Gestão Financeira, Patrimonial e Administrativa
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
    limpeza textual, classificação temática e por motivo, gerando o CSV consolidado em data/.
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
        objeto_limpo = limpar_descricao_objeto(item.get("objetoCompra", ""))
        val_estimado = item.get("valorTotalEstimado")

        # Classificação por motivo e extração de palavras-chave da proposta
        motivo_proposta, palavras_chave = classificar_motivo_e_palavras_chave(objeto_limpo)

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
            "É Capital": is_capital(municipio, uf_sigla),
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
            "Última Atualização": format_datetime(item.get("dataAtualizacao")),
            "Link PNCP": link_pncp,
            "Link Sistema Origem": link_origem_str
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
