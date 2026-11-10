import os
import json
import time
from datetime import datetime, timedelta
from typing import Optional
import requests

def baixar_dados_brutos(
    ufs=("PB", "PE"),
    data_final: Optional[str] = None,
    output_json: str = os.path.join("data", "dados_brutos_pncp.json")
):
    """
    Fase de Extração Incremental e Idempotente (Extract):
    Consome a API pública do PNCP e realiza Upsert (Update + Insert) pelo
    identificador único 'numeroControlePNCP' no arquivo data/dados_brutos_pncp.json.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)

    if not data_final:
        data_final = (datetime.now() + timedelta(days=60)).strftime("%Y%m%d")

    # Carrega base bruta existente (se houver) para garantir extração incremental sem duplicatas
    itens_por_id = {}
    if os.path.exists(output_json):
        try:
            with open(output_json, "r", encoding="utf-8") as f:
                existentes = json.load(f)
                for item in existentes:
                    chave = item.get("numeroControlePNCP")
                    if chave:
                        itens_por_id[chave] = item
        except Exception:
            itens_por_id = {}

    qtd_antes = len(itens_por_id)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })

    print("=" * 70)
    print("   PNCP - EXTRAÇÃO INCREMENTAL E IDEMPOTENTE DA API")
    print(f"   UFs: {', '.join(ufs)} | Status: Recebendo Proposta")
    print(f"   Registros já existentes em cache: {qtd_antes}")
    print("=" * 70)

    novos_extraidos = 0
    atualizados_extraidos = 0

    for uf in ufs:
        uf = uf.upper().strip()
        pagina = 1
        total_paginas = 1
        total_uf = 0

        print(f"\nBaixando dados da UF: {uf}...")

        while pagina <= total_paginas:
            url = (
                f"https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
                f"?uf={uf}&dataFinal={data_final}&pagina={pagina}&tamanhoPagina=50"
            )

            data = None
            max_tentativas = 8
            for tentativa in range(1, max_tentativas + 1):
                time.sleep(1.0)
                try:
                    resp = session.get(url, timeout=30)
                    if resp.status_code == 429:
                        espera = min(3.0 * (2 ** (tentativa - 1)), 30.0)
                        print(f"   [Rate Limit 429] Aguardando {espera:.1f}s antes de tentar novamente ({tentativa}/{max_tentativas})...")
                        time.sleep(espera)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    espera = min(2.0 * tentativa, 20.0)
                    if tentativa == max_tentativas:
                        print(f"   [Erro] Falha ao consultar página {pagina} de {uf}: {e}")
                    else:
                        time.sleep(espera)

            if not data:
                print(f"   [Aviso] Interrompendo coleta de {uf} na página {pagina}.")
                break

            total_paginas = data.get("totalPaginas", 1)
            itens = data.get("data", [])

            for item in itens:
                item["_uf_consulta"] = uf
                chave = item.get("numeroControlePNCP")
                if chave:
                    if chave in itens_por_id:
                        atualizados_extraidos += 1
                    else:
                        novos_extraidos += 1
                    itens_por_id[chave] = item
                total_uf += 1

            print(f"   [{uf}] Página {pagina}/{total_paginas} baixada ({total_uf} itens lidos)")
            pagina += 1

    lista_consolidada = list(itens_por_id.values())
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(lista_consolidada, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("   Extração Incremental Concluída!")
    print(f"   - Novos editais inéditos adicionados: {novos_extraidos}")
    print(f"   - Editais existentes sincronizados:   {atualizados_extraidos}")
    print(f"   - Total único consolidado no JSON:    {len(lista_consolidada)}")
    print("=" * 70)

baixar_dados_brutos()
