# 🏅 Gold FVG Signal Bot

Monitors **XAUUSD (Gold)** for ICT-style FVG + IFVG trade setups and sends **two-stage Telegram alerts**. Runs automatically on **GitHub Actions** every 5 minutes — no server needed.

---

## 📡 Strategy Logic

```
1H Chart  →  Detect Bearish / Bullish FVG
                ↓
          Price enters 1H FVG zone
                ↓
        ⚡ ALERT 1 sent via Telegram
                ↓
    Scan 5M + 3M for IFVGs inside the 1H FVG
    (IFVG must be within 16 pips of swing high/low)
                ↓
     Price closes a candle through the IFVG
                ↓
        Check RR ≥ 1.75  →  else SKIP
                ↓
        🏅 ALERT 2 sent via Telegram
           A+ if both 3M + 5M IFVGs found
           B+ if only one timeframe IFVG found
```

---

## 📱 Telegram Alert Examples

**Alert 1 — Zone Entry:**
```
⚡ ALERT 1 — Price Entered 1H FVG
2026-03-21 14:00 UTC

🔴 Direction: BEARISH
📦 1H FVG Zone: $4,586.00 – $4,600.00
💰 Current Price: $4,592.50

👀 Watching for 3M / 5M IFVG confirmation near swing point…
```

**Alert 2 — Entry Signal:**
```
🏅 ALERT 2 — ENTRY SIGNAL  |  🏆 A+ SETUP
2026-03-21 14:15 UTC

Direction: SHORT 🔴

📍 Entry:  $4,592.50
🛑 SL:     $4,601.00  (8.5 pips)
🎯 TP:     $4,577.50  (15.0 pips)
📊 RR:     1.76R

📦 1H FVG:  $4,586.00 – $4,600.00
✅ 5M IFVG: $4,591.00 – $4,595.00
✅ 3M IFVG: $4,590.50 – $4,594.00
```

---

## 🚀 Setup Guide

### 1. Create a Telegram Bot
1. Message **@BotFather** on Telegram → `/newbot`
2. Copy your **Bot Token**
3. Start a chat with your bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Send any message to the bot, refresh the URL, copy the **`chat.id`**

### 2. Add GitHub Secrets
Go to: **Repo → Settings → Secrets and variables → Actions**

| Secret Name | Value |
|---|---|
| `TELEGRAM_TOKEN` | Your BotFather token |
| `TELEGRAM_CHAT_ID` | Your numeric chat ID |

### 3. Push to GitHub
```bash
git init
git add .
git commit -m "Gold FVG bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

The workflow runs every **5 minutes on weekdays (Mon–Fri, 6 AM–10 PM UTC)**.

---

## ⚙️ Configuration (`gold_bot.py`)

```python
PIP              = 0.10   # 1 pip value for Gold
IFVG_MAX_PIPS    = 16     # Max distance: IFVG to swing high/low
MIN_RR           = 1.75   # Minimum risk-reward ratio
SWING_LOOKBACK   = 10     # Candles back to find swing high/low on 5M
FVG_LOOKBACK     = 50     # Only consider 1H FVGs from last 50 candles
```

## 📁 File Structure

```
├── gold_bot.py                     # Main bot logic
├── requirements.txt                # Python deps
├── README.md
└── .github/
    └── workflows/
        └── gold_bot.yml            # GitHub Actions schedule
```
