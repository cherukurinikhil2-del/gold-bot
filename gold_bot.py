"""
Gold FVG Signal Bot
====================
Strategy:
  1. Detect bearish/bullish FVGs on 1H chart (last 30 hours only)
  2. ALERT 1  when price enters a 1H FVG zone (FVG permanently retired after)
  3. Scan 5M chart for IFVG inside FVG, within 16 pips of recent swing high/low
  4. ALERT 2  when price closes candle through the 5M IFVG (A+ entry signal)
     - SL = most recent swing high/low on 5M
     - TP = next structural swing, capped at 2R, skipped if < 1.7R
  5. ALERT 3  when price hits TP or SL (trade closed notification)
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TICKER           = "GC=F"
PIP              = 0.10
IFVG_MAX_PIPS    = 16
MIN_RR           = 1.7
MAX_RR           = 2.0
SWING_LOOKBACK   = 10
FVG_MAX_AGE_HRS  = 30
STATE_FILE       = "bot_state.json"

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram not configured:\n")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print("✅ Telegram sent.")
        else:
            print(f"❌ Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"alerted_fvg": [], "alerted_zone_entered": [], "alerted_entry": [], "open_trades": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def zone_key(fvg: dict) -> str:
    return f"{fvg['top']:.2f}_{fvg['bottom']:.2f}_{fvg['direction']}"


# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def fetch(interval: str, period: str) -> pd.DataFrame:
    df = yf.download(TICKER, interval=interval, period=period, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for interval={interval}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df.dropna()


# ─────────────────────────────────────────────
# FVG DETECTION
# ─────────────────────────────────────────────

def detect_fvgs(df: pd.DataFrame, direction: str) -> list[dict]:
    fvgs  = []
    highs = df["High"].values
    lows  = df["Low"].values
    times = df.index
    for i in range(2, len(df)):
        if direction == "bearish" and lows[i - 2] > highs[i]:
            fvgs.append({"direction": direction, "top": float(lows[i - 2]),
                         "bottom": float(highs[i]), "time": str(times[i]), "index": i})
        elif direction == "bullish" and highs[i - 2] < lows[i]:
            fvgs.append({"direction": direction, "top": float(lows[i]),
                         "bottom": float(highs[i - 2]), "time": str(times[i]), "index": i})
    return fvgs


# ─────────────────────────────────────────────
# IFVG DETECTION
# ─────────────────────────────────────────────

def detect_ifvgs(df: pd.DataFrame) -> list[dict]:
    ifvgs  = []
    closes = df["Close"].values
    times  = df.index
    for direction in ["bullish", "bearish"]:
        for fvg in detect_fvgs(df, direction):
            idx = fvg["index"]
            for j in range(idx + 1, len(df)):
                if direction == "bullish" and closes[j] < fvg["bottom"]:
                    ifvgs.append({"direction": "bearish_ifvg", "top": fvg["top"],
                                  "bottom": fvg["bottom"], "flip_time": str(times[j]), "flip_index": j})
                    break
                elif direction == "bearish" and closes[j] > fvg["top"]:
                    ifvgs.append({"direction": "bullish_ifvg", "top": fvg["top"],
                                  "bottom": fvg["bottom"], "flip_time": str(times[j]), "flip_index": j})
                    break
    return ifvgs


# ─────────────────────────────────────────────
# SWING HIGH / LOW
# ─────────────────────────────────────────────

def swing_high(df: pd.DataFrame) -> float:
    return float(df["High"].iloc[-SWING_LOOKBACK:].max())

def swing_low(df: pd.DataFrame) -> float:
    return float(df["Low"].iloc[-SWING_LOOKBACK:].min())

def next_swing_low(df: pd.DataFrame, below: float) -> float:
    for v in df["Low"].values[::-1]:
        if float(v) < below - 5 * PIP:
            return float(v)
    return float(df["Low"].min())

def next_swing_high(df: pd.DataFrame, above: float) -> float:
    for v in df["High"].values[::-1]:
        if float(v) > above + 5 * PIP:
            return float(v)
    return float(df["High"].max())


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def ifvg_near_swing(ifvg: dict, swing_price: float) -> bool:
    mid  = (ifvg["top"] + ifvg["bottom"]) / 2
    return abs(mid - swing_price) / PIP <= IFVG_MAX_PIPS

def ifvg_overlaps_fvg(ifvg: dict, fvg: dict) -> bool:
    return ifvg["bottom"] <= fvg["top"] and ifvg["top"] >= fvg["bottom"]

def price_broke_ifvg(df: pd.DataFrame, ifvg: dict) -> bool:
    last_close = float(df["Close"].iloc[-1])
    if ifvg["direction"] == "bearish_ifvg":
        return last_close < ifvg["bottom"]
    elif ifvg["direction"] == "bullish_ifvg":
        return last_close > ifvg["top"]
    return False


# ─────────────────────────────────────────────
# TELEGRAM MESSAGES
# ─────────────────────────────────────────────

def msg_alert1(fvg: dict, price: float) -> str:
    arrow = "🔴" if fvg["direction"] == "bearish" else "🟢"
    lbl   = "BEARISH" if fvg["direction"] == "bearish" else "BULLISH"
    return (
        f"⚡ <b>ALERT 1 — Price Entered 1H FVG</b>\n"
        f"<code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n\n"
        f"{arrow} Direction: <b>{lbl}</b>\n"
        f"📦 1H FVG Zone: <b>${fvg['bottom']:,.2f} – ${fvg['top']:,.2f}</b>\n"
        f"💰 Current Price: <b>${price:,.2f}</b>\n\n"
        f"👀 <i>Watching for 5M IFVG confirmation near swing point…</i>"
    )

def msg_alert2(fvg, ifvg_5m, entry, sl, tp, rr, direction) -> str:
    dirlbl  = "SHORT 🔴" if direction == "short" else "LONG 🟢"
    sl_pips = abs(entry - sl) / PIP
    tp_pips = abs(tp - entry) / PIP
    return (
        f"🏆 <b>ALERT 2 — A+ ENTRY SIGNAL</b>\n"
        f"<code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n\n"
        f"Direction: <b>{dirlbl}</b>\n\n"
        f"📍 Entry:  <b>${entry:,.2f}</b>\n"
        f"🛑 SL:     <b>${sl:,.2f}</b>  ({sl_pips:.1f} pips)\n"
        f"🎯 TP:     <b>${tp:,.2f}</b>  ({tp_pips:.1f} pips)\n"
        f"📊 RR:     <b>{rr:.2f}R</b>\n\n"
        f"📦 1H FVG:  ${fvg['bottom']:,.2f} – ${fvg['top']:,.2f}\n"
        f"✅ 5M IFVG: ${ifvg_5m['bottom']:,.2f} – ${ifvg_5m['top']:,.2f}"
    )

def msg_alert3(trade: dict, result: str, current_price: float) -> str:
    if result == "tp":
        emoji  = "🎯"
        header = "TP HIT — TRADE WON"
        color  = "✅"
        pips   = abs(trade["tp"] - trade["entry"]) / PIP
    else:
        emoji  = "🛑"
        header = "SL HIT — TRADE CLOSED"
        color  = "❌"
        pips   = abs(trade["sl"] - trade["entry"]) / PIP

    dirlbl = "SHORT 🔴" if trade["direction"] == "short" else "LONG 🟢"
    return (
        f"{emoji} <b>ALERT 3 — {header}</b>\n"
        f"<code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n\n"
        f"{color} Result: <b>{'WIN' if result == 'tp' else 'LOSS'}</b>\n"
        f"Direction: <b>{dirlbl}</b>\n\n"
        f"📍 Entry:      <b>${trade['entry']:,.2f}</b>\n"
        f"🏁 Exit Price: <b>${current_price:,.2f}</b>\n"
        f"📏 Pips:       <b>{pips:.1f} pips</b>\n"
        f"📊 RR:         <b>{trade['rr']:.2f}R</b>"
    )


# ─────────────────────────────────────────────
# CHECK OPEN TRADES FOR TP / SL
# ─────────────────────────────────────────────

def check_open_trades(state: dict, df_5m: pd.DataFrame) -> dict:
    """Check each open trade — send Alert 3 if TP or SL has been hit."""
    if not state.get("open_trades"):
        return state

    still_open = []
    for trade in state["open_trades"]:
        direction = trade["direction"]
        sl        = trade["sl"]
        tp        = trade["tp"]
        entry_time = pd.Timestamp(trade.get("entry_time", df_5m.index[0]))
        if entry_time.tzinfo is None:
            entry_time = entry_time.tz_localize("UTC")

        # Only look at candles AFTER the entry time
        df_after = df_5m[df_5m.index > entry_time]
        
        outcome = None
        exit_price = None

        # Iterate forward through time (same as backtest)
        for t, c in df_after.iterrows():
            h, l = float(c["High"]), float(c["Low"])
            if direction == "short":
                if h >= sl:
                    outcome, exit_price = "loss", sl
                    break
                if l <= tp:
                    outcome, exit_price = "win", tp
                    break
            else:
                if l <= sl:
                    outcome, exit_price = "loss", sl
                    break
                if h >= tp:
                    outcome, exit_price = "win", tp
                    break

        if outcome == "loss":
            print(f"    🛑 SL hit on {direction} trade @ ${sl:.2f}")
            send_telegram(msg_alert3(trade, "sl", sl))
        elif outcome == "win":
            print(f"    🎯 TP hit on {direction} trade @ ${tp:.2f}")
            send_telegram(msg_alert3(trade, "tp", tp))
        else:
            still_open.append(trade)

    state["open_trades"] = still_open
    return state


# ─────────────────────────────────────────────
# MAIN STRATEGY
# ─────────────────────────────────────────────

def run() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*55}\n🤖 Gold FVG Bot — {now}\n{'='*55}")

    state = load_state()
    if "open_trades" not in state:
        state["open_trades"] = []
    if "alerted_zone_entered" not in state:
        state["alerted_zone_entered"] = []

    try:
        df_1h = fetch("1h", "30d")
        df_5m = fetch("5m", "5d")
    except Exception as e:
        send_telegram(f"⚠️ <b>Gold Bot Error</b>\nData fetch failed: {e}")
        return

    current_price = float(df_1h["Close"].iloc[-1])
    print(f"💰 Price: ${current_price:,.2f}")

    # ── Check open trades first ───────────────
    if state["open_trades"]:
        print(f"📋 Checking {len(state['open_trades'])} open trade(s)...")
        state = check_open_trades(state, df_5m)
        save_state(state)

    # ── Detect 1H FVGs within last 30 hours ──
    all_fvgs = detect_fvgs(df_1h, "bearish") + detect_fvgs(df_1h, "bullish")
    cutoff   = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=FVG_MAX_AGE_HRS)

    def fvg_ts(f):
        ts = pd.Timestamp(f["time"])
        return ts if ts.tzinfo else ts.tz_localize("UTC")

    recent = [f for f in all_fvgs if fvg_ts(f) >= cutoff]
    print(f"📦 {len(recent)} 1H FVGs within last 30 hours")

    for fvg in recent:
        fid = zone_key(fvg)

        # Skip if already produced a trade — 1 FVG = 1 trade
        if fid in state["alerted_fvg"]:
            print(f"  ↳ FVG {fvg['bottom']:.2f}–{fvg['top']:.2f} already traded — skipped")
            continue

        if not (fvg["bottom"] <= current_price <= fvg["top"]):
            continue

        print(f"  ✓ Price inside {fvg['direction']} FVG: {fvg['bottom']:.2f}–{fvg['top']:.2f}")

        # ALERT 1 — notify price entered FVG (but do NOT retire the FVG)
        if fid not in state["alerted_zone_entered"]:
            send_telegram(msg_alert1(fvg, current_price))
            state["alerted_zone_entered"].append(fid)
            state["alerted_zone_entered"] = state["alerted_zone_entered"][-100:]
            save_state(state)

        # Trade direction
        direction       = "short" if fvg["direction"] == "bearish" else "long"
        target_ifvg_dir = "bearish_ifvg" if direction == "short" else "bullish_ifvg"

        sh        = swing_high(df_5m)
        sl_ref    = swing_low(df_5m)
        swing_ref = sh if direction == "short" else sl_ref

        ifvgs_5m = [
            i for i in detect_ifvgs(df_5m)
            if i["direction"] == target_ifvg_dir
            and ifvg_overlaps_fvg(i, fvg)
            and ifvg_near_swing(i, swing_ref)
        ]

        if not ifvgs_5m:
            print("    ↳ No valid 5M IFVG found near swing — skip")
            continue

        best_5m = ifvgs_5m[-1]

        if not price_broke_ifvg(df_5m, best_5m):
            print("    ↳ 5M IFVG found but price hasn't broken it yet")
            continue

        # Entry / SL / TP
        entry = current_price

        if direction == "short":
            sl     = swing_high(df_5m) + (2 * PIP)
            raw_tp = next_swing_low(df_5m, entry)
        else:
            sl     = swing_low(df_5m) - (2 * PIP)
            raw_tp = next_swing_high(df_5m, entry)

        risk = abs(entry - sl)
        if risk == 0:
            print("    ↳ Risk = 0, skip")
            continue

        raw_rr = abs(raw_tp - entry) / risk
        if raw_rr < MIN_RR:
            print(f"    ↳ RR {raw_rr:.2f} < {MIN_RR} minimum — skip")
            continue

        if raw_rr > MAX_RR:
            tp = entry - (risk * MAX_RR) if direction == "short" else entry + (risk * MAX_RR)
            rr = MAX_RR
            print(f"    ↳ TP capped at 2R (swing was {raw_rr:.2f}R away)")
        else:
            tp = raw_tp
            rr  = raw_rr

        # ALERT 2
        eid = f"{fid}_{entry:.2f}"
        if eid in state["alerted_entry"]:
            print("    ↳ Entry alert already sent")
            continue

        send_telegram(msg_alert2(fvg, best_5m, entry, sl, tp, rr, direction))

        state["alerted_entry"].append(eid)
        state["alerted_entry"] = state["alerted_entry"][-50:]

        # NOW retire the FVG — trade confirmed (1 FVG = 1 trade)
        state["alerted_fvg"].append(fid)

        # Save open trade for TP/SL monitoring
        state["open_trades"].append({
            "entry_time": str(df_5m.index[-1]),
            "entry":      round(entry, 2),
            "sl":         round(sl, 2),
            "tp":         round(tp, 2),
            "rr":         round(rr, 2),
            "direction":  direction,
            "entry_id":   eid,
        })

        save_state(state)
        print(f"    ✅ A+ entry alert sent | RR={rr:.2f} | Trade saved for monitoring")


if __name__ == "__main__":
    run()
