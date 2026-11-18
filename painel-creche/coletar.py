"""Coleta os dados da unidade Nave Tatuapé (TecPet) e salva em JSON bruto."""
import json, sys, time, urllib.request, urllib.parse, datetime as dt, os

SHOP = os.environ.get("TECPET_SHOP", "1885")  # Nave Tatuapé
BASE = "https://api.tec.pet"
OUT = sys.argv[1] if len(sys.argv) > 1 else "dados_brutos.json"

def get(path, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"x-shop": SHOP, "Accept": "application/json"})
    for tent in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if tent == 4: raise
            time.sleep(2 * (tent + 1))

def paginar(path, chave="data", **params):
    out, page = [], 1
    while True:
        r = get(path, page=page, limit=100, **params)
        itens = r.get(chave) or []
        out += itens
        if not r.get("pagination", {}).get("hasMore") or not itens:
            return out
        page += 1

def janelas(ini, fim, dias=90):
    a = ini
    while a <= fim:
        b = min(a + dt.timedelta(days=dias - 1), fim)
        yield a.isoformat(), b.isoformat()
        a = b + dt.timedelta(days=1)

hoje = dt.date.today()
ini_ano = dt.date(hoje.year, 1, 1)
fim_fut = hoje + dt.timedelta(days=90)

dados = {"geradoEm": dt.datetime.now(dt.timezone.utc).isoformat(), "shop": SHOP}
dados["config"] = get("/v1/shop/configurations")

b = []
for a, z in janelas(ini_ano, fim_fut):
    b += paginar("/v1/booking", startDate=a, endDate=z)
dados["bookings"] = list({x["id"]: x for x in b}.values())
print("agendamentos", len(dados["bookings"]), file=sys.stderr)

inv = []
for a, z in janelas(ini_ano, hoje):
    inv += paginar("/v1/invoice", startDate=a, endDate=z)
dados["invoices"] = list({x["id"]: x for x in inv}.values())
print("faturas", len(dados["invoices"]), file=sys.stderr)

tr = []
for a, z in janelas(ini_ano, hoje):
    tr += paginar("/v1/transaction", dateFrom=a, dateTo=z)
dados["transactions"] = tr
print("pagamentos", len(tr), file=sys.stderr)

dados["petPlans"] = paginar("/v1/pet-plan", chave="list", endDateFrom=(hoje - dt.timedelta(days=60)).isoformat())
print("planos", len(dados["petPlans"]), file=sys.stderr)

# Só os clientes que aparecem em creche/hotel (a lista completa tem a rede toda)
from concurrent.futures import ThreadPoolExecutor
SEG = {"DAY_CARE", "HOTEL"}
ids = {x["clientId"] for x in dados["bookings"] if x.get("segmentType") in SEG}
ids |= {x["clientId"] for x in dados["invoices"] if x.get("segmentType") in SEG}
ids |= {x["clientId"] for x in dados["petPlans"] if any(c.get("segmentType") in SEG for i in x.get("invoices", []) for c in i.get("control", []))}
ids.discard(None)
with ThreadPoolExecutor(8) as ex:
    dados["clients"] = [c for c in ex.map(lambda i: get(f"/v1/client/{i}"), sorted(ids)) if c]
print("clientes", len(dados["clients"]), file=sys.stderr)

dados["analyticsSales"] = get("/v1/analytics/sales", dateFrom=ini_ano.isoformat(), dateTo=hoje.isoformat(), granularity="MONTH", groupBy="SEGMENT")

json.dump(dados, open(OUT, "w"), ensure_ascii=False)
print("ok", OUT, file=sys.stderr)
