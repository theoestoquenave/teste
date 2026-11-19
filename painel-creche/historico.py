"""Hotel antes de 2026: noites de diária 24h por pet, desde o início do histórico no TecPet (out/2025).

Uso: python3 historico.py saida.json
O painel junta este arquivo (fixo) com a agenda de 2026 (atualizada todo dia) para listar todos os pets
que já usaram o hotel. Só precisa rodar de novo se o histórico antigo mudar.
"""
import json, sys, datetime as dt, collections, urllib.request, urllib.parse, time
from concurrent.futures import ThreadPoolExecutor

SHOP, BASE, OUT = "1885", "https://api.tec.pet", sys.argv[1]
INICIO, FIM = dt.date(2025, 9, 1), dt.date(2025, 12, 31)
CODE = open(__file__).read()


def get(path, **params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"x-shop": SHOP})
    for t in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if t == 4:
                raise
            time.sleep(2 * (t + 1))


def hotel(nomes):
    n = " ".join(nomes).lower()
    return "24 horas" in n or "gato" in n


bookings, a = [], INICIO
while a <= FIM:
    b = min(a + dt.timedelta(days=89), FIM)
    page = 1
    while True:
        r = get("/v1/booking", startDate=a.isoformat(), endDate=b.isoformat(), page=page, limit=100)
        bookings += r["data"]
        if not r["pagination"]["hasMore"]:
            break
        page += 1
    a = b + dt.timedelta(days=1)

noites = collections.defaultdict(set)
for x in bookings:
    if x.get("segmentType") in ("DAY_CARE", "HOTEL") and x["status"] != "REMOVED" and hotel(s["name"] for s in x["services"]):
        noites[(x["clientId"], (x.get("petName") or "").strip())].add(x["dateIso"])

with ThreadPoolExecutor(8) as ex:
    cli = dict(zip({c for c, _ in noites}, ex.map(lambda i: get(f"/v1/client/{i}"), {c for c, _ in noites})))


def fone(c):
    p = "".join(ch for ch in ((c or {}).get("phoneNumber") or "") if ch.isdigit())
    return f"({p[:2]}) {p[2:7]}-{p[7:]}" if len(p) == 11 else (f"({p[:2]}) {p[2:6]}-{p[6:]}" if len(p) == 10 else p)


def falecidos(cid):
    r = get("/v1/pet", clientId=cid, includeDeceased="true", limit=100)
    return {(p.get("name") or "").strip().lower() for p in r.get("data", []) if p.get("deceased")}


with ThreadPoolExecutor(8) as ex:
    mortos = dict(zip(list(cli), ex.map(falecidos, list(cli))))

rows = []
for (cid, pet), ds in noites.items():
    ds = sorted(ds)
    est = 1 + sum(1 for x, y in zip(ds, ds[1:]) if (dt.date.fromisoformat(y) - dt.date.fromisoformat(x)).days > 1)
    rows.append({"clienteId": str(cid), "cliente": (cli.get(cid) or {}).get("name") or f"Cliente {cid}", "telefone": fone(cli.get(cid)),
                 "pet": pet, "noites": len(ds), "estadias": est, "primeira": ds[0], "ultima": ds[-1],
                 "falecido": pet.lower() in mortos.get(cid, set())})
rows.sort(key=lambda r: -r["noites"])
json.dump({"rows": rows, "meta": [
    {"label": "Origem", "value": "API TecPet, loja 1885 – Nave Tatuapé: diárias 24h e Diária Gato não canceladas"},
    {"label": "Período", "value": f"{INICIO} a {FIM} (não há agendamentos antes de out/2025 no TecPet)"},
    {"label": "Coletado em", "value": dt.datetime.now(dt.timezone.utc).isoformat()},
    {"label": "historico.py", "value": CODE, "type": "code", "lang": "python"},
]}, open(OUT, "w"), ensure_ascii=False)
print(len(bookings), "agendamentos;", len(rows), "pets;", sum(r["noites"] for r in rows), "noites", file=sys.stderr)
