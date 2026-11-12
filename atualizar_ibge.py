import os
import csv
from datetime import datetime
import requests

METADATA_UFS = {
    "25": {"UF": "PB", "Nome_Estado": "Paraíba", "Regiao": "Nordeste", "Capital": "João Pessoa"},
    "26": {"UF": "PE", "Nome_Estado": "Pernambuco", "Regiao": "Nordeste", "Capital": "Recife"}
}

# Taxas de variação real em volume (%) divulgadas nos releases do Sistema de Contas Regionais
CRESCIMENTO_REAL_CONHECIDO = {
    ("PB", 2020): -3.0,
    ("PB", 2021): 3.9,
    ("PB", 2022): 5.6,
    ("PB", 2023): 3.0,
    ("PE", 2020): -3.2,
    ("PE", 2021): 3.8,
    ("PE", 2022): 3.2,
    ("PE", 2023): 2.4,
}

def atualizar_dados_ibge_ufs(
    ano_inicial: int = 2020,
    output_csv: str = os.path.join("data", "dados_ibge_ufs.csv")
):
    """
    Consulta a API oficial SIDRA do IBGE:
    - Tabela 5938: Produto Interno Bruto a preços correntes (Mil Reais)
    - Tabela 6579: Estimativas Anuais de População
    - Tabela 4709: População do Censo Demográfico 2022
    Verifica se o PIB do ano esperado (ano_atual - 2, ex: 2024 em 2026) já foi publicado
    e atualiza o arquivo data/dados_ibge_ufs.csv.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    ano_alvo = datetime.now().year - 2

    print("=" * 70)
    print("   IBGE SIDRA API - ATUALIZAÇÃO ANUAL DE PIB E POPULAÇÃO")
    print(f"   UFs: PB, PE | Série: {ano_inicial} até {ano_alvo} (Ano-Alvo da Edição Atual)")
    print("=" * 70)

    # Verifica se o ano-alvo já foi gravado anteriormente no CSV para evitar requisições desnecessárias
    anos_ja_salvos = set()
    if os.path.exists(output_csv):
        with open(output_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            anos_ja_salvos = {int(r["Ano_PIB"]) for r in reader if str(r.get("Ano_PIB", "")).isdigit()}
        if ano_alvo in anos_ja_salvos:
            print(f"\n[OK] O PIB do ano-alvo {ano_alvo} já está salvo em '{output_csv}'.")
            print("Nenhuma nova consulta necessária para UFs até o próximo ciclo anual.")
            print("=" * 70)
            return

    session = requests.Session()

    # 1. Buscar População do Censo 2022 (Tabela 4709)
    populacao_por_uf_ano = {}
    url_censo = "https://apisidra.ibge.gov.br/values/t/4709/n3/25,26/v/93/p/2022"
    resp_censo = session.get(url_censo, timeout=20)
    if resp_censo.status_code == 200:
        for item in resp_censo.json()[1:]:
            cod_uf = str(item.get("D1C", ""))
            val = item.get("V", "")
            if cod_uf in METADATA_UFS and str(val).isdigit():
                pop_censo = int(val)
                # O IBGE utiliza a base do Censo 2022 para os cálculos de 2022 e 2023
                populacao_por_uf_ano[(cod_uf, 2022)] = pop_censo
                populacao_por_uf_ano[(cod_uf, 2023)] = pop_censo

    # 2. Buscar Estimativas Anuais de População (Tabela 6579)
    url_pop = "https://apisidra.ibge.gov.br/values/t/6579/n3/25,26/v/9324/p/all"
    resp_pop = session.get(url_pop, timeout=20)
    if resp_pop.status_code == 200:
        for item in resp_pop.json()[1:]:
            cod_uf = str(item.get("D1C", ""))
            ano_str = str(item.get("D3C", ""))
            val = item.get("V", "")
            if cod_uf in METADATA_UFS and ano_str.isdigit() and str(val).isdigit():
                ano = int(ano_str)
                if ano >= ano_inicial:
                    populacao_por_uf_ano[(cod_uf, ano)] = int(val)

    # 3. Buscar PIB Estadual a Preços Correntes em Mil Reais (Tabela 5938)
    url_pib = "https://apisidra.ibge.gov.br/values/t/5938/n3/25,26/v/37/p/all"
    resp_pib = session.get(url_pib, timeout=20)
    if resp_pib.status_code != 200:
        print(f"[ERRO] Falha ao consultar Tabela 5938 do IBGE para UFs (HTTP {resp_pib.status_code}).")
        return

    pib_por_uf_ano = {}
    anos_encontrados = set()
    for item in resp_pib.json()[1:]:
        cod_uf = str(item.get("D1C", ""))
        ano_str = str(item.get("D3C", ""))
        val = item.get("V", "")
        if cod_uf in METADATA_UFS and ano_str.isdigit() and str(val).isdigit():
            ano = int(ano_str)
            if ano >= ano_inicial:
                # A tabela 5938 retorna em Mil Reais; multiplicamos por 1.000 para Reais
                pib_por_uf_ano[(cod_uf, ano)] = int(val) * 1000
                anos_encontrados.add(ano)

    ultimo_ano_ibge = max(anos_encontrados) if anos_encontrados else None
    print(f"\nAnos de UFs encontrados na API SIDRA: {sorted(anos_encontrados)}")

    if ano_alvo in anos_encontrados:
        print(f"[SUCESSO] O PIB estadual de {ano_alvo} FOI PUBLICADO pelo IBGE e será gravado agora!")
    else:
        print(
            f"[RETRY DIÁRIO] O PIB estadual de {ano_alvo} ainda não foi liberado na API do IBGE "
            f"(último ano disponível: {ultimo_ano_ibge}). Nova tentativa será feita amanhã."
        )
        if anos_encontrados and anos_encontrados.issubset(anos_ja_salvos):
            print("Todos os anos de UFs retornados já constam no CSV. Mantido sem alterações.")
            print("=" * 70)
            return

    # 4. Montar linhas ordenadas por UF e Ano (decrescente)
    linhas_csv = []
    for cod_uf in ["25", "26"]:
        meta = METADATA_UFS[cod_uf]
        uf_sigla = meta["UF"]
        anos_uf = sorted([a for (c, a) in pib_por_uf_ano.keys() if c == cod_uf], reverse=True)

        for ano in anos_uf:
            pib_reais = pib_por_uf_ano[(cod_uf, ano)]
            pop = populacao_por_uf_ano.get((cod_uf, ano))
            if not pop:
                anos_pop_disp = sorted([a for (c, a) in populacao_por_uf_ano.keys() if c == cod_uf])
                pop = populacao_por_uf_ano[(cod_uf, anos_pop_disp[-1])] if anos_pop_disp else 1

            pib_bilhoes = pib_reais / 1_000_000_000
            pib_formatado = f"R$ {pib_bilhoes:,.2f} bilhões".replace(".", ",")
            pib_per_capita = round(pib_reais / pop, 2)

            cresc = CRESCIMENTO_REAL_CONHECIDO.get((uf_sigla, ano))
            if cresc is None:
                pib_ant = pib_por_uf_ano.get((cod_uf, ano - 1))
                cresc = round(((pib_reais - pib_ant) / pib_ant) * 100, 1) if pib_ant else 0.0

            linhas_csv.append({
                "Ano_PIB": ano,
                "UF": uf_sigla,
                "Nome_Estado": meta["Nome_Estado"],
                "Regiao": meta["Regiao"],
                "Capital": meta["Capital"],
                "Populacao": pop,
                "PIB_Reais": pib_reais,
                "PIB_Formatado": pib_formatado,
                "PIB_per_Capita_Reais": f"{pib_per_capita:.2f}",
                "Crescimento_Real_Anual_Pct": cresc
            })

    if linhas_csv:
        fieldnames = list(linhas_csv[0].keys())
        with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(linhas_csv)

        print(f"\nTabela '{output_csv}' verificada/atualizada com {len(linhas_csv)} registros.")
        print("=" * 70)


def atualizar_dados_ibge_municipios(
    ano_inicial: int = 2020,
    output_csv: str = os.path.join("data", "dados_ibge_municipios.csv")
):
    """
    Consulta a API oficial SIDRA do IBGE para todos os municípios de PB e PE:
    - Tabela 5938 (n6/in n3 25,26): PIB Municipal a preços correntes (Mil Reais)
    - Tabela 4709 (n6/in n3 25,26): População Censo 2022
    - Tabela 6579 (n6/in n3 25,26): População Estimada Anual
    Calcula o PIB per capita municipal e salva em data/dados_ibge_municipios.csv.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    ano_alvo = datetime.now().year - 2

    print("=" * 70)
    print("   IBGE SIDRA API - ATUALIZAÇÃO ANUAL DE PIB E POPULAÇÃO (MUNICÍPIOS)")
    print(f"   Municípios: PB e PE | Série: {ano_inicial} até {ano_alvo}")
    print("=" * 70)

    anos_ja_salvos = set()
    if os.path.exists(output_csv):
        with open(output_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            anos_ja_salvos = {int(r["Ano_PIB"]) for r in reader if str(r.get("Ano_PIB", "")).isdigit()}
        if ano_alvo in anos_ja_salvos:
            print(f"\n[OK] O PIB municipal de {ano_alvo} já está salvo em '{output_csv}'.")
            print("Nenhuma nova consulta necessária para Municípios até o próximo ciclo anual.")
            print("=" * 70)
            return

    session = requests.Session()

    # 1. População Censo 2022 por Município (Tabela 4709)
    print("\n[1/3] Consultando População do Censo Demográfico 2022 (Tabela 4709)...")
    pop_mun_ano = {}
    url_censo = "https://apisidra.ibge.gov.br/values/t/4709/n6/in%20n3%2025,26/v/93/p/2022"
    resp_censo = session.get(url_censo, timeout=30)
    if resp_censo.status_code == 200:
        for item in resp_censo.json()[1:]:
            cod_ibge = str(item.get("D1C", ""))
            val = item.get("V", "")
            if str(val).isdigit():
                pop_val = int(val)
                pop_mun_ano[(cod_ibge, 2022)] = pop_val
                pop_mun_ano[(cod_ibge, 2023)] = pop_val

    # 2. População Estimada Anual por Município (Tabela 6579)
    print("[2/3] Consultando Estimativas Anuais de População (Tabela 6579)...")
    url_pop = "https://apisidra.ibge.gov.br/values/t/6579/n6/in%20n3%2025,26/v/9324/p/all"
    resp_pop = session.get(url_pop, timeout=30)
    if resp_pop.status_code == 200:
        for item in resp_pop.json()[1:]:
            cod_ibge = str(item.get("D1C", ""))
            ano_str = str(item.get("D3C", ""))
            val = item.get("V", "")
            if ano_str.isdigit() and str(val).isdigit():
                ano = int(ano_str)
                if ano >= ano_inicial:
                    pop_mun_ano[(cod_ibge, ano)] = int(val)

    # 3. PIB Municipal a Preços Correntes em Mil Reais (Tabela 5938)
    print("[3/3] Consultando PIB Municipal a Preços Correntes (Tabela 5938)...")
    url_pib = "https://apisidra.ibge.gov.br/values/t/5938/n6/in%20n3%2025,26/v/37/p/all"
    resp_pib = session.get(url_pib, timeout=40)
    if resp_pib.status_code != 200:
        print(f"[ERRO] Falha ao consultar Tabela 5938 de municípios (HTTP {resp_pib.status_code}).")
        return

    dados_pib = resp_pib.json()[1:]
    linhas_csv = []
    anos_encontrados = set()

    for item in dados_pib:
        cod_ibge = str(item.get("D1C", ""))
        nome_completo = str(item.get("D1N", ""))
        ano_str = str(item.get("D3C", ""))
        val_str = str(item.get("V", "")).strip()

        if not (ano_str.isdigit() and val_str.isdigit()):
            continue

        ano = int(ano_str)
        if ano < ano_inicial:
            continue

        anos_encontrados.add(ano)

        # Tratar nome e UF a partir de "Nome da Cidade - UF"
        if " - " in nome_completo:
            partes = nome_completo.rsplit(" - ", 1)
            municipio = partes[0].strip()
            uf_sigla = partes[1].strip()
        else:
            municipio = nome_completo
            uf_sigla = "PB" if cod_ibge.startswith("25") else ("PE" if cod_ibge.startswith("26") else "")

        nome_estado = "Paraíba" if uf_sigla == "PB" else "Pernambuco"
        eh_capital = "Sim" if municipio.lower() in ["joao pessoa", "joão pessoa", "recife"] else "Não"

        # Tabela 5938 informa em Mil Reais
        pib_reais = int(val_str) * 1000

        pop = pop_mun_ano.get((cod_ibge, ano))
        if not pop:
            anos_disp = sorted([a for (c, a) in pop_mun_ano.keys() if c == cod_ibge])
            pop = pop_mun_ano[(cod_ibge, anos_disp[-1])] if anos_disp else 1

        pib_per_capita = round(pib_reais / pop, 2)

        # Formatação do PIB
        if pib_reais >= 1_000_000_000:
            pib_fmt = f"R$ {pib_reais / 1_000_000_000:,.2f} bilhões".replace(".", ",")
        else:
            pib_fmt = f"R$ {pib_reais / 1_000_000:,.2f} milhões".replace(".", ",")

        linhas_csv.append({
            "Codigo_Municipio_IBGE": cod_ibge,
            "Municipio": municipio,
            "UF": uf_sigla,
            "Nome_Estado": nome_estado,
            "É Capital": eh_capital,
            "Ano_PIB": ano,
            "Populacao": pop,
            "PIB_Reais": pib_reais,
            "PIB_Formatado": pib_fmt,
            "PIB_per_Capita_Reais": f"{pib_per_capita:.2f}"
        })

    if ano_alvo not in anos_encontrados and anos_encontrados and anos_encontrados.issubset(anos_ja_salvos):
        print("Todos os anos de Municípios retornados já constam no CSV. Mantido sem alterações.")
        print("=" * 70)
        return

    # Ordenar por UF, Nome do Município e Ano (decrescente)
    linhas_csv.sort(key=lambda r: (r["UF"], r["Municipio"], -r["Ano_PIB"]))

    if linhas_csv:
        fieldnames = list(linhas_csv[0].keys())
        with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(linhas_csv)

        print(f"\n[SUCESSO] Tabela '{output_csv}' gravada com {len(linhas_csv)} registros municipais.")
        print(f"Anos municipais processados: {sorted(anos_encontrados)}")
        print("=" * 70)


def atualizar_tudo():
    atualizar_dados_ibge_ufs()
    atualizar_dados_ibge_municipios()


if __name__ == "__main__":
    atualizar_tudo()
