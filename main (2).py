# FULL AI STOCK SCREENER BOT (FIX - SQLite Version)

# =========================
# IMPORT
# =========================
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from matplotlib.gridspec import GridSpec
import numpy as np
import os
import sqlite3
import json
from datetime import datetime

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ganti file JSON dengan SQLite
DB_FILE = "bot_data.db"

# =========================
# DATABASE SETUP (SQLite)
# =========================

def init_db():
    """Inisialisasi database SQLite - buat tabel jika belum ada"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Tabel watchlist: menyimpan daftar saham per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            PRIMARY KEY (user_id, ticker)
        )
    """)

    # Tabel fixed_entry_levels: menyimpan entry level FIX per user per ticker
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixed_entry_levels (
            user_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (user_id, ticker)
        )
    """)

    conn.commit()
    conn.close()


# =========================
# HELPER: WATCHLIST (menggantikan load/save JSON watchlist)
# =========================

def load_watchlist(user_id: str) -> list:
    """Ambil semua ticker dari watchlist user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY rowid",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def add_to_watchlist(user_id: str, ticker: str) -> bool:
    """Tambah ticker ke watchlist, return False jika sudah ada"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)",
            (user_id, ticker)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # sudah ada
    finally:
        conn.close()


def remove_from_watchlist(user_id: str, ticker: str) -> bool:
    """Hapus ticker dari watchlist, return False jika tidak ada"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def ticker_in_watchlist(user_id: str, ticker: str) -> bool:
    """Cek apakah ticker sudah ada di watchlist"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker)
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


# =========================
# HELPER: FIXED ENTRY LEVELS (menggantikan load/save JSON fixed_entry)
# =========================

def load_fixed_entries_user(user_id: str) -> dict:
    """Ambil semua entry level FIX untuk user tertentu"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticker, data FROM fixed_entry_levels WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for ticker, data_str in rows:
        try:
            result[ticker] = json.loads(data_str)
        except Exception:
            pass
    return result


def get_fixed_entry(user_id: str, ticker: str):
    """Ambil entry level FIX untuk 1 ticker"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT data FROM fixed_entry_levels WHERE user_id = ? AND ticker = ?",
        (user_id, ticker)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def save_fixed_entry(user_id: str, ticker: str, data: dict):
    """Simpan/update entry level FIX untuk 1 ticker"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO fixed_entry_levels (user_id, ticker, data)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, ticker) DO UPDATE SET data = excluded.data
        """,
        (user_id, ticker, json.dumps(data))
    )
    conn.commit()
    conn.close()


def delete_fixed_entry(user_id: str, ticker: str):
    """Hapus entry level FIX untuk 1 ticker"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM fixed_entry_levels WHERE user_id = ? AND ticker = ?",
        (user_id, ticker)
    )
    conn.commit()
    conn.close()


# =========================
# TEXT
# =========================
OPENING = """
🤖 AI STOCK SCREENER (IDX) - READY!

📊 COMMANDS:

/signal - Cari Saham (Umum)
/bsjp - Cari Saham (BSJP)
/bsjpplan BBCA - BSJP Trading Plan
/bsjptop - Top BSJP Auto Plan

/filter bullish - Trend Bullish
/filter breakout - Saham Breakout
/filter volume - Volume Spike
/filter reversal - Reversal Oversold

/watchlist - Kelola Watchlist
/rekapwl - Rekap Watchlist

/compare - Bandingkan Saham
/alert - Set Alert Harga
/daily - Daily Market Report

/topgainer - Top Gainer
/topvolume - Top Volume
/hotstock - Saham Potensial

/plan BBCA - Rencana Trading
/snr BBCA - Support Resistance
/ml BBCA - Analisis Tren AI

🆕 *CHART COMMANDS (NEW!)*:
/chart BBCA - Advanced Chart
/signals BBCA - Trading Signals Chart


/help - Tutorial
/id - Chat ID
"""

HELP_TEXT = """
📚 TUTORIAL

📊 *SCREENING:*
/signal → screening saham umum
/bsjp → screening saham BSJP
/bsjpplan BBCA → BSJP Trading Plan
/bsjptop → Top BSJP Auto Plan

🎯 *FILTER:*
/filter bullish
/filter breakout
/filter volume
/filter reversal

⭐ *WATCHLIST:*
/watchlist add BBCA
/watchlist remove BBCA
/watchlist show
/rekapwl → rekap performa

📈 *ANALISIS:*
/compare BBCA BBRI
/plan BBCA → Advanced Trading Plan
/snr BBCA
/ml BBCA

🆕 *CHART BARU:*
/chart BBCA → Candlestick + MA + BB + RSI
/signals BBCA → Chart dengan sinyal trading


📊 *MARKET:*
/daily → Daily Market Report
/topgainer → Top Gainer
/topvolume → Top Volume
/hotstock → Saham Potensial

⚠️ DISCLAIMER: Bukan ajakan beli/jual. DYOR!
"""

DISCLAIMER = """
⚠️ DISCLAIMER

Bukan ajakan beli/jual.
DYOR & Manage Your Risk.
"""

# =========================
# HELPER
# =========================
def fix_yf_columns(df):

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df


# =========================
# LOAD TICKERS
# =========================
def load_tickers():

    try:

        df = pd.read_excel("saham.xlsx")

        tickers = (
            df["Kode"]
            .dropna()
            .astype(str)
            .tolist()
        )

        return [t + ".JK" for t in tickers]

    except:

        return [
            "BBCA.JK",
            "BBRI.JK",
            "BMRI.JK",
            "TLKM.JK",
            "ASII.JK",
            "BRMS.JK",
            "MDKA.JK",
            "ANTM.JK"
        ]


# =========================
# SIGNAL
# =========================
def run_screener():

    tickers = load_tickers()

    results = []

    data = yf.download(
        tickers,
        period="6mo",
        interval="1d",
        group_by='ticker',
        progress=False,
        threads=False
    )

    for ticker in tickers:

        try:

            if ticker not in data.columns.levels[0]:
                continue

            df = data[ticker].dropna()

            df = fix_yf_columns(df)

            df = df.apply(
                pd.to_numeric,
                errors='coerce'
            )

            df = df.dropna()

            if df.empty:
                continue

            if len(df) < 20:
                continue

            df["MA5"] = (
                df["Close"]
                .rolling(5)
                .mean()
            )

            df["MA20"] = (
                df["Close"]
                .rolling(20)
                .mean()
            )

            df["VOL_MA5"] = (
                df["Volume"]
                .rolling(5)
                .mean()
            )

            df["VOL_MA20"] = (
                df["Volume"]
                .rolling(20)
                .mean()
            )

            last = df.iloc[-1]

            price = float(last["Close"])
            volume = float(last["Volume"])
            ma5 = float(last["MA5"])
            ma20 = float(last["MA20"])
            vol_ma5 = float(last["VOL_MA5"])
            vol_ma20 = float(last["VOL_MA20"])

            info = yf.Ticker(ticker).info

            market_cap = info.get(
                "marketCap",
                0
            )

            cond1 = ma5 > ma20

            cond2 = (
                vol_ma5 >
                (1.2 * vol_ma20)
            )

            cond3 = price > 200

            cond4 = volume > 500000

            cond5 = (
                market_cap >
                1_000_000_000_000
            )

            if (
                cond1 and
                cond2 and
                cond3 and
                cond4 and
                cond5
            ):

                score = 0

                if cond1:
                    score += 1

                if cond2:
                    score += 1

                if price > ma20:
                    score += 1

                signal = (
                    "🔥 STRONG BUY"
                    if score == 3
                    else "✅ BUY"
                )

                results.append({
                    "ticker": ticker.replace(".JK", ""),
                    "price": int(price),
                    "volume": int(volume),
                    "signal": signal
                })

        except Exception as e:
            print(f"Error {ticker}: {e}")
            continue

    if not results:
        return "❌ Tidak ada saham sesuai signal"

    df_res = pd.DataFrame(results)

    df_res = df_res.sort_values(
        by="volume",
        ascending=False
    )

    msg = "🔥 SIGNAL SAHAM 🔥\n\n"

    for _, r in df_res.head(15).iterrows():

        msg += (
            f"{r['signal']}\n"
            f"{r['ticker']} | {r['price']}\n\n"
        )

    return msg

# =========================
# BSJP SCREENER
# =========================
def run_bsjp_screener():

    tickers = load_tickers()

    results = []

    tickers = tickers[:200]

    for ticker in tickers:

        try:

            df = yf.download(
                ticker,
                period="1mo",
                interval="1d",
                progress=False,
                threads=False
            )

            df = fix_yf_columns(df)

            df = df.dropna()

            if len(df) < 10:
                continue

            last = df.iloc[-1]

            prev = df.iloc[-2]

            price = float(
                last["Close"]
            )

            prev_price = float(
                prev["Close"]
            )

            volume = float(
                last["Volume"]
            )

            prev_volume = float(
                prev["Volume"]
            )

            ma5 = (
                df["Close"]
                .rolling(5)
                .mean()
                .iloc[-1]
            )

            value = (
                price *
                volume
            )

            c1 = (
                price >=
                (1.05 * prev_price)
            )

            c2 = (
                price >=
                float(ma5)
            )

            c3 = (
                volume >=
                (1.2 * prev_volume)
            )

            c4 = (
                value >=
                5_000_000_000
            )

            if c1 and c2 and c3 and c4:

                results.append({

                    "ticker":
                    ticker.replace(".JK",""),

                    "price":
                    round(price,2),

                    "change":
                    round(
                        (
                            (
                                price /
                                prev_price
                            ) - 1
                        ) * 100,
                        2
                    ),

                    "volume":
                    int(volume),

                    "value":
                    value
                })

        except:
            continue

    if not results:

        return (
            "❌ Tidak ada saham "
            "sesuai rules BSJP"
        )

    df_res = pd.DataFrame(results)

    df_res = df_res.sort_values(
        by="value",
        ascending=False
    )

    msg = (
        "🚀 BSJP SIGNAL\n\n"
    )

    for _, r in df_res.head(10).iterrows():

        msg += (
            f"🔥 {r['ticker']}\n"
            f"Price : {r['price']}\n"
            f"Change : {r['change']}%\n"
            f"Volume : {r['volume']:,}\n"
            f"Value : "
            f"{round(r['value']/1e9,2)}B\n\n"
        )

    return msg

# =========================
# SECTOR MAP
# =========================
SECTOR_MAP = {

    "BANKING": [
        "BBCA.JK",
        "BBRI.JK",
        "BMRI.JK",
        "BBNI.JK"
    ],

    "TECH": [
        "GOTO.JK",
        "BUKA.JK",
        "DCII.JK"
    ],

    "ENERGY": [
        "ADRO.JK",
        "PTBA.JK",
        "MEDC.JK",
        "PGAS.JK"
    ],

    "HEALTH": [
        "MIKA.JK",
        "SILO.JK",
        "HEAL.JK"
    ],

    "CONSUMER": [
        "ICBP.JK",
        "INDF.JK",
        "MYOR.JK",
        "UNVR.JK"
    ],

    "PROPERTY": [
        "BSDE.JK",
        "PWON.JK",
        "CTRA.JK"
    ]
}


# =========================
# DAILY REPORT
# =========================
async def daily_cmd(update, context):

    await update.message.reply_text(
        "📊 Membuat Daily Market Report..."
    )

    sector_results = []

    for sector, tickers in SECTOR_MAP.items():

        changes = []

        for ticker in tickers:

            try:

                df = yf.download(
                    ticker,
                    period="5d",
                    progress=False
                )

                df = fix_yf_columns(df)

                df = df.dropna()

                if len(df) < 2:
                    continue

                last = float(
                    df["Close"].iloc[-1]
                )

                prev = float(
                    df["Close"].iloc[-2]
                )

                change = (
                    (
                        last / prev
                    ) - 1
                ) * 100

                changes.append(change)

            except:
                continue

        if len(changes) == 0:
            continue

        avg_change = round(
            np.mean(changes),
            2
        )

        sector_results.append({

            "sector":
            sector,

            "change":
            avg_change
        })

    sector_results = sorted(
        sector_results,
        key=lambda x: x["change"],
        reverse=True
    )

    market_avg = np.mean([
        x["change"]
        for x in sector_results
    ])

    sentiment = (
        "BULLISH 🟢"
        if market_avg > 0
        else "BEARISH 🔴"
    )

    msg = (
        "📊 DAILY MARKET REPORT\n\n"
    )

    msg += (
        f"📈 MARKET SENTIMENT : "
        f"{sentiment}\n\n"
    )

    msg += (
        "🔥 SECTOR PERFORMANCE\n\n"
    )

    for s in sector_results:

        emoji = (
            "🟢"
            if s["change"] > 0
            else "🔴"
        )

        msg += (
            f"{emoji} "
            f"{s['sector']} "
            f"{s['change']}%\n"
        )

    top_sector = sector_results[0]

    msg += (
        f"\n🚀 HOT SECTOR : "
        f"{top_sector['sector']}"
    )

    msg += (
        "\n\n🔥 HOT STOCK\n"
    )

    hot = run_bsjp_screener()

    msg += hot[:500]

    await update.message.reply_text(msg)

# =========================
# COMPARE SAHAM
# =========================
async def compare_cmd(update, context):

    if len(context.args) < 2:

        return await update.message.reply_text(
            "Contoh:\n"
            "/compare BBCA BBRI"
        )

    stock1 = (
        context.args[0]
        .upper() + ".JK"
    )

    stock2 = (
        context.args[1]
        .upper() + ".JK"
    )

    await update.message.reply_text(
        f"📊 Membandingkan "
        f"{stock1.replace('.JK','')} "
        f"vs "
        f"{stock2.replace('.JK','')}..."
    )

    def analyze(ticker):

        try:

            df = yf.download(
                ticker,
                period="6mo",
                interval="1d",
                progress=False,
                threads=False
            )

            df = fix_yf_columns(df)

            df = df.dropna()

            if len(df) < 50:

                return {
                    "price": 0,
                    "rsi": 0,
                    "macd_signal": "NO DATA",
                    "trend": "NO DATA",
                    "momentum": "NO DATA",
                    "score": 0,
                    "signal": "❌ NO DATA"
                }

            price = float(
                df["Close"].iloc[-1]
            )

            df["EMA20"] = (
                df["Close"]
                .ewm(span=20)
                .mean()
            )

            ema20 = float(
                df["EMA20"].iloc[-1]
            )

            delta = df["Close"].diff()

            gain = (
                delta.where(delta > 0, 0)
                .rolling(14)
                .mean()
            )

            loss = (
                -delta.where(delta < 0, 0)
                .rolling(14)
                .mean()
            )

            rs = gain / loss

            rsi = (
                100 -
                (
                    100 / (1 + rs)
                )
            )

            last_rsi = round(
                float(rsi.iloc[-1]),
                2
            )

            ema12 = (
                df["Close"]
                .ewm(span=12)
                .mean()
            )

            ema26 = (
                df["Close"]
                .ewm(span=26)
                .mean()
            )

            macd = ema12 - ema26

            signal_line = (
                macd
                .ewm(span=9)
                .mean()
            )

            macd_last = float(
                macd.iloc[-1]
            )

            signal_last = float(
                signal_line.iloc[-1]
            )

            macd_signal = (
                "Bullish 🟢"
                if macd_last > signal_last
                else "Bearish 🔴"
            )

            momentum = (
                "UP 🟢"
                if (
                    price >
                    float(df["Close"].iloc[-6])
                )
                else "DOWN 🔴"
            )

            trend = (
                "Bullish 🟢"
                if price > ema20
                else "Bearish 🔴"
            )

            score = 0

            if price > ema20:
                score += 1

            if last_rsi > 50:
                score += 1

            if macd_last > signal_last:
                score += 1

            if (
                price >
                float(df["Close"].iloc[-6])
            ):
                score += 1

            if score == 4:

                signal = "🔥 VERY STRONG"

            elif score == 3:

                signal = "✅ STRONG"

            elif score == 2:

                signal = "⚠️ NEUTRAL"

            elif score == 1:

                signal = "❌ WEAK"

            else:

                signal = "☠️ VERY WEAK"

            return {

                "price": round(price,2),

                "rsi": last_rsi,

                "macd_signal": macd_signal,

                "trend": trend,

                "momentum": momentum,

                "score": score,

                "signal": signal
            }

        except:

            return {

                "price": 0,

                "rsi": 0,

                "macd_signal": "ERROR",

                "trend": "ERROR",

                "momentum": "ERROR",

                "score": 0,

                "signal": "❌ ERROR"
            }

    s1 = analyze(stock1)

    s2 = analyze(stock2)

    if s1["score"] > s2["score"]:

        winner = stock1.replace(".JK","")

    elif s2["score"] > s1["score"]:

        winner = stock2.replace(".JK","")

    else:

        winner = "DRAW"

    msg = f"""
📊 COMPARE SAHAM

====================

🏢 {stock1.replace('.JK','')}

💰 Price : {s1['price']}
📈 RSI : {s1['rsi']}
📊 MACD : {s1['macd_signal']}
📉 Trend : {s1['trend']}
⚡ Momentum : {s1['momentum']}

🏆 Score : {s1['score']}/4
🎯 Signal : {s1['signal']}

====================

🏢 {stock2.replace('.JK','')}

💰 Price : {s2['price']}
📈 RSI : {s2['rsi']}
📊 MACD : {s2['macd_signal']}
📉 Trend : {s2['trend']}
⚡ Momentum : {s2['momentum']}

🏆 Score : {s2['score']}/4
🎯 Signal : {s2['signal']}

====================

🥇 WINNER :
{winner}
"""

    await update.message.reply_text(msg)

# =========================
# FILTER (DIPERKETAT)
# =========================
async def filter_cmd(update, context):

    if not context.args:
        return await update.message.reply_text(
            "📊 FILTER SAHAM (STRICT MODE)\n\n"
            "/filter bullish\n"
            "/filter breakout\n"
            "/filter volume\n"
            "/filter reversal\n\n"
            "Filter ketat:\n"
            "✓ Price > 500\n"
            "✓ Volume > 500.000\n"
            "✓ Minimal 50 data"
        )

    mode = context.args[0].lower()

    await update.message.reply_text(
        f"🔍 Scan filter {mode} (strict mode)..."
    )

    tickers = load_tickers()
    tickers = tickers[:100]

    results = []

    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                period="3mo",
                progress=False,
                threads=False
            )

            df = fix_yf_columns(df)
            df = df.dropna()

            if len(df) < 50:
                continue

            close = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2])
            volume = float(df["Volume"].iloc[-1])

            if close < 500:
                continue

            if volume < 500000:
                continue

            avg_volume_20 = df["Volume"].rolling(20).mean().iloc[-1]
            avg_volume_50 = df["Volume"].rolling(50).mean().iloc[-1]

            ma5 = df["Close"].rolling(5).mean().iloc[-1]
            ma20 = df["Close"].rolling(20).mean().iloc[-1]
            ma50 = df["Close"].rolling(50).mean().iloc[-1]

            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            last_rsi = round(float(rsi.iloc[-1]), 2)

            passed = False
            status = ""
            extra_info = ""

            if mode == "bullish":
                cond1 = ma5 > ma20 > ma50
                cond2 = close > ma50
                cond3 = close > ma20
                cond4 = last_rsi > 50
                cond5 = volume > avg_volume_20

                passed = cond1 and cond2 and cond3 and cond4 and cond5
                status = "BULLISH 🟢"
                extra_info = f"MA5>MA20>MA50 | RSI {last_rsi}"

            elif mode == "breakout":
                high20 = df["High"].rolling(20).max().iloc[-2]
                high50 = df["High"].rolling(50).max().iloc[-2]

                cond1 = close >= high20 * 0.995
                cond2 = close >= high50 * 0.99
                cond3 = volume > (1.5 * avg_volume_20)
                cond4 = volume > avg_volume_50

                passed = cond1 and cond2 and cond3 and cond4
                status = "BREAKOUT 🚀"
                extra_info = f"Res20: {int(high20)} | Vol: {volume/avg_volume_20:.1f}x"

            elif mode == "volume":
                vol_ratio_20 = volume / avg_volume_20 if avg_volume_20 > 0 else 1
                vol_ratio_50 = volume / avg_volume_50 if avg_volume_50 > 0 else 1

                cond1 = volume > (2.0 * avg_volume_20)
                cond2 = volume > (1.5 * avg_volume_50)
                cond3 = close > ma20

                passed = cond1 and cond2 and cond3
                status = "VOLUME SPIKE 🔥"
                extra_info = f"{vol_ratio_20:.1f}x avg20 | {vol_ratio_50:.1f}x avg50"

            elif mode == "reversal":
                cond1 = last_rsi < 35

                cond2 = close > df["Close"].rolling(5).mean().iloc[-2]
                cond3 = volume > avg_volume_20

                high20 = df["High"].rolling(20).max().iloc[-1]
                drop_pct = (high20 - close) / high20 * 100
                cond4 = drop_pct > 10

                passed = cond1 and cond2 and cond3 and cond4
                status = "REVERSAL 🔥"
                extra_info = f"RSI {last_rsi} | Turun {drop_pct:.1f}%"

            if passed:
                change = round(((close / prev_close) - 1) * 100, 2)

                results.append({
                    "ticker": ticker.replace(".JK", ""),
                    "price": round(close, 2),
                    "change": change,
                    "rsi": last_rsi,
                    "status": status,
                    "volume": int(volume),
                    "extra": extra_info
                })

        except Exception as e:
            print(f"Error {ticker}: {e}")
            continue

    if not results:
        msg = f"❌ TIDAK ADA SAHAM UNTUK FILTER {mode.upper()}\n\n"
        msg += "Filter ketat yang berlaku:\n"
        msg += "• Harga minimal Rp500\n"
        msg += "• Volume minimal 500.000\n"

        if mode == "bullish":
            msg += "• MA5 > MA20 > MA50\n• Harga > MA50\n• RSI > 50\n"
        elif mode == "breakout":
            msg += "• Break resistance 20h & 50h\n• Volume > 1.5x rata-rata\n"
        elif mode == "volume":
            msg += "• Volume > 2x rata-rata 20h\n• Harga > MA20\n"
        elif mode == "reversal":
            msg += "• RSI < 35\n• Volume konfirmasi\n• Turun > 10%\n"

        return await update.message.reply_text(msg)

    if mode == "bullish":
        results = sorted(results, key=lambda x: x["change"], reverse=True)
    elif mode == "breakout":
        results = sorted(results, key=lambda x: x["volume"], reverse=True)
    elif mode == "volume":
        results = sorted(results, key=lambda x: x["volume"], reverse=True)
    elif mode == "reversal":
        results = sorted(results, key=lambda x: x["rsi"])

    msg = f"📊 FILTER {mode.upper()} (STRICT MODE)\n"
    msg += f"{'='*40}\n\n"

    for i, r in enumerate(results[:15], 1):
        emoji = "🟢" if r["change"] >= 0 else "🔴"

        msg += f"{i}. {emoji} *{r['ticker']}*\n"
        msg += f"   Price: Rp{r['price']:,.0f} | {r['change']:+.2f}%\n"
        msg += f"   RSI: {r['rsi']} | Volume: {r['volume']:,}\n"
        msg += f"   📌 {r['status']}\n"

        if r.get('extra'):
            msg += f"   📊 {r['extra']}\n"

        msg += "\n"

    msg += f"{'='*40}\n"
    msg += f"📈 Total saham lolos: {len(results)}\n"
    msg += f"⚠️ DYOR sebelum mengambil keputusan"

    await update.message.reply_text(msg)


# =========================
# TOP GAINER
# =========================
async def topgainer_cmd(update, context):

    await update.message.reply_text(
        "🚀 Scan Top Gainer..."
    )

    tickers = load_tickers()

    results = []

    for ticker in tickers:

        try:

            df = yf.download(
                ticker,
                period="5d",
                progress=False
            )

            df = fix_yf_columns(df)

            df = df.dropna()

            last = float(
                df["Close"].iloc[-1]
            )

            prev = float(
                df["Close"].iloc[-2]
            )

            change = (
                (
                    last / prev
                ) - 1
            ) * 100

            results.append({

                "ticker":
                ticker.replace(".JK",""),

                "change":
                round(change,2)
            })

        except:
            continue

    df_res = pd.DataFrame(results)

    df_res = df_res.sort_values(
        by="change",
        ascending=False
    )

    msg = "🚀 TOP GAINER\n\n"

    for _, r in df_res.head(10).iterrows():

        msg += (
            f"{r['ticker']} "
            f"| {r['change']}%\n"
        )

    await update.message.reply_text(msg)


# =========================
# TOP VOLUME
# =========================
async def topvolume_cmd(update, context):

    await update.message.reply_text(
        "📊 Scan Top Volume..."
    )

    tickers = load_tickers()

    results = []

    for ticker in tickers:

        try:

            df = yf.download(
                ticker,
                period="5d",
                progress=False
            )

            df = fix_yf_columns(df)

            df = df.dropna()

            volume = float(
                df["Volume"].iloc[-1]
            )

            results.append({

                "ticker":
                ticker.replace(".JK",""),

                "volume":
                volume
            })

        except:
            continue

    df_res = pd.DataFrame(results)

    df_res = df_res.sort_values(
        by="volume",
        ascending=False
    )

    msg = "📊 TOP VOLUME\n\n"

    for _, r in df_res.head(10).iterrows():

        msg += (
            f"{r['ticker']} "
            f"| {int(r['volume']):,}\n"
        )

    await update.message.reply_text(msg)


# =========================
# HOT STOCK
# =========================
async def hotstock_cmd(update, context):

    await update.message.reply_text(
        "🔥 Scan Hot Stock..."
    )

    signal = run_screener()

    bsjp = run_bsjp_screener()

    msg = (
        "🔥 HOT STOCK\n\n"
        "Gabungan Signal + BSJP\n\n"
    )

    msg += signal[:700]

    msg += "\n\n"

    msg += bsjp[:700]

    await update.message.reply_text(msg)


# =========================
# FIXED ENTRY LEVEL CALCULATOR
# =========================

def calculate_fixed_entry_levels(ticker_symbol):
    """
    Hitung 4 skenario entry SEKALI SAJA (saat pertama add)
    dan simpan FIX, TIDAK AKAN BERUBAH
    """
    try:
        df = yf.download(
            ticker_symbol,
            period="6mo",
            interval="1d",
            progress=False
        )

        df = fix_yf_columns(df)
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna()

        if df.empty or len(df) < 50:
            return None

        current_price = float(df["Close"].iloc[-1])

        atr = calculate_atr(df)

        sr = calculate_support_resistance_deep(df)

        entry_normal = current_price
        entry_pullback = sr["S1"] if sr["S1"] < current_price else current_price * 0.98
        entry_deep = sr["S2"] if sr["S2"] < current_price else current_price * 0.96
        breakout_level = sr["R1"] + (atr * 0.2)
        entry_breakout = breakout_level if breakout_level > current_price else current_price * 1.02

        def calculate_scenario_levels(entry, atr, sr, is_breakout=False):
            support_levels = [sr["S1"], sr["S2"], sr["S3"], sr["S4"]]

            if is_breakout:
                support_below = [s for s in support_levels if s < entry]
                nearest_support = max(support_below) if support_below else entry * 0.97
                stop_loss = nearest_support - (atr * 0.2)
            else:
                supports_below = [s for s in support_levels if s < entry]
                nearest_support = max(supports_below) if supports_below else entry * 0.97
                stop_loss = nearest_support - (atr * 0.2)

            risk_abs = entry - stop_loss
            risk_pct = (risk_abs / entry) * 100 if entry > 0 else 5
            tp1_pct = max(3.0, risk_pct)
            tp2_pct = tp1_pct * 2
            tp3_pct = tp1_pct * 3

            return {
                "entry": round(entry, 0),
                "sl": round(stop_loss, 0),
                "risk_pct": round(risk_pct, 1),
                "tp1_pct": round(tp1_pct, 1),
                "tp2_pct": round(tp2_pct, 1),
                "tp3_pct": round(tp3_pct, 1),
                "tp1": round(entry * (1 + tp1_pct/100), 0),
                "tp2": round(entry * (1 + tp2_pct/100), 0),
                "tp3": round(entry * (1 + tp3_pct/100), 0)
            }

        return {
            "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price_at_create": round(current_price, 0),
            "scenarios": {
                "normal": {
                    "name": "NORMAL",
                    "display_name": "📊 NORMAL",
                    "key": "normal",
                    "entry": entry_normal,
                    **calculate_scenario_levels(entry_normal, atr, sr, False)
                },
                "pullback": {
                    "name": "PULLBACK (S1)",
                    "display_name": "📉 PULLBACK (S1)",
                    "key": "pullback",
                    "entry": entry_pullback,
                    **calculate_scenario_levels(entry_pullback, atr, sr, False)
                },
                "deep": {
                    "name": "DEEP (S2)",
                    "display_name": "🔻 DEEP (S2)",
                    "key": "deep",
                    "entry": entry_deep,
                    **calculate_scenario_levels(entry_deep, atr, sr, False)
                },
                "breakout": {
                    "name": "BREAKOUT",
                    "display_name": "🚀 BREAKOUT",
                    "key": "breakout",
                    "entry": entry_breakout,
                    **calculate_scenario_levels(entry_breakout, atr, sr, True)
                }
            }
        }
    except Exception as e:
        print(f"Error in calculate_fixed_entry_levels: {e}")
        return None


# =========================
# TRADING PLAN HELPERS
# =========================

def calculate_atr(df, period=14):
    """Calculate Average True Range"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    return atr.iloc[-1]

def calculate_support_resistance_deep(df):
    """Find support dan resistance dengan level lebih dalam"""
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    pivot = (high[-1] + low[-1] + close[-1]) / 3
    range_hl = high[-1] - low[-1]

    r1 = pivot + range_hl * 0.382
    r2 = pivot + range_hl * 0.618
    r3 = pivot + range_hl * 1.000
    r4 = pivot + range_hl * 1.382
    r5 = pivot + range_hl * 1.618

    s1 = pivot - range_hl * 0.382
    s2 = pivot - range_hl * 0.618
    s3 = pivot - range_hl * 1.000
    s4 = pivot - range_hl * 1.382

    high_20 = max(high[-20:])
    high_50 = max(high[-50:]) if len(high) >= 50 else high_20

    return {
        "R1": round(r1, 2), "R2": round(r2, 2), "R3": round(r3, 2),
        "R4": round(r4, 2), "R5": round(r5, 2),
        "S1": round(s1, 2), "S2": round(s2, 2), "S3": round(s3, 2),
        "S4": round(s4, 2),
        "Pivot": round(pivot, 2),
        "High20": round(high_20, 2),
        "High50": round(high_50, 2)
    }

def calculate_confidence(df, current_price, sr, volume_confirmation):
    """Hitung confidence score (0-100)"""
    confidence = 50

    ma5 = df["Close"].rolling(5).mean().iloc[-1]
    ma20 = df["Close"].rolling(20).mean().iloc[-1]
    ma50 = df["Close"].rolling(50).mean().iloc[-1]

    if ma5 > ma20 > ma50:
        confidence += 20
    elif ma5 > ma20:
        confidence += 10

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = float(rsi.iloc[-1])

    if 40 <= last_rsi <= 60:
        confidence += 15
    elif 30 <= last_rsi <= 70:
        confidence += 5

    volume = float(df["Volume"].iloc[-1])
    avg_volume = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ratio = volume / avg_volume if avg_volume > 0 else 1

    if vol_ratio > 1.5:
        confidence += 15
    elif vol_ratio > 1.2:
        confidence += 10

    if current_price <= sr["S1"] * 1.02:
        confidence += 10

    return min(confidence, 100)

def advanced_trading_plan(ticker_symbol):
    """
    Trading plan dengan RISK 3% dari entry
    Stop Loss di bawah support terdekat dari entry
    4 SKENARIO ENTRY: Normal, Pullback, Deep, BREAKOUT
    TP hanya 3 LEVEL dengan TP1 minimal 3%
    """
    try:
        df = yf.download(
            ticker_symbol,
            period="6mo",
            interval="1d",
            progress=False
        )

        df = fix_yf_columns(df)
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna()

        if df.empty or len(df) < 50:
            return "❌ Data tidak cukup untuk analisis akurat"

        current_price = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])

        atr = calculate_atr(df)
        sr = calculate_support_resistance_deep(df)

        is_breakout = current_price > sr["R1"]
        is_strong_breakout = current_price > sr["R2"]

        volume = float(df["Volume"].iloc[-1])
        avg_volume_20 = df["Volume"].rolling(20).mean().iloc[-1]
        volume_confirmation = volume > (1.3 * avg_volume_20)

        confidence = calculate_confidence(df, current_price, sr, volume_confirmation)

        entry1 = current_price
        entry2 = sr["S1"] if sr["S1"] < current_price else current_price * 0.98
        entry3 = sr["S2"] if sr["S2"] < current_price else current_price * 0.96
        breakout_level = sr["R1"] + (atr * 0.2)
        entry4 = breakout_level if breakout_level > current_price else current_price * 1.02

        support_levels = [sr["S1"], sr["S2"], sr["S3"], sr["S4"]]

        def get_stop_loss(entry_price, support_levels, is_breakout_entry=False):
            if is_breakout_entry:
                support_below = [s for s in support_levels if s < entry_price]
                if support_below:
                    nearest_support = max(support_below)
                    stop_loss = nearest_support - (atr * 0.2)
                else:
                    stop_loss = entry_price * 0.97
            else:
                supports_below = [s for s in support_levels if s < entry_price]
                if supports_below:
                    nearest_support = max(supports_below)
                    stop_loss = nearest_support - (atr * 0.2)
                else:
                    stop_loss = entry_price * 0.97

            return stop_loss, entry_price - stop_loss

        sl1, risk1_abs = get_stop_loss(entry1, support_levels, False)
        sl2, risk2_abs = get_stop_loss(entry2, support_levels, False)
        sl3, risk3_abs = get_stop_loss(entry3, support_levels, False)
        sl4, risk4_abs = get_stop_loss(entry4, support_levels, True)

        risk1_pct = (risk1_abs / entry1) * 100
        risk2_pct = (risk2_abs / entry2) * 100
        risk3_pct = (risk3_abs / entry3) * 100
        risk4_pct = (risk4_abs / entry4) * 100

        account_size = 100_000_000
        target_risk_pct = 3.0

        max_risk_amount = account_size * (target_risk_pct / 100)

        def calculate_position_size(risk_abs):
            if risk_abs <= 0:
                return 0
            return int(max_risk_amount / risk_abs)

        pos1 = calculate_position_size(risk1_abs)
        pos2 = calculate_position_size(risk2_abs)
        pos3 = calculate_position_size(risk3_abs)
        pos4 = calculate_position_size(risk4_abs)

        pos1 = max(pos1, 100) if pos1 > 0 else 0
        pos2 = max(pos2, 100) if pos2 > 0 else 0
        pos3 = max(pos3, 100) if pos3 > 0 else 0
        pos4 = max(pos4, 100) if pos4 > 0 else 0

        pos_value1 = pos1 * entry1
        pos_value2 = pos2 * entry2
        pos_value3 = pos3 * entry3
        pos_value4 = pos4 * entry4

        def calculate_tps(entry_price, risk_pct):
            risk_amount = entry_price * (risk_pct / 100)

            min_tp1_pct = max(3.0, risk_pct)
            tp1_amount = entry_price * (min_tp1_pct / 100)
            tp1 = entry_price + tp1_amount

            tp2_amount = tp1_amount * 2
            tp2 = entry_price + tp2_amount

            tp3_amount = tp1_amount * 3
            tp3 = entry_price + tp3_amount

            rr1 = tp1_amount / risk_amount if risk_amount > 0 else 0
            rr2 = tp2_amount / risk_amount if risk_amount > 0 else 0
            rr3 = tp3_amount / risk_amount if risk_amount > 0 else 0

            return {
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "tp3": round(tp3, 2),
                "tp1_pct": round(min_tp1_pct, 1),
                "tp2_pct": round(min_tp1_pct * 2, 1),
                "tp3_pct": round(min_tp1_pct * 3, 1),
                "rr1": round(rr1, 1),
                "rr2": round(rr2, 1),
                "rr3": round(rr3, 1),
                "risk_amount": round(risk_amount, 2),
                "risk_pct": risk_pct
            }

        tps1 = calculate_tps(entry1, risk1_pct)
        tps2 = calculate_tps(entry2, risk2_pct)
        tps3 = calculate_tps(entry3, risk3_pct)
        tps4 = calculate_tps(entry4, risk4_pct)

        ma5 = df["Close"].rolling(5).mean().iloc[-1]
        ma20 = df["Close"].rolling(20).mean().iloc[-1]
        ma50 = df["Close"].rolling(50).mean().iloc[-1]

        if ma5 > ma20 > ma50:
            trend = "BULLISH 🟢 (Strong)"
        elif ma5 > ma20:
            trend = "BULLISH 🟢 (Moderate)"
        elif ma5 < ma20 < ma50:
            trend = "BEARISH 🔴"
        else:
            trend = "NEUTRAL ⚪"

        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        last_rsi = round(float(rsi.iloc[-1]), 2)

        if last_rsi > 70:
            rsi_status = "OVERBOUGHT ⚠️ (Hati-hati beli)"
        elif last_rsi < 30:
            rsi_status = "OVERSOLD 🔥 (Potensi rebound)"
        else:
            rsi_status = "NORMAL ✅"

        vol_ratio = volume / avg_volume_20 if avg_volume_20 > 0 else 1

        if vol_ratio > 1.5:
            vol_status = "🔥 HIGH (Volume besar)"
        elif vol_ratio > 1.2:
            vol_status = "✅ GOOD (Volume di atas rata-rata)"
        elif vol_ratio > 0.8:
            vol_status = "📊 NORMAL"
        else:
            vol_status = "⚠️ LOW (Volume rendah)"

        breakout_status = ""
        if is_breakout:
            if is_strong_breakout and volume_confirmation:
                breakout_status = "✅ AKTIF - Strong Breakout dengan volume!"
            elif is_breakout:
                breakout_status = "⚠️ Breakout terdeteksi, tunggu konfirmasi volume"
        else:
            breakout_status = "❌ Belum breakout"

        msg = f"""
📈 TRADING PLAN - RISK 3% PER TRADE (LONG ONLY)
{ticker_symbol.replace('.JK', '')}
{'='*70}

📊 DATA MARKET:
• Harga saat ini: Rp{current_price:,.0f}
• Perubahan: {((current_price/prev_close)-1)*100:+.2f}%
• ATR (14): Rp{atr:,.0f}
• RSI (14): {last_rsi} ({rsi_status})
• Trend: {trend}
• Volume: {volume:,} ({vol_ratio:.1f}x) {vol_status}

🚀 STATUS BREAKOUT:
• Resistance R1: Rp{sr['R1']:,.0f}
• Resistance R2: Rp{sr['R2']:,.0f}
• Status: {breakout_status}

{'='*70}
🎯 SKENARIO 1: ENTRY NORMAL
━━━━━━━━━━━━━━━━━━━━

💰 Entry: Rp{entry1:,.0f}
🛑 Stop Loss: Rp{sl1:,.0f}
⚠️ Risk: {risk1_pct:.1f}% (Rp{risk1_abs:,.0f}/saham)
📦 Posisi: {pos1:,} lembar (Rp{pos_value1:,.0f})

🎯 TAKE PROFIT (3 LEVEL):
• TP1: Rp{tps1['tp1']:,.0f} (+{tps1['tp1_pct']:.1f}%) | R:R 1:{tps1['rr1']}
• TP2: Rp{tps1['tp2']:,.0f} (+{tps1['tp2_pct']:.1f}%) | R:R 1:{tps1['rr2']}
• TP3: Rp{tps1['tp3']:,.0f} (+{tps1['tp3_pct']:.1f}%) | R:R 1:{tps1['rr3']}

━━━━━━━━━━━━━━━━━━━━

🎯 SKENARIO 2: ENTRY PULLBACK
━━━━━━━━━━━━━━━━━━━━

💰 Entry: Rp{entry2:,.0f}
🛑 Stop Loss: Rp{sl2:,.0f}
⚠️ Risk: {risk2_pct:.1f}% (Rp{risk2_abs:,.0f}/saham)
📦 Posisi: {pos2:,} lembar (Rp{pos_value2:,.0f})

🎯 TAKE PROFIT (3 LEVEL):
• TP1: Rp{tps2['tp1']:,.0f} (+{tps2['tp1_pct']:.1f}%) | R:R 1:{tps2['rr1']}
• TP2: Rp{tps2['tp2']:,.0f} (+{tps2['tp2_pct']:.1f}%) | R:R 1:{tps2['rr2']}
• TP3: Rp{tps2['tp3']:,.0f} (+{tps2['tp3_pct']:.1f}%) | R:R 1:{tps2['rr3']}

━━━━━━━━━━━━━━━━━━━━

🎯 SKENARIO 3: ENTRY DEEP
━━━━━━━━━━━━━━━━━━━━

💰 Entry: Rp{entry3:,.0f}
🛑 Stop Loss: Rp{sl3:,.0f}
⚠️ Risk: {risk3_pct:.1f}% (Rp{risk3_abs:,.0f}/saham)
📦 Posisi: {pos3:,} lembar (Rp{pos_value3:,.0f})

🎯 TAKE PROFIT (3 LEVEL):
• TP1: Rp{tps3['tp1']:,.0f} (+{tps3['tp1_pct']:.1f}%) | R:R 1:{tps3['rr1']}
• TP2: Rp{tps3['tp2']:,.0f} (+{tps3['tp2_pct']:.1f}%) | R:R 1:{tps3['rr2']}
• TP3: Rp{tps3['tp3']:,.0f} (+{tps3['tp3_pct']:.1f}%) | R:R 1:{tps3['rr3']}

━━━━━━━━━━━━━━━━━━━━

🚀 SKENARIO 4: ENTRY BREAKOUT
━━━━━━━━━━━━━━━━━━━━

💰 Entry: Rp{entry4:,.0f}
📌 Breakout Level: Rp{sr['R1']:,.0f}
🛑 Stop Loss: Rp{sl4:,.0f}
⚠️ Risk: {risk4_pct:.1f}% (Rp{risk4_abs:,.0f}/saham)
📦 Posisi: {pos4:,} lembar (Rp{pos_value4:,.0f})

🎯 TAKE PROFIT (3 LEVEL):
• TP1: Rp{tps4['tp1']:,.0f} (+{tps4['tp1_pct']:.1f}%) | R:R 1:{tps4['rr1']}
• TP2: Rp{tps4['tp2']:,.0f} (+{tps4['tp2_pct']:.1f}%) | R:R 1:{tps4['rr2']}
• TP3: Rp{tps4['tp3']:,.0f} (+{tps4['tp3_pct']:.1f}%) | R:R 1:{tps4['rr3']}

⚠️ SYARAT BREAKOUT:
• Harga > R1 ({sr['R1']:,.0f})
• Volume > 1.3x rata-rata
• Candlestick bullish

━━━━━━━━━━━━━━━━━━━━
{'='*70}
📐 LEVEL SUPPORT & RESISTANCE:

SUPPORT (di bawah):              RESISTANCE (di atas):
S1: Rp{sr['S1']:,.0f}            R1: Rp{sr['R1']:,.0f}
S2: Rp{sr['S2']:,.0f}            R2: Rp{sr['R2']:,.0f}
S3: Rp{sr['S3']:,.0f}            R3: Rp{sr['R3']:,.0f}
S4: Rp{sr['S4']:,.0f}            R4: Rp{sr['R4']:,.0f}
                                 R5: Rp{sr['R5']:,.0f}

{'='*70}
⭐ CONFIDENCE SCORE: {confidence}/100
"""

        if confidence >= 70:
            msg += "✅ HIGH CONFIDENCE - Cocok untuk entry\n"
        elif confidence >= 50:
            msg += "⚠️ MEDIUM CONFIDENCE - Entry dengan scaling\n"
        else:
            msg += "❌ LOW CONFIDENCE - Sebaiknya tunggu koreksi\n"

        msg += f"""
{'='*70}
💼 MANAJEMEN MODAL (Rp100jt):

• Risk per trade: {target_risk_pct}% (Rp{max_risk_amount:,.0f})
• Max kerugian per trade: Rp{max_risk_amount:,.0f}
• Max 5 posisi bersamaan (total risk 15%)
• Gunakan STOP LOSS wajib!

{'='*70}
⭐ CONFIDENCE SCORE: {confidence}/100
"""

        if confidence >= 70:
            msg += "✅ HIGH CONFIDENCE - Aggressive position size\n"
        elif confidence >= 50:
            msg += "⚠️ MEDIUM CONFIDENCE - Normal position size\n"
        else:
            msg += "❌ LOW CONFIDENCE - Wait for better setup\n"

        msg += f"""
{'='*70}
📋 STRATEGI SCALING OUT (3 LEVEL):
━━━━━━━━━━━━━━━━━━━━

🎯 TP1
• Action : Jual 40%
• Stop Loss :
  Move ke Break Even
  (Entry Price)

━━━━━━━━━━━━━━━━━━━━

🎯 TP2
• Action : Jual 35%
• Stop Loss :
  Move ke +1.5%

━━━━━━━━━━━━━━━━━━━━

🎯 TP3
• Action : Jual 25%
• Stop Loss :
  Full Exit / Trail SL

━━━━━━━━━━━━━━━━━━━━

{'='*70}
💰 SIMULASI PROFIT (Skenario 1 - Normal Entry):

Entry: Rp{entry1:,.0f} ({pos1:,} lembar = Rp{pos_value1:,.0f})
Risk: 3% = Rp{max_risk_amount:,.0f}

Jika mencapai:
• TP1 ({tps1['tp1_pct']:.1f}%): Jual 40% → Profit Rp{pos_value1 * (tps1['tp1_pct']/100) * 0.4:,.0f}
• TP2 ({tps1['tp2_pct']:.1f}%): Jual 35% → Profit Rp{pos_value1 * (tps1['tp2_pct']/100) * 0.35:,.0f}
• TP3 ({tps1['tp3_pct']:.1f}%): Jual 25% → Profit Rp{pos_value1 * (tps1['tp3_pct']/100) * 0.25:,.0f}

TOTAL PROFIT: Rp{(pos_value1 * (tps1['tp1_pct']/100 * 0.4 + tps1['tp2_pct']/100 * 0.35 + tps1['tp3_pct']/100 * 0.25)):,.0f}
({(tps1['tp1_pct']*0.4 + tps1['tp2_pct']*0.35 + tps1['tp3_pct']*0.25):.1f}% dari modal)

{'='*70}
✅ RULES WAJIB:

1. RISK 3% SUDAH DITENTUKAN
2. STOP LOSS DI BAWAH SUPPORT
3. SCALING OUT WAJIB DI SETIAP TP
4. JANGAN AVERAGING DOWN
5. HORMATI STOP LOSS!

💡 REKOMENDASI SKENARIO:
• Skenario 1: Trader agresif
• Skenario 2: Paling aman (pullback)
• Skenario 3: Entry kedua/avg
• 🚀 Skenario 4: Breakout trader

⚠️ DISCLAIMER: Bukan ajakan beli/jual. DYOR!
"""
        return msg

    except Exception as e:
        print(f"Error in advanced_trading_plan: {e}")
        return f"❌ Error generating trading plan: {str(e)}"


# =========================
# WATCHLIST COMMAND (SQLite version)
# =========================

async def watchlist_cmd(update, context):
    """
    Kelola watchlist dengan entry level FIX (tidak berubah)
    Data disimpan di SQLite, bukan JSON
    """
    user = str(update.effective_user.id)

    if not context.args:
        return await update.message.reply_text(
            "⭐ WATCHLIST COMMAND\n\n"
            "/watchlist add BBCA - Tambah saham (entry level dihitung SEKALI & FIX)\n"
            "/watchlist remove BBCA - Hapus saham\n"
            "/watchlist show - Lihat watchlist\n"
            "/rekapwl - Lihat rekap performa (status berubah sesuai harga hari ini)\n\n"
            "💡 Entry level TIDAK AKAN BERUBAH meskipun harga saham bergerak!"
        )

    action = context.args[0].lower()

    # =========================
    # SHOW
    # =========================
    if action == "show":
        saham = load_watchlist(user)
        if not saham:
            return await update.message.reply_text("📭 Watchlist kosong")

        msg = "⭐ *WATCHLIST (ENTRY LEVEL FIX/TIDAK BERUBAH)*\n"
        msg += "=" * 50 + "\n\n"

        for s in saham:
            fixed = get_fixed_entry(user, s)
            if fixed:
                msg += f"📌 *{s}*\n"
                msg += f"   📅 Tanggal add: {fixed.get('created_date', '-')}\n"
                msg += f"   💰 Harga saat add: Rp{fixed.get('price_at_create', 0):,.0f}\n"
                msg += f"\n   🎯 *LEVEL ENTRY (FIX/TIDAK BERUBAH):*\n"
                msg += f"   ├─ 📊 NORMAL    : Rp{fixed['scenarios']['normal']['entry']:,.0f}\n"
                msg += f"   ├─ 📉 PULLBACK  : Rp{fixed['scenarios']['pullback']['entry']:,.0f}\n"
                msg += f"   ├─ 🔻 DEEP      : Rp{fixed['scenarios']['deep']['entry']:,.0f}\n"
                msg += f"   └─ 🚀 BREAKOUT  : Rp{fixed['scenarios']['breakout']['entry']:,.0f}\n"
                msg += f"\n   🎯 *TP/SL (FIX/TIDAK BERUBAH):*\n"
                msg += f"   ├─ TP1: +{fixed['scenarios']['normal']['tp1_pct']}% → Rp{fixed['scenarios']['normal']['tp1']:,.0f}\n"
                msg += f"   ├─ TP2: +{fixed['scenarios']['normal']['tp2_pct']}% → Rp{fixed['scenarios']['normal']['tp2']:,.0f}\n"
                msg += f"   ├─ TP3: +{fixed['scenarios']['normal']['tp3_pct']}% → Rp{fixed['scenarios']['normal']['tp3']:,.0f}\n"
                msg += f"   └─ SL : -{fixed['scenarios']['normal']['risk_pct']}% → Rp{fixed['scenarios']['normal']['sl']:,.0f}\n\n"
            else:
                msg += f"⚠️ {s} (belum ada entry level, gunakan /watchlist update {s})\n\n"

        return await update.message.reply_text(msg)

    # =========================
    # ADD
    # =========================
    if action == "add":
        if len(context.args) < 2:
            return await update.message.reply_text("Contoh: /watchlist add BBCA")

        stock = context.args[1].upper()

        if ticker_in_watchlist(user, stock):
            return await update.message.reply_text(f"⚠️ {stock} sudah ada di watchlist")

        await update.message.reply_text(
            f"📊 Menghitung entry level untuk {stock} (SEKALI & TIDAK AKAN BERUBAH)..."
        )

        ticker_symbol = stock + ".JK"
        fixed_levels = calculate_fixed_entry_levels(ticker_symbol)

        if fixed_levels:
            # Simpan ke SQLite
            save_fixed_entry(user, stock, fixed_levels)
            add_to_watchlist(user, stock)

            msg = f"""
✅ *{stock} BERHASIL DITAMBAHKAN!*

📅 Tanggal entry: {fixed_levels['created_date']}
💰 Harga saat add: Rp{fixed_levels['price_at_create']:,.0f}

📊 *LEVEL ENTRY (FIX/TIDAK AKAN BERUBAH):*
├─ 📊 NORMAL    : Rp{fixed_levels['scenarios']['normal']['entry']:,.0f}
├─ 📉 PULLBACK  : Rp{fixed_levels['scenarios']['pullback']['entry']:,.0f}
├─ 🔻 DEEP      : Rp{fixed_levels['scenarios']['deep']['entry']:,.0f}
└─ 🚀 BREAKOUT  : Rp{fixed_levels['scenarios']['breakout']['entry']:,.0f}

🎯 *TP/SL (FIX/TIDAK AKAN BERUBAH):*
├─ TP1: +{fixed_levels['scenarios']['normal']['tp1_pct']}% → Rp{fixed_levels['scenarios']['normal']['tp1']:,.0f}
├─ TP2: +{fixed_levels['scenarios']['normal']['tp2_pct']}% → Rp{fixed_levels['scenarios']['normal']['tp2']:,.0f}
├─ TP3: +{fixed_levels['scenarios']['normal']['tp3_pct']}% → Rp{fixed_levels['scenarios']['normal']['tp3']:,.0f}
└─ SL : -{fixed_levels['scenarios']['normal']['risk_pct']}% → Rp{fixed_levels['scenarios']['normal']['sl']:,.0f}

💡 Entry level ini TIDAK AKAN PERNAH BERUBAH!
📊 Setiap hari jalankan /rekapwl untuk update status (RUNNING/TP1/TP2/TP3/SL)
"""
            await update.message.reply_text(msg)
        else:
            return await update.message.reply_text(
                f"❌ Gagal menghitung entry level untuk {stock}. Data tidak cukup."
            )

    # =========================
    # UPDATE
    # =========================
    if action == "update":
        if len(context.args) < 2:
            return await update.message.reply_text("Contoh: /watchlist update BBCA")

        stock = context.args[1].upper()

        if not ticker_in_watchlist(user, stock):
            return await update.message.reply_text(f"⚠️ {stock} tidak ada di watchlist")

        await update.message.reply_text(f"📊 Update entry level untuk {stock}...")

        ticker_symbol = stock + ".JK"
        fixed_levels = calculate_fixed_entry_levels(ticker_symbol)

        if fixed_levels:
            save_fixed_entry(user, stock, fixed_levels)
            await update.message.reply_text(
                f"✅ Entry level untuk {stock} berhasil diupdate!\n"
                f"📅 Tanggal update: {fixed_levels['created_date']}"
            )
        else:
            return await update.message.reply_text(
                f"❌ Gagal update entry level untuk {stock}."
            )

    # =========================
    # REMOVE
    # =========================
    if action == "remove":
        if len(context.args) < 2:
            return await update.message.reply_text("Contoh: /watchlist remove BBCA")

        stock = context.args[1].upper()

        if remove_from_watchlist(user, stock):
            delete_fixed_entry(user, stock)
            return await update.message.reply_text(f"❌ {stock} dihapus dari watchlist")
        else:
            return await update.message.reply_text(f"⚠️ {stock} tidak ada di watchlist")

    await update.message.reply_text("❌ Command tidak dikenal")


# =========================
# REKAP WATCHLIST (SQLite version)
# =========================

async def rekap_watchlist_cmd(update, context):
    """
    Rekap watchlist - Entry level FIX (dari SQLite), hanya STATUS yang berubah
    """
    user = str(update.effective_user.id)
    watchlist = load_watchlist(user)

    if not watchlist:
        return await update.message.reply_text(
            "📭 Watchlist kosong!\n\n"
            "Tambahkan saham dulu:\n"
            "/watchlist add BBCA"
        )

    await update.message.reply_text(
        f"📊 Merekap {len(watchlist)} saham...\n"
        "Entry level FIX (tidak berubah), status diupdate berdasarkan harga hari ini"
    )

    results = []

    for ticker in watchlist:
        try:
            fixed = get_fixed_entry(user, ticker)

            if not fixed:
                results.append({
                    "ticker": ticker,
                    "error": True,
                    "status_text": "⚠️ BELUM ADA ENTRY LEVEL (gunakan /watchlist update)"
                })
                continue

            ticker_symbol = ticker + ".JK"

            df = yf.download(
                ticker_symbol,
                period="5d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False
            )

            df = fix_yf_columns(df)
            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna()

            if df.empty:
                results.append({
                    "ticker": ticker,
                    "error": True,
                    "status_text": "❌ NO DATA"
                })
                continue

            low_today = float(df["Low"].iloc[-1])
            high_today = float(df["High"].iloc[-1])
            close_price = float(df["Close"].iloc[-1])

            if len(df) >= 2:
                prev_close = float(df["Close"].iloc[-2])
            else:
                prev_close = close_price

            daily_change = ((close_price / prev_close) - 1) * 100

            scenarios = fixed["scenarios"]

            active = None
            active_scenarios = []

            for key, scenario in scenarios.items():
                entry_price = scenario["entry"]
                if low_today >= entry_price:
                    active_scenarios.append({
                        "key": key,
                        "scenario": scenario,
                        "entry": entry_price
                    })

            if active_scenarios:
                active_scenarios.sort(key=lambda x: x["entry"], reverse=True)
                active = active_scenarios[0]
                scenario_data = active["scenario"]

                pct_from_entry = ((close_price - scenario_data["entry"]) / scenario_data["entry"]) * 100

                if close_price >= scenario_data["tp3"]:
                    tp_status = f"🏆 TP3 HIT (+{scenario_data['tp3_pct']}%)"
                    status_code = "TP3_HIT"
                elif close_price >= scenario_data["tp2"]:
                    tp_status = f"🥈 TP2 HIT (+{scenario_data['tp2_pct']}%)"
                    status_code = "TP2_HIT"
                elif close_price >= scenario_data["tp1"]:
                    tp_status = f"🥉 TP1 HIT (+{scenario_data['tp1_pct']}%)"
                    status_code = "TP1_HIT"
                elif close_price <= scenario_data["sl"]:
                    tp_status = f"💀 STOP LOSS (-{scenario_data['risk_pct']}%)"
                    status_code = "SL_HIT"
                elif close_price > scenario_data["entry"]:
                    tp_status = f"🟢 RUNNING (Profit {pct_from_entry:+.1f}%)"
                    status_code = "RUNNING"
                elif close_price < scenario_data["entry"]:
                    tp_status = f"🔴 RUNNING (Loss {pct_from_entry:+.1f}%)"
                    status_code = "RUNNING"
                else:
                    tp_status = f"⚪ AT ENTRY"
                    status_code = "AT_ENTRY"

                results.append({
                    "ticker": ticker,
                    "created_date": fixed.get("created_date", "-"),
                    "price_at_create": fixed.get("price_at_create", 0),
                    "low_today": low_today,
                    "high_today": high_today,
                    "close_price": close_price,
                    "daily_change": daily_change,
                    "is_kena": True,
                    "scenario_name": scenario_data["display_name"],
                    "entry_price_fix": scenario_data["entry"],
                    "pct_from_entry": pct_from_entry,
                    "status": tp_status,
                    "status_code": status_code,
                    "tp1_pct": scenario_data["tp1_pct"],
                    "tp2_pct": scenario_data["tp2_pct"],
                    "tp3_pct": scenario_data["tp3_pct"],
                    "tp1_price": scenario_data["tp1"],
                    "tp2_price": scenario_data["tp2"],
                    "tp3_price": scenario_data["tp3"],
                    "sl_price": scenario_data["sl"],
                    "risk_pct": scenario_data["risk_pct"],
                    "all_scenarios": scenarios
                })
            else:
                nearest = None
                nearest_diff = float('inf')
                for key, scenario in scenarios.items():
                    entry_price = scenario["entry"]
                    if entry_price > 0:
                        diff = entry_price - low_today
                        if 0 < diff < nearest_diff:
                            nearest_diff = diff
                            nearest = scenario

                results.append({
                    "ticker": ticker,
                    "created_date": fixed.get("created_date", "-"),
                    "price_at_create": fixed.get("price_at_create", 0),
                    "low_today": low_today,
                    "high_today": high_today,
                    "close_price": close_price,
                    "daily_change": daily_change,
                    "is_kena": False,
                    "nearest_entry": nearest["entry"] if nearest else "-",
                    "need_drop": f"{round((nearest_diff/low_today)*100,1)}%" if nearest else "-",
                    "all_scenarios": scenarios
                })

        except Exception as e:
            print(f"Error {ticker}: {e}")
            results.append({
                "ticker": ticker,
                "error": True,
                "status_text": f"❌ ERROR"
            })

    # ==================== BUAT EXCEL ====================
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_file = f"watchlist_rekap_{timestamp}.xlsx"

    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        sheet1_data = []
        for r in results:
            if r.get("error"):
                sheet1_data.append({
                    "Saham": r["ticker"],
                    "Status": r.get("status_text", "ERROR"),
                })
            elif r.get("is_kena"):
                sheet1_data.append({
                    "Saham": r["ticker"],
                    "Tanggal Add": r.get("created_date", "-"),
                    "Harga Add": f"{r['price_at_create']:,.0f}",
                    "Harga Hari Ini": f"{r['close_price']:,.0f}",
                    "Daily %": f"{r['daily_change']:+.2f}",
                    "Low": f"{r['low_today']:,.0f}",
                    "High": f"{r['high_today']:,.0f}",
                    "🔥 SKENARIO KENA": r["scenario_name"],
                    "Entry Price (FIX)": f"{r['entry_price_fix']:,.0f}",
                    "Profit/Loss": f"{r['pct_from_entry']:+.2f}%",
                    "STATUS": r["status"],
                    "TP1": f"+{r['tp1_pct']}% (Rp{r['tp1_price']:,.0f})",
                    "TP2": f"+{r['tp2_pct']}% (Rp{r['tp2_price']:,.0f})",
                    "TP3": f"+{r['tp3_pct']}% (Rp{r['tp3_price']:,.0f})",
                    "SL": f"-{r['risk_pct']}% (Rp{r['sl_price']:,.0f})",
                })
            else:
                sheet1_data.append({
                    "Saham": r["ticker"],
                    "Tanggal Add": r.get("created_date", "-"),
                    "Harga Add": f"{r['price_at_create']:,.0f}",
                    "Harga Hari Ini": f"{r['close_price']:,.0f}",
                    "Daily %": f"{r['daily_change']:+.2f}",
                    "Low": f"{r['low_today']:,.0f}",
                    "High": f"{r['high_today']:,.0f}",
                    "🔥 SKENARIO KENA": "BELUM KENA",
                    "Entry Price (FIX)": "-",
                    "Profit/Loss": "-",
                    "STATUS": f"⏳ Butuh turun ke Rp{r.get('nearest_entry', '-'):,.0f} (drop {r.get('need_drop', '-')})",
                    "TP1": "-",
                    "TP2": "-",
                    "TP3": "-",
                    "SL": "-",
                })

        df1 = pd.DataFrame(sheet1_data)
        df1.to_excel(writer, sheet_name="STATUS_HARI_INI", index=False)

        sheet2_data = []
        for r in results:
            if "all_scenarios" in r:
                for key, sc in r["all_scenarios"].items():
                    is_kena = False
                    if r.get("is_kena") and r.get("scenario_name") == sc["display_name"]:
                        is_kena = True
                    sheet2_data.append({
                        "Saham": r["ticker"],
                        "Skenario": sc["display_name"],
                        "Status": "✅ KENA" if is_kena else "❌ TIDAK KENA",
                        "Entry (FIX)": f"{sc['entry']:,.0f}",
                        "SL (FIX)": f"{sc['sl']:,.0f}",
                        "Risk %": f"{sc['risk_pct']}%",
                        "TP1 %": f"{sc['tp1_pct']}%",
                        "TP1": f"{sc['tp1']:,.0f}",
                        "TP2 %": f"{sc['tp2_pct']}%",
                        "TP2": f"{sc['tp2']:,.0f}",
                        "TP3 %": f"{sc['tp3_pct']}%",
                        "TP3": f"{sc['tp3']:,.0f}",
                    })

        if sheet2_data:
            df2 = pd.DataFrame(sheet2_data)
            df2.to_excel(writer, sheet_name="DETAIL_SKENARIO_FIX", index=False)

    kena_count = len([r for r in results if r.get("is_kena")])
    tp_hit_count = len([r for r in results if r.get("status_code") in ["TP1_HIT", "TP2_HIT", "TP3_HIT"]])
    sl_hit_count = len([r for r in results if r.get("status_code") == "SL_HIT"])

    await update.message.reply_document(
        open(excel_file, "rb"),
        caption=f"""
📊 *WATCHLIST REKAP - {datetime.now().strftime('%Y-%m-%d %H:%M')}*
{'='*35}

📈 Total: {len(results)} saham

🎯 *HARI INI:*
✅ SKENARIO KENA: {kena_count} saham
🏆 TP HIT: {tp_hit_count} saham
💀 SL HIT: {sl_hit_count} saham

💡 *PENTING:*
• Entry level adalah FIX (sesuai saat add saham)
• Hanya STATUS yang berubah mengikuti harga hari ini
• Entry level TIDAK PERNAH BERUBAH

📁 File Excel:
• STATUS_HARI_INI: Status posisi terkini
• DETAIL_SKENARIO_FIX: Detail 4 skenario (tidak berubah)
"""
    )

    os.remove(excel_file)


# =========================
# ALERT
# =========================
async def alert_cmd(update, context):

    if len(context.args) < 2:

        return await update.message.reply_text(
            "/alert BBCA 9500"
        )

    stock = context.args[0].upper()

    target = context.args[1]

    msg = (
        "🔔 ALERT BERHASIL\n\n"
        f"Saham : {stock}\n"
        f"Target : {target}"
    )

    await update.message.reply_text(msg)


# =========================
# BSJP TRADING PLAN (LONG ONLY)
# =========================

def bsjp_trading_plan(ticker_symbol):
    """
    Trading Plan khusus BSJP untuk posisi LONG/BUY saja
    """
    try:
        df = yf.download(
            ticker_symbol,
            period="3mo",
            interval="1d",
            progress=False
        )

        df = fix_yf_columns(df)
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna()

        if df.empty or len(df) < 20:
            return "❌ Data tidak cukup untuk analisis BSJP"

        current_price = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-2])
        current_volume = float(df["Volume"].iloc[-1])
        prev_volume = float(df["Volume"].iloc[-2])

        current_value = current_price * current_volume
        atr = calculate_atr(df, period=10)

        rule_1 = current_price >= (1.05 * prev_price)
        rule_2 = current_price >= df["Close"].rolling(5).mean().iloc[-1]
        rule_3 = current_volume >= (1.2 * prev_volume)
        rule_4 = current_value >= 5_000_000_000

        rules_passed = sum([rule_1, rule_2, rule_3, rule_4])
        daily_change = ((current_price / prev_price) - 1) * 100

        high = df["High"].values
        low = df["Low"].values
        close = df["Close"].values

        pivot = (high[-1] + low[-1] + close[-1]) / 3
        r1 = pivot + (high[-1] - low[-1]) * 0.382
        r2 = pivot + (high[-1] - low[-1]) * 0.618
        s1 = pivot - (high[-1] - low[-1]) * 0.382
        s2 = pivot - (high[-1] - low[-1]) * 0.618

        atr_stop = current_price - (2.5 * atr)
        support_stop = s2 if s2 > 0 else current_price * 0.9
        pct_stop = current_price * 0.9

        stop_loss = max(atr_stop, support_stop, pct_stop)
        max_stop = current_price * 0.85
        if stop_loss < max_stop:
            stop_loss = max_stop

        risk_per_share = current_price - stop_loss
        risk_pct = (risk_per_share / current_price) * 100

        tp1 = current_price + (risk_per_share * 1.2)
        tp2 = current_price + (risk_per_share * 2.0)
        tp3 = current_price + (risk_per_share * 3.0)

        if tp1 > r1 and r1 > current_price:
            tp1 = r1
        if tp2 > r2 and r2 > tp1:
            tp2 = r2

        account_size = 100_000_000
        risk_per_trade_pct = 3.0
        max_risk_amount = account_size * (risk_per_trade_pct / 100)

        avg_value = (close[-20:] * df["Volume"].values[-20:]).mean()
        liquidity_adj = 1.0
        if avg_value < 10_000_000_000:
            liquidity_adj = 0.6

        adjusted_risk = max_risk_amount * liquidity_adj
        position_size = int(adjusted_risk / risk_per_share) if risk_per_share > 0 else 0
        position_value = position_size * current_price

        entry_limit = s1 if s1 < current_price else current_price * 0.97

        confidence = rules_passed * 20

        vol_ma5 = df["Volume"].rolling(5).mean().iloc[-1]
        vol_spike = current_volume / vol_ma5 if vol_ma5 > 0 else 1
        if vol_spike > 1.5:
            confidence += 20
        elif vol_spike > 1.2:
            confidence += 10

        msg = f"""
🚀 BSJP TRADING PLAN (LONG/BUY): {ticker_symbol.replace('.JK', '')}
{'='*55}

📊 HASIL SCREENING BSJP:
{'✅' if rule_1 else '❌'} Rule 1: Harga ≥ 5% ({daily_change:+.1f}%)
{'✅' if rule_2 else '❌'} Rule 2: Harga ≥ MA5
{'✅' if rule_3 else '❌'} Rule 3: Volume ≥ 1.2x ({current_volume/prev_volume:.1f}x)
{'✅' if rule_4 else '❌'} Rule 4: Nilai ≥ 5B ({current_value/1e9:.1f}B)

STATUS: {rules_passed}/4 LOLOS
MOMENTUM: {daily_change:+.1f}%

{'='*55}
🎯 LEVEL ENTRY (BELI):

1. ENTRY AGGRESSIF: {current_price:,.0f}
   → Setelah ada konfirmasi candlestick

2. ENTRY KONSERVATIF: {entry_limit:,.0f}
   → Tunggu pullback ke support S1
   → Lebih aman untuk BSJP

3. ENTRY BREAKOUT: DI ATAS {r1:,.0f}
   → Jika tembus resistance

{'='*55}
🛑 STOP LOSS (CUT LOSS) - BSJP STYLE:

• Harga Stop Loss: {stop_loss:,.0f}
• Kerugian per saham: {risk_per_share:,.0f}
• Persen Risiko: {risk_pct:.1f}%
• Metode: 2.5x ATR + Support

⚠️ Catatan: Stop loss lebih lebar karena 
volatilitas saham BSJP lebih tinggi

{'='*55}
🎯 TARGET PROFIT (TAKE PROFIT):

• TP1: {tp1:,.0f} | R:R 1:{((tp1-current_price)/risk_per_share):.1f}
• TP2: {tp2:,.0f} | R:R 1:{((tp2-current_price)/risk_per_share):.1f}
• TP3: {tp3:,.0f} | R:R 1:{((tp3-current_price)/risk_per_share):.1f}

📐 LEVEL RESISTANCE BSJP:
• R1: {r1:,.0f}
• R2: {r2:,.0f}

{'='*55}
💼 MANAJEMEN MODAL (Modal Rp 100jt):

• Risk per trade: {risk_per_trade_pct}%
• Maksimal kerugian: Rp {adjusted_risk:,.0f}
• Jumlah saham: {position_size:,} lembar
• Nilai posisi: Rp {position_value:,.0f}

{'='*55}
⭐ KONFIDENSI BSJP: {min(confidence, 100)}/100
"""

        if confidence >= 70:
            msg += "✅ HIGH - Saham layak beli, BSJP qualified\n"
        elif confidence >= 50:
            msg += "⚠️ MEDIUM - Bisa beli dengan scaling\n"
        else:
            msg += "❌ LOW - Belum qualified, tunggu signal lebih kuat\n"

        msg += f"""
{'='*55}
📋 LANGKAH EKSEKUSI BSJP (LONG ONLY)

TAHAP 1 - PERSIAPAN:
☐ Pastikan 4 rules BSJP terpenuhi minimal 3
☐ Cek volume > 200.000 lot/transaksi
☐ Pastikan tidak ada berita negatif

TAHAP 2 - EKSEKUSI:
☐ Entry {rules_passed * 15}% dari modal di harga entry
☐ Gunakan LIMIT ORDER, jangan market order
☐ Pasang stop loss setelah entry

TAHAP 3 - MONITORING:
☐ Jika harga turun 3% dari entry, evaluasi ulang
☐ Jika harga naik ke TP1 → take profit 50%
☐ Naikkan stop loss ke harga modal

TAHAP 4 - EXIT:
☐ Jika momentum melemah, exit lebih awal
☐ Jangan serakah, profit adalah profit

⚠️ RISIKO KHUSUS BSJP:
• Volatilitas tinggi (bisa gap up/down)
• Likuiditas bisa kering saat jam makan siang
• Slippage saat entry/exit
• Harga mudah dipengaruhi berita

💡 TIPS BSJP:
• Waktu terbaik entry: 09:30-11:00
• Hindari entry jam 11:30-13:30
• Catat level psikologis: kelipatan 50 (200, 250, 300...)
• Jangan trading jika volume < 100.000
• Cut loss lebih cepat jika melanggar rule 1
"""

        return msg

    except Exception as e:
        print(f"Error in BSJP trading plan: {e}")
        return f"❌ Error generating BSJP plan: {str(e)}"


# =========================
# BSJP TOP PLAN
# =========================
async def bsjp_top_plan_cmd(update, context):
    """
    Screening BSJP + Auto generate plan untuk top stocks
    Usage: /bsjptop
    """
    await update.message.reply_text("🔍 Screening BSJP stocks...")

    screener_result = run_bsjp_screener()

    lines = screener_result.split('\n')
    top_tickers = []

    for line in lines:
        if '🔥' in line and len(top_tickers) < 3:
            parts = line.split()
            if len(parts) >= 2:
                ticker = parts[1].strip()
                if ticker and ticker not in top_tickers:
                    top_tickers.append(ticker)

    if not top_tickers:
        return await update.message.reply_text(
            "❌ No BSJP qualified stocks found\n\n"
            "Try: /bsjp to see candidates"
        )

    await update.message.reply_text(
        f"🎯 TOP {len(top_tickers)} BSJP STOCKS\n"
        f"Generating trading plans...\n\n"
    )

    for ticker in top_tickers[:2]:
        plan = bsjp_trading_plan(ticker + ".JK")

        if len(plan) > 4096:
            for i in range(0, len(plan), 4000):
                await update.message.reply_text(plan[i:i+4000])
        else:
            await update.message.reply_text(plan)

        if ticker != top_tickers[-1]:
            await update.message.reply_text("--- Next Stock ---")


# =========================
# SNR
# =========================
def generate_snr(ticker):

    df = yf.download(ticker, period="6mo", interval="1d")
    df = fix_yf_columns(df)
    df = df.apply(pd.to_numeric, errors='coerce').dropna()

    high = df["High"].rolling(20).max().iloc[-1]
    low = df["Low"].rolling(20).min().iloc[-1]
    r = high - low

    r1,r2,r3 = high, high+r*0.5, high+r
    s1,s2,s3 = low, low-r*0.5, low-r

    plt.figure(figsize=(10,6), facecolor='black')
    ax = plt.gca()
    ax.set_facecolor('black')

    for i in range(len(df)):
        c = 'lime' if df['Close'].iloc[i]>=df['Open'].iloc[i] else 'red'
        plt.plot([i,i],[df['Low'].iloc[i],df['High'].iloc[i]],color=c)
        plt.plot([i,i],[df['Open'].iloc[i],df['Close'].iloc[i]],color=c,linewidth=3)

    for y in [r1,r2,r3]:
        plt.axhline(y,color='red')
    for y in [s1,s2,s3]:
        plt.axhline(y,color='lime')

    x=len(df)+2
    plt.text(x,r1,f'R1 {int(r1)}',color='red')
    plt.text(x,r2,f'R2 {int(r2)}',color='red')
    plt.text(x,r3,f'R3 {int(r3)}',color='red')

    plt.text(x,s1,f'S1 {int(s1)}',color='lime')
    plt.text(x,s2,f'S2 {int(s2)}',color='lime')
    plt.text(x,s3,f'S3 {int(s3)}',color='lime')

    plt.xlim(0,len(df)+10)
    plt.title(ticker,color='white')
    plt.xticks(color='white')
    plt.yticks(color='white')

    file=f"{ticker}_snr.png"
    plt.savefig(file,facecolor='black')
    plt.close()
    return file


# =========================
# ML
# =========================
def generate_ml(ticker):

    df = yf.download(ticker, period="6mo", interval="1d")
    df = fix_yf_columns(df)
    df = df.apply(pd.to_numeric, errors='coerce').dropna()

    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    x = np.arange(len(df))
    slope, intercept = np.polyfit(x, df["Close"], 1)
    trend = slope*x + intercept

    std = np.std(df["Close"] - trend)
    upper = trend + std
    lower = trend - std

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1]

    short = "UP" if df["Close"].iloc[-1] > df["Close"].iloc[-10] else "DOWN"
    mid = "UP" if slope > 0 else "DOWN"
    long = "UP" if df["Close"].iloc[-1] > df["EMA200"].iloc[-1] else "DOWN"

    plt.figure(figsize=(12,7), facecolor='black')
    ax = plt.gca()
    ax.set_facecolor('black')

    for i in range(len(df)):
        c = 'lime' if df['Close'].iloc[i]>=df['Open'].iloc[i] else 'red'
        plt.plot([i,i],[df['Low'].iloc[i],df['High'].iloc[i]],color=c)
        plt.plot([i,i],[df['Open'].iloc[i],df['Close'].iloc[i]],color=c,linewidth=3)

    ema = df["EMA200"]
    plt.plot(range(len(ema)), ema, color='yellow', linewidth=3, zorder=5)
    plt.text(len(df)+2, ema.iloc[-1], f'EMA200 {int(ema.iloc[-1])}', color='yellow')

    plt.plot(trend, color='blue')
    plt.plot(upper, color='red')
    plt.plot(lower, color='red')

    plt.text(
        0,
        max(df["High"]),
        f"Short : {short}\nMid   : {mid}\nLong  : {long}\n\nRSI : {round(last_rsi,1)}",
        color='white',
        fontsize=10,
        verticalalignment='top'
    )

    plt.xlim(0,len(df)+10)
    plt.title(ticker,color='white')
    plt.xticks(color='white')
    plt.yticks(color='white')

    file=f"{ticker}_ml.png"
    plt.savefig(file,facecolor='black')
    plt.close()
    return file


# =========================
# ADVANCED CHART
# =========================

def calculate_rsi(series, period=14):
    """Calculate RSI"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def generate_advanced_chart(ticker_symbol, period="3mo"):
    """
    Generate advanced chart dengan candlestick, MA, BB, RSI, volume
    """
    try:
        df = yf.download(ticker_symbol, period=period, interval="1d", progress=False)
        df = fix_yf_columns(df)
        df = df.apply(pd.to_numeric, errors='coerce').dropna()

        if len(df) < 30:
            return None

        fig = plt.figure(figsize=(16, 10), facecolor='#1a1a2e')
        fig.patch.set_facecolor('#1a1a2e')

        gs = GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.08)

        ax1 = plt.subplot(gs[0])
        ax1.set_facecolor('#16213e')

        width = 0.6

        for i in range(len(df)):
            if df['Close'].iloc[i] >= df['Open'].iloc[i]:
                color = '#00d2ff'
                body_color = '#00d2ff'
            else:
                color = '#ff6b6b'
                body_color = '#ff6b6b'

            ax1.plot([i, i],
                    [df['Low'].iloc[i], df['High'].iloc[i]],
                    color=color, linewidth=0.8, alpha=0.7)

            body_bottom = min(df['Open'].iloc[i], df['Close'].iloc[i])
            body_height = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
            rect = Rectangle((i - width/2, body_bottom),
                           width, body_height,
                           facecolor=body_color, alpha=0.7,
                           edgecolor=color, linewidth=0.5)
            ax1.add_patch(rect)

        ma20 = df['Close'].rolling(20).mean()
        ma50 = df['Close'].rolling(50).mean()
        ma200 = df['Close'].rolling(200).mean()

        ax1.plot(range(len(ma20)), ma20, color='#ffd93d', linewidth=1.5,
                label='MA20', alpha=0.9)
        ax1.plot(range(len(ma50)), ma50, color='#6bcb77', linewidth=1.5,
                label='MA50', alpha=0.9)
        if len(df) >= 200:
            ax1.plot(range(len(ma200)), ma200, color='#ff6b6b', linewidth=1.5,
                    label='MA200', alpha=0.9)

        bb_period = 20
        bb_std = 2
        sma = df['Close'].rolling(bb_period).mean()
        std = df['Close'].rolling(bb_period).std()
        upper_bb = sma + (std * bb_std)
        lower_bb = sma - (std * bb_std)

        ax1.fill_between(range(len(df)), lower_bb, upper_bb,
                         color='#4d4d4d', alpha=0.2, label='Bollinger Bands')
        ax1.plot(range(len(df)), upper_bb, color='#888888', linewidth=0.8, alpha=0.5)
        ax1.plot(range(len(df)), lower_bb, color='#888888', linewidth=0.8, alpha=0.5)

        lookback = min(20, len(df))
        recent_highs = df['High'].rolling(lookback).max()
        resistance = recent_highs.iloc[-1]
        support = df['Low'].rolling(lookback).min().iloc[-1]

        ax1.axhline(y=resistance, color='#ff6b6b', linestyle='--',
                   linewidth=1, alpha=0.7, label=f'Resistance: {resistance:.0f}')
        ax1.axhline(y=support, color='#00d2ff', linestyle='--',
                   linewidth=1, alpha=0.7, label=f'Support: {support:.0f}')

        last_rsi_val = calculate_rsi(df['Close']).iloc[-1]

        buy_signals = []
        sell_signals = []

        for i in range(5, len(df)-1):
            if ma20.iloc[i-1] <= ma50.iloc[i-1] and ma20.iloc[i] > ma50.iloc[i]:
                buy_signals.append((i, df['Low'].iloc[i]))
            elif ma20.iloc[i-1] >= ma50.iloc[i-1] and ma20.iloc[i] < ma50.iloc[i]:
                sell_signals.append((i, df['High'].iloc[i]))
            elif last_rsi_val < 30 and i == len(df)-2:
                buy_signals.append((i, df['Low'].iloc[i]))
            elif last_rsi_val > 70 and i == len(df)-2:
                sell_signals.append((i, df['High'].iloc[i]))

        for idx, price in buy_signals[-5:]:
            ax1.scatter(idx, price, color='#00ff00', s=150,
                       marker='^', zorder=5, edgecolors='white', linewidth=1.5,
                       label='Buy Signal' if idx == buy_signals[-1][0] else "")

        for idx, price in sell_signals[-5:]:
            ax1.scatter(idx, price, color='#ff0000', s=150,
                       marker='v', zorder=5, edgecolors='white', linewidth=1.5,
                       label='Sell Signal' if idx == sell_signals[-1][0] else "")

        ax1.set_ylabel('Price (Rp)', color='white', fontsize=10)
        ax1.tick_params(axis='both', colors='white')
        ax1.grid(True, alpha=0.2, color='white')
        ax1.set_xlim(0, len(df))
        ax1.legend(loc='upper left', facecolor='#1a1a2e', edgecolor='white',
                  labelcolor='white', fontsize=8)

        ax2 = plt.subplot(gs[1], sharex=ax1)
        ax2.set_facecolor('#16213e')

        colors_vol = ['#00d2ff' if df['Close'].iloc[i] >= df['Open'].iloc[i]
                     else '#ff6b6b' for i in range(len(df))]
        ax2.bar(range(len(df)), df['Volume'], color=colors_vol, alpha=0.7, width=0.8)
        ax2.set_ylabel('Volume', color='white', fontsize=10)
        ax2.tick_params(axis='both', colors='white')
        ax2.grid(True, alpha=0.2, color='white')

        vol_ma = df['Volume'].rolling(20).mean()
        ax2.plot(range(len(vol_ma)), vol_ma, color='#ffd93d', linewidth=1,
                alpha=0.7, label='Volume MA20')

        ax3 = plt.subplot(gs[2], sharex=ax1)
        ax3.set_facecolor('#16213e')

        rsi = calculate_rsi(df['Close'])
        ax3.plot(range(len(rsi)), rsi, color='#ffd93d', linewidth=1.5)
        ax3.axhline(y=70, color='#ff6b6b', linestyle='--', alpha=0.7, linewidth=1)
        ax3.axhline(y=30, color='#00d2ff', linestyle='--', alpha=0.7, linewidth=1)
        ax3.axhline(y=50, color='white', linestyle=':', alpha=0.3, linewidth=0.8)
        ax3.fill_between(range(len(rsi)), 30, 70, color='#4d4d4d', alpha=0.2)
        ax3.set_ylabel('RSI', color='white', fontsize=10)
        ax3.set_ylim(0, 100)
        ax3.tick_params(axis='both', colors='white')
        ax3.grid(True, alpha=0.2, color='white')

        dates = df.index
        date_positions = range(0, len(df), max(1, len(df)//10))
        date_labels = [dates[i].strftime('%d-%b') for i in date_positions]
        ax3.set_xticks(date_positions)
        ax3.set_xticklabels(date_labels, rotation=45, ha='right', color='white')

        info_text = f"""
        Current: {df['Close'].iloc[-1]:,.0f}
        Change: {((df['Close'].iloc[-1]/df['Close'].iloc[-2])-1)*100:+.2f}%
        RSI: {rsi.iloc[-1]:.1f}
        Volume: {df['Volume'].iloc[-1]/1e6:.1f}M
        """

        ax1.text(0.98, 0.97, info_text, transform=ax1.transAxes,
                fontsize=9, verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='#1a1a2e', alpha=0.8),
                color='white', fontfamily='monospace')

        ticker_name = ticker_symbol.replace('.JK', '')
        plt.suptitle(f'{ticker_name} - Advanced Technical Analysis',
                    color='white', fontsize=14, fontweight='bold', y=0.98)

        plt.tight_layout()

        file = f"{ticker_name}_advanced_chart.png"
        plt.savefig(file, facecolor='#1a1a2e', dpi=150, bbox_inches='tight')
        plt.close()

        return file

    except Exception as e:
        print(f"Error generating advanced chart: {e}")
        return None


def generate_trading_signals_chart(ticker_symbol):
    """
    Chart dengan annotated trading signals
    """
    try:
        df = yf.download(ticker_symbol, period="6mo", interval="1d", progress=False)
        df = fix_yf_columns(df)
        df = df.apply(pd.to_numeric, errors='coerce').dropna()

        if len(df) < 50:
            return None

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                       gridspec_kw={'height_ratios': [3, 1]},
                                       facecolor='#1a1a2e')
        fig.patch.set_facecolor('#1a1a2e')

        ax1.set_facecolor('#16213e')

        for i in range(len(df)):
            color = '#00d2ff' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ff6b6b'
            ax1.vlines(i, df['Low'].iloc[i], df['High'].iloc[i], colors=color, linewidth=1, alpha=0.7)
            ax1.vlines(i, df['Open'].iloc[i], df['Close'].iloc[i], colors=color, linewidth=3, alpha=0.9)

        ma20 = df['Close'].rolling(20).mean()
        ma50 = df['Close'].rolling(50).mean()

        ax1.plot(range(len(ma20)), ma20, color='#ffd93d', linewidth=1.5, label='MA20')
        ax1.plot(range(len(ma50)), ma50, color='#6bcb77', linewidth=1.5, label='MA50')

        last_idx = len(df) - 1
        golden_cross_found = False

        for i in range(5, len(df)):
            if not golden_cross_found and ma20.iloc[i-1] <= ma50.iloc[i-1] and ma20.iloc[i] > ma50.iloc[i]:
                ax1.annotate('GOLDEN CROSS', xy=(i, df['Low'].iloc[i]),
                            xytext=(i, df['Low'].iloc[i] - df['Low'].iloc[i]*0.08),
                            arrowprops=dict(arrowstyle='->', color='#00ff00', lw=1.5),
                            color='#00ff00', fontsize=9, fontweight='bold',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.8))
                ax1.scatter(i, df['Low'].iloc[i], color='#00ff00', s=150, marker='^', zorder=5)
                golden_cross_found = True

        rsi = calculate_rsi(df['Close'])

        if rsi.iloc[-1] < 30 and df['Close'].iloc[-1] > df['Close'].iloc[-2]:
            ax1.annotate('OVERSOLD BOUNCE', xy=(last_idx, df['Low'].iloc[-1]),
                        xytext=(last_idx - 10, df['Low'].iloc[-1] - df['Low'].iloc[-1]*0.1),
                        arrowprops=dict(arrowstyle='->', color='#00d2ff', lw=2),
                        color='#00d2ff', fontsize=9, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.8))

        ax2.set_facecolor('#16213e')
        colors_vol = ['#00d2ff' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ff6b6b'
                      for i in range(len(df))]
        ax2.bar(range(len(df)), df['Volume'], color=colors_vol, alpha=0.7, width=0.8)
        ax2.set_ylabel('Volume', color='white')
        ax2.tick_params(colors='white')
        ax2.grid(True, alpha=0.2)

        vol_ma = df['Volume'].rolling(20).mean()
        for i in range(len(df)):
            if df['Volume'].iloc[i] > vol_ma.iloc[i] * 1.5:
                ax2.axvspan(i - 0.5, i + 0.5, alpha=0.3, color='yellow')

        ax1.set_title(f'{ticker_symbol.replace(".JK", "")} - Trading Signals Analysis',
                     color='white', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Price (Rp)', color='white')
        ax1.tick_params(colors='white')
        ax1.grid(True, alpha=0.2)
        ax1.legend(loc='upper left', facecolor='#1a1a2e', labelcolor='white')

        dates = df.index
        date_positions = range(0, len(df), max(1, len(df)//10))
        date_labels = [dates[i].strftime('%d-%b') for i in date_positions]
        ax2.set_xticks(date_positions)
        ax2.set_xticklabels(date_labels, rotation=45, ha='right', color='white')

        fig.subplots_adjust(left=0.05, right=0.95, top=0.93, bottom=0.08, hspace=0.15)

        file = f"{ticker_symbol.replace('.JK', '')}_signals.png"
        plt.savefig(file, facecolor='#1a1a2e', dpi=150, bbox_inches='tight')
        plt.close()

        return file

    except Exception as e:
        print(f"Error generating signals chart: {e}")
        return None


# =========================
# CHART COMMANDS
# =========================

async def advanced_chart_cmd(update, context):
    """
    /chart BBCA - Generate advanced chart with indicators
    """
    if not context.args:
        return await update.message.reply_text(
            "📊 Advanced Chart\n\n"
            "Usage: /chart BBCA\n\n"
            "Features:\n"
            "• Candlestick chart\n"
            "• Multiple MAs (20, 50, 200)\n"
            "• Bollinger Bands\n"
            "• Support/Resistance\n"
            "• RSI subplot\n"
            "• Volume analysis\n"
            "• Auto buy/sell signals"
        )

    ticker = context.args[0].upper() + ".JK"

    await update.message.reply_text(f"📈 Generating advanced chart for {ticker}...")

    file = generate_advanced_chart(ticker)

    if file:
        await update.message.reply_photo(open(file, "rb"),
                                        caption=f"📊 *{ticker.replace('.JK', '')} - Advanced Technical Analysis*\n\n"
                                               f"🟢 *Bullish Signals:* MA20 > MA50, RSI > 50\n"
                                               f"🔴 *Bearish Signals:* MA20 < MA50, RSI < 50\n\n"
                                               f"💡 *Trading Tips:*\n"
                                               f"• Buy when price bounces from support\n"
                                               f"• Sell when price hits resistance\n"
                                               f"• Wait for golden cross for confirmation",
                                        parse_mode='Markdown')
        os.remove(file)
    else:
        await update.message.reply_text("❌ Failed to generate chart. Data insufficient.")


async def signals_chart_cmd(update, context):
    """
    /signals BBCA - Chart with annotated trading signals
    """
    if not context.args:
        return await update.message.reply_text(
            "📈 *Trading Signals Chart*\n\n"
            "Usage: /signals BBCA\n\n"
            "Shows:\n"
            "• Golden/Death Cross signals\n"
            "• Oversold/Overbought alerts\n"
            "• Volume spikes\n"
            "• Buy/Sell entry points",
            parse_mode='Markdown'
        )

    ticker = context.args[0].upper() + ".JK"

    await update.message.reply_text(f"🔍 Analyzing {ticker.replace('.JK', '')} for trading signals...")

    file = generate_trading_signals_chart(ticker)

    if file:
        await update.message.reply_photo(
            open(file, "rb"),
            caption=f"🎯 *{ticker.replace('.JK', '')} - Trading Signals*\n\n"
                   f"✅ *Buy Signal when:*\n"
                   f"• Golden Cross (MA20 crosses above MA50)\n"
                   f"• RSI < 30 + bullish reversal candle\n"
                   f"• High volume breakout (1.5x normal)\n\n"
                   f"❌ *Sell Signal when:*\n"
                   f"• Death Cross (MA20 crosses below MA50)\n"
                   f"• RSI > 70 + bearish reversal candle\n"
                   f"• Price hits strong resistance\n\n"
                   f"{DISCLAIMER}",
            parse_mode='Markdown'
        )
        os.remove(file)
    else:
        await update.message.reply_text(
            "❌ Failed to generate signals chart. Data insufficient (need at least 50 days)."
        )


# =========================
# BASIC COMMANDS
# =========================
async def start(update, context):

    await update.message.reply_text(
        OPENING
    )


async def help_cmd(update, context):

    await update.message.reply_text(
        HELP_TEXT
    )


async def signal_cmd(update, context):

    await update.message.reply_text(
        "⏳ Lagi scan signal..."
    )

    result = run_screener()

    await update.message.reply_text(
        DISCLAIMER +
        "\n\n" +
        result
    )


async def bsjp_cmd(update, context):

    await update.message.reply_text(
        "🚀 Lagi scan BSJP..."
    )

    result = run_bsjp_screener()

    await update.message.reply_text(
        DISCLAIMER +
        "\n\n" +
        result
    )


async def plan_cmd(update, context):
    """
    Command handler untuk advanced trading plan
    Usage: /plan BBCA
    """
    if not context.args:
        return await update.message.reply_text(
            "📈 ADVANCED TRADING PLAN\n\n"
            "Usage: /plan BBCA\n\n"
            "Features:\n"
            "• ATR-based stop loss\n"
            "• Multiple R:R targets\n"
            "• Position sizing\n"
            "• Order flow analysis\n"
            "• Confidence scoring"
        )

    ticker = context.args[0].upper() + ".JK"

    await update.message.reply_text(
        f"🔍 Generating advanced trading plan for {ticker}..."
    )

    result = advanced_trading_plan(ticker)

    if len(result) > 4096:
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000])
    else:
        await update.message.reply_text(result)


async def id_cmd(update, context):

    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"🆔 CHAT ID\n\n{chat_id}"
    )


async def snr_cmd(update, context):

    if not context.args:

        return await update.message.reply_text(
            "Contoh:\n/snr BBCA"
        )

    ticker = (
        context.args[0]
        .upper() + ".JK"
    )

    await update.message.reply_text(
        f"📊 Membuat chart SNR {ticker}..."
    )

    file = generate_snr(ticker)

    if file is None:

        return await update.message.reply_text(
            "❌ Data tidak cukup"
        )

    await update.message.reply_photo(
        open(file, "rb")
    )

    os.remove(file)


async def ml_cmd(update, context):

    if not context.args:

        return await update.message.reply_text(
            "Contoh:\n/ml BBCA"
        )

    ticker = (
        context.args[0]
        .upper() + ".JK"
    )

    await update.message.reply_text(
        f"🤖 Membuat chart ML {ticker}..."
    )

    file = generate_ml(ticker)

    if file is None:

        return await update.message.reply_text(
            "❌ Data tidak cukup"
        )

    await update.message.reply_photo(
        open(file, "rb")
    )

    os.remove(file)


async def bsjp_plan_cmd(update, context):
    """
    Command handler untuk BSJP trading plan
    Usage: /bsjpplan BBCA
    """
    if not context.args:
        return await update.message.reply_text(
            "📈 BSJP TRADING PLAN\n\n"
            "Usage: /bsjpplan BBCA\n\n"
            "BSJP Rules:\n"
            "• Price ≥ 5% dari previous\n"
            "• Price ≥ MA5\n"
            "• Volume ≥ 1.2x previous\n"
            "• Value ≥ 5 Miliar\n\n"
            "Fitur:\n"
            "• BSJP-specific screening rules\n"
            "• Momentum-based targets\n"
            "• Wider stop loss (2.5x ATR)\n"
            "• Liquidity risk assessment\n"
            "• Phased entry/exit strategy"
        )

    ticker = context.args[0].upper() + ".JK"

    await update.message.reply_text(
        f"🔍 Generating BSJP trading plan for {ticker}..."
    )

    result = bsjp_trading_plan(ticker)

    if len(result) > 4096:
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000])
    else:
        await update.message.reply_text(result)


# =========================
# RUN BOT
# =========================
if __name__ == "__main__":

    # Inisialisasi database SQLite saat bot pertama kali jalan
    init_db()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # =========================
    # BASIC
    # =========================
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))

    # =========================
    # SIGNAL
    # =========================
    app.add_handler(CommandHandler("signal", signal_cmd))
    app.add_handler(CommandHandler("bsjp", bsjp_cmd))

    # =========================
    # FILTER
    # =========================
    app.add_handler(CommandHandler("filter", filter_cmd))

    # =========================
    # WATCHLIST
    # =========================
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("rekapwl", rekap_watchlist_cmd))

    # =========================
    # ALERT
    # =========================
    app.add_handler(CommandHandler("alert", alert_cmd))

    # =========================
    # COMPARE
    # =========================
    app.add_handler(CommandHandler("compare", compare_cmd))

    # =========================
    # DAILY REPORT
    # =========================
    app.add_handler(CommandHandler("daily", daily_cmd))

    # =========================
    # TOP GAINER
    # =========================
    app.add_handler(CommandHandler("topgainer", topgainer_cmd))

    # =========================
    # TOP VOLUME
    # =========================
    app.add_handler(CommandHandler("topvolume", topvolume_cmd))

    # =========================
    # HOT STOCK
    # =========================
    app.add_handler(CommandHandler("hotstock", hotstock_cmd))

    # =========================
    # PLAN
    # =========================
    app.add_handler(CommandHandler("plan", plan_cmd))

    # =========================
    # SNR
    # =========================
    app.add_handler(CommandHandler("snr", snr_cmd))

    # =========================
    # ML
    # =========================
    app.add_handler(CommandHandler("ml", ml_cmd))

    # =========================
    # BSJP PLAN
    # =========================
    app.add_handler(CommandHandler("bsjpplan", bsjp_plan_cmd))
    app.add_handler(CommandHandler("bsjptop", bsjp_top_plan_cmd))

    # =========================
    # CHART
    # =========================
    app.add_handler(CommandHandler("chart", advanced_chart_cmd))
    app.add_handler(CommandHandler("signals", signals_chart_cmd))

 if __name__ == "__main__":

    init_db()

    app.run_polling()