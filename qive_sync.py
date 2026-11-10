#!/usr/bin/env python3
"""Baixa da Qive (Arquivei) os XMLs de NF-e recebidas para importar no painel.

Fluxo:
  1. Busca as NF-e recebidas na API da Qive (GET /v1/nfe/received), página a página,
     a partir do cursor salvo na última execução.
  2. Decodifica cada XML e grava em qive_xml/<chave>.xml.
  3. Pula as notas cuja chave já está lançada no painel (campo chaveNFe do index.html).
  4. Os arquivos novos são importados no painel pelo botão "Importar XML de NF",
     que mostra a revisão antes de salvar — essa é a etapa de aprovação.

Autenticação: os cabeçalhos X-API-ID e X-API-KEY são injetados pelo proxy do
ambiente (segredo de rede para api.arquivei.com.br). Fora desse ambiente, defina
QIVE_API_ID e QIVE_API_KEY.

Uso:
  python3 qive_sync.py              # busca a partir do último cursor
  python3 qive_sync.py --desde-inicio  # ignora o cursor e busca tudo
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("QIVE_BASE_URL", "https://api.arquivei.com.br")
AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_XML = os.path.join(AQUI, "qive_xml")
ARQ_CURSOR = os.path.join(AQUI, "qive_cursor.json")
PAINEL = os.path.join(AQUI, "index.html")
LIMITE = 50


def chaves_no_painel():
    try:
        with open(PAINEL, encoding="utf-8") as f:
            return set(re.findall(r'"chaveNFe":"(\d{44})"', f.read()))
    except FileNotFoundError:
        return set()


def ler_cursor():
    try:
        with open(ARQ_CURSOR, encoding="utf-8") as f:
            return int(json.load(f).get("cursor", 0))
    except (FileNotFoundError, ValueError):
        return 0


def salvar_cursor(cursor):
    with open(ARQ_CURSOR, "w", encoding="utf-8") as f:
        json.dump({"cursor": cursor}, f)


def buscar(cursor):
    url = f"{BASE_URL}/v1/nfe/received?cursor={cursor}&limit={LIMITE}"
    headers = {"Accept": "application/json"}
    if os.environ.get("QIVE_API_ID") and os.environ.get("QIVE_API_KEY"):
        headers["X-API-ID"] = os.environ["QIVE_API_ID"]
        headers["X-API-KEY"] = os.environ["QIVE_API_KEY"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        if e.code == 401:
            sys.exit(
                "A Qive recusou as credenciais (401). Confira se o segredo de rede "
                "tem os valores corretos de API-ID e API-KEY.\nResposta: " + corpo
            )
        sys.exit(f"Erro HTTP {e.code} da Qive: {corpo}")


def proximo_cursor(resp, atual):
    nxt = (resp.get("page") or {}).get("next") or ""
    m = re.search(r"cursor=(\d+)", nxt)
    return int(m.group(1)) if m else atual


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--desde-inicio", action="store_true", help="ignora o cursor salvo")
    args = ap.parse_args()

    os.makedirs(PASTA_XML, exist_ok=True)
    ja_lancadas = chaves_no_painel()
    cursor = 0 if args.desde_inicio else ler_cursor()
    novas = repetidas = 0

    while True:
        resp = buscar(cursor)
        docs = resp.get("data") or []
        for d in docs:
            chave = d.get("access_key", "")
            if chave in ja_lancadas:
                repetidas += 1
                continue
            destino = os.path.join(PASTA_XML, f"{chave}.xml")
            if os.path.exists(destino):
                continue
            with open(destino, "wb") as f:
                f.write(base64.b64decode(d.get("xml", "")))
            novas += 1
        novo = proximo_cursor(resp, cursor)
        if not docs or novo == cursor:
            break
        cursor = novo
        salvar_cursor(cursor)

    salvar_cursor(cursor)
    print(f"{novas} NF-e nova(s) salva(s) em {PASTA_XML}")
    print(f"{repetidas} já estavam lançadas no painel e foram puladas")
    if novas:
        print('Importe no painel: "Importar XML de NF" → selecione os arquivos da pasta.')


if __name__ == "__main__":
    main()
