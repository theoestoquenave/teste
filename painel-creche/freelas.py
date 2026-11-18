"""Gasto com freelancers do setor hotel (Nave Tatuapé), a partir das planilhas do Drive.

Uso: python3 freelas.py rpa.xlsx free_colaborador.xlsx saida.json [AAAA-MM-DD]

Regras (combinadas com o Theo em 18/11/2026):
- Planilha RPA: o setor hotel é marcado na coluna "Unidade" ("Hotel", "Hotal", "Tatuapé/Hotel"...).
  Para cada mês vale a aba de total do mês; se ela não existe ou está vazia, somam-se as abas semanais
  com data até hoje. Linhas sem valor legível ou acima de R$ 5.000 ficam de fora e vão para o meta.
- Planilha Free Colaborador: uma aba por mês; entra a linha com coluna "Setor" contendo "hotel".
- As duas planilhas se somam (lançamentos repetidos em ambas contam duas vezes, como combinado).
- Nenhum dado pessoal além do nome do profissional sai daqui (sem telefone, CPF, PIX, endereço).
"""
import json, re, sys, datetime as dt, collections
import openpyxl

RPA, FREE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
HOJE = dt.date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else dt.date.today()
ANO = HOJE.year
CODE = open(__file__).read()
MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    t = v.upper().replace("R$", "").replace("RS", "").strip()
    m = re.match(r"^\s*([\d.,]+)", t)
    if not m:
        return None
    s = m.group(1).rstrip(".,")
    if re.fullmatch(r"\d{1,3}(,\d{3})+,\d{2}", s):  # "3,500,00"
        s = s.replace(",", "", s.count(",") - 1)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def txt(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


linhas, fora = [], []

# ---------------- RPA ----------------
wb = openpyxl.load_workbook(RPA, data_only=True, read_only=True)


def data_aba(nome):
    """Data de uma aba semanal: '06 01 2026 OK', '03022026', '12 05', '04 08 2026'."""
    s = re.sub(r"[^\d ]", " ", nome).split()
    s = "".join(s) if len("".join(s)) in (4, 8) else " ".join(s)
    try:
        if re.fullmatch(r"\d{8}", s):
            return dt.date(int(s[4:]), int(s[2:4]), int(s[:2]))
        p = s.split() if " " in s else [s[:2], s[2:4]]
        return dt.date(int(p[2]) if len(p) > 2 else ANO, int(p[1]), int(p[0]))
    except (ValueError, IndexError):
        return None


def ler_rpa(ws):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    h = [txt(c).lower() for c in rows[0]]
    desloc = 1 if len(h) > 1 and h[0] == h[1] == "profissional" else 0  # cabeçalho com coluna a mais
    c_obs = next((i for i, x in enumerate(h) if "serv" in x), 18) - desloc
    out = []
    for r in rows[1:]:
        if not r or not r[0] or len(r) < 4:
            continue
        out.append({"nome": txt(r[0]), "unidade": txt(r[2]), "valor_bruto": r[3], "obs": txt(r[c_obs]) if c_obs < len(r) else ""})
    return out


# Agrupa as abas em meses: abas semanais seguidas da aba de total que fecha o mês.
grupos, atual = [], {"semanas": [], "total": None}
comecou = False
for ws in wb.worksheets:
    nome = ws.title.strip()
    eh_total = bool(re.match(r"(total|todos)", nome, re.I))
    if not comecou:
        d = data_aba(nome)
        if not (d and d.year == ANO) and not (eh_total and str(ANO) in nome):
            continue
        comecou = True
    if eh_total:
        atual["total"] = ws
        grupos.append(atual)
        atual = {"semanas": [], "total": None}
    else:
        d = data_aba(nome)
        if d:
            atual["semanas"].append((d, ws))
if atual["semanas"]:
    grupos.append(atual)

for g in grupos:
    datas = [d for d, _ in g["semanas"]]
    if g["total"] is not None and re.search(r"(\d{2})\s*(\d{4})", g["total"].title):
        m = re.search(r"(\d{2})\s*(\d{4})", g["total"].title)
        mes = f"{m.group(2)}-{m.group(1)}"
    elif datas:
        mes = collections.Counter(f"{d.year}-{d.month:02d}" for d in datas).most_common(1)[0][0]
    else:
        continue
    if mes[:4] != str(ANO):
        continue
    regs = ler_rpa(g["total"]) if g["total"] is not None else []
    origem_aba = g["total"].title.strip() if regs else None
    if not regs:  # mês sem total fechado: soma as semanas já passadas
        regs = []
        for d, ws in g["semanas"]:
            if d <= HOJE:
                for x in ler_rpa(ws):
                    x["semana"] = d.isoformat()
                    regs.append(x)
        origem_aba = "abas semanais até " + HOJE.strftime("%d/%m")
    for x in regs:
        if not re.search(r"hot[ae]l", x["unidade"], re.I):
            continue
        v = num(x["valor_bruto"])
        if v is None or v <= 0 or v > 5000:
            fora.append({"planilha": "RPA", "mes": mes, "profissional": x["nome"], "motivo": f"valor ilegível: {txt(x['valor_bruto'])[:30]}"})
            continue
        linhas.append({"id": f"rpa-{len(linhas)}", "mes": mes, "planilha": "RPA", "profissional": x["nome"], "valor": round(v, 2),
                       "quando": x.get("semana") or "", "detalhe": x["obs"][:80], "aba": origem_aba})

# ---------------- Free Colaborador ----------------
wb2 = openpyxl.load_workbook(FREE, data_only=True, read_only=True)
for ws in wb2.worksheets:
    nome = ws.title.strip().lower()
    mes_n = next((n for k, n in MESES.items() if k in nome), 1 if "colaborador" in nome else None)
    if not mes_n:
        continue
    mes = f"{ANO}-{mes_n:02d}"
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        continue
    h = [txt(c).lower() for c in rows[0]]
    col = lambda k: next((i for i, x in enumerate(h) if k in x), None)
    cn, cv, cs, cd = col("profissional"), col("valor"), col("setor"), col("data")
    if None in (cn, cv, cs):
        continue
    for r in rows[1:]:
        if not r or cs >= len(r) or "hotel" not in txt(r[cs]).lower():
            continue
        v = num(r[cv]) if cv < len(r) else None
        pro = txt(r[cn]) or "(sem nome)"
        if v is None or v <= 0 or v > 5000:
            fora.append({"planilha": "Free Colaborador", "mes": mes, "profissional": pro, "motivo": f"valor ilegível: {txt(r[cv])[:30] if cv < len(r) else ''}"})
            continue
        linhas.append({"id": f"free-{len(linhas)}", "mes": mes, "planilha": "Free Colaborador", "profissional": pro, "valor": round(v, 2),
                       "quando": txt(r[cd])[:60] if cd is not None and cd < len(r) else "", "detalhe": "", "aba": ws.title.strip()})

linhas.sort(key=lambda r: (r["mes"], r["planilha"], r["profissional"]))
meta = [
    {"label": "Origem", "value": "Google Drive: 'PLANILHA RPA NAVE 2025.xlsx' e 'Free Coladorador' (só setor hotel)"},
    {"label": "Gerado em", "value": dt.datetime.now(dt.timezone.utc).isoformat()},
    {"label": "Linhas de hotel fora da soma", "value": json.dumps(fora, ensure_ascii=False) if fora else "nenhuma"},
    {"label": "freelas.py", "value": CODE, "type": "code", "lang": "python"},
]
json.dump({"rows": linhas, "meta": meta}, open(OUT, "w"), ensure_ascii=False)
tot = collections.defaultdict(float)
for r in linhas:
    tot[(r["mes"], r["planilha"])] += r["valor"]
for k in sorted(tot):
    print(k, round(tot[k], 2), file=sys.stderr)
print("total", round(sum(r["valor"] for r in linhas), 2), "linhas", len(linhas), "fora", len(fora), file=sys.stderr)
