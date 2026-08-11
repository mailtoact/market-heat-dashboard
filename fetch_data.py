import csv, io, json, math, urllib.request
from datetime import datetime, timezone

# Market Heat V2
# Data sources:
#   FRED CSV endpoints for macro series
#   Yahoo Finance chart endpoint for DXY (DX-Y.NYB)
#
# No API keys are required. If a provider changes its endpoint, edit only this file.

FRED = {
    "DGS2":"2Y Treasury","DGS10":"10Y Treasury","DGS20":"20Y Treasury","DGS30":"30Y Treasury",
    "DCOILWTICO":"WTI Crude","UNRATE":"Unemployment",
    "BAMLH0A0HYM2":"HY Credit Spread","BAMLC0A0CM":"IG Credit Spread"
}

def get(url, attempts=4, timeout=60):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; MarketHeatDashboard/2.0)",
                    "Accept": "text/csv,application/json,text/plain,*/*",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                import time
                time.sleep(3 * attempt)
    raise RuntimeError(f"Request failed after {attempts} attempts: {url} | {last_error}")

def fred_csv(series):
    raw=get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=2024-01-01")
    out=[]
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            v=float(row[series])
            if math.isfinite(v): out.append((row["DATE"],v))
        except: pass
    return out

def yahoo_dxy():
    p1=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp())
    p2=int(datetime.now(timezone.utc).timestamp())
    raw=get(f"https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?period1={p1}&period2={p2}&interval=1d")
    res=json.loads(raw)["chart"]["result"][0]
    out=[]
    for ts,cl in zip(res["timestamp"],res["indicators"]["quote"][0]["close"]):
        if cl is not None: out.append((datetime.fromtimestamp(ts,timezone.utc).date().isoformat(),float(cl)))
    return out

series={k:fred_csv(k) for k in FRED}
series["DXY"]=yahoo_dxy()

def last(rows): return rows[-1] if rows else (None,None)
def hist(rows,n=90): return [{"v":round(v,5)} for _,v in rows[-n:]]
def pct(rows,n=30):
    if len(rows)<=n:return None
    a,b=rows[-1][1],rows[-1-n][1]
    return (a/b-1)*100 if b else None
def delta(rows,n=30):
    if len(rows)<=n:return None
    return rows[-1][1]-rows[-1-n][1]
def avg(rows,n):
    vals=[v for _,v in rows[-n:]]
    return sum(vals)/len(vals) if vals else None

# Score 0..100. Each component intentionally uses transparent thresholds.
def clamp(x): return max(0,min(100,x))
def band(v, low, high, reverse=False):
    if v is None:return 50
    x=(v-low)/(high-low)*100
    return clamp(100-x if reverse else x)

def score_metric(name, rows):
    _,v=last(rows)
    if v is None:return 50
    ch=delta(rows,30) or 0
    p=abs(pct(rows,30) or 0)
    if name=="Unemployment":
        # Level and acceleration. 4.0 is benign, 5.0+ increasingly concerning.
        return clamp(25 + (v-4.0)*35 + max(0,ch)*70)
    if name=="HY Credit Spread":
        return clamp(10 + (v-2.5)*18 + max(0,ch)*25)
    if name=="IG Credit Spread":
        return clamp(10 + (v-0.7)*42 + max(0,ch)*30)
    if name=="WTI Crude":
        # Oil is dangerous when it is both high and rising quickly.
        return clamp(15 + max(0,v-75)*1.5 + max(0,p-5)*3)
    if name=="DXY":
        # Strong/rapid USD tightening can stress global liquidity; falling USD is not automatically benign.
        return clamp(30 + max(0,v-100)*4 + max(0,ch)*2)
    if name=="10Y Treasury":
        return clamp(20 + max(0,v-4.0)*28 + max(0,ch)*12)
    if name=="30Y Treasury":
        return clamp(25 + max(0,v-4.5)*25 + max(0,ch)*12)
    return 50

def curve_rows(a,b):
    # Align by date.
    bm={d:v for d,v in b}
    return [(d,va-bm[d]) for d,va in a if d in bm]

def metric(name, rows, unit="", signal="", dec=2, heat=None):
    d,v=last(rows); h=score_metric(name,rows) if heat is None else heat
    return {"name":name,"display":"—" if v is None else f"{v:.{dec}f}","unit":unit,
            "heat":round(h),"label":"Normal" if h<25 else "Watch" if h<50 else "Elevated" if h<70 else "Stress",
            "signal":signal,"change_pct":None if pct(rows) is None else round(pct(rows),2),
            "date":d,"history":hist(rows)}

# Derived indicators
rates2,rates10,rates20,rates30=[series[x] for x in ["DGS2","DGS10","DGS20","DGS30"]]
curve10_2=curve_rows(rates10,rates2)
curve30_10=curve_rows(rates30,rates10)

# Sahm Rule: current 3-month average unemployment minus lowest 3-month average in prior 12 months.
u=series["UNRATE"]; uv=[v for _,v in u]
sahm_rows=[]
for i in range(14,len(uv)):
    cur=sum(uv[i-2:i+1])/3
    prior=[sum(uv[j-2:j+1])/3 for j in range(i-14,i)]
    sahm_rows.append((u[i][0],max(0,cur-min(prior))))
sahm=last(sahm_rows)[1] if sahm_rows else None
sahm_heat=clamp((sahm or 0)*120)

# Bucket scores
infl=score_metric("WTI Crude",series["DCOILWTICO"])
rates=0.45*score_metric("10Y Treasury",rates10)+0.55*score_metric("30Y Treasury",rates30)
labor=0.65*score_metric("Unemployment",u)+0.35*sahm_heat
credit=0.70*score_metric("HY Credit Spread",series["BAMLH0A0HYM2"])+0.30*score_metric("IG Credit Spread",series["BAMLC0A0CM"])
usd=score_metric("DXY",series["DXY"])

# Credit/labor deserve more weight for recession detection.
score=round(0.18*infl+0.23*rates+0.25*labor+0.26*credit+0.08*usd)

def regime(s):
    if s<25:return "🟢 Low heat — Goldilocks","Macro conditions are broadly benign. The main objective is to watch for deterioration in direction, not react to isolated readings."
    if s<50:return "🟡 Elevated — Watch","Some pressure is building, but the dashboard is not showing a broad recession/financial-stress regime. Watch credit and labor confirmation."
    if s<70:return "🟠 High heat — Defensive","Multiple indicators are becoming restrictive or fragile. Risk management should increase until credit/labor stabilize."
    return "🔴 Stress — Recession risk","Broad macro or financial stress is present. Credit and labor deterioration are high-priority signals."

reg,desc=regime(score)

# Portfolio posture is intentionally conservative and qualitative.
if score<25:
    posture=("🟢 Risk-on / normal","Maintain strategic allocation. No macro reason from this dashboard alone to make a large defensive move.",
             [("Equities","Normal"),("Gold","Core / neutral"),("BTC","Risk-on"),("Bonds","Neutral"),("Cash","Normal")])
elif score<50:
    posture=("🟡 Neutral / selective","Keep strategic exposure, but avoid increasing risk aggressively while heat is elevated. Prefer liquidity and quality.",
             [("Equities","Hold / selective"),("Gold","Hold"),("BTC","Neutral"),("Bonds","Neutral"),("Cash","Build modestly")])
elif score<70:
    posture=("🟠 Defensive tilt","Reduce concentration and speculative risk. Favor quality, duration when recession pressure is rising, gold, and a larger liquidity buffer.",
             [("Equities","Defensive"),("Gold","Add / hold"),("BTC","Reduce / hedge"),("Bonds","Add selectively"),("Cash","Build")])
else:
    posture=("🔴 Capital preservation","Treat this as a risk-control regime. Reassess leverage and concentrated risk; preserve liquidity until credit/labor improve.",
             [("Equities","Defensive"),("Gold","Core / add"),("BTC","Minimize risk"),("Bonds","Quality / duration"),("Cash","High")])

# Alerts based on the actual data, not just score.
alerts=[]
def add_alert(title,text,priority):
    alerts.append((priority,title,text))

hy=last(series["BAMLH0A0HYM2"])[1]; hy30=delta(series["BAMLH0A0HYM2"])
un=last(u)[1]; un30=delta(u)
wti=last(series["DCOILWTICO"])[1]; wti30=pct(series["DCOILWTICO"])
dxy=last(series["DXY"])[1]; dxy30=pct(series["DXY"])
y30=last(rates30)[1]; y30d=delta(rates30)

if hy30 is not None and hy30>0.40:add_alert("Credit is widening",f"HY spread is up {hy30:.2f} percentage points over 30 days. This is a higher-priority recession warning.",1)
elif hy is not None and hy>5:add_alert("Credit is elevated",f"HY spread is {hy:.2f}%. Watch for further widening and confirmation from labor.",2)
else:add_alert("Credit is contained",f"HY spread is {hy:.2f}% and has not shown a major 30-day widening.",4)

if un30 is not None and un30>0.30:add_alert("Labor is deteriorating",f"Unemployment is up {un30:.2f} percentage points over the latest 30-day/monthly observation window.",1)
elif sahm is not None and sahm>=0.50:add_alert("Sahm Rule triggered",f"Sahm Rule is {sahm:.2f}pp, above the classic 0.50pp recession threshold.",1)
else:add_alert("Labor has not confirmed recession",f"Unemployment is {un:.1f}% and Sahm Rule is {sahm:.2f}pp.",4)

if y30 is not None and y30d is not None and y30>5 and y30d>0.20:add_alert("Long-end rates are hot",f"30Y is {y30:.2f}% and up {y30d:.2f}pp over 30 days.",2)
else:add_alert("Long-end rates are the watch point",f"30Y Treasury is {y30:.2f}%; monitor term premium and fiscal/inflation expectations.",4)

if wti30 is not None and wti30>10:add_alert("Oil shock risk",f"WTI is up {wti30:.1f}% over 30 days. A sustained energy move can revive inflation pressure.",2)
else:add_alert("Oil is not a major shock signal",f"WTI is ${wti:.2f}/bbl with a 30-day move of {wti30:.1f}%.",4)

if dxy30 is not None and dxy30>3:add_alert("USD tightening signal",f"DXY is up {dxy30:.1f}% over 30 days. Combine with credit and yields to assess global liquidity stress.",2)
else:add_alert("USD is a context signal",f"DXY is {dxy:.2f}; interpret its direction alongside yields and credit.",4)

alerts=sorted(alerts,key=lambda x:x[0])[:4]

out={
 "updated":datetime.now(timezone.utc).isoformat(),
 "score":score,
 "accent":"#32d296" if score<25 else "#f5c451" if score<50 else "#fb923c" if score<70 else "#f87171",
 "regime":reg,"regimeDesc":desc,
 "chips":[f"Rates {round(rates)}/100",f"Credit {round(credit)}/100",f"Labor {round(labor)}/100",f"Oil {round(infl)}/100",f"DXY {round(usd)}/100"],
 "gauges":[{"name":"Inflation / oil","score":round(infl)},{"name":"Rates / term premium","score":round(rates)},{"name":"Labor / recession","score":round(labor)},{"name":"Credit stress","score":round(credit)},{"name":"USD / liquidity","score":round(usd)}],
 "posture":{"title":posture[0],"text":posture[1],"items":[{"name":a,"value":b} for a,b in posture[2]]},
 "alerts":[{"title":a[1],"text":a[2]} for a in alerts],
 "rates":[
    metric("2Y Treasury",rates2,"%", "Front-end policy expectations; rising rapidly can indicate tighter expected policy.",2),
    metric("10Y Treasury",rates10,"%", "Benchmark long-term rate; combines real-rate, inflation and term-premium pressure.",2),
    metric("20Y Treasury",rates20,"%", "Long-duration fiscal/inflation pressure.",2),
    metric("30Y Treasury",rates30,"%", "Long-term inflation/fiscal credibility and term premium.",2),
    metric("10Y − 2Y",curve10_2,"pp","Curve context; positive does not automatically mean bullish or bearish.",2,heat=clamp(25+max(0,abs(last(curve10_2)[1]-0.5))*20)),
    metric("30Y − 10Y",curve30_10,"pp","Long-end term-premium signal.",2,heat=clamp(25+max(0,last(curve30_10)[1]-0.3)*80))
 ],
 "macro":[
    metric("WTI Crude",series["DCOILWTICO"],"$/bbl","Oil is most concerning when both level and rate of change are high.",2),
    metric("Unemployment",u,"%","Labor deterioration is more important than a single unemployment level.",1),
    {"name":"Sahm Rule","display":f"{sahm:.2f}" if sahm is not None else "—","unit":"pp","heat":round(sahm_heat),"label":"Normal" if sahm_heat<25 else "Watch" if sahm_heat<50 else "Elevated" if sahm_heat<70 else "Stress","signal":"Classic recession threshold is 0.50pp.","change_pct":None,"date":last(sahm_rows)[0] if sahm_rows else None,"history":hist(sahm_rows)},
    metric("HY Credit Spread",series["BAMLH0A0HYM2"],"%","High-yield spread is one of the highest-priority financial-stress gauges.",2),
    metric("IG Credit Spread",series["BAMLC0A0CM"],"%","Investment-grade spread provides a broader credit-stress check.",2),
    metric("DXY",series["DXY"],"","USD direction changes global financial conditions; interpret jointly with rates and credit.",2)
 ]
}
print(json.dumps(out,indent=2))
