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
    Fase de Extração (Extract):
    Consome a API pública do PNCP e salva os dados brutos (JSON) exatamente
    como são entregues pelo servidor na pasta data/.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)

    if not data_final:
        data_final = (datetime.now() + timedelta(days=60)).strftime("%Y%m%d")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })

    print("=" * 70)
    print("   PNCP - EXTRAÇÃO DE DADOS BRUTOS DA API")
    print(f"   UFs: {', '.join(ufs)} | Status: Recebendo Proposta")
    print(f"   Arquivo de Destino: {output_json}")
    print("=" * 70)

    todos_itens = []

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
                todos_itens.append(item)
                total_uf += 1

            print(f"   [{uf}] Página {pagina}/{total_paginas} baixada ({total_uf} itens acumulados)")
            pagina += 1

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(todos_itens, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"   Extração concluída!")
    print(f"   Total de registros brutos salvos: {len(todos_itens)}")
    print(f"   Arquivo salvo: {output_json}")
    print("=" * 70)

baixar_dados_brutos()
