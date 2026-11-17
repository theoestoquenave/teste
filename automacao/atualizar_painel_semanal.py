#!/usr/bin/env python3
"""
Rotina semanal: puxa os serviços de CLÍNICA executados na TecPet desde o último
lançamento já importado, e gera o HTML atualizado do painel.

Uso:
  python3 -I atualizar_painel_semanal.py <html_atual> <html_saida>

<html_atual>: arquivo local com o HTML completo do painel (ex.: o arquivo salvo
              por um `Artifact read` da URL do painel ao vivo).
<html_saida>: onde escrever o HTML já atualizado, pronto pra publicar.

Autenticação: espera que a rede do ambiente já injete o header Authorization
(Bearer) nas chamadas para api.tec.pet via Segredo de Rede — não lê nenhum
.env nem token daqui. Só NÃO roda sem essa configuração (a chamada volta 401).

Não publica nada sozinho: só gera o arquivo de saída. Quem publica é o agente
que chama este script, via Artifact tool.
"""
import sys, os, json, random, time, urllib.request, urllib.error
from datetime import date, timedelta

TECPET_BASE = 'https://api.tec.pet/v1'

def http_get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

def tecpet_get(pathname, shop=None, params=None, tries=4):
    qs = []
    for k, v in (params or {}).items():
        qs.append(f'{k}={urllib.parse.quote(str(v))}')
    url = TECPET_BASE + pathname + ('?' + '&'.join(qs) if qs else '')
    headers = {'Authorization': 'Bearer __SECRET__', 'Content-Type': 'application/json'}
    if shop:
        headers['x-shop'] = str(shop)
    last_err = None
    for i in range(tries):
        try:
            return http_get_json(url, headers)
        except urllib.error.HTTPError as e:
            if e.code in (429,) or e.code >= 500:
                last_err = e
                time.sleep(1.5 * (2 ** i))
                continue
            raise RuntimeError(f'HTTP {e.code} em {pathname}: {e.read()[:300]}')
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(1.5 * (2 ** i))
    raise RuntimeError(f'falha de rede em {pathname}: {last_err}')

import urllib.parse

def find_matching_bracket(text, open_pos):
    assert text[open_pos] == '['
    depth = 0; i = open_pos; in_string = False; escape = False; n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == '"': in_string = False
        else:
            if c == '"': in_string = True
            elif c == '[': depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0: return i
        i += 1
    raise ValueError('fechamento nao encontrado')

def extract_array(content, key):
    idx = content.find(key)
    if idx == -1 or content.count(key) != 1:
        raise ValueError(f'esperava ocorrência única de {key}')
    arr_open = idx + len(key) - 1
    arr_close = find_matching_bracket(content, arr_open)
    return arr_open, arr_close, json.loads(content[arr_open:arr_close+1])

def janelas(de, ate, dias=92):
    out = []
    a = de
    while a <= ate:
        b = min(ate, a + timedelta(days=dias - 1))
        out.append((a.isoformat(), b.isoformat()))
        a = b + timedelta(days=1)
    return out

BASE36 = '0123456789abcdefghijklmnopqrstuvwxyz'
def to_base36(n):
    if n == 0: return '0'
    s = ''
    while n:
        n, r = divmod(n, 36); s = BASE36[r] + s
    return s
def rand_suffix(k=5):
    return ''.join(random.choice(BASE36) for _ in range(k))

def main():
    if len(sys.argv) != 3:
        print('uso: atualizar_painel_semanal.py <html_atual> <html_saida>', file=sys.stderr)
        sys.exit(2)
    src, dst = sys.argv[1], sys.argv[2]

    with open(src, encoding='utf-8') as f:
        content = f.read()

    lanc_open, lanc_close, lancamentos = extract_array(content, '"lancamentos":[')
    _, _, tipos_servico = extract_array(content, '"tiposServico":[')
    catalogo = {t['nome']: t for t in tipos_servico}

    PREFIXO_NOTA = 'Importado da API TecPet (clínica) — '
    datas_importadas = [l['data'] for l in lancamentos if l.get('subtipo') == 'servico' and (l.get('nota') or '').startswith(PREFIXO_NOTA)]
    if datas_importadas:
        ultima = date.fromisoformat(max(datas_importadas))
    else:
        # fallback: nunca rodou isso aqui ainda — não deveria acontecer em uso normal
        ultima = date.fromisoformat(max(l['data'] for l in lancamentos if l.get('subtipo') == 'servico'))
    desde = ultima + timedelta(days=1)
    ate = date.today() - timedelta(days=1)  # até ontem, pra não pegar dia incompleto

    print(f'Última data já importada (API clínica): {ultima.isoformat()}')
    print(f'Puxando de {desde.isoformat()} até {ate.isoformat()}')

    if desde > ate:
        print('Nada a fazer — já está em dia.')
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(content)
        return

    shops_body = tecpet_get('/shop', params={'limit': 100})
    shops = [s for s in shops_body.get('data', []) if 'master' not in (s.get('name') or '').lower()]
    print(f'{len(shops)} unidades (excluindo Master)')

    ocorrencias = []
    for shop in shops:
        shop_id = shop['id']
        nome = shop.get('name') or str(shop_id)
        n = 0
        for wde, wate in janelas(desde, ate):
            last_id = 0
            while True:
                body = tecpet_get('/booking', shop=shop_id, params={
                    'startDate': wde, 'endDate': wate, 'status': 'DONE,DELIVERED', 'limit': 500, 'lastId': last_id})
                rows = body.get('data') or []
                for bk in rows:
                    if bk.get('segmentType') != 'CLINIC':
                        continue
                    dia = (bk.get('dateIso') or '')[:10] or bk.get('date')
                    for s in bk.get('services') or []:
                        ocorrencias.append({'unidade': nome, 'data': dia, 'tipoServico': s.get('name')})
                        n += 1
                if not body.get('pagination', {}).get('hasMore') or not rows:
                    break
                last_id = rows[-1]['id']
        print(f'  {nome}: {n} ocorrências de clínica')

    print(f'Total de ocorrências novas: {len(ocorrencias)}')

    now_ms = int(time.time() * 1000)
    novos = []
    for i, oc in enumerate(ocorrencias):
        nome_serv = oc['tipoServico']
        cat = catalogo.get(nome_serv)
        grupo = cat['grupo'] if cat else nome_serv
        mult = cat['mult'] if cat else 1
        j = {
            'id': 'l_' + to_base36(now_ms + i) + rand_suffix(),
            'tipo': 'saida', 'subtipo': 'servico', 'data': oc['data'],
            'tipoServico': nome_serv, 'tipoServicoGrupo': grupo, 'tipoServicoMult': mult,
            'unidade': oc['unidade'], 'itens': [],
            'nota': PREFIXO_NOTA + oc['unidade'], 'criadoEm': now_ms,
        }
        novos.append(j)

    parts = []
    for l in novos:
        j = json.dumps(l, ensure_ascii=False, separators=(',', ':'))
        if '<' in j:
            raise ValueError('valor inseguro contendo "<": ' + j)
        parts.append(j)

    if parts:
        insercao = ',' + ','.join(parts)
        new_content = content[:lanc_close] + insercao + content[lanc_close:]
    else:
        new_content = content

    # checagem de segurança: lançamentos com itens (afetam saldo/valor em estoque) não podem mudar
    def com_itens(lancs):
        return sorted(l['id'] for l in lancs if l.get('itens'))
    lanc_open2, lanc_close2, lancamentos_final = extract_array(new_content, '"lancamentos":[')
    if com_itens(lancamentos) != com_itens(lancamentos_final):
        raise RuntimeError('ABORTADO: a atualização mexeria em lançamentos que afetam o saldo/valor em estoque — isso não deveria acontecer nesta rotina.')

    with open(dst, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'Lançamentos antes: {len(lancamentos)} | depois: {len(lancamentos_final)}')
    print(f'Arquivo atualizado escrito em: {dst}')

if __name__ == '__main__':
    main()
