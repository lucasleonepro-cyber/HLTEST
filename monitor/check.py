#!/usr/bin/env python3
"""Surveillance Hyperliquid Earn : envoie une notification ntfy si la marge baisse
ou quand des HYPE arrivent sur le solde spot. Lecture seule, bibliothèque standard uniquement."""
import json, os, sys, time, urllib.request

API = "https://api.hyperliquid.xyz/info"
ADDR = os.environ.get("WALLET", "0x36693fd5fCfE40cb21438C4E1EC8088d4b89AD1c")
TOPIC = os.environ.get("NTFY_TOPIC", "")
THRESH = [float(x) for x in os.environ.get("THRESHOLDS", "25,20,15,10").split(",")]
PAGE = os.environ.get("PAGE_URL", "")
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
SUMMARY_HOUR_UTC = int(os.environ.get("SUMMARY_HOUR_UTC", "7"))

def q(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def notify(title, msg, prio="default", tags=""):
    print(f"[notif] {title} | {msg}")
    if not TOPIC:
        return
    headers = {"Title": title.encode("utf-8"), "Priority": prio, "Tags": tags}
    if PAGE:
        headers["Click"] = PAGE
    req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=msg.encode("utf-8"), headers=headers)
    urllib.request.urlopen(req, timeout=20).read()

def fr(x, d=2):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")

def main():
    bl = q({"type": "borrowLendUserState", "user": ADDR})
    res = {i: r for i, r in q({"type": "allBorrowLendReserveStates"})}
    spot = q({"type": "spotClearinghouseState", "user": ADDR})
    ds = q({"type": "delegatorSummary", "user": ADDR})

    coll_w = coll_l = coll_f = 0.0
    hype_coll = 0.0
    debt = 0.0
    for idx, st in bl.get("tokenToState", []):
        r = res.get(idx, {})
        ltv, px = float(r.get("ltv", 0)), float(r.get("oraclePx", 0))
        s, b = float(st["supply"]["value"]), float(st["borrow"]["value"])
        if s > 0 and ltv > 0:
            v = s * px
            coll_w += v * ltv; coll_l += v * (1 + ltv) / 2; coll_f += v * (ltv + (1 - ltv) * 2 / 3)
            if idx == 150: hype_coll = s
        debt += b * px
    P = float(res.get(150, {}).get("oraclePx", 0))
    hype_spot = sum(float(b["total"]) for b in spot.get("balances", []) if b["coin"] == "HYPE")
    pending = float(ds.get("totalPendingWithdrawal", 0))

    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f: state = json.load(f)
    new = dict(state)

    if debt > 0 and hype_coll > 0:
        liq_p = debt / (hype_coll * 0.825)
        liq_f = debt / (hype_coll * (0.65 + 0.35 * 2 / 3))
        margin = (1 - liq_p / P) * 100
        hf = coll_w / debt * 100
        # niveau = plus petit seuil franchi
        level = None
        for t in sorted(THRESH):
            if margin < t: level = t; break
        prev = state.get("level")
        # hystérésis : on ne « remonte » de niveau que si la marge dépasse le seuil précédent de 3 points
        if prev is not None and level is not None and level > prev and margin < prev + 3:
            level = prev
        if prev is not None and level is None and margin < max(THRESH) + 3:
            level = max(THRESH) if prev < max(THRESH) else prev
        line = f"HYPE {fr(P)} $ · marge {fr(margin,1)} % · liq. partielle {fr(liq_p)} $ · totale {fr(liq_f)} $ · HF {fr(hf,0)} %"
        if bl.get("health") in ("marketLiquidatable", "backstopLiquidatable") or margin <= 0:
            if state.get("liq") != True:
                notify("🚨 Liquidation en cours", line, "max", "rotating_light")
            new["liq"] = True
        else:
            new["liq"] = False
        if level is not None and (prev is None or level < prev):
            notify(f"⚠️ Marge sous {fr(level,0)} %", line, "high" if level <= 15 else "default", "warning")
        if level is None and prev is not None:
            notify("✅ Marge revenue au-dessus de " + fr(max(THRESH),0) + " %", line, "low", "white_check_mark")
        new["level"] = level
        print(line)
    else:
        new["level"] = None
        line = f"HYPE {fr(P)} $ · aucun emprunt"
        print(line)

    # arrivée de HYPE sur le spot
    prev_spot = state.get("hype_spot")
    if prev_spot is not None and hype_spot > prev_spot + 0.5:
        notify("🎉 HYPE arrivés sur ton solde spot", f"{fr(hype_spot)} HYPE disponibles. Dépose-les en garantie (Earn → Supply) pour qu'ils protègent.", "high", "tada")
    new["hype_spot"] = hype_spot
    new["pending"] = pending

    # résumé quotidien
    now = time.gmtime()
    today = time.strftime("%Y-%m-%d", now)
    if now.tm_hour == SUMMARY_HOUR_UTC and state.get("summary_day") != today:
        notify("📊 Point du jour Hyperliquid", line + (f" · {fr(pending)} HYPE en déstaking" if pending > 0 else ""), "low", "bar_chart")
        new["summary_day"] = today

    if new != state:
        with open(STATE_FILE, "w") as f: json.dump(new, f, indent=1)
        print("state changed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Erreur :", e); sys.exit(1)
