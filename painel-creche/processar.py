"""Transforma os dados brutos do TecPet (coletar.py) nos arquivos do painel de Creche & Hotel.

Uso: python3 processar.py dados_brutos.json pasta_saida/
Gera um JSON por conjunto de dados, no formato {rows, meta}.
"""
import json, sys, os, collections, datetime as dt

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
d = json.load(open(SRC))
SEG = {"DAY_CARE", "HOTEL"}
CODE = open(__file__).read()

STATUS_AG = {"SCHEDULED": "Agendado", "CONFIRMED": "Confirmado", "IN_SERVICE": "Hospedado/na creche",
             "DONE": "Concluído", "DELIVERED": "Entregue", "RECEIVED": "Recebido", "REMOVED": "Cancelado"}
STATUS_FAT = {"PAID": "Paga", "UNPAID": "Em aberto", "OVERDUE": "Vencida", "CANCELED": "Cancelada", "NO_CHARGE": "Sem cobrança"}
STATUS_PLANO = {"ACTIVE": "Ativo", "CANCELING": "Cancelando", "CANCELED": "Cancelado", "EXPIRED": "Expirado",
                "OVERDUE": "Pagamento vencido", "SOLD_OFF": "Diárias esgotadas", "FINISHED": "Encerrado", "PENDING": "Pendente"}


def tipo_servico(nome):
    n = (nome or "").lower()
    if "24 horas" in n or "gato" in n or "aluguel" in n:
        return "Hotel"
    if "diária" in n or "diaria" in n or "daycare" in n:
        return "Creche"
    return "Outros"


def dia_local(iso):
    """Data no fuso de São Paulo (UTC-3) a partir de um ISO em UTC."""
    if not iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")) - dt.timedelta(hours=3)
    return t.date().isoformat()


clientes = {c["id"]: c for c in d["clients"]}
for i in d["invoices"]:  # nome de quem não veio no cadastro
    if i.get("clientId") and i["clientId"] not in clientes:
        clientes[i["clientId"]] = {"id": i["clientId"], "name": i.get("clientName")}


def nome_cli(cid):
    return (clientes.get(cid) or {}).get("name") or f"Cliente {cid}"


def tel_cli(cid):
    c = clientes.get(cid) or {}
    p = c.get("phoneNumber")
    if not p:
        return ""
    p = "".join(ch for ch in p if ch.isdigit())
    if len(p) == 11:
        return f"({p[:2]}) {p[2:7]}-{p[7:]}"
    if len(p) == 10:
        return f"({p[:2]}) {p[2:6]}-{p[6:]}"
    return p


hoje = dt.date.fromisoformat(dia_local(d["geradoEm"]))
gerado = d["geradoEm"]

# ---------- agendamentos de creche/hotel ----------
ags = []
for b in d["bookings"]:
    if b.get("segmentType") not in SEG:
        continue
    nome_serv = " + ".join(s["name"] for s in b["services"])
    tipos = {tipo_servico(s["name"]) for s in b["services"]}
    tipo = "Hotel" if "Hotel" in tipos else ("Creche" if "Creche" in tipos else "Outros")
    ags.append({
        "id": str(b["id"]), "data": b["dateIso"], "tipo": tipo, "servico": nome_serv,
        "status": STATUS_AG.get(b["status"], b["status"]), "cancelado": b["status"] == "REMOVED",
        "pet": b.get("petName") or "", "petId": b.get("petId"), "clienteId": b.get("clientId"),
        "cliente": nome_cli(b.get("clientId")), "telefone": tel_cli(b.get("clientId")),
        "pacote": bool(b.get("petPlanId")), "faturaId": (b.get("invoice") or {}).get("id"),
    })
ags.sort(key=lambda r: (r["data"], r["pet"]))
validos = [a for a in ags if not a["cancelado"]]

# hotel: noites agrupadas em estadias (noites seguidas do mesmo pet)
noites = [a for a in validos if a["tipo"] == "Hotel"]
por_pet = collections.defaultdict(list)
for n in noites:
    por_pet[n["petId"]].append(n)
estadias = []
for pet, ns in por_pet.items():
    ns.sort(key=lambda r: r["data"])
    atual = None
    for n in ns:
        dia = dt.date.fromisoformat(n["data"])
        if atual and (dia - atual["_ult"]).days <= 1:
            if dia != atual["_ult"]:
                atual["noites"] += 1
            atual["_ult"] = dia
        else:
            atual = {"pet": n["pet"], "cliente": n["cliente"], "telefone": n["telefone"], "clienteId": n["clienteId"],
                     "entrada": n["data"], "_ult": dia, "noites": 1}
            estadias.append(atual)
        n["estadia"] = len(estadias)
for e in estadias:
    e["saida"] = (e.pop("_ult") + dt.timedelta(days=1)).isoformat()
    ent, sai = dt.date.fromisoformat(e["entrada"]), dt.date.fromisoformat(e["saida"])
    e["situacao"] = "Hospedado agora" if ent <= hoje < sai else ("Futura" if ent > hoje else "Concluída")
    e["id"] = f'{e["clienteId"]}-{e["pet"]}-{e["entrada"]}'
estadias.sort(key=lambda r: (r["entrada"], r["pet"]))

# ---------- faturas ----------
bk = {str(b["id"]): b for b in d["bookings"]}
planos = {p["id"]: p for p in d["petPlans"]}
fats = []
for i in d["invoices"]:
    if i.get("segmentType") not in SEG:
        continue
    if i["type"] == "PLAN":
        p = planos.get(i.get("petPlanId"))
        nome = p["plan"]["name"] if p else "Pacote"
        tipo = "Hotel" if "aluguel" in nome.lower() else "Creche"
        origem = "Pacote"
    else:
        b = bk.get(str(i.get("bookingId")))
        nome = " + ".join(s["name"] for s in b["services"]) if b else "Agendamento"
        tipo = tipo_servico(nome) if b else "Creche"
        origem = "Avulso"
    st = STATUS_FAT.get(i["status"], i["status"])
    fats.append({
        "id": i["id"], "ref": i.get("reference"), "criada": dia_local(i["createdDate"]), "mes": dia_local(i["createdDate"])[:7],
        "vencimento": dia_local(i.get("dueDate")), "pagaEm": dia_local(i.get("paidDate")),
        "cliente": i.get("clientName") or nome_cli(i.get("clientId")), "clienteId": i.get("clientId"),
        "telefone": tel_cli(i.get("clientId")), "pet": i.get("petName") or "",
        "tipo": tipo, "origem": origem, "servico": nome, "status": st,
        "total": round(i["totalValue"] or 0, 2), "pago": round(i["paidValue"] or 0, 2),
        "aberto": round(i["unpaidValue"] or 0, 2) if i["status"] in ("UNPAID", "OVERDUE") else 0,
        "valida": i["status"] not in ("CANCELED",),
        "diasAtraso": max(0, (hoje - dt.date.fromisoformat(dia_local(i["dueDate"]))).days) if i.get("dueDate") and i["status"] in ("UNPAID", "OVERDUE") else 0,
    })
fats.sort(key=lambda r: r["criada"])

# ---------- pacotes de creche ----------
pacs = []
for p in d["petPlans"]:
    ctrl = [c for inv in p["invoices"] for c in inv["control"] if c.get("segmentType") in SEG]
    if not ctrl:
        continue
    cur = [c for inv in p["invoices"] if inv.get("current") for c in inv["control"] if c.get("segmentType") in SEG] or ctrl
    qtd = sum(c["quantity"] for c in cur)
    # O TecPet conta como "usada" toda diária vinculada ao pacote, inclusive as agendadas para o futuro.
    # Aqui "usadas" são só as que já aconteceram (até hoje), contadas pelos agendamentos deste pacote.
    vinc = sorted(b["dateIso"] for b in d["bookings"] if b.get("petPlanId") == p["id"] and b["status"] != "REMOVED")
    usadas = sum(1 for x in vinc if x <= hoje.isoformat())
    agendadas = sum(1 for x in vinc if x > hoje.isoformat())
    fim = dia_local(p["endDate"])
    inv_cur = next((inv for inv in p["invoices"] if inv.get("current")), p["invoices"][0] if p["invoices"] else {})
    pacs.append({
        "id": str(p["id"]), "pet": p["pet"]["name"], "cliente": nome_cli(p["clientId"]), "telefone": tel_cli(p["clientId"]),
        "plano": p["plan"]["name"], "status": STATUS_PLANO.get(p["status"], p["status"]),
        "inicio": dia_local(p["startDate"]), "fim": fim, "diasParaFim": (dt.date.fromisoformat(fim) - hoje).days,
        "contratadas": qtd, "usadas": usadas, "agendadas": agendadas, "restantes": max(0, qtd - usadas),
        "semAgendar": max(0, qtd - usadas - agendadas), "usadasTecpet": sum(c["used"] for c in cur),
        "ultimaDiaria": max((x for x in vinc if x <= hoje.isoformat()), default=None),
        "proximaDiaria": min((x for x in vinc if x > hoje.isoformat()), default=None),
        "valor": round(p.get("partialPrice") or p.get("price") or 0, 2),
        "faturaAtual": STATUS_FAT.get(inv_cur.get("status"), inv_cur.get("status") or ""),
        "vencimentoFatura": dia_local(inv_cur.get("dueDate")),
        "vigente": p["status"] in ("ACTIVE", "PENDING", "OVERDUE", "SOLD_OFF", "CANCELING"),
    })
ultimo = {}
for p in sorted(pacs, key=lambda r: r["inicio"]):
    ultimo[(p["cliente"], p["pet"].strip())] = p["id"]
for p in pacs:  # pacote mais recente de cada pet; renovações deixam o antigo de fora dos alertas
    p["atual"] = ultimo[(p["cliente"], p["pet"].strip())] == p["id"]
pacs.sort(key=lambda r: (not r["vigente"], r["fim"]))

# ---------- clientes ----------
cl = collections.defaultdict(lambda: {"diasCreche": 0, "noitesHotel": 0, "estadias": 0, "pets": set(), "datas": [], "datasHotel": [],
                                      "faturado": 0.0, "recebido": 0.0, "aberto": 0.0, "pacoteAtivo": False})
for a in validos:
    if a["data"] > hoje.isoformat():
        continue
    c = cl[a["clienteId"]]
    c["pets"].add(a["pet"])
    c["datas"].append(a["data"])
    if a["tipo"] == "Hotel":
        c["noitesHotel"] += 1
        c["datasHotel"].append(a["data"])
    elif a["tipo"] == "Creche":
        c["diasCreche"] += 1
for e in estadias:
    if e["entrada"] <= hoje.isoformat():
        cl[e["clienteId"]]["estadias"] += 1
for f in fats:
    if f["valida"]:
        c = cl[f["clienteId"]]
        c["faturado"] += f["total"]
        c["recebido"] += f["pago"]
        c["aberto"] += f["aberto"]
for p in pacs:
    if p["vigente"]:
        for cid, c in clientes.items():
            if (c.get("name") or "") == p["cliente"]:
                cl[cid]["pacoteAtivo"] = True
proxima = {}
for a in validos:
    if a["data"] >= hoje.isoformat():
        proxima.setdefault(a["clienteId"], a["data"])
clis = []
for cid, c in cl.items():
    if not c["datas"] and not c["faturado"]:
        continue
    ds = sorted(c["datas"])
    ult = ds[-1] if ds else None
    meses = len({x[:7] for x in ds})
    clis.append({
        "clienteId": str(cid), "cliente": nome_cli(cid), "telefone": tel_cli(cid), "pets": ", ".join(sorted(p for p in c["pets"] if p)),
        "diasCreche": c["diasCreche"], "noitesHotel": c["noitesHotel"], "estadiasHotel": c["estadias"],
        "visitas": len(ds), "mesesAtivos": meses, "mediaMes": round(len(ds) / meses, 1) if meses else 0,
        "primeira": ds[0] if ds else None, "ultima": ult,
        "diasSemVir": (hoje - dt.date.fromisoformat(ult)).days if ult else None,
        "proxima": proxima.get(cid), "usouHotel": c["noitesHotel"] > 0,
        "faturado": round(c["faturado"], 2), "recebido": round(c["recebido"], 2), "aberto": round(c["aberto"], 2),
        "pacoteAtivo": c["pacoteAtivo"],
    })
clis.sort(key=lambda r: -r["visitas"])

# ---------- recebimentos por forma de pagamento ----------
pag = collections.defaultdict(float)
for t in d["transactions"]:
    if t.get("segmentType") in SEG and t.get("status") == "CONFIRMED" and t.get("type") == "IN":
        pag[(dia_local(t["date"])[:7], t.get("paymentMethodName") or t.get("paymentMethodType") or "Outro")] += t["value"] or 0
pags = [{"mes": m, "forma": f, "valor": round(v, 2)} for (m, f), v in sorted(pag.items())]

# ---------- grava ----------
meta_comum = [
    {"label": "Origem", "value": "API TecPet (api.tec.pet), loja 1885 – Nave Tatuapé, segmento Creche/Hotel"},
    {"label": "Coletado em", "value": gerado},
    {"label": "Período", "value": f"{hoje.year}-01-01 até hoje (agenda até 90 dias à frente)"},
    {"label": "processar.py", "value": CODE, "type": "code", "lang": "python"},
]


def grava(nome, rows, extra=None):
    json.dump({"rows": rows, "meta": (extra or []) + meta_comum}, open(os.path.join(OUT, nome + ".json"), "w"), ensure_ascii=False)
    print(nome, len(rows), file=sys.stderr)


for a in ags:
    a.pop("petId", None)
grava("agenda", ags)
grava("estadias", estadias)
grava("faturas", fats)
grava("pacotes", pacs)
grava("clientes", clis)
grava("recebimentos", pags)
grava("falecidos", [{"id": str(p["id"]), "pet": (p.get("name") or "").strip(), "clienteId": str(p["clientId"])}
                    for p in d.get("pets", []) if p.get("deceased")])
