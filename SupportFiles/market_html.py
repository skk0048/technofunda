"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  HTML REPORT GENERATOR  v6.3  —  market_html.py                           ║
║                                                                            ║
║  v6.3 changes:                                                             ║
║   • Signal vocabulary: Buy→Bullish, Strong Buy→Very Strong, Sell→Bearish  ║
║     Neutral→Neutral — display-only remap; engine logic unchanged           ║
║   • Sec_Signal in opportunity cards also remapped                          ║
║   • Cell BG color removed for Opportunities/Stocks/Global/Patterns/ETF    ║
║     tabs; Market + Sectors retain full colour                              ║
║   • Font zoom: range widened 0.6→2.0 (was 0.8→1.6)                       ║
║   • Stats bar hidden on individual market pages;                           ║
║     build_html_report returns it so index.html can embed it                ║
║   • TV hover preview (v6.2): iframe pre-warm, daily chart, 720×500        ║
║   • On/Off toggle in header; size constants TV_PREVIEW_W/H                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import pandas as pd
import os
import re
from datetime import datetime, timedelta

# Chart-pattern recency cap (days). Patterns older than this are hidden in the
# Patterns tab regardless of timeframe. See request #8.
PATTERN_RECENT_DAYS = 15

# ── Sector Strength control ───────────────────────────────────────────────────
# Set to False to hide the "Sector Strength" bars section from the Sectors tab.
# The Sector Performance, Sector Rotation, and Industry Rotation sections are
# unaffected — only the bar chart at the top of the Sectors tab is hidden.
ENABLE_SECTOR_STRENGTH = True


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL LABEL → CSS CLASS
# ─────────────────────────────────────────────────────────────────────────────

_SL_CLASS = {
    "🌟 Triple Confirmed": "sl-triple",
    "🌟 RS30 + Long":      "sl-triple",
    "🌟 RS30 + Swing":     "sl-prime",
    "🌟 RS30 Leader":      "sl-prime",
    "🌟 Long Momentum":    "sl-prime",
    "🌟 Prime Setup":      "sl-prime",
    "✅ Long Momentum":    "sl-confirmed",
    "✅ Strong RS":        "sl-confirmed",
    "📈 Swing Entry":      "sl-rsbuy",
    "📈 RS Leader":        "sl-rsbuy",
    "👁 Setup Building":   "sl-watch",
    "👁 RS30 Watch":       "sl-watch",
    "👁 LST Watch":        "sl-watch",
    "👁 MST Watch":        "sl-watch",
    "👁 Watch":            "sl-watch",
    "⬜ Neutral":          "sl-neutral",
    "🔴 RS Breakdown":     "sl-avoid",
}
_AT_CLASS = {
    "PRIME BUY":     "sl-prime",
    "CONFIRMED BUY": "sl-confirmed",
    "RS BUY":        "sl-rsbuy",
    "WATCH":         "sl-watch",
    "NEUTRAL":       "sl-neutral",
    "AVOID":         "sl-avoid",
}


def _signal_class(val):
    v = str(val or "")
    return _SL_CLASS.get(v) or _AT_CLASS.get(v) or ""


# ── Signal vocabulary display remap (v6.3) ───────────────────────────────────
# The engine uses "Buy"/"Strong Buy"/"Sell"/"Neutral" internally.
# We remap these to plain-English market sentiment words for display only.
# Signal_Label (emoji labels) are kept unchanged — they are already good.
_SIG_DISPLAY = {
    # Signal column
    "Buy":        "Bullish",
    "Sell":       "Bearish",
    "Neutral":    "Neutral",
    # Enhanced column
    "Strong Buy": "Very Strong",
    # Sec_Signal / sector Signal
    "Strong Buy": "Very Strong",
}
_ENH_DISPLAY = {
    "Strong Buy": "Very Strong",
    "Buy":        "Strong",
    "Neutral":    "Neutral",
    "Sell":       "Weak",
}
# Sector-level signal (Build: Buy/Sell/Neutral → Bullish/Bearish/Neutral)
_SEC_SIG_DISPLAY = {
    "Buy":     "Bullish",
    "Sell":    "Bearish",
    "Neutral": "Neutral",
}
# MST / LST / RS30 sub-signals
_SUB_SIG_DISPLAY = {
    "Buy":     "Active",
    "Watch":   "Building",
    "Neutral": "—",
    "Sell":    "Exit",
}

def _remap_signal(val, mapping):
    """Return remapped display string, falling back to original if not in map."""
    v = str(val or "")
    return mapping.get(v, v)


# Normalised lookup key: lowercase, strip spaces / underscores / '>' so that
# headers like "RS_22%", "% > SMA50", "AbvSMA50%", "1M_Score" all collapse to
# the same canonical token. Fixes breadth/rotation colours not firing (#6/#7).
def _norm_key(col):
    return re.sub(r"[\s_>]", "", str(col).lower().strip())


# ── Column tooltips: hover text for abbreviated headers ───────────────────────
_COL_TIPS = {
    "symbol":        "Stock ticker symbol. Click to open in TradingView.",
    "company":       "Company name.",
    "sector":        "GICS sector classification.",
    "rank":          "Overall rank within this list (best = 1).",
    "sec_rank":      "Rank of this stock's sector vs all sectors in this market.",
    "chg_1d%":       "Price change % today vs previous close.",
    "chg_5d%":       "Price change % over the last 5 trading days.",
    "rs_22d_idx%":   "Relative Strength vs the market index over 22 trading days (~1 month). Positive = stock is outperforming the market.",
    "rs_55d_idx%":   "Relative Strength vs the market index over 55 trading days (~3 months). Positive = sustained outperformance.",
    "rs_22d_sec%":   "Relative Strength vs the stock's own sector over 22 days. Shows whether the stock leads within its sector.",
    "rs_55d_sec%":   "Relative Strength vs the stock's own sector over 55 days.",
    "rs_120d_idx%":  "Relative Strength vs the market index over 120 trading days (~6 months).",
    "rs_252d_idx%":  "Relative Strength vs the market index over 252 trading days (~1 year).",
    "rsl_14":        "RS Line momentum over 14 periods — measures how fast relative strength is changing. Positive = accelerating outperformance.",
    "w_rs21%":       "Weekly Relative Strength over 21 weeks. Captures longer-term momentum.",
    "signal":        "Current signal based on RS conditions: Bullish, Neutral, or Bearish.",
    "signal_label":  "Primary signal label: Prime (highest conviction) → Confirmed → RS Leader → Watch → Neutral → Avoid.",
    "sec_signal":    "Signal for the stock's entire sector. Bullish sector + bullish stock = higher conviction.",
    "sec_gated":     "✓ = stock's sector is also in a Buy signal. Adds confidence to the individual stock signal.",
    "sec_rs22d%":    "Relative Strength of the stock's sector vs the market index over 22 days.",
    "enhanced":      "Enhanced signal combining RS, SMA alignment, and RSI confirmation. Very Strong = all conditions met.",
    "mst_signal":    "Monthly Supertrend signal direction: Buy or Sell. Captures the primary monthly trend.",
    "lst_signal":    "Long-term Supertrend signal (weekly): Buy or Sell.",
    "rs30_signal":   "RS30 weekly signal: positive RS vs index over 30 weeks.",
    "supertrend":    "Daily Supertrend direction: Buy = price above Supertrend line. Key entry/exit filter.",
    "trend":         "Overall trend assessment combining SMA positions and Supertrend: Strong Bullish, Bullish, Neutral, Bearish, Strong Bearish.",
    "sma_score":     "Count of key moving averages (20/50/100/200-day) the stock is currently trading above. Max = 4. Higher = stronger trend.",
    "total_score":   "Combined score across RS, trend, and signal conditions. Higher = stronger overall setup.",
    "fin_score":     "Fundamental quality score based on revenue growth, profit margins, and return on equity. Higher = better fundamentals.",
    "atr5":          "5-period Average True Range — recent daily volatility in price terms. Drives the sleeve stop loss (SL = ATR(5) × 1.2).",
    "sl_buy%":       "Suggested entry level expressed as % above the last close, based on the strategy signal price.",
    "sl_buy_price":  "Absolute suggested entry price based on the strategy signal.",
    "sl_grade":      "Fundamental quality grade (A to F). A = strong fundamentals. F = weak or missing data.",
    "from_52w_high%":"% below the 52-week high. 0% = at all-time high. -5% = 5% below 52W high. Closer to 0 = stronger momentum.",
    "rel_vol":       "Relative Volume — today\'s volume as a multiple of the 20-day average. >1.5 = above-average interest. >2 = high volume.",
    "p/e":           "Price-to-Earnings ratio. Lower = cheaper relative to earnings. Context-dependent by sector.",
    "sales_yoy%":    "Revenue (Sales) growth year-over-year % — latest annual report vs prior year.",
    "pat_yoy%":      "Profit After Tax growth year-over-year % — measures earnings growth.",
    "sales_qoq%":    "Revenue growth quarter-over-quarter % — most recent quarter vs prior quarter.",
    "pat_qoq%":      "Profit After Tax growth quarter-over-quarter %.",
    "roe%":          "Return on Equity % — how efficiently the company generates profit from shareholders' equity.",
    "margin%":       "Net profit margin % — profit as a share of total revenue.",
    "price":         "Last closing price in local currency.",
    "index_price":   "Index closing price.",
    "stocks":        "Total number of stocks in this group (sector/index).",
    "valid":         "Stocks with enough data to generate valid signals.",
    "adv/dec":       "Advancing stocks / Declining stocks today.",
    "rs22%":         "% of stocks in this group with positive 22-day RS vs the index. ≥60 = bullish breadth.",
    "rs55%":         "% of stocks in this group with positive 55-day RS vs the index. ≥60 = sustained bullish breadth.",
    "rsi50%":        "% of stocks with RSI above 50. ≥60 = majority in bullish momentum.",
    "abvsma20%":     "% of stocks trading above their 20-day moving average. Short-term breadth indicator.",
    "abvsma50%":     "% of stocks trading above their 50-day moving average. Medium-term breadth.",
    "abvsma100%":    "% of stocks trading above their 100-day moving average.",
    "abvsma200%":    "% of stocks trading above their 200-day moving average. Long-term market health indicator.",
    "1m_score":      "Market breadth score over 1 month. ≥60 = Bullish · 40-60 = Neutral · <40 = Bearish.",
    "3m_score":      "Market breadth score over 3 months.",
    "6m_score":      "Market breadth score over 6 months.",
    "1m_zone":       "Zone classification for 1-month breadth: Bullish / Neutral / Bearish.",
    "3m_zone":       "Zone classification for 3-month breadth.",
    "6m_zone":       "Zone classification for 6-month breadth.",
    "1m%":           "Price return over the last 1 month.",
    "3m%":           "Price return over the last 3 months.",
    "6m%":           "Price return over the last 6 months.",
    "12m%":          "Price return over the last 12 months.",
    "ytd%":          "Year-to-date price return.",
    "rs_1m%":        "Relative return vs index over 1 month (stock return minus index return).",
    "rs_3m%":        "Relative return vs index over 3 months.",
    "rs_6m%":        "Relative return vs index over 6 months.",
}

def _col_tip(col):
    """Return a title= attribute string for the given column, or empty string."""
    key = re.sub(r"[\s_]", "", str(col).lower().strip()).replace("%","_pct")
    # Try exact norm key first, then cleaned version
    raw = str(col).lower().strip()
    tip = _COL_TIPS.get(raw) or _COL_TIPS.get(re.sub(r"[\s]","_",raw))
    if not tip:
        # normalised lookup: drop non-alpha except % and /
        nk = re.sub(r"[^a-z0-9%/]","_", raw).strip("_")
        tip = _COL_TIPS.get(nk)
    return f' title="{tip}"' if tip else ""

# 0-100 breadth / score columns → ≥60 green · 40-60 orange · <40 red.
_BREADTH_KEYS = {_norm_key(c) for c in (
    "rs22%", "rs55%", "rsi50%", "rsi>50%",
    "abvsma20%", "abvsma50%", "abvsma100%", "abvsma200%",
    "%>sma20", "%>sma50", "%>sma100", "%>sma200",
    "1m_score", "3m_score", "6m_score", "12m_score",
    "breadth%", "breadth_score", "momentum_score",
)}
# Return / change columns stay on the diverging (pos/neg) scale even inside a
# breadth-mode table — these are NOT 0-100 figures.
_RETURN_KEYS = {_norm_key(c) for c in (
    "chg1d%", "chg5d%",
    "rs22d%", "rs55d%", "rs120d%", "rs252d%",
    "rs22didx%", "rs55didx%", "rs120didx%", "rs252didx%",
    "rs22dsec%", "rs55dsec%",
    "1m%", "3m%", "6m%", "12m%", "ytd%",
    "salesyoy%", "patyoy%", "salesqoq%", "patqoq%",
    "roe%", "margin%", "wrs21%", "wrs30%", "mrs12%", "sleevers",
)}


def _is_breadth_col(col, pct_mode=None):
    """Should this column use the 60/40 green/amber/red breadth scale?"""
    k = _norm_key(col)
    if k in _RETURN_KEYS:
        return False
    if k in _BREADTH_KEYS:
        return True
    # score / breadth columns wherever they appear (sector & industry rotation)
    if ("score" in k or "breadth" in k or "percentile" in k) and "scorecard" not in k:
        return True
    # In a dedicated breadth table, treat every remaining percent column as 0-100
    if pct_mode == "breadth" and k.endswith("%"):
        return True
    return False


def _cell_class(col, val, pct_mode=None, no_bg=False):
    # Breadth / rotation 0-100 colouring — suppress entirely when no_bg
    if _is_breadth_col(col, pct_mode):
        if no_bg: return ""
        try:
            f = float(val)
            if f >= 60: return "bd-green"
            if f >= 40: return "bd-amber"
            return "bd-red"
        except: pass

    col = str(col).lower().strip()

    # ── Signal-label (sl-* classes have both BG + text colour) ────────────────
    if col == "signal_label" or col == "action_tier":
        cls = _signal_class(val)
        if no_bg:
            # Map sl-* → sl-*-text (text colour only, no background)
            _sl_text = {
                "sl-triple":    "sl-triple-text",
                "sl-prime":     "sl-prime-text",
                "sl-confirmed": "sl-confirmed-text",
                "sl-rsbuy":     "sl-rsbuy-text",
                "sl-watch":     "sl-watch-text",
                "sl-neutral":   "sl-neutral-text",
                "sl-avoid":     "sl-avoid-text",
            }
            return _sl_text.get(cls, cls)
        return cls

    # ── Signal / Enhanced / Sec_Signal (sig-* classes have BG colour) ─────────
    if col in ("signal", "enhanced", "sec_signal"):
        raw = str(val)
        _sig_full = {
            "Strong Buy": "sig-strongbuy", "Buy": "sig-buy",
            "Sell": "sig-sell", "Neutral": "sig-neutral",
            "Very Strong": "sig-strongbuy", "Bullish": "sig-buy",
            "Strong": "sig-buy", "Bearish": "sig-sell", "Weak": "sig-sell",
        }
        _sig_text = {
            "Strong Buy": "sig-strongbuy-text", "Buy": "sig-buy-text",
            "Sell": "sig-sell-text", "Neutral": "sig-neutral-text",
            "Very Strong": "sig-strongbuy-text", "Bullish": "sig-buy-text",
            "Strong": "sig-buy-text", "Bearish": "sig-sell-text", "Weak": "sig-sell-text",
        }
        return (_sig_text if no_bg else _sig_full).get(raw, "")

    # ── MST / LST / RS30 sub-signals ──────────────────────────────────────────
    if col in ("mst_signal", "lst_signal", "rs30_signal"):
        raw = str(val)
        _sub_full = {
            "Buy": "sig-buy", "Active": "sig-buy",
            "Watch": "sig-neutral", "Building": "sig-neutral", "Neutral": "",
        }
        _sub_text = {
            "Buy": "sig-buy-text", "Active": "sig-buy-text",
            "Watch": "sig-neutral-text", "Building": "sig-neutral-text", "Neutral": "",
        }
        return (_sub_text if no_bg else _sub_full).get(raw, "")

    if col == "action":
        return {"BUY": "sig-buy", "SELL": "sig-sell", "WAIT": "sig-neutral"}.get(str(val), "")
    if col == "supertrend":
        return {"Buy": "pos", "Sell": "neg"}.get(str(val), "")
    if col == "trend":
        v = str(val)
        if "Bullish" in v or "BULLISH" in v: return "pos-strong"
        if "Bearish" in v or "BEARISH" in v: return "neg-strong"
        return ""
    # Zone text columns in breadth/rotation tables (e.g. 1m_zone, 3m_zone)
    if col.endswith("_zone") or col in ("zone",):
        v = str(val)
        if "Bullish" in v: return "txt-bull"
        if "Bearish" in v: return "txt-bear"
        if "Neutral" in v: return "txt-neut"
        return ""
    if col == "sec_gated":
        return "pos-strong" if str(val) == "✓" else "dim"
    if col == "sl_grade":
        return {"A": "pos-strong", "B": "pos", "C": "pos-dim",
                "D": "neg-dim", "F": "neg"}.get(str(val), "")
    if col in ("sl_buy%", "sl%", "sl_sell%"):
        try:
            f = float(val)
            if f <= 3:  return "pos-strong"
            if f <= 5:  return "pos"
            if f <= 8:  return "pos-dim"
            if f <= 12: return "neg-dim"
            return "neg"
        except: pass
    if col == "eps":
        try:
            f = float(val)
            if f > 0:  return "pos"
            if f < 0:  return "neg-strong"
        except: pass

    # ── Chart-pattern table (request #4) ──────────────────────────────────────
    # Pattern name in bold; RS_Signal / Direction coloured by sentiment;
    # RS_Score (a weighted RS%) and RR (risk:reward) coloured by quality.
    if col == "pattern":
        return "cell-bold"
    if col == "rs_signal":
        return {"Buy": "sig-buy-text", "Strong Buy": "sig-strongbuy-text",
                "Sell": "sig-sell-text", "Neutral": "sig-neutral-text"}.get(str(val), "")
    if col == "direction":
        v = str(val).upper()
        if v == "BULLISH": return "pos-strong"
        if v == "BEARISH": return "neg-strong"
        return ""
    if col == "rr":
        try:
            f = float(val)
            if f >= 2:   return "pos-strong"
            if f >= 1.5: return "pos"
            if f >= 1:   return "pos-dim"
            return "neg"
        except: pass

    # ── Percent columns — text-colour only in no-bg tabs (no background) ────────
    if col == "from_52w_high%":
        try:
            f = float(val)
            if f >= -3:   return "pos-strong"
            if f >= -8:   return "pos"
            if f >= -15:  return "pos-dim"
            if f >= -25:  return "neg-dim"
            if f >= -40:  return "neg"
            return "neg-strong"
        except: pass
    if col == "rel_vol":
        try:
            f = float(val)
            if f >= 3:   return "pos-strong"
            if f >= 1.5: return "pos"
            if f >= 1.0: return "pos-dim"
            return "neg-dim"
        except: pass
    pct_cols = {
        "chg_1d%", "chg_5d%", "rs_22d%", "rs_55d%", "rs_120d%", "rs_252d%",
        "rs_22d_idx%", "rs_55d_idx%", "rs_120d_idx%", "rs_252d_idx%",
        "1m%", "3m%", "6m%", "12m%", "ytd%", "sales_yoy%", "pat_yoy%",
        "sales_qoq%", "pat_qoq%", "roe%", "margin%", "w_rs21%", "w_rs30%",
        "m_rs12%", "sec_rs22d%", "sec_rs55d%", "sleeve_rs", "rs_score",
    }
    if col in pct_cols or col.endswith("%"):
        try:
            f = float(val)
            if f > 5:  return "pos-strong"
            if f > 0:  return "pos"
            if f < -5: return "neg-strong"
            if f < 0:  return "neg"
        except: pass
    return ""


def _fmt(val):
    if val is None: return ""
    if isinstance(val, float):
        if np.isnan(val): return ""
        if val == int(val) and abs(val) < 1e9: return str(int(val))
        return f"{val:.2f}"
    s = str(val)
    return "" if s in ("nan","None","") else s


_CUR_MKT = "INDIA"   # set per-report by build_html_report; used for TradingView links

# ── yfinance suffix  →  TradingView exchange prefix ──────────────────────────
# Sorted longest-first so ".TWO" is checked before ".T", ".KL" before ".L", etc.
_SUFFIX_MAP = {
    # India
    ".NS": "NSE",  ".BO": "BSE",
    # Saudi Arabia
    ".SR": "TADAWUL",
    # China
    ".SS": "SSE",  ".SH": "SSE",          # Shanghai (.SS = yfinance, .SH = other)
    ".SZ": "SZSE",                          # Shenzhen
    # Hong Kong
    ".HK": "HKEX",
    # Japan
    ".T":  "TSE",
    # South Korea
    ".KS": "KRX",  ".KQ": "KOSDAQ",
    # Taiwan
    ".TWO": "TPEX",  ".TW": "TWSE",
    # Australia
    ".AX": "ASX",
    # UK
    ".L":  "LSE",
    # Germany
    ".DE": "XETR",  ".F": "FWB",      # TV uses XETR (not XETRA) for Xetra
    # France / Netherlands (Euronext)
    ".PA": "EURONEXT",  ".AS": "EURONEXT",
    # Spain
    ".MC": "BME",
    # Italy
    ".MI": "MIL",
    # Sweden / Nordics
    ".ST": "OMXSTO",                   # TV uses OMXSTO (not OMX) for Stockholm
    # Switzerland
    ".SW": "SIX",                      # TV uses SIX (not SWX) for SIX Swiss Exchange
    # Canada
    ".TO": "TSX",  ".V": "TSXV",
    # Brazil
    ".SA": "BMFBOVESPA",
    # Singapore
    ".SI": "SGX",
    # Thailand
    ".BK": "SET",
    # Malaysia
    ".KL": "MYX",                      # TV uses MYX (not KLSE) for Bursa Malaysia
    # South Africa
    ".JO": "JSE",
    # Poland
    ".WA": "GPW",
    # Turkey  (yfinance uses .IS)
    ".IS": "BIST",
    # UAE
    ".DU": "DFM",  ".AD": "ADX",
    # Indonesia
    ".JK": "IDX",
    # Mexico
    ".MX": "BMV",
}
# Pre-sort by length descending once so the loop is always correct.
_SUFFIX_ITEMS = sorted(_SUFFIX_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# Yahoo Finance commodity/futures/forex symbols that must map directly to
# their TradingView equivalents — checked before suffix stripping.
_DIRECT_TV_MAP = {
    # Futures (Yahoo =F  →  TV exchange:symbol1!)
    "GC=F":     "COMEX:GC1!",      # Gold
    "SI=F":     "COMEX:SI1!",      # Silver
    "HG=F":     "COMEX:HG1!",      # Copper
    "PL=F":     "NYMEX:PL1!",      # Platinum
    "CL=F":     "NYMEX:CL1!",      # Crude Oil WTI
    "BZ=F":     "NYMEX:BB1!",      # Brent Crude
    "NG=F":     "NYMEX:NG1!",      # Natural Gas
    "KC=F":     "ICEUS:KC1!",      # Coffee
    "ZC=F":     "CBOT:ZC1!",       # Corn
    "ZW=F":     "CBOT:ZW1!",       # Wheat
    "ZS=F":     "CBOT:ZS1!",       # Soybeans
    # Dollar Index
    "DX-Y.NYB": "TVC:DXY",
    # Forex (Yahoo =X  →  TV FX:)
    "USDINR=X": "FX:USDINR",
    "EURINR=X": "FX:EURINR",
    "EURUSD=X": "FX:EURUSD",
    "GBPUSD=X": "FX:GBPUSD",
    "USDJPY=X": "FX:USDJPY",
    "USDCAD=X": "FX:USDCAD",
    "AUDUSD=X": "FX:AUDUSD",
    "USDCHF=X": "FX:USDCHF",
}

# When a symbol has NO file-extension suffix, fall back to the market code.
_MARKET_EXCHANGE = {
    "INDIA": "NSE",
    "USA":   "",            # US: bare symbol; TV resolves it natively
    "US":    "",            # market_usa_html passes "US" — same as USA
    "UK":    "LSE",
    "DE":    "XETR",
    "JP":    "TSE",
    "CN":    "SSE",
    "HK":    "HKEX",
    "KR":    "KRX",
    "TW":    "TWSE",
    "AU":    "ASX",
    "CA":    "TSX",
    "SA":    "TADAWUL",     # market code SA = Saudi Arabia
    "BR":    "BMFBOVESPA",
    "SG":    "SGX",
    "TH":    "SET",
    "MY":    "MYX",
    "ZA":    "JSE",
    "PL":    "GPW",
    "TR":    "BIST",
    "AE":    "DFM",         # UAE default → Dubai Financial Market
    "ID":    "IDX",
    "MX":    "BMV",
    "CH":    "SIX",
    "FR":    "EURONEXT",
    "ES":    "BME",
    "IT":    "MIL",
    "NL":    "EURONEXT",
    "SE":    "OMXSTO",
}


def _tv_link(sym, market=None):
    """Wrap a ticker in a TradingView chart hyperlink.

    Strips yfinance-style country suffixes (e.g. .SR, .SS, .SZ, .HK, .KS, .T …)
    and builds a correctly prefixed TradingView URL so Saudi, China, HK, Korea,
    Japan, etc. all resolve instead of showing a broken symbol page.
    Falls back to the market-code exchange when the symbol carries no suffix.
    Commodity/futures/forex symbols (GC=F, DX-Y.NYB, EURUSD=X …) are mapped
    directly via _DIRECT_TV_MAP before suffix stripping is attempted.
    """
    market = (market or _CUR_MKT).upper()
    s = str(sym).strip()
    if not s or s in ("—", "nan", "None"):
        return _fmt(sym)

    # 0. Direct override for futures, DXY, forex (=F / =X / .NYB symbols).
    if s in _DIRECT_TV_MAP:
        tv   = _DIRECT_TV_MAP[s].replace(":", "%3A")
        base = s   # display the original Yahoo symbol (e.g. GC=F)
        url  = "https://www.tradingview.com/chart/?symbol=" + tv
        return (f'<a href="{url}" target="_blank" rel="noopener" '
                f'class="tv-link" data-tv="{tv}" title="Open {s} in TradingView">{s}</a>')

    base = s
    exch = ""
    su   = s.upper()

    # 1. Try every known suffix (longest first avoids partial matches).
    for suf, tv_exch in _SUFFIX_ITEMS:
        if su.endswith(suf.upper()):
            base = s[: -len(suf)]
            exch = tv_exch
            break

    # 2. No suffix found — use market-level default.
    if exch == "" and base == s:
        exch = _MARKET_EXCHANGE.get(market, "")

    tv  = (exch + "%3A" + base) if exch else base
    url = "https://www.tradingview.com/chart/?symbol=" + tv

    # Preview override: NSE symbols don't render in TradingView's free
    # widgetembed (hover preview), but the SAME ticker on BSE does. So show the
    # BSE listing in the hover preview while keeping NSE for the click-through
    # chart (which is the better/primary chart). data-tv-preview is read by the
    # hover JS; when absent the hover falls back to data-tv.
    preview_attr = f' data-tv-preview="BSE%3A{base}"' if exch == "NSE" else ""

    return (f'<a href="{url}" target="_blank" rel="noopener" '
            f'class="tv-link" data-tv="{tv}"{preview_attr} '
            f'title="Open {base} in TradingView">{base}</a>')


# ─────────────────────────────────────────────────────────────────────────────
#  TABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

_SKIP_COLS = {"tv_symbol","_o","primary_rs_period","yahoo"}
_LEFT_COLS = {"symbol","company","name","sector","industry","country","region",
              "commodity","group","chart_pattern","setup_desc","strategy","notes",
              "signal_type","trend","signal_label","etf"}

# Identity columns that stay visible across every mobile column-set toggle.
_GRP_PIN = {"symbol","company","name","price","chg_1d%","signal_label",
            "country","commodity","etf","rank"}


def _auto_group_map(cols):
    """Classify each column into pin / analysis / tech / fin by name, so the mobile
       column-set toggle works on any table without per-table column lists.
       Order matters: 'score' columns and fundamentals are claimed before the
       generic technical/analysis keyword sweeps."""
    gm = {}
    for c in cols:
        cl = c.lower().strip()
        if cl in _GRP_PIN:
            gm[cl] = "pin"
        elif "score" in cl:                                            # *_Score → analysis
            gm[cl] = "analysis"
        elif any(k in cl for k in ("sales","pat_","roe","d/e","p/e","eps",
                                   "mkt_cap","margin","dividend","book","p/b")):
            gm[cl] = "fin"
        elif any(k in cl for k in ("rsi","trend","sma","52w","rel_vol","sl_",
                                   "supertrend","breakout","mst_signal","lst_signal",
                                   "rs30","atr","abv_","pattern","macd","adx")):
            gm[cl] = "tech"
        elif any(k in cl for k in ("rs_","_rs","w_rs","rs%","sec_","sector","industry",
                                   "region","group","enhanced","signal","1m%","3m%",
                                   "6m%","12m%","1w%","mom","benchmark")):
            gm[cl] = "analysis"
        else:
            gm[cl] = "pin"          # unknown → always visible (safe default)
    return gm


def _build_table(df, table_id, searchable=True, max_rows=2000, pct_mode=None, no_bg=False,
                 link_cols=("symbol",), link_market=None, groups=False,
                 group_default="analysis"):
    """link_cols: header names (lowercase) whose cells become TradingView links.
       link_market: market code passed to _tv_link (e.g. 'US' for global ETF/commodity
       tables so US-listed tickers aren't prefixed with the page's home exchange).
       groups: when True, enable the mobile column-set toggle (chips appear only
       ≤640px; columns auto-classified by _auto_group_map). group_default: the group
       shown first on phones."""
    if df is None or df.empty:
        return '<p class="empty">No data available.</p>'
    df = df.head(max_rows).copy()

    # ── Signal vocabulary remap (v6.3) ─────────────────────────────────────
    # Remap display values in a copy so engine logic is never touched.
    for col in df.columns:
        cl = col.lower().strip()
        if cl == "signal":
            df[col] = df[col].map(lambda v: _remap_signal(v, _SEC_SIG_DISPLAY))
        elif cl == "enhanced":
            df[col] = df[col].map(lambda v: _remap_signal(v, _ENH_DISPLAY))
        elif cl == "sec_signal":
            df[col] = df[col].map(lambda v: _remap_signal(v, _SEC_SIG_DISPLAY))
        elif cl in ("mst_signal","lst_signal","rs30_signal"):
            df[col] = df[col].map(lambda v: _remap_signal(v, _SUB_SIG_DISPLAY))

    cols = [c for c in df.columns if c.lower().strip() not in _SKIP_COLS]

    # ── Column-group classes (mobile column-set toggle) ─────────────────────
    # Active only when groups=True, so every other table renders byte-for-byte
    # as before (no size cost across the 28 pages).
    group_map = _auto_group_map(cols) if groups else None
    freeze_col = None
    if group_map:
        freeze_col = next((c for c in cols
                           if group_map.get(c.lower().strip()) == "pin"),
                          cols[0] if cols else None)
    def _grp_cls(c):
        if not group_map:
            return ""
        extra = " col-sym" if c == freeze_col else ""
        return f" gcol g-{group_map.get(c.lower().strip(), 'pin')}{extra}"
    gcls = [_grp_cls(c) for c in cols]

    def _cls_attr(base, gc):
        full = (base + gc).strip()
        return f' class="{full}"' if full else ""

    ths = "".join(
        f'<th{_cls_attr("", gc)} style="text-align:{"left" if c.lower() in _LEFT_COLS else "center"}"'
        f'{_col_tip(c)} onclick="sortTable(this)">{c}</th>'
        for c, gc in zip(cols, gcls)
    )
    rows_html = ""
    for _, row in df.iterrows():
        tds = ""
        for c, gc in zip(cols, gcls):
            val = row[c]; cls = _cell_class(c, val, pct_mode, no_bg=no_bg)
            display = (_tv_link(val, link_market) if c.lower().strip() in link_cols
                       else _fmt(val))
            align = "left" if c.lower() in _LEFT_COLS else "center"
            ca = _cls_attr(cls, gc)
            tds += f'<td{ca} style="text-align:{align}">{display}</td>'
        rows_html += f"<tr>{tds}</tr>"
    col_filter = ""
    if searchable:
        cfs = "".join(
            f'<th{_cls_attr("", gcls[i])}><input class="cf" data-col="{i}" '
            f'title="Filter: &gt;15  &lt;40  &gt;=60  10-20  or text" '
            f'oninput="filterColumn(this,\'{table_id}\')" placeholder="🔍"></th>'
            for i in range(len(cols))
        )
        col_filter = f'<tr class="col-filter">{cfs}</tr>'
    chips = ""
    if group_map:
        present = {group_map[c.lower().strip()] for c in cols}
        if present - {"pin"}:          # at least one collapsible group exists
            defs  = [("analysis", "Analysis"), ("tech", "Technical"), ("fin", "Finance")]
            avail = [(g, lbl) for g, lbl in defs if g in present]
            gd    = group_default if group_default in present else avail[0][0]
            _chip = lambda g, lbl, act="": (
                f'<button class="grp-chip {act}" data-grp="{g}" '
                f'onclick="setGroup(\'{table_id}\',\'{g}\',this)">{lbl}</button>')
            chips = (f'<div class="grp-chips" data-for="{table_id}" data-default="{gd}">'
                     f'<span class="grp-chips-lbl">Columns:</span>'
                     + _chip("all", "All", "active")
                     + "".join(_chip(g, lbl) for g, lbl in avail)
                     + '</div>')
    search = (f'<div class="tbl-search"><input type="text" placeholder="🔍 Filter all columns…  (per-column accepts &gt;15, &lt;40, 10-20)"'
              f' data-global-for="{table_id}" oninput="filterTable(this,\'{table_id}\')"></div>') if searchable else ""
    return (f'{search}{chips}<div class="tbl-wrap"><table id="{table_id}" class="data-tbl">'
            f'<thead><tr>{ths}</tr>{col_filter}</thead><tbody>{rows_html}</tbody></table></div>'
            f'<p class="row-count" id="{table_id}-count">{len(df)} rows</p>')


def _reorder_leading(df, leading):
    """Return df with `leading` columns moved to the front (only those present),
    preserving the original order of every remaining column. Non-destructive."""
    if df is None or df.empty:
        return df
    lead = [c for c in leading if c in df.columns]
    rest = [c for c in df.columns if c not in lead]
    return df[lead + rest]


# ─────────────────────────────────────────────────────────────────────────────
#  MARKET HEALTH CARD
# ─────────────────────────────────────────────────────────────────────────────

def _build_health_card(stock_df, sector_str_df, market):
    if stock_df is None or stock_df.empty: return ""
    sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
    at_col = "Action_Tier"  if "Action_Tier"  in stock_df.columns else None
    def _cnt_sl(e):
        return int(stock_df[sl_col].astype(str).str.startswith(e).sum()) if sl_col else 0
    def _cnt_at(v):
        return int((stock_df[at_col] == v).sum()) if at_col else 0
    prime = _cnt_sl("🌟") or _cnt_at("PRIME BUY")
    conf  = _cnt_sl("✅") or _cnt_at("CONFIRMED BUY")
    rsbuy = _cnt_sl("📈") or _cnt_at("RS BUY")
    watch = _cnt_sl("👁") or _cnt_at("WATCH")
    avoid = _cnt_sl("🔴") or _cnt_at("AVOID")
    total = len(stock_df)
    buy_pct = round((prime+conf+rsbuy)/max(total,1)*100)
    mood, mcls = (("Risk-On 🟢","mood-on") if buy_pct>=50
                  else (("Mixed ⚪","mood-mix") if buy_pct>=25
                  else ("Risk-Off 🔴","mood-off")))
    top_secs = ""; worst_secs = ""
    if sector_str_df is not None and not sector_str_df.empty:
        for _, r in sector_str_df.head(3).iterrows():
            sig = r.get("Signal","")
            cls = "pos-strong" if sig=="Buy" else ("neg" if sig=="Sell" else "dim")
            rs  = r.get("RS_22d%", r.get("RS_55d%",0)) or 0
            top_secs += f'<span class="sec-pill {cls}">{r["Sector"]} {rs:+.1f}%</span>'
        # Worst 3 sectors (weakest first) — always shown in red
        worst = sector_str_df.tail(3).iloc[::-1]
        for _, r in worst.iterrows():
            rs = r.get("RS_22d%", r.get("RS_55d%",0)) or 0
            worst_secs += f'<span class="sec-pill neg">{r["Sector"]} {rs:+.1f}%</span>'
    return f"""<div class="health-card">
  <div class="hc-grid">
    <div class="hc-block"><div class="hc-label">Market Mood</div><div class="hc-value {mcls}">{mood}</div></div>
    <div class="hc-block"><div class="hc-label">Universe</div><div class="hc-value">{total}</div></div>
    <div class="hc-block"><div class="hc-label">Buy Setups</div><div class="hc-value pos-strong">{prime+conf+rsbuy} <span class="hc-sub">({buy_pct}%)</span></div></div>
    <div class="hc-block"><div class="hc-label">🌟 Prime</div><div class="hc-value sl-triple-inline">{prime}</div></div>
    <div class="hc-block"><div class="hc-label">✅ Confirmed</div><div class="hc-value sl-confirmed-inline">{conf}</div></div>
    <div class="hc-block"><div class="hc-label">📈 RS Buy</div><div class="hc-value sl-rsbuy-inline">{rsbuy}</div></div>
    <div class="hc-block"><div class="hc-label">👁 Watch</div><div class="hc-value sl-watch-inline">{watch}</div></div>
    <div class="hc-block"><div class="hc-label">🔴 Avoid</div><div class="hc-value sl-avoid-inline">{avoid}</div></div>
  </div>
  <div class="hc-sectors"><span class="hc-label">🟢 Top Sectors: </span>{top_secs}</div>
  <div class="hc-sectors"><span class="hc-label">🔴 Worst Sectors: </span>{worst_secs}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT CARDS
# ─────────────────────────────────────────────────────────────────────────────

def _build_snap_cards(snapshot_df):
    if snapshot_df is None or snapshot_df.empty: return ""
    cards = ""
    for _, row in snapshot_df.iterrows():
        name=_fmt(row.get("Name","")); price=(_fmt(row.get("Price","")) or "—")
        chg1=row.get("Chg_1D%",""); trend=_fmt(row.get("Trend",""))
        if not name or "──" in name: continue
        try:
            cf=float(chg1)
            if cf != cf or cf in (float('inf'), float('-inf')): raise ValueError("nan/inf")
            cls="pos" if cf>0 else ("neg" if cf<0 else ""); cs=f"{cf:+.2f}%"
        except: cls=""; cs=(_fmt(chg1) or "N/A")
        tc="pos-strong" if "Bullish" in trend else ("neg-strong" if "Bearish" in trend else "dim")
        cards += (f'<div class="snap-card"><div class="snap-name">{name}</div>'
                  f'<div class="snap-price">{price}</div>'
                  f'<div class="snap-chg {cls}">{cs}</div>'
                  f'<div class="snap-trend {tc}">{trend}</div></div>')
    return f'<div class="snap-grid">{cards}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  BEGINNER EXPLANATION PANELS
# ─────────────────────────────────────────────────────────────────────────────

_OPP_PANEL = '''<details class="beginner-panel">
  <summary>What am I looking at? — Opportunities explained</summary>
  <ul>
    <li><strong>🌟 Prime</strong> — Highest conviction setup. Stock is outperforming the market and sector on multiple timeframes with strong fundamentals. Best setups to research first.</li>
    <li><strong>✅ Confirmed / Long Momentum</strong> — Most conditions are met. Strong relative strength with technical confirmation. Worth adding to your watchlist.</li>
    <li><strong>📈 RS Leader / RS Buy</strong> — Positive relative strength vs market and sector. Early-stage momentum — watch for breakout confirmation.</li>
    <li><strong>Green = outperforming</strong> the market index. <strong>Red = underperforming</strong>. Gray = no clear direction.</li>
    <li>Hover over any column header for a full description. <a href="#" onclick="showTab(\'guide\');return false;">See the full Signal Guide →</a></li>
  </ul>
</details>'''

_STOCK_PANEL = '''<details class="beginner-panel">
  <summary>What am I looking at? — All Stocks table explained</summary>
  <ul>
    <li><strong>Signal_Label</strong> — Each stock is classified from 🌟 Prime (strongest) to 🔴 Avoid (weakest vs market). Focus on Prime and Confirmed first.</li>
    <li><strong>RS_22d_Idx% / RS_55d_Idx%</strong> — How much the stock has outperformed (+) or underperformed (−) the market index over 22 and 55 trading days.</li>
    <li><strong>SMA_Score</strong> — Count of moving averages (20/50/100/200-day) the stock is trading above. Score 4 = strongest uptrend.</li>
    <li><strong>Trend</strong> — Overall trend assessment: Strong Bullish → Bullish → Neutral → Bearish → Strong Bearish.</li>
    <li>Hover over any column header for a full description. Use the search box to filter by sector, symbol, or score range (e.g. &gt;60). <a href="#" onclick="showTab(\'guide\');return false;">Full Guide →</a></li>
  </ul>
</details>'''


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR BARS
# ─────────────────────────────────────────────────────────────────────────────

def _build_sector_bars(sector_df):
    if sector_df is None or sector_df.empty: return ""
    html = '<div class="sector-bars">'
    for _, row in sector_df.iterrows():
        sec=_fmt(row.get("Sector","")); sig=_fmt(row.get("Signal",""))
        rs22=row.get("RS_22d%",0); rs55=row.get("RS_55d%",0)
        rank=_fmt(row.get("Rank","")); rsi=_fmt(row.get("RSI_14",""))
        try: r22=float(rs22); r55=float(rs55)
        except: r22=0; r55=0
        bar_w=min(abs(r22)*3,100)
        icon="✅" if sig=="Buy" else ("🔴" if sig=="Sell" else "⬜")
        sc="sig-buy" if sig=="Buy" else ("sig-sell" if sig=="Sell" else "sig-neutral")
        rsi_cls="pos" if rsi and float(rsi)>50 else "neg" if rsi and float(rsi)<50 else ""
        html += (f'<div class="sec-row">'
                 f'<div class="sec-rank">#{rank}</div>'
                 f'<div class="sec-name">{icon} {sec}</div>'
                 f'<div class="sec-bar-wrap"><div class="sec-bar {"bar-pos" if r22>=0 else "bar-neg"}" style="width:{bar_w:.0f}%"></div></div>'
                 f'<div class="sec-rs {"" if r22>=0 else "neg"}">{r22:+.1f}%</div>'
                 f'<div class="sec-rs55 {"" if r55>=0 else "neg"}">{r55:+.1f}%</div>'
                 f'<div class="sec-rsi {rsi_cls}">RSI {rsi}</div>'
                 f'<div class="{sc} sec-sig-badge">{sig}</div></div>')
    return html + "</div>"


# ─────────────────────────────────────────────────────────────────────────────
#  OPPORTUNITY CARDS
# ─────────────────────────────────────────────────────────────────────────────

def _build_opportunity_cards(df):
    if df is None or df.empty: return ""
    if "Message" in df.columns:
        return f'<p class="empty">{df["Message"].iloc[0]}</p>'
    prev_sec=""; html=""
    for _, row in df.iterrows():
        sec=_fmt(row.get("Sector","")); sym=_fmt(row.get("Symbol",""))
        if not sym: continue
        if sec != prev_sec:
            sec_sig=_fmt(row.get("Sec_Signal",""))
            sec_sig_display = _remap_signal(sec_sig, _SEC_SIG_DISPLAY)
            sec_rs=row.get("Sec_RS22d%",row.get("Sec_RS55d%",""))
            try: rs_s=f"{float(sec_rs):+.1f}%"
            except: rs_s=_fmt(sec_rs)
            sc="sig-buy" if sec_sig=="Buy" else ("sig-sell" if sec_sig=="Sell" else "sig-neutral")
            html += (f'<div class="opp-sec-hdr"><span>{sec}</span>'
                     f'<span class="{sc}">{sec_sig_display} {rs_s}</span></div>')
            prev_sec=sec
        sl=_fmt(row.get("Signal_Label",row.get("Action_Tier",""))); sl_c=_signal_class(sl)
        company=_fmt(row.get("Company","")); price=_fmt(row.get("Price",""))
        rs22=row.get("RS_22d_Idx%",""); rsi=_fmt(row.get("RSI_14",""))
        sl_pct=_fmt(row.get("SL_Buy%","")); sl_gr=_fmt(row.get("SL_Grade",""))
        score=_fmt(row.get("Total_Score","")); sal_yoy=_fmt(row.get("Sales_YoY%",""))
        pat_yoy=_fmt(row.get("PAT_YoY%","")); chart_p=_fmt(row.get("Chart_Pattern",""))
        try: rs_s=f"{float(rs22):+.1f}%"
        except: rs_s=_fmt(rs22)
        rs_cls="pos-strong" if rs_s.startswith("+") else "neg-strong"
        sl_g_cls={"A":"pos-strong","B":"pos","C":"pos-dim","D":"neg-dim","F":"neg"}.get(sl_gr,"")
        html += f"""<div class="opp-card">
  <div class="opp-head"><span class="opp-sym">{_tv_link(sym)}</span><span class="sl-badge {sl_c}">{sl}</span></div>
  <div class="opp-company">{company}</div>
  <div class="opp-metrics">
    <div class="m-row"><span class="ml">Price</span><span>{price}</span></div>
    <div class="m-row"><span class="ml">RS 22d</span><span class="{rs_cls}">{rs_s}</span></div>
    <div class="m-row"><span class="ml">RSI</span><span>{rsi}</span></div>
    <div class="m-row"><span class="ml">SL%</span><span>{sl_pct}% <span class="{sl_g_cls}">[{sl_gr}]</span></span></div>
    <div class="m-row"><span class="ml">Score</span><span class="pos">{score}</span></div>
    <div class="m-row"><span class="ml">Sales YoY</span><span>{sal_yoy}%</span></div>
    <div class="m-row"><span class="ml">PAT YoY</span><span>{pat_yoy}%</span></div>
  </div>
  {f'<div class="opp-pattern">{chart_p}</div>' if chart_p else ''}
  <button class="copy-btn sm" data-orig="📋" onclick="copyText(this,'{sym},')">📋 TV</button>
</div>"""
    return f'<div class="opp-cards">{html}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  SLEEVE TABLES  —  Interactive position sizing + Zerodha basket + tracking
# ─────────────────────────────────────────────────────────────────────────────

_SLEEVE_META = {
    "A":    ("sl-confirmed","Core — Large Cap",       "Monthly · Nifty 1–50"),
    "B":    ("sl-rsbuy",    "Growth — Mid-Large",     "Fortnightly · Nifty 51–200"),
    "C":    ("sl-watch",    "Aggressive — Small-Mid", "Weekly · Nifty 201–500"),
    "D":    ("sl-neutral",  "Global ETFs",            "Monthly · Country + Commodity"),
    "US_A": ("sl-confirmed","Mega Cap",               "Monthly · S&P Top 50"),
    "US_B": ("sl-rsbuy",    "Large Cap",              "Fortnightly · S&P 51–200"),
    "US_C": ("sl-watch",    "Mid Cap",                "Weekly · S&P 201–500"),
    "US_D": ("sl-neutral",  "Global ETFs",            "Monthly · Country + Commodity"),
}

# Columns to show in sleeve tables (will auto-filter to available ones)
_SLEEVE_SHOW = ["Rank","Symbol","Company","Sector","Signal_Label",
                "Price","Sleeve_RS","RS_22d_Idx%","RS_55d_Idx%",
                "ATR5","SL_Buy%","SL_Grade","Equal_Wt%","ATR_Wt%",
                "Sales_YoY%","PAT_YoY%","ROE%"]


def _build_sleeve_tables(sleeve_df, market="INDIA"):
    """
    Parse combined sleeve_df → 4 separate interactive tables.
    Each table has:
      • Capital input + auto qty/amount/SL-price calculator
      • Zerodha basket CSV download (NSE/BSE)
      • 'Track Entry' button → saves prices to window.storage
      • P&L column loaded from storage on page open
    """
    if sleeve_df is None or sleeve_df.empty:
        return '<p class="empty">Sleeve data unavailable.</p>'

    # ── Parse sleeve sections from combined df ─────────────────────────────
    sections: dict = {}
    cur_key = None; cur_rows = []
    for _, row in sleeve_df.iterrows():
        rv = str(row.get("Rank","") or "")
        if rv.startswith("━━━") and "SLEEVE" in rv.upper():
            if cur_key and cur_rows: sections[cur_key] = cur_rows[:]
            cur_key = None; cur_rows = []
            for k in ["US_D","US_C","US_B","US_A","D","C","B","A"]:
                if f"SLEEVE {k}" in rv.upper(): cur_key=k; break
        elif cur_key and str(rv).strip().isdigit():
            cur_rows.append(dict(row))
    if cur_key and cur_rows: sections[cur_key] = cur_rows

    if not sections:
        # Flat fallback
        try:
            data = sleeve_df[sleeve_df["Rank"].astype(str).str.strip().str.isdigit()].copy()
            cols = [c for c in _SLEEVE_SHOW if c in data.columns]
            return _build_table(data[cols] if cols else data, "tbl-sleeve-all")
        except: return _build_table(sleeve_df, "tbl-sleeve-all")

    is_india = (market == "INDIA")
    currency  = "₹" if is_india else "$"
    default_capital = "1000000" if is_india else "50000"

    html = f"""<div class="sleeve-global-ctrl">
  <div class="ctrl-row">
    <div class="ctrl-field">
      <label class="ctrl-label">Portfolio Capital ({currency})</label>
      <input type="number" id="global-capital" class="cap-input"
             value="{default_capital}" placeholder="{default_capital}"
             oninput="recalcAll()">
    </div>
    <div class="ctrl-field">
      <label class="ctrl-label">Risk per stock (%&nbsp;of&nbsp;capital)</label>
      <input type="number" id="global-risk" class="cap-input" style="width:90px"
             value="1" min="0.1" max="5" step="0.1" oninput="recalcAll()">
    </div>
    <div class="ctrl-field">
      <label class="ctrl-label">SL fallback (%)</label>
      <input type="number" id="global-sl-cap" class="cap-input" style="width:80px"
             value="5" min="1" max="15" step="0.5" oninput="recalcAll()"
             title="Used only when a stock has no ATR data. The ATR(5)×1.2 stop drives sizing otherwise.">
    </div>
  </div>
  <div class="ctrl-formula">
    <strong>Formula:</strong>
    Qty&nbsp;=&nbsp;⌊ (Capital&nbsp;×&nbsp;Risk%) &nbsp;÷&nbsp; (Price&nbsp;×&nbsp;SL%) ⌋
    &nbsp;·&nbsp;
    SL%&nbsp;=&nbsp;ATR(5)&nbsp;×&nbsp;1.2&nbsp;÷&nbsp;Price (fallback above if no ATR)
    &nbsp;·&nbsp;
    Total deployment is scaled down if it would exceed Portfolio Capital
  </div>
</div>"""

    for key, rows in sections.items():
        if not rows: continue
        df_sec = pd.DataFrame(rows).reset_index(drop=True)
        meta   = _SLEEVE_META.get(key, ("sl-neutral", key, ""))
        badge_cls, label, subtitle = meta
        safe_key = key.lower().replace("_","")
        n = len(df_sec)

        # Build table rows with data-* attributes for JS
        risk_currency = "₹" if is_india else "$"
        thead_extra = (f"<th title='Risk-based quantity'>Qty</th>"
                       f"<th title='Qty × Price'>Amount ({currency})</th>"
                       f"<th title='Hard stop price'>SL Price</th>"
                       f"<th title='Max loss if stopped out'>Risk ({risk_currency})</th>"
                       f"<th title='Eff. SL% used'>eSL%</th>"
                       f"<th title='P&amp;L vs tracked entry'>P&amp;L</th>")
        show_cols = [c for c in _SLEEVE_SHOW if c in df_sec.columns]

        ths = "".join(
            f'<th style="text-align:{"left" if c.lower() in _LEFT_COLS else "center"}"{_col_tip(c)}>{c}</th>'
            for c in show_cols
        ) + thead_extra

        tbody = ""
        for _, row in df_sec.iterrows():
            sym   = str(row.get("Symbol","") or "").replace(".NS","").replace(".BO","")
            price = _fmt(row.get("Price",""))
            atrwt = _fmt(row.get("ATR_Wt%", row.get("Equal_Wt%","")))
            sl_pct= _fmt(row.get("SL_Buy%",""))
            # data-* attributes for JS calculator
            attrs = (f'data-sym="{sym}" data-price="{price}" '
                     f'data-atrwt="{atrwt}" data-sl="{sl_pct}"')
            tds = ""
            for c in show_cols:
                val=row.get(c,""); cls=_cell_class(c,val)
                display=(_tv_link(val, "US" if key.startswith("US_") else _CUR_MKT)
                         if c.lower().strip()=="symbol" else _fmt(val))
                align="left" if c.lower() in _LEFT_COLS else "center"
                ca=f' class="{cls}"' if cls else ""
                tds += f'<td{ca} style="text-align:{align}">{display}</td>'
            # Calculator cells (filled by JS)
            tds += ('<td class="calc-cell qty-cell">—</td>'
                    '<td class="calc-cell amt-cell">—</td>'
                    '<td class="calc-cell slp-cell">—</td>'
                    '<td class="calc-cell rsk-cell">—</td>'
                    '<td class="calc-cell esl-cell">—</td>'
                    '<td class="calc-cell pl-cell">—</td>')
            tbody += f'<tr {attrs}>{tds}</tr>'

        # Broker buttons — Zerodha for India, IBKR for US (both shown for India as optional)
        is_us_sleeve = key.startswith("US_")
        if is_us_sleeve:
            broker_btns = (
                f'<button class="action-btn blue" onclick="downloadIBKR(\'{safe_key}\',\'False\')">'
                f'📥 IBKR Basket CSV</button>'
            )
        else:
            broker_btns = (
                f'<button class="action-btn orange" onclick="downloadZerodha(\'{safe_key}\')">'
                f'📥 Zerodha Basket JSON</button>'
                f'<button class="action-btn blue" onclick="downloadIBKR(\'{safe_key}\',\'True\')">'
                f'📥 IBKR Basket CSV</button>'
            )

        html += f"""<div class="sleeve-block">
  <div class="sleeve-header">
    <span class="sl-badge {badge_cls}">{key}</span>
    <div class="sleeve-title">{label}</div>
    <div class="sleeve-sub">{subtitle} · {n} stocks</div>
    <div class="sleeve-summary" id="sum-{safe_key}"></div>
  </div>

  <div class="sleeve-actions">
    <button class="action-btn green" onclick="calcSleeve('{safe_key}')">⚡ Recalculate</button>
    {broker_btns}
    <button class="action-btn amber" onclick="trackEntry('{safe_key}')">💾 Track Entry</button>
    <button class="action-btn grey"  onclick="clearTracking('{safe_key}')">🗑 Clear Tracking</button>
    <span class="track-msg" id="tmsg-{safe_key}"></span>
    <span class="entry-date" id="edate-{safe_key}"></span>
  </div>

  <div class="tbl-wrap">
    <table id="sleeve-{safe_key}" class="data-tbl sleeve-tbl">
      <thead><tr>{ths}</tr></thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
  <div class="sleeve-footer">
    Total Deployed: <strong id="total-{safe_key}">—</strong> &nbsp;|&nbsp;
    Total P&amp;L: <strong id="plsum-{safe_key}">—</strong>
  </div>
</div>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL GUIDE
# ─────────────────────────────────────────────────────────────────────────────

_GUIDE_ROWS = [
    ("🌟 Triple Confirmed","sl-triple",
     "RS30 + LST + MST all Buy. Highest conviction. All TFs aligned.",
     "Weekly RS30>0, monthly RS12>0, daily RS55>0. Price > 20d swing high."),
    ("🌟 RS30 Leader","sl-prime",
     "Weekly RS(30)>0 + EMA10>EMA30 + within 10% of 52W High + Sales QoQ≥15% + PAT QoQ≥15%.",
     "TechnoFunda weekly momentum strategy. Breakout above 20-day swing high required."),
    ("🌟 Long Momentum","sl-prime",
     "LST Buy + strong fundamentals (fin_score≥5). Monthly trend bullish. 60-120 day swing.",
     "Monthly RS12>0, RSI12>50, Revenue+, PAT+. Weekly RS21>0 + ST + EMA200."),
    ("✅ Long Momentum","sl-confirmed",
     "LST Buy. Monthly pre-conditions + weekly entry confirmed. 60-120 day swing.",
     "Monthly RS12>0 + RSI12>50. Weekly RS21>0 + RSI12>50 + Supertrend + EMA200."),
    ("✅ Strong RS","sl-confirmed",
     "All 5 peer filters: RS Buy + beats sector avg + beats industry avg + sector>0 + industry>0.",
     "Four RS checks positive + stock outperforms peers on RS_55d."),
    ("📈 Swing Entry","sl-rsbuy",
     "MST Buy. Weekly pre-cond + daily entry + 20d breakout. 20-60 day swing.",
     "Weekly RS21>0, RSI>50. Daily RS55>0, RSI>50, Supertrend=Buy, Close>EMA200, breakout."),
    ("📈 RS Leader","sl-rsbuy",
     "RS Buy: RS_22d>0 AND RS_55d>0 vs index AND sector. Awaiting TF confirmation.",
     "Four RS checks positive: 22d-idx, 55d-idx, 22d-sec, 55d-sec."),
    ("👁 Watch","sl-watch",
     "Pre-conditions met, no breakout yet. Wait for close above 20-day swing high.",
     "RS30/LST/MST Watch: technical setup building, entry trigger not yet fired."),
    ("⬜ Neutral","sl-neutral",
     "Mixed RS signals. No clear direction. Monitor only.", ""),
    ("🔴 RS Breakdown","sl-avoid",
     "All RS values negative. Stock lagging index and sector. Avoid or exit.",
     "RS_22d_Idx<0 + RS_55d_Idx<0 + RS_22d_Sec<0 + RS_55d_Sec<0."),
]


def _build_guide():
    rows = "".join(
        f'<div class="guide-row"><div class="guide-label-col"><span class="sl-badge {cls}">{lbl}</span></div>'
        f'<div class="guide-content"><div class="guide-summary">{s}</div>'
        f'{"<div class=guide-detail>"+d+"</div>" if d else ""}</div></div>'
        for lbl,cls,s,d in _GUIDE_ROWS
    )
    meta = """<div class="guide-meta">
  <h3>Score Formula</h3>
  <div class="guide-table">
    <div class="gt-row"><span class="gt-k">Total_Score</span><span>RS_Score×0.6 + Fin_Score×2 + SL_Bonus</span></div>
    <div class="gt-row"><span class="gt-k">RS_Score</span><span>RS_22d×35% + RS_55d×30% + RS_120d×20% + RS_252d×15%</span></div>
    <div class="gt-row"><span class="gt-k">Fin_Score</span><span>Sales_YoY≥15% +2 | PAT_YoY≥15% +2 | ROE≥15% +2 | Margin≥10% +1 | D/E&lt;1 +1</span></div>
    <div class="gt-row"><span class="gt-k">EPS</span><span>Trailing twelve-month Earnings Per Share (currency). Green = profitable, Red = loss-making.</span></div>
    <div class="gt-row"><span class="gt-k">SL_Bonus</span><span>A +4 | B +3 | C +2 | D +1 | R:R≥3× +2 | ≥2× +1</span></div>
  </div>
  <h3>SL Grade</h3>
  <div class="guide-table">
    <div class="gt-row"><span class="sl-badge sl-confirmed">A ≤3%</span><span>Ideal — tight stop</span></div>
    <div class="gt-row"><span class="sl-badge sl-confirmed">B ≤5%</span><span>Good — MST</span></div>
    <div class="gt-row"><span class="sl-badge sl-watch">C ≤8%</span><span>Acceptable — LST</span></div>
    <div class="gt-row"><span class="sl-badge sl-avoid">F &gt;12%</span><span>Too wide — skip</span></div>
  </div>
</div>"""
    return f'<div class="guide">{rows}{meta}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def _build_dashboard(df):
    if df is None or df.empty: return ""
    html = ""
    for _, row in df.iterrows():
        k=_fmt(row.get("Key","")); v=_fmt(row.get("Value",""))
        if not k and not v: html += '<div class="dash-spacer"></div>'; continue
        if k.startswith("══") or k.startswith("──"):
            html += f'<div class="dash-section">{k}</div>'; continue
        is_tv = any(x in k.upper() for x in [
            "TV", "TRADINGVIEW", "WATCHLIST", "ALL BUY", "STRONG BUY",
            "PRIME BUY", "CONFIRMED BUY", "RS BUY", "MST", "LST", "RS30", "TOP-"
        ])
        # Any value that looks like a comma-separated symbol list is copyable,
        # so every watchlist row (Strong Buy / MST / LST / RS30 / All Buy /
        # Top-20 …) gets its own Copy button — not just "All Buy".
        looks_like_list = (v.count(",") >= 1)
        if (is_tv or looks_like_list) and v and len(v) > 3:
            v_html = (f'<span class="tv-list">{v[:200]}{"…" if len(v)>200 else ""}</span>'
                      f'<button class="copy-btn sm" data-orig="📋"'
                      f' onclick="copyText(this,\'{v.replace(chr(39),"")}\')">Copy</button>')
        else: v_html = v
        vcls = (" sl-triple-inline" if k.startswith("🌟") else
                " sl-confirmed-inline" if k.startswith("✅") else
                " sl-rsbuy-inline" if k.startswith("📈") else
                " sl-watch-inline" if k.startswith("👁") else
                " sl-avoid-inline" if k.startswith("🔴") else "")
        html += (f'<div class="dash-row"><div class="dash-key">{k}</div>'
                 f'<div class="dash-val{vcls}">{v_html}</div></div>')
    return html


# ─────────────────────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --bg:#0f1117;--bg2:#151820;--bg3:#1c1f2e;
  --border:rgba(255,255,255,0.07);
  --text:#e2e4ec;--text2:#8b90a8;--text3:#7b82a0;
  --accent:#5b8def;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;
  --radius:10px;--shadow:0 2px 14px rgba(0,0,0,.4);
  --sl-triple-bg:#0d2b1a;--sl-triple-fg:#4ade80;
  --sl-prime-bg:#0f3024; --sl-prime-fg:#86efac;
  --sl-conf-bg:#c8e6c9;  --sl-conf-fg:#1b5e20;
  --sl-rsbuy-bg:#e8f5e9; --sl-rsbuy-fg:#1b5e20;
  --sl-watch-bg:#2d1b0d; --sl-watch-fg:#fde68a;
  --sl-neutral-bg:#374151;--sl-neutral-fg:#9ca3af;
  --sl-avoid-bg:#2d0d0d; --sl-avoid-fg:#fca5a5;
  /* Inline signal-count text colours — bright enough to read on dark/navy. */
  --ink-green:#34d399;--ink-amber:#fbbf24;--ink-red:#f87171;
}
html[data-theme="light"]{
  --bg:#f8fafc;--bg2:#fff;--bg3:#f1f5f9;
  --border:rgba(0,0,0,.07);--text:#1e293b;--text2:#64748b;--text3:#94a3b8;
  --sl-triple-bg:#dcfce7;--sl-triple-fg:#14532d;
  --sl-prime-bg:#d1fae5; --sl-prime-fg:#166534;
  --sl-watch-bg:#fefce8; --sl-watch-fg:#92400e;
  --sl-avoid-bg:#fef2f2; --sl-avoid-fg:#991b1b;
  --sl-neutral-bg:#f3f4f6;--sl-neutral-fg:#6b7280;
  /* Darker ink on the light theme so counts stay legible on white. */
  --ink-green:#15803d;--ink-amber:#b45309;--ink-red:#dc2626;
}
/* Navy / Blue Trader theme — overrides structural palette; signal colours
   inherit the dark defaults which read well on a deep-navy background. */
html[data-theme="navy"]{
  --bg:#0a1929;--bg2:#102a43;--bg3:#173a5e;
  --border:rgba(130,180,255,.14);
  --text:#e8f0fc;--text2:#a3bcd9;--text3:#7daac8;
  --accent:#4d9fff;--shadow:0 2px 16px rgba(0,18,46,.55);
}
*{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);font-size:15px;line-height:1.5;}
.app-header{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 16px;position:sticky;top:0;z-index:100;
  display:flex;align-items:center;justify-content:space-between;gap:10px;}
.app-title{font-size:15px;font-weight:700;color:var(--accent);}
.app-meta{font-size:11px;color:var(--text3);}
.app-brand-row{display:flex;align-items:center;gap:10px;}
.home-link{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;
  color:var(--text2);text-decoration:none;background:var(--bg3);border:1px solid var(--border);
  padding:5px 10px;border-radius:8px;transition:all .15s;white-space:nowrap;}
.home-link:hover{color:var(--accent);border-color:var(--accent);}
.country-nav-select{background:var(--bg3);border:1px solid var(--border);color:var(--text);
  font-size:12px;font-weight:600;padding:5px 8px;border-radius:8px;cursor:pointer;outline:none;
  min-width:160px;max-width:200px;}
.country-nav-select:focus{border-color:var(--accent);}
/* Feedback form */
.feedback-section{background:var(--bg2);border-top:1px solid var(--border);
  padding:24px clamp(12px,3vw,40px);}
.feedback-title{font-size:16px;font-weight:700;color:var(--accent);margin:0 0 6px;}
.feedback-sub{font-size:13px;color:var(--text2);margin:0 0 14px;}
.feedback-form{display:flex;flex-direction:column;gap:10px;max-width:600px;}
.fb-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.fb-input,.fb-textarea{background:var(--bg3);border:1px solid var(--border);color:var(--text);
  border-radius:var(--radius);padding:9px 12px;font-size:13px;font-family:inherit;
  outline:none;transition:border-color .15s;}
.fb-input:focus,.fb-textarea:focus{border-color:var(--accent);}
.fb-textarea{min-height:90px;resize:vertical;}
.fb-btn{align-self:flex-start;background:var(--accent);color:#fff;border:none;
  border-radius:var(--radius);padding:9px 20px;font-size:13px;font-weight:600;
  cursor:pointer;transition:opacity .15s;}
.fb-btn:hover{opacity:.85;}
/* Floating feedback button */
.fb-float{position:fixed;bottom:24px;right:20px;z-index:200;background:var(--accent);
  color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:12px;font-weight:600;
  cursor:pointer;box-shadow:0 3px 12px rgba(0,0,0,.3);text-decoration:none;
  display:flex;align-items:center;gap:5px;transition:opacity .15s;}
.fb-float:hover{opacity:.85;}
@media(max-width:600px){.fb-row{grid-template-columns:1fr;}}
.disclaimer-footer{background:var(--bg2);border-top:2px solid var(--border);
  padding:20px clamp(12px,3vw,40px);margin-top:30px;font-size:11.5px;line-height:1.7;color:var(--text3);}
.disclaimer-footer h4{font-size:12px;font-weight:700;color:var(--text2);margin:0 0 8px;
  text-transform:uppercase;letter-spacing:.5px;}
.disclaimer-footer p{margin:0 0 8px;}
.disclaimer-footer strong{color:var(--text2);}
.disclaimer-footer .df-brand{color:var(--accent);font-weight:700;}
.disclaimer-footer a{color:var(--text2);text-decoration:underline;}
.sl-badge{display:inline-block;padding:3px 9px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap;}
.sl-triple{background:var(--sl-triple-bg);color:var(--sl-triple-fg);}
.sl-prime{background:var(--sl-prime-bg);color:var(--sl-prime-fg);}
.sl-confirmed{background:var(--sl-conf-bg);color:var(--sl-conf-fg);}
.sl-rsbuy{background:var(--sl-rsbuy-bg);color:var(--sl-rsbuy-fg);}
.sl-watch{background:var(--sl-watch-bg);color:var(--sl-watch-fg);}
.sl-neutral{background:var(--sl-neutral-bg);color:var(--sl-neutral-fg);}
.sl-avoid{background:var(--sl-avoid-bg);color:var(--sl-avoid-fg);}
.sl-triple-inline{color:var(--ink-green);font-weight:700;}
.sl-confirmed-inline{color:var(--ink-green);font-weight:600;}
.sl-rsbuy-inline{color:var(--ink-green);font-weight:600;}
.sl-watch-inline{color:var(--ink-amber);font-weight:600;}
.sl-avoid-inline{color:var(--ink-red);font-weight:600;}
.stats-bar{display:flex;gap:8px;padding:8px 12px;background:var(--bg2);
  border-bottom:1px solid var(--border);overflow-x:auto;scrollbar-width:none;}
.stats-bar::-webkit-scrollbar{display:none;}
.tab-bar{display:flex;overflow-x:auto;background:var(--bg2);
  border-bottom:1px solid var(--border);position:sticky;top:49px;z-index:99;scrollbar-width:none;}
.tab-bar::-webkit-scrollbar{display:none;}
.tab-btn{padding:10px 14px;font-size:13px;white-space:nowrap;border:none;
  background:none;color:var(--text2);cursor:pointer;
  border-bottom:2px solid transparent;transition:all .15s;flex-shrink:0;}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600;}
.tab-btn:hover{color:var(--text);}
.tab-content{display:none;padding:14px clamp(12px,3vw,40px);max-width:100%;margin:0 auto;}
.tab-content.active{display:block;}
.sec-title{font-size:14px;font-weight:600;color:var(--text);
  margin:18px 0 4px;border-left:3px solid var(--accent);padding-left:10px;}
.sec-title:first-child{margin-top:0;}
.sec-subtitle{font-size:11px;color:var(--text-dim);margin:0 0 8px 13px;padding:0;}
/* Health card */
.health-card{background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius);padding:16px;margin-bottom:16px;}
.hc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:12px;margin-bottom:12px;}
.hc-block{text-align:center;}
.hc-label{font-size:11px;color:var(--text3);margin-bottom:4px;}
.hc-value{font-size:18px;font-weight:700;}
.hc-sub{font-size:12px;font-weight:400;color:var(--text2);}
.hc-sectors{display:flex;flex-wrap:wrap;gap:6px;align-items:center;}
.sec-pill{padding:3px 8px;border-radius:8px;font-size:12px;font-weight:500;background:var(--bg3);color:var(--text2);}
.sec-pill.pos-strong{background:#0d3320;color:#4ade80;}
.sec-pill.neg{background:#2d0d0d;color:#fca5a5;}
.mood-on{color:#22c55e;}.mood-mix{color:var(--amber);}.mood-off{color:var(--red);}
/* Snapshot */
.snap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:16px;}
.snap-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;}
.snap-name{font-size:11px;color:var(--text3);margin-bottom:3px;}
.snap-price{font-size:15px;font-weight:700;}
.snap-chg{font-size:13px;font-weight:500;margin-top:2px;}
.snap-trend{font-size:11px;margin-top:3px;}
/* Sector bars */
.sector-bars{display:flex;flex-direction:column;gap:5px;margin-bottom:16px;}
.sec-row{display:grid;grid-template-columns:24px 1fr 80px 52px 52px 52px 56px;
  align-items:center;gap:6px;background:var(--bg2);border-radius:6px;
  padding:6px 10px;border:1px solid var(--border);}
.sec-rank{color:var(--text3);font-size:11px;}
.sec-name{font-size:13px;font-weight:500;}
.sec-bar-wrap{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;}
.sec-bar{height:100%;border-radius:3px;min-width:2px;}
.bar-pos{background:var(--green);}.bar-neg{background:var(--red);}
.sec-rs,.sec-rs55,.sec-rsi{font-size:12px;text-align:right;}
.sec-sig-badge{font-size:11px;font-weight:600;text-align:center;padding:2px 5px;border-radius:4px;}
.sig-buy{background:#c8e6c9;color:#1b5e20;}.sig-sell{background:#ffcdd2;color:#b71c1c;}
.sig-neutral{background:#fff9c4;color:#5d4037;}.sig-strongbuy{background:#006b3c;color:#fff;}
/* Beginner explanation panel */
.beginner-panel{background:var(--bg2);border:1px solid var(--border);border-left:4px solid var(--accent);
  border-radius:var(--radius);padding:10px 14px;margin-bottom:14px;font-size:13px;}
.beginner-panel summary{cursor:pointer;font-weight:600;color:var(--accent);list-style:none;
  display:flex;align-items:center;gap:6px;}
.beginner-panel summary::-webkit-details-marker{display:none;}
.beginner-panel summary::before{content:"ℹ️";}
.beginner-panel ul{margin:8px 0 0 16px;padding:0;line-height:1.7;color:var(--text2);}
.beginner-panel ul li{margin-bottom:2px;}
.beginner-panel a{color:var(--accent);text-decoration:none;}
.beginner-panel a:hover{text-decoration:underline;}
/* Text-only variants for no-bg tabs (Opportunities/Stocks/Global/Patterns) */
.sig-buy-text{color:#16a34a;font-weight:600;}
.sig-sell-text{color:#dc2626;font-weight:600;}
.sig-neutral-text{color:var(--text2);}
.sig-strongbuy-text{color:#15803d;font-weight:700;}
/* Signal-label text-only: map sl-* → colour without background */
.data-tbl td.sl-triple-text{color:#4ade80!important;font-weight:700;}
.data-tbl td.sl-prime-text{color:#86efac!important;font-weight:700;}
.data-tbl td.sl-confirmed-text{color:#16a34a!important;font-weight:600;}
.data-tbl td.sl-rsbuy-text{color:#22c55e!important;}
.data-tbl td.sl-watch-text{color:#f59e0b!important;}
.data-tbl td.sl-neutral-text{color:var(--text3)!important;}
.data-tbl td.sl-avoid-text{color:#ef4444!important;font-weight:600;}
/* Opportunity cards */
.opp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-bottom:16px;}
.opp-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:12px 14px;transition:border-color .2s;}
.opp-card:hover{border-color:var(--accent);}
.opp-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;}
.opp-sym{font-size:17px;font-weight:700;}
.tv-link{color:var(--accent);text-decoration:none;font-weight:700;border-bottom:1px dotted var(--accent);}
.tv-link:hover{text-decoration:none;border-bottom-style:solid;}
.opp-sym .tv-link{color:inherit;border-bottom:none;}
.opp-company{font-size:12px;color:var(--text3);margin-bottom:8px;}
.opp-metrics{display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;margin-bottom:8px;}
.m-row{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border);}
.ml{color:var(--text2);}
.opp-pattern{font-size:11px;color:var(--accent);margin-bottom:6px;}
.opp-sec-hdr{display:flex;justify-content:space-between;align-items:center;
  font-size:13px;font-weight:600;padding:8px 4px;color:var(--text2);
  border-bottom:1px solid var(--border);margin-bottom:8px;grid-column:1/-1;}
/* Tables */
.tbl-search{margin-bottom:8px;}
.tbl-search input{width:100%;padding:8px 12px;border-radius:8px;
  border:1px solid var(--border);background:var(--bg2);color:var(--text);font-size:14px;outline:none;}
.tbl-search input:focus{border-color:var(--accent);}
.stock-toolbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;}
.stock-toolbar-left{display:flex;gap:8px;flex-wrap:wrap;}
.stock-toolbar-right{display:flex;gap:6px;flex-wrap:wrap;}
.sector-sel{background:var(--bg3);border:1px solid var(--border);color:var(--text);font-size:12px;font-weight:500;padding:5px 8px;border-radius:8px;cursor:pointer;outline:none;}
.sector-sel:focus{border-color:var(--accent);}
.scr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px;margin-bottom:10px;}
.scr-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:7px 10px;cursor:pointer;transition:border-color .2s,transform .1s;}
.scr-card:hover{border-color:var(--accent);transform:translateY(-1px);}
.scr-card.active{border-color:var(--accent);background:rgba(91,141,239,.08);}
.scr-icon{font-size:16px;margin-bottom:2px;}
.scr-name{font-size:12px;font-weight:700;margin-bottom:2px;}
.scr-desc{font-size:10px;color:var(--text2);line-height:1.4;}
.scr-status{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text2);padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:10px;}
@media(max-width:600px){.stock-toolbar{flex-direction:column;align-items:flex-start;}}
.tbl-wrap{overflow-x:auto;border-radius:var(--radius);border:1px solid var(--border);margin-bottom:6px;}
table.data-tbl{border-collapse:collapse;width:100%;font-size:12px;min-width:400px;}
.data-tbl thead th{background:#0d1730;color:#90caf9;padding:8px 10px;
  font-weight:600;font-size:11px;white-space:nowrap;cursor:pointer;user-select:none;
  border-bottom:1px solid var(--border);position:sticky;top:0;}
.data-tbl thead th:hover{background:#1a2a4a;}
.data-tbl thead th::after{content:" ↕";opacity:.4;}
.data-tbl thead th.asc::after{content:" ↑";opacity:1;}
.data-tbl thead th.desc::after{content:" ↓";opacity:1;}
.data-tbl tbody tr:nth-child(even){background:var(--bg3);}
.data-tbl tbody tr:hover{background:rgba(91,141,239,.08);}
.data-tbl td{padding:6px 10px;border-bottom:1px solid var(--border);white-space:nowrap;}
.row-count{font-size:11px;color:var(--text3);margin-bottom:12px;}
.data-tbl td.sl-triple{background:var(--sl-triple-bg)!important;color:var(--sl-triple-fg)!important;font-weight:700;}
.data-tbl td.sl-prime{background:var(--sl-prime-bg)!important;color:var(--sl-prime-fg)!important;font-weight:700;}
.data-tbl td.sl-confirmed{background:var(--sl-conf-bg)!important;color:var(--sl-conf-fg)!important;font-weight:600;}
.data-tbl td.sl-rsbuy{background:var(--sl-rsbuy-bg)!important;color:var(--sl-rsbuy-fg)!important;}
.data-tbl td.sl-watch{background:var(--sl-watch-bg)!important;color:var(--sl-watch-fg)!important;}
.data-tbl td.sl-avoid{background:var(--sl-avoid-bg)!important;color:var(--sl-avoid-fg)!important;font-weight:600;}
.pos-strong{color:var(--green);font-weight:600;}.pos{color:#81c784;}
.pos-dim{color:#a5d6a7;}.neg-strong{color:var(--red);font-weight:600;}
.neg{color:#e57373;}.neg-dim{color:#ef9a9a;}.dim{color:var(--text3);}
.cell-bold{font-weight:700;}
/* Breadth / rotation 0-100 columns: ≥60 green · 40-60 amber · <40 red */
.data-tbl td.bd-green{background:rgba(34,197,94,.13)!important;color:#22c55e!important;font-weight:600;}
.data-tbl td.bd-amber{background:rgba(245,158,11,.13)!important;color:#f59e0b!important;font-weight:600;}
.data-tbl td.bd-red{background:rgba(239,68,68,.13)!important;color:#ef4444!important;font-weight:600;}
/* Text signal cells: Bullish / Neutral / Bearish (Trend & Zone columns) */
.data-tbl td.txt-bull{background:rgba(16,185,129,.13)!important;color:#10b981!important;font-weight:600;}
.data-tbl td.txt-sbull{background:rgba(16,185,129,.22)!important;color:#10b981!important;font-weight:700;}
.data-tbl td.txt-bear{background:rgba(239,68,68,.13)!important;color:#ef4444!important;font-weight:600;}
.data-tbl td.txt-sbear{background:rgba(239,68,68,.22)!important;color:#ef4444!important;font-weight:700;}
.data-tbl td.txt-neut{background:rgba(100,116,139,.10)!important;color:#8896b0!important;font-weight:500;}
/* Sleeve calculator */
.sleeve-global-ctrl{background:var(--bg2);border:1px solid var(--accent);
  border-radius:var(--radius);padding:14px 16px;margin-bottom:16px;}
.ctrl-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:16px;margin-bottom:10px;}
.ctrl-field{display:flex;flex-direction:column;gap:4px;}
.ctrl-label{font-size:11px;font-weight:600;color:var(--text2);}
.ctrl-formula{font-size:11px;color:var(--text3);line-height:1.6;padding-top:6px;
  border-top:1px solid var(--border);}
.ctrl-formula strong{color:var(--accent);}
.cap-input{background:var(--bg3);border:1px solid var(--border);color:var(--text);
  padding:6px 10px;border-radius:6px;font-size:14px;width:150px;outline:none;}
.cap-input:focus{border-color:var(--accent);}
.sleeve-block{margin-bottom:28px;}
.sleeve-header{background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius) var(--radius) 0 0;padding:12px 16px;
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  border-bottom:2px solid var(--accent);}
.sleeve-title{font-size:14px;font-weight:600;}
.sleeve-sub{font-size:12px;color:var(--text2);}
.sleeve-summary{font-size:12px;color:var(--accent);margin-left:auto;}
.sleeve-actions{display:flex;flex-wrap:wrap;gap:8px;padding:10px 0;align-items:center;}
.action-btn{padding:6px 14px;border-radius:6px;font-size:12px;
  border:none;cursor:pointer;font-weight:600;transition:opacity .15s;}
.action-btn:hover{opacity:.85;}
.action-btn.green{background:#16a34a;color:#fff;}
.action-btn.blue{background:#1d4ed8;color:#fff;}
.action-btn.amber{background:#d97706;color:#fff;}
.action-btn.orange{background:#c2410c;color:#fff;}
.action-btn.grey{background:#374151;color:#9ca3af;}
.track-msg{font-size:12px;color:var(--green);margin-left:4px;}
.entry-date{font-size:11px;color:var(--text3);margin-left:8px;}
.calc-cell{font-size:12px;text-align:right!important;font-family:monospace;}
.sleeve-tbl .qty-cell{font-weight:700;color:var(--accent);}
.sleeve-tbl .amt-cell{color:var(--text2);}
.sleeve-tbl .slp-cell{color:var(--red);}
.sleeve-tbl .rsk-cell{color:var(--amber);}
.sleeve-tbl .pl-cell.pos-strong{color:var(--green);font-weight:700;}
.sleeve-tbl .pl-cell.neg-strong{color:var(--red);font-weight:700;}
.sleeve-footer{padding:8px 12px;font-size:13px;color:var(--text2);
  background:var(--bg2);border:1px solid var(--border);
  border-radius:0 0 var(--radius) var(--radius);border-top:none;}
/* Dashboard */
.dash-section{background:#0d47a1;color:#90caf9;padding:8px 12px;border-radius:6px;
  font-weight:600;font-size:13px;margin:10px 0 4px;}
.dash-row{display:grid;grid-template-columns:1fr 1fr;
  border-bottom:1px solid var(--border);padding:6px 4px;gap:8px;}
.dash-key{font-size:12px;font-weight:500;color:var(--text2);}
.dash-val{font-size:12px;color:var(--text);word-break:break-all;}
.dash-spacer{height:8px;}
.tv-list{font-size:11px;color:var(--text3);word-break:break-all;}
/* Guide */
.guide{display:flex;flex-direction:column;gap:10px;margin-bottom:16px;}
.guide-row{display:grid;grid-template-columns:200px 1fr;gap:12px;
  background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px;}
.guide-label-col{display:flex;align-items:flex-start;padding-top:2px;}
.guide-summary{font-size:13px;margin-bottom:4px;line-height:1.5;}
.guide-detail{font-size:11px;color:var(--text2);line-height:1.5;}
.guide-meta{margin-top:20px;display:flex;flex-direction:column;gap:16px;}
.guide-meta h3{font-size:13px;font-weight:600;color:var(--text2);margin-bottom:6px;}
.guide-table{display:flex;flex-direction:column;gap:4px;}
.gt-row{display:flex;gap:12px;font-size:12px;padding:5px 8px;border-radius:4px;background:var(--bg2);}
.gt-k{font-weight:600;color:var(--accent);min-width:140px;}
/* Toggle */
.view-toggle{display:flex;gap:6px;margin-bottom:10px;}
.vt-btn{padding:5px 14px;border-radius:6px;font-size:12px;
  border:1px solid var(--border);background:transparent;color:var(--text2);cursor:pointer;}
.vt-btn.active{background:var(--accent);color:#fff;border-color:var(--accent);}
/* Buttons */
.copy-btn{margin-top:8px;padding:5px 12px;border-radius:6px;
  border:1px solid var(--accent);background:transparent;color:var(--accent);
  font-size:12px;cursor:pointer;transition:all .15s;}
.copy-btn:hover{background:var(--accent);color:#fff;}
.copy-btn.sm{padding:3px 8px;font-size:11px;margin-top:6px;}
.copy-btn.copied{background:#16a34a;border-color:var(--green);color:#fff;}
.empty{color:var(--text3);font-size:13px;padding:20px 0;text-align:center;}
/* ── Mobile column-set toggle (chips hidden on desktop) ─────────────────── */
.grp-chips{display:none;align-items:center;gap:6px;margin-bottom:8px;flex-wrap:wrap;}
.grp-chips-lbl{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;}
.grp-chip{padding:5px 12px;border-radius:6px;font-size:12px;border:1px solid var(--border);
  background:transparent;color:var(--text2);cursor:pointer;transition:all .15s;}
.grp-chip.active{background:var(--accent);color:#fff;border-color:var(--accent);}
table.data-tbl.gv-analysis .gcol:not(.g-pin):not(.g-analysis),
table.data-tbl.gv-tech     .gcol:not(.g-pin):not(.g-tech),
table.data-tbl.gv-fin      .gcol:not(.g-pin):not(.g-fin){display:none;}
@media(max-width:640px){
  .sec-row{grid-template-columns:20px 1fr 44px 44px;}.sec-bar-wrap,.sec-rs55,.sec-rsi{display:none;}
  .opp-cards{grid-template-columns:1fr;}
  .snap-grid{grid-template-columns:repeat(2,1fr);}
  .guide-row{grid-template-columns:1fr;}.guide-label-col{margin-bottom:6px;}
  .dash-row{grid-template-columns:1fr;}
  .hc-grid{grid-template-columns:repeat(4,1fr);}
  .sleeve-global-ctrl{flex-direction:column;align-items:flex-start;}
  /* Column-set chips become visible only on phones; pin the Symbol column so it
     stays on-screen while the remaining columns scroll. The frozen column must
     look identical to its neighbours — no special colour, font or shadow. The
     header keeps the thead styling it already has; body cells only get an opaque
     fill matching the row stripe so scrolling content can't show through. */
  .grp-chips{display:flex;}
  table.data-tbl th.col-sym,table.data-tbl td.col-sym{position:sticky;left:0;z-index:3;}
  .data-tbl tbody td.col-sym{background:var(--bg);}
  .data-tbl tbody tr:nth-child(even) td.col-sym{background:var(--bg3);}
}
/* ── #8 Header controls: theme selector + font scaling ────────────────── */
.hdr-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;}
.ctrl-group{display:flex;align-items:center;gap:5px;background:var(--bg3);
  border:1px solid var(--border);border-radius:8px;padding:3px 7px;}
.ctrl-group label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;}
.theme-select{background:var(--bg2);color:var(--text);border:1px solid var(--border);
  border-radius:6px;font-size:12px;padding:4px 6px;cursor:pointer;outline:none;}
.fs-btn{width:26px;height:26px;border:none;border-radius:6px;background:var(--bg2);
  color:var(--text);font-size:15px;font-weight:700;cursor:pointer;line-height:1;}
.fs-btn:hover{background:var(--accent);color:#fff;}
/* ── #8 Per-column filter row (turns each table into a scanner) ───────── */
.data-tbl thead tr.col-filter th{padding:3px 4px;background:var(--bg2);}
.col-filter input{width:100%;min-width:52px;box-sizing:border-box;font-size:11px;
  padding:3px 5px;border:1px solid var(--border);border-radius:5px;
  background:var(--bg);color:var(--text);outline:none;}
.col-filter input:focus{border-color:var(--accent);}
/* ── #8 Responsive ────────────────────────────────────────────────────── */
@media(max-width:640px){
  .tab-content{padding:10px 8px;}
  .app-title{font-size:13px;}
  .hdr-controls{gap:5px;}
  .ctrl-group label{display:none;}
  table.data-tbl{font-size:11px;}
}

/* ── TradingView Hover Preview (v6.2) ──────────────────────────────────── */
#tv-preview-box {
  position: fixed;
  display: none;
  z-index: 9999;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.45);
  overflow: hidden;
  pointer-events: none;
}
#tv-preview-header {
  height: 30px;
  line-height: 30px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  background: var(--bg3);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
#tv-preview-iframe {
  width: 100%;
  border: none;
  display: block;
}
#tv-preview-toggle {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--text2);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
#tv-preview-toggle.tv-on  { background: var(--accent); color: #fff; border-color: var(--accent); }
#tv-preview-toggle.tv-off { background: var(--bg3);    color: var(--text3); }
"""

# ─────────────────────────────────────────────────────────────────────────────
#  JAVASCRIPT
# ─────────────────────────────────────────────────────────────────────────────

JS = r"""
/* ── TAB SWITCHING ─────────────────────────────────────────────────────── */
// showTab is defined here AND redefined later (after TV code) to add
// _tvAttachHovers on every tab switch. The second definition wins in JS.
function showTab(id){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
  localStorage.setItem('activeTab',id);
}

/* ── THEME + FONT SCALING (#8) ─────────────────────────────────────────── */
function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  try{localStorage.setItem('theme',t);}catch(e){}
  const sel=document.getElementById('theme-select'); if(sel)sel.value=t;
}
function setFont(delta){
  let z=parseFloat(localStorage.getItem('fontZoom')||'0.9');
  z=Math.min(2.0,Math.max(0.6,z+delta*0.1));
  document.documentElement.style.zoom=z;
  try{localStorage.setItem('fontZoom',String(z));}catch(e){}
}
function _initThemeFont(){
  setTheme(localStorage.getItem('theme')||'light');
  document.documentElement.style.zoom=parseFloat(localStorage.getItem('fontZoom')||'0.9');
}

/* ── TABLE FILTER — global box + per-column scanner inputs (#8) ───────────
   Per-column inputs accept logical/numeric operators in addition to text:
     >15   <40   >=60   <=5   =12   !=0   10-20 (range)   10..20 (range)
   Anything else is treated as a plain text (substring) match.            */
function _cellNum(text){
  const m = String(text).replace(/[,\s₹$%]/g,'').match(/-?\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : NaN;
}
function matchFilter(text, qRaw){
  const q = (qRaw||'').trim();
  if(!q) return true;
  // operator: >, <, >=, <=, =, ==, !=
  const op = q.match(/^(>=|<=|!=|==|=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
  if(op){
    const num = _cellNum(text);
    if(isNaN(num)) return false;
    const val = parseFloat(op[2]);
    switch(op[1]){
      case '>':  return num >  val;
      case '<':  return num <  val;
      case '>=': return num >= val;
      case '<=': return num <= val;
      case '=':
      case '==': return num === val;
      case '!=': return num !== val;
    }
  }
  // range: a-b or a..b (both ends numeric)
  const rng = q.match(/^(-?\d+(?:\.\d+)?)\s*(?:\.\.|-)\s*(-?\d+(?:\.\d+)?)$/);
  if(rng){
    const num = _cellNum(text);
    if(isNaN(num)) return false;
    const lo = parseFloat(rng[1]), hi = parseFloat(rng[2]);
    return num >= Math.min(lo,hi) && num <= Math.max(lo,hi);
  }
  // fallback: plain text substring match
  return String(text).toLowerCase().includes(q.toLowerCase());
}
const _extraFilters={};
// Generic setter: colKey = exact header text (lowercase), mode = 'contains'|'exact'|'gte'|'lte'|'range'
function setDropFilter(tableId,colKey,val,mode){
  _extraFilters[tableId]=_extraFilters[tableId]||{};
  if(!val){delete _extraFilters[tableId][colKey];}
  else{_extraFilters[tableId][colKey]={val,mode};}
  applyFilters(tableId);
}
// Legacy aliases kept for backward compat
function filterBySector(val,tableId){setDropFilter(tableId,'sector',val.toLowerCase(),'contains');}
function filterBySignal(val,tableId){setDropFilter(tableId,'signal_label',val.toLowerCase(),'contains');}
function applyFilters(tableId){
  const table=document.getElementById(tableId); if(!table)return;
  const tb=table.tBodies[0]; if(!tb)return;
  const filters=[];
  table.querySelectorAll('thead tr.col-filter input').forEach(inp=>{
    const v=inp.value.trim(); if(v)filters.push([parseInt(inp.dataset.col,10),v]);
  });
  const g=document.querySelector('[data-global-for="'+tableId+'"]');
  const gq=g?g.value.trim().toLowerCase():'';
  const extra=_extraFilters[tableId]||{};
  // Build colKey → index map from header row
  const colIdx={};
  table.querySelectorAll('thead tr:first-child th').forEach((th,i)=>{
    const t=th.textContent.replace(/[\u2195\u2191\u2193]/g,'').trim().toLowerCase().replace(/[^a-z0-9_%]/g,'_');
    colIdx[t]=i;
  });
  let vis=0;
  for(const row of tb.rows){
    if(row.classList.contains('col-filter')){row.style.display='';continue;}
    let show=true;
    if(gq&&!row.textContent.toLowerCase().includes(gq))show=false;
    if(show){
      for(const [key,f] of Object.entries(extra)){
        const idx=colIdx[key]; if(idx===undefined)continue;
        const c=row.cells[idx]; if(!c){show=false;break;}
        const ct=c.textContent.trim();
        if(f.mode==='contains'){if(!ct.toLowerCase().includes(String(f.val).toLowerCase())){show=false;break;}}
        else if(f.mode==='exact'){if(ct.toLowerCase()!==String(f.val).toLowerCase()){show=false;break;}}
        else if(f.mode==='gte'){const n=parseFloat(ct);if(isNaN(n)||n<parseFloat(f.val)){show=false;break;}}
        else if(f.mode==='lte'){const n=parseFloat(ct);if(isNaN(n)||n>parseFloat(f.val)){show=false;break;}}
        else if(f.mode==='range'){
          const [lo,hi]=f.val.split(',').map(Number);
          const n=parseFloat(ct);if(isNaN(n)||n<lo||n>hi){show=false;break;}
        }
      }
    }
    if(show){for(const f of filters){const c=row.cells[f[0]];if(!c||!matchFilter(c.textContent,f[1])){show=false;break;}}}
    row.style.display=show?'':'none'; if(show)vis++;
  }
  const cnt=document.getElementById(tableId+'-count'); if(cnt)cnt.textContent=vis+' rows';
}
function filterTable(input,tableId){applyFilters(tableId);}
function filterColumn(input,tableId){applyFilters(tableId);}
function resetStockFilters(){
  ['sector-filter','signal-filter','trend-filter','secgated-filter','sma-filter','rs22-filter',
   'pattern-filter','slgrade-filter','finscore-filter','salesqoq-filter','patqoq-filter','roe-filter','de-filter']
    .forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
  delete _extraFilters['tbl-stocks'];
  const g=document.querySelector('[data-global-for="tbl-stocks"]');if(g)g.value='';
  applyFilters('tbl-stocks');
}
function exportStocksTV(tableId){
  const table=document.getElementById(tableId); if(!table)return;
  const tb=table.tBodies[0]; if(!tb)return;
  let symCol=-1;
  table.querySelectorAll('thead th').forEach((th,i)=>{if(th.textContent.trim().toLowerCase()==='symbol')symCol=i;});
  if(symCol<0)return;
  const syms=[];
  for(const row of tb.rows){
    if(row.style.display==='none')continue;
    const cell=row.cells[symCol]; if(!cell)continue;
    const sym=cell.textContent.trim().split('\n')[0].trim(); if(sym)syms.push(sym);
  }
  if(!syms.length)return;
  const text=syms.join(',');
  navigator.clipboard.writeText(text).then(()=>{
    const btn=document.querySelector('[onclick*="exportStocksTV"]');
    if(btn){const o=btn.textContent;btn.textContent='\u2705 Copied '+syms.length+' symbols!';
      btn.classList.add('copied');setTimeout(()=>{btn.textContent=o;btn.classList.remove('copied');},3000);}
  }).catch(()=>{const el=document.createElement('textarea');el.value=text;document.body.appendChild(el);el.select();document.execCommand('copy');document.body.removeChild(el);});
}
function exportTableCSV(tableId){
  const table=document.getElementById(tableId); if(!table)return;
  const rows=[];
  const ths=table.querySelectorAll('thead tr:first-child th');
  rows.push(Array.from(ths).map(th=>'"'+th.textContent.replace(/[\u2195\u2191\u2193]/g,'').trim()+'"').join(','));
  for(const row of table.tBodies[0].rows){
    if(row.style.display==='none'||row.classList.contains('col-filter'))continue;
    rows.push(Array.from(row.cells).map(td=>'"'+td.textContent.trim().replace(/"/g,'""')+'"').join(','));
  }
  const blob=new Blob([rows.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download=(tableId||'stocks')+'_export.csv';a.click();URL.revokeObjectURL(a.href);
}
const SCREEN_DEFS={
  rs30_buy:{cat:'signal',name:'🟢 RS30 Buy',
    test(row,h){const r30=_sv(row,_ci(h,'RS30_Signal'));const rs=_n(_sv(row,_ci(h,'RS_22d_Idx%')));const sq=_n(_sv(row,_ci(h,'Sales_QoQ%')));const pq=_n(_sv(row,_ci(h,'PAT_QoQ%')));
    return _isBuy(r30)&&rs!==null&&rs>0&&sq!==null&&sq>15&&pq!==null&&pq>15;}},
  mst_buy:{cat:'signal',name:'📈 MST Swing Buy',
    test(row,h){const mst=_sv(row,_ci(h,'MST_Signal'));const tr=_sv(row,_ci(h,'Trend')).toLowerCase();const rsi=_n(_sv(row,_ci(h,'RSI_14')));
    return _isBuy(mst)&&tr.includes('bull')&&rsi!==null&&rsi>50;}},
  lst_buy:{cat:'signal',name:'🚀 LST Long Buy',
    test(row,h){const lst=_sv(row,_ci(h,'LST_Signal'));const sma=_n(_sv(row,_ci(h,'SMA_Score')));const rs55=_n(_sv(row,_ci(h,'RS_55d_Idx%')));
    return _isBuy(lst)&&sma!==null&&sma>=3&&rs55!==null&&rs55>0;}},
  prime:{cat:'signal',name:'🌟 Prime Setups',
    test(row,h){const sig=_sv(row,_ci(h,'Signal_Label')).toLowerCase();const gate=_sv(row,_ci(h,'Sec_Gated'));const sma=_n(_sv(row,_ci(h,'SMA_Score')));
    return (sig.includes('prime')||sig.includes('triple'))&&gate==='✓'&&sma===4;}},
  enhanced_buy:{cat:'signal',name:'✅ Enhanced Buy',
    test(row,h){const sig=_sv(row,_ci(h,'Signal_Label')).toLowerCase();const fin=_n(_sv(row,_ci(h,'Fin_Score')));const sma=_n(_sv(row,_ci(h,'SMA_Score')));
    return (sig.includes('prime')||sig.includes('confirmed'))&&fin!==null&&fin>=4&&sma!==null&&sma>=3;}},
  chart_vcp:{cat:'signal',name:'📐 VCP Pattern',
    test(row,h){const cp=_sv(row,_ci(h,'Chart_Pattern')).toLowerCase();return cp.includes('vcp');}},
  chart_pennant:{cat:'signal',name:'🏳 Pennant / Flag',
    test(row,h){const cp=_sv(row,_ci(h,'Chart_Pattern')).toLowerCase();return cp.includes('pennant')||cp.includes('flag');}},
  chart_hs:{cat:'signal',name:'🔄 Inv H&S Pattern',
    test(row,h){const cp=_sv(row,_ci(h,'Chart_Pattern')).toLowerCase();return cp.includes('inv')&&cp.includes('head');}},
  low_pe:{cat:'fundamental',name:'💲 Low P/E',
    test(row,h){const pe=_n(_sv(row,_ci(h,'P/E')));const py=_n(_sv(row,_ci(h,'PAT_YoY%')));
    return pe!==null&&pe>1&&pe<15&&py!==null&&py>0;}},
  low_de:{cat:'fundamental',name:'🛡 Low Debt (D/E)',
    test(row,h){const de=_n(_sv(row,_ci(h,'D/E')));const roe=_n(_sv(row,_ci(h,'ROE%')));
    return de!==null&&de<0.3&&roe!==null&&roe>10;}},
  high_roe:{cat:'fundamental',name:'🏆 High ROE',
    test(row,h){const roe=_n(_sv(row,_ci(h,'ROE%')));const de=_n(_sv(row,_ci(h,'D/E')));const py=_n(_sv(row,_ci(h,'PAT_YoY%')));
    return roe!==null&&roe>20&&de!==null&&de<1&&py!==null&&py>10;}},
  pat_qoq200:{cat:'fundamental',name:'💥 PAT QoQ 200%',
    test(row,h){const pq=_n(_sv(row,_ci(h,'PAT_QoQ%')));return pq!==null&&pq>=200;}},
  pat_yoy200:{cat:'fundamental',name:'💥 PAT YoY 200%',
    test(row,h){const py=_n(_sv(row,_ci(h,'PAT_YoY%')));return py!==null&&py>=200;}},
  sales_qoq200:{cat:'fundamental',name:'📦 Sales QoQ 200%',
    test(row,h){const sq=_n(_sv(row,_ci(h,'Sales_QoQ%')));return sq!==null&&sq>=200;}},
  sales_yoy200:{cat:'fundamental',name:'📦 Sales YoY 200%',
    test(row,h){const sy=_n(_sv(row,_ci(h,'Sales_YoY%')));return sy!==null&&sy>=200;}},
  high_eps:{cat:'fundamental',name:'💰 High EPS',
    test(row,h){const eps=_n(_sv(row,_ci(h,'EPS')));const sma=_n(_sv(row,_ci(h,'SMA_Score')));
    return eps!==null&&eps>10&&sma!==null&&sma>=2;}},
  quality_growth:{cat:'fundamental',name:'💎 Quality + Growth',
    test(row,h){const roe=_n(_sv(row,_ci(h,'ROE%')));const py=_n(_sv(row,_ci(h,'PAT_YoY%')));const sy=_n(_sv(row,_ci(h,'Sales_YoY%')));const de=_n(_sv(row,_ci(h,'D/E')));
    return roe!==null&&roe>15&&py!==null&&py>15&&sy!==null&&sy>10&&de!==null&&de<1;}},
  near52high:{cat:'trend',name:'📈 Near 52-Week High',
    test(row,h){const f52=_n(_sv(row,_ci(h,'From_52W_High%')));const rs=_n(_sv(row,_ci(h,'RS_22d_Idx%')));
    return f52!==null&&f52>=-8&&rs!==null&&rs>0;}},
  above200sma:{cat:'trend',name:'🟢 Above 200 SMA',
    test(row,h){const sma=_n(_sv(row,_ci(h,'SMA_Score')));return sma===4;}},
  golden_cross:{cat:'trend',name:'✨ Golden Cross Zone',
    test(row,h){const tr=_sv(row,_ci(h,'Trend')).toLowerCase();const sma=_n(_sv(row,_ci(h,'SMA_Score')));const rs=_n(_sv(row,_ci(h,'RS_22d_Idx%')));
    return tr.includes('bull')&&sma===4&&rs!==null&&rs>5;}},
  vol_spike:{cat:'trend',name:'🔥 Volume Spike',
    test(row,h){const rv=_n(_sv(row,_ci(h,'Rel_Vol')));const sig=_sv(row,_ci(h,'Signal_Label')).toLowerCase();
    return rv!==null&&rv>=3&&!sig.includes('avoid');}},
  rsi_pullback:{cat:'trend',name:'📉 RSI Pullback Buy',
    test(row,h){const rsi=_n(_sv(row,_ci(h,'RSI_14')));const rs=_n(_sv(row,_ci(h,'RS_22d_Idx%')));const tr=_sv(row,_ci(h,'Trend')).toLowerCase();
    return rsi!==null&&rsi>=35&&rsi<=50&&rs!==null&&rs>0&&tr.includes('bull');}},
  momentum:{cat:'trend',name:'🏁 Momentum Leaders',
    test(row,h){const sig=_sv(row,_ci(h,'Signal_Label')).toLowerCase();const rs=_n(_sv(row,_ci(h,'RS_22d_Idx%')));const sma=_n(_sv(row,_ci(h,'SMA_Score')));const rsi=_n(_sv(row,_ci(h,'RSI_14')));
    return (sig.includes('prime')||sig.includes('confirmed'))&&rs!==null&&rs>5&&sma!==null&&sma>=3&&rsi!==null&&rsi>55;}},
  sector_leader:{cat:'sector',name:'🎯 Sector Leaders',
    test(row,h){const gate=_sv(row,_ci(h,'Sec_Gated'));const rs22=_n(_sv(row,_ci(h,'RS_22d_Idx%')));const rs55=_n(_sv(row,_ci(h,'RS_55d_Idx%')));const sma=_n(_sv(row,_ci(h,'SMA_Score')));
    return gate==='✓'&&rs22!==null&&rs22>8&&rs55!==null&&rs55>5&&sma!==null&&sma>=3;}},
  rs_breakout:{cat:'sector',name:'⚡ RS Breakout',
    test(row,h){const rs22=_n(_sv(row,_ci(h,'RS_22d_Idx%')));const rs55=_n(_sv(row,_ci(h,'RS_55d_Idx%')));const rv=_n(_sv(row,_ci(h,'Rel_Vol')));const tr=_sv(row,_ci(h,'Trend')).toLowerCase();
    return rs22!==null&&rs22>10&&rs55!==null&&rs55>5&&rv!==null&&rv>1.5&&tr.includes('bull');}},
  dividend:{cat:'sector',name:'💵 Dividend + Stability',
    test(row,h){const roe=_n(_sv(row,_ci(h,'ROE%')));const de=_n(_sv(row,_ci(h,'D/E')));const py=_n(_sv(row,_ci(h,'PAT_YoY%')));const sma=_n(_sv(row,_ci(h,'SMA_Score')));
    return roe!==null&&roe>12&&de!==null&&de<0.5&&py!==null&&py>5&&sma!==null&&sma>=2;}}
};
function _ci(headers,name){const n=name.toLowerCase();for(let i=0;i<headers.length;i++){if(headers[i].textContent.replace(/[\u2195\u2191\u2193]/g,'').trim().toLowerCase()===n)return i;}return -1;}
function _sv(row,idx){return idx>=0&&row.cells[idx]?row.cells[idx].textContent.trim():'';}
function _n(v){const f=parseFloat(v);return isNaN(f)?null:f;}
/* MST/LST/RS30 cells display the remapped word 'Active' (engine value 'Buy').
   Accept both so the signal screens match regardless of display vocabulary. */
function _isBuy(v){const s=String(v).trim().toLowerCase();return s==='buy'||s==='active';}
let _activeScreen=null;
function runScreen(cardEl,screenKey){
  const def=SCREEN_DEFS[screenKey];if(!def)return;
  if(_activeScreen===screenKey){resetScreen();return;}
  _activeScreen=screenKey;
  document.querySelectorAll('.scr-card').forEach(c=>c.classList.remove('active'));
  cardEl.classList.add('active');
  const src=document.getElementById('tbl-stocks');if(!src)return;
  const headers=Array.from(src.querySelectorAll('thead tr:first-child th'));
  const matched=[];
  for(const row of src.tBodies[0].rows){if(def.test(row,headers))matched.push(row.cloneNode(true));}
  const thead=src.querySelector('thead').cloneNode(true);
  thead.querySelectorAll('tr.col-filter').forEach(r=>r.remove());
  const tbody=document.createElement('tbody');matched.forEach(r=>tbody.appendChild(r));
  const tbl=document.createElement('table');tbl.id='scr-result-tbl';tbl.className='data-tbl';
  tbl.appendChild(thead);tbl.appendChild(tbody);
  const wrap=document.createElement('div');wrap.className='tbl-wrap';wrap.appendChild(tbl);
  const rw=document.getElementById('scr-result-wrap');rw.innerHTML='';rw.appendChild(wrap);rw.style.display='';
  const st=document.getElementById('scr-status');st.style.display='flex';
  document.getElementById('scr-status-text').textContent=def.name+' — '+matched.length+' stocks matched';
}
function resetScreen(){
  _activeScreen=null;
  document.querySelectorAll('.scr-card').forEach(c=>c.classList.remove('active'));
  document.getElementById('scr-result-wrap').style.display='none';
  document.getElementById('scr-status').style.display='none';
}

/* ── HIDE INTERNAL SCREENER COLUMNS ──────────────────────────── */
function _hideInternalCols(){
  const tbl=document.getElementById('tbl-stocks');if(!tbl)return;
  const HIDDEN=['mst_signal','lst_signal','rs30_signal'];
  const ths=Array.from(tbl.querySelectorAll('thead tr:first-child th'));
  ths.forEach((th,i)=>{
    const nm=th.textContent.replace(/[↕↑↓]/g,'').trim().toLowerCase();
    if(HIDDEN.includes(nm)){
      tbl.querySelectorAll('tr').forEach(r=>{if(r.cells[i])r.cells[i].style.display='none';});
    }
  });
}
document.addEventListener('DOMContentLoaded',_hideInternalCols);

function filterScreenCat(btn,cat){
  document.querySelectorAll('.scr-cat-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.scr-card').forEach(c=>{
    c.style.display=(cat==='all'||c.dataset.cat===cat)?'':'none';
  });
  document.querySelectorAll('.scr-cat-label').forEach(l=>{
    l.style.display=(cat==='all'||l.dataset.label===cat)?'':'none';
  });
}

/* ── TABLE SORT ────────────────────────────────────────────────────────── */
function sortTable(th){
  const table=th.closest('table');
  const tb=table.tBodies[0];
  const col=th.cellIndex;
  const asc=!th.classList.contains('asc');
  table.querySelectorAll('th').forEach(h=>h.classList.remove('asc','desc'));
  th.classList.add(asc?'asc':'desc');
  Array.from(tb.rows).sort((a,b)=>{
    let av=a.cells[col]?.textContent.trim()||'';
    let bv=b.cells[col]?.textContent.trim()||'';
    const af=parseFloat(av.replace(/[+%,]/g,''));
    const bf=parseFloat(bv.replace(/[+%,]/g,''));
    if(!isNaN(af)&&!isNaN(bf))return asc?af-bf:bf-af;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  }).forEach(r=>tb.appendChild(r));
}

/* ── COPY ──────────────────────────────────────────────────────────────── */
function copyText(btn,text){
  const orig=btn.dataset.orig||btn.textContent;
  navigator.clipboard.writeText(text).then(()=>{
    btn.textContent='✅ Copied!';btn.classList.add('copied');
    setTimeout(()=>{btn.textContent=orig;btn.classList.remove('copied');},2000);
  }).catch(()=>{
    const el=document.createElement('textarea');
    el.value=text;document.body.appendChild(el);
    el.select();document.execCommand('copy');document.body.removeChild(el);
    btn.textContent='✅ Copied!';
    setTimeout(()=>{btn.textContent=orig;},2000);
  });
}

/* ── VIEW TOGGLE ───────────────────────────────────────────────────────── */
function toggleView(sid,mode){
  document.querySelectorAll('#'+sid+' .vt-btn').forEach(b=>b.classList.remove('active'));
  document.querySelector('#'+sid+' [data-mode="'+mode+'"]').classList.add('active');
  const cv=document.getElementById(sid+'-cards');
  const tv=document.getElementById(sid+'-table');
  if(cv)cv.style.display=mode==='cards'?'':'none';
  if(tv)tv.style.display=mode==='table'?'':'none';
}

/* ── Mobile column-set toggle ──────────────────────────────────────────────
   Adds/removes a gv-<group> class on the table; CSS hides columns not in the
   active group. Pinned columns and column indices are untouched, so sort and
   per-column filters keep working unchanged. */
function setGroup(tid,grp,btn){
  const t=document.getElementById(tid); if(!t)return;
  t.classList.remove('gv-analysis','gv-tech','gv-fin');
  if(grp!=='all') t.classList.add('gv-'+grp);
  const bar=btn.closest('.grp-chips');
  if(bar) bar.querySelectorAll('.grp-chip').forEach(b=>b.classList.toggle('active',b===btn));
}
function _initGroups(){
  if(!window.matchMedia('(max-width:640px)').matches) return;  // desktop: show all
  document.querySelectorAll('.grp-chips').forEach(bar=>{
    const tid=bar.getAttribute('data-for');
    const def=bar.getAttribute('data-default')||'analysis';
    const btn=bar.querySelector('.grp-chip[data-grp="'+def+'"]');
    if(btn) setGroup(tid,def,btn);
  });
}
document.addEventListener('DOMContentLoaded',_initGroups);

/* ── SLEEVE CALCULATOR ─────────────────────────────────────────────────────
   Formula:  Qty = floor( (Capital × Risk%) / (Price × effective_SL%) )
   effective_SL = min(SL_Buy% from engine, Max SL cap input)
   If SL_Buy% is missing/zero → uses Max SL cap as fallback
   This is pure risk-based sizing — ATR_Wt% is NOT used for qty.
   ─────────────────────────────────────────────────────────────────────── */
function fmtNum(n, currency){
  const c = currency || '₹';
  if(isNaN(n) || n === 0) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if(abs >= 10000000) return sign + c + (abs/10000000).toFixed(2) + 'Cr';
  if(abs >= 100000)   return sign + c + (abs/100000).toFixed(2) + 'L';
  if(abs >= 1000)     return sign + c + Math.round(abs).toLocaleString('en-IN');
  return sign + c + abs.toFixed(2);
}

function getCurrency(){
  // Detect currency symbol from capital input label
  const lbl = document.querySelector('.ctrl-label');
  return (lbl && lbl.textContent.includes('$')) ? '$' : '₹';
}

function recalcAll(){
  document.querySelectorAll('[id^="sleeve-"]').forEach(tbl => {
    calcSleeve(tbl.id.replace('sleeve-', ''));
  });
}

function calcSleeve(key){
  const capital  = parseFloat(document.getElementById('global-capital')?.value) || 0;
  const riskPct  = parseFloat(document.getElementById('global-risk')?.value)    || 1;
  const slCap    = parseFloat(document.getElementById('global-sl-cap')?.value)  || 5;
  const tbl      = document.getElementById('sleeve-' + key);
  if(!tbl || capital <= 0) return;

  const cur = getCurrency();

  // ── Pass 1: risk-based base sizing per row ───────────────────────────────
  //   Qty = floor( (Capital × Risk%) / (Price × SL%) )
  //   #6: SL% is the ATR(5)×1.2 stop from the engine (row.dataset.sl).
  //       The 'Max SL cap' input is only a fallback when ATR is unavailable.
  const items = [];
  for(const row of tbl.tBodies[0].rows){
    const price = parseFloat(row.dataset.price) || 0;
    const slRaw = parseFloat(row.dataset.sl)    || 0;   // ATR-based SL% from engine
    const cells = {
      q:   row.querySelector('.qty-cell'),
      a:   row.querySelector('.amt-cell'),
      slp: row.querySelector('.slp-cell'),
      r:   row.querySelector('.rsk-cell'),
      esl: row.querySelector('.esl-cell'),
    };
    if(price <= 0){
      Object.values(cells).forEach(c=>{ if(c) c.textContent='—'; });
      continue;
    }
    const effectiveSL = (slRaw > 0) ? slRaw : slCap;     // ATR drives; cap = fallback
    const riskAmount  = capital * riskPct / 100;
    const riskPerShr  = price * effectiveSL / 100;
    const baseQty     = riskPerShr > 0 ? Math.floor(riskAmount / riskPerShr) : 0;
    items.push({price, slRaw, effectiveSL, baseQty, cells});
  }

  // ── #7: cap total deployment at portfolio capital ────────────────────────
  //   Pure risk sizing can deploy far more than the account holds. Scale every
  //   position down by the same factor so the sum fits the capital ceiling.
  let baseDeployed = 0;
  items.forEach(it => { baseDeployed += it.baseQty * it.price; });
  const scale = (baseDeployed > capital && baseDeployed > 0) ? capital / baseDeployed : 1;

  // ── Pass 2: apply scale, fill cells, accumulate totals ───────────────────
  let totalDeployed = 0, totalRisk = 0, n = 0;
  for(const it of items){
    const qty        = scale < 1 ? Math.floor(it.baseQty * scale) : it.baseQty;
    const amount     = qty * it.price;
    const slPrice    = it.price * (1 - it.effectiveSL / 100);
    const actualRisk = qty * it.price * it.effectiveSL / 100;
    const {q, a, slp, r, esl} = it.cells;
    if(q)   q.textContent   = qty > 0 ? qty.toLocaleString('en-IN') : '—';
    if(a)   a.textContent   = qty > 0 ? fmtNum(amount, cur) : '—';
    if(slp) slp.textContent = qty > 0 ? slPrice.toFixed(2) : '—';
    if(r)   r.textContent   = qty > 0 ? fmtNum(actualRisk, cur) : '—';
    if(esl){
      esl.textContent = it.effectiveSL.toFixed(1) + '%';
      esl.style.color = (it.slRaw <= 0) ? '#f59e0b' : '';
      esl.title = it.slRaw > 0
        ? `ATR(5)×1.2 stop: ${it.slRaw.toFixed(1)}%`
        : `No ATR data → fallback ${it.effectiveSL.toFixed(1)}%`;
    }
    totalDeployed += amount;
    totalRisk     += actualRisk;
    if(qty > 0) n++;
  }

  const sumEl = document.getElementById('sum-'  + key);
  const totEl = document.getElementById('total-' + key);
  const scaleNote = scale < 1
    ? ' · ⚖ scaled to ' + Math.round(scale*100) + '% to fit capital'
    : '';
  if(sumEl) sumEl.textContent =
    n + ' stocks · Deployed ' + fmtNum(totalDeployed, cur) +
    ' / ' + fmtNum(capital, cur) +
    ' · Risk ' + fmtNum(totalRisk, cur) +
    ' (' + (capital > 0 ? (totalRisk/capital*100).toFixed(1) : '0') + '% of capital)' +
    scaleNote;
  if(totEl) totEl.textContent = fmtNum(totalDeployed, cur);
}

/* ── ZERODHA BASKET JSON ─────────────────────────────────────────────────
   Format matches Zerodha's basket order import exactly.
   Based on the official Zerodha basket JSON structure (array of order objects).
   ⚠ instrumentToken is set to 0 — Zerodha resolves by tradingsymbol+exchange.
   In Zerodha Kite: Orders → Basket Orders → Import from file
   ─────────────────────────────────────────────────────────────────────── */
function downloadZerodha(key){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  const basket = [];
  let weight = 0;

  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const price = parseFloat(row.dataset.price)||0;
    const qty   = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    if(!sym||qty<=0) continue;

    // Limit price = current price + 0.5% buffer (rounded to nearest 0.05 tick)
    const rawLimit   = price * 1.005;
    const limitPrice = Math.round(rawLimit / 0.05) * 0.05;
    const lp         = parseFloat(limitPrice.toFixed(2));

    basket.push({
      id: Date.now() + weight,
      instrument: {
        tradingsymbol:  sym,
        scripCode:      "",
        type:           "EQ",
        symbol:         sym,
        segment:        "NSE",
        exchange:       "NSE",
        tickSize:       0.05,
        lotSize:        1,
        company:        sym,
        tradable:       true,
        precision:      2,
        fullName:       sym,
        niceName:       sym,
        niceNameHTML:   sym,
        stockWidget:    true,
        exchangeToken:  0,
        instrumentToken:0,
        isin:           "",
        related:        [],
        underlying:     null,
        auctionNumber:  null,
        isEquity:       true,
        isWeekly:       false
      },
      weight: weight,
      params: {
        transactionType:  "BUY",
        product:          "CNC",
        orderType:        "LIMIT",
        validity:         "DAY",
        validityTTL:      1,
        quantity:         qty,
        price:            lp,
        triggerPrice:     0,
        disclosedQuantity:0,
        lastPrice:        parseFloat(price.toFixed(2)),
        variety:          "regular",
        tags:             []
      }
    });
    weight++;
  }

  if(basket.length===0){
    alert('Calculate quantities first (click ⚡ Recalculate)');return;
  }

  const blob = new Blob([JSON.stringify(basket,null,2)],{type:'application/json'});
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `sleeve_${key}_zerodha_basket.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ── IBKR BASKET CSV ─────────────────────────────────────────────────────
   Format: TWS BasketTrader CSV (all retail IBKR accounts support this).
   How to use in TWS: File → Open → Basket Trader → Import from File
   Or: Orders menu → Import from File
   ─────────────────────────────────────────────────────────────────────── */
function downloadIBKR(key, isIndia){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  const isInd = (isIndia==='True');
  const exchange = isInd ? 'NSE'   : 'SMART';
  const currency = isInd ? 'INR'   : 'USD';

  // IBKR basket file header updated to your exact sequence
  const HEADER = [
    'Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 
    'Currency', 'TimeInForce', 'OrderType', 'LmtPrice'
  ];
  let csv = HEADER.join(',') + '\n';
  let count = 0;

  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const price = parseFloat(row.dataset.price)||0;
    const qty   = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    if(!sym||qty<=0) continue;

    // Limit price = current price + 0.5% buffer
    const lmtPrice = parseFloat((price * 1.005).toFixed(isInd ? 2 : 2));

    const fields = [
      'BUY',        // Action
      qty,          // Quantity
      sym,          // Symbol
      'STK',        // SecType
      exchange,     // Exchange
      currency,     // Currency
      'DAY',        // TimeInForce
      'LMT',        // OrderType
      lmtPrice      // LmtPrice
    ];
    csv += fields.join(',') + '\n';
    count++;
  }

  if(count===0){
    alert('Calculate quantities first (click ⚡ Recalculate)');return;
  }

  const blob = new Blob([csv],{type:'text/csv'});
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `sleeve_${key}_ibkr_basket.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ── ENTRY TRACKING (window.storage) ───────────────────────────────────── */
async function trackEntry(key){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl){return;}
  const date    = new Date().toISOString().split('T')[0];
  const capital = parseFloat(document.getElementById('global-capital')?.value)||0;
  const entries = [];
  for(const row of tbl.tBodies[0].rows){
    const sym  = (row.dataset.sym||'').trim();
    const price= parseFloat(row.dataset.price)||0;
    const qty  = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    const sl   = parseFloat(row.dataset.sl)||0;
    if(sym && qty>0){
      entries.push({sym,entry_price:price,qty,sl_pct:sl,entry_date:date});
    }
  }
  if(entries.length===0){
    document.getElementById('tmsg-'+key).textContent='⚠ Calculate quantities first';
    return;
  }
  try{
    await window.storage.set('sleeve_'+key+'_entry',
      JSON.stringify({date,capital,entries}));
    document.getElementById('tmsg-'+key).textContent=
      '✅ Tracked '+entries.length+' positions on '+date;
    document.getElementById('edate-'+key).textContent='Entry: '+date;
    loadTracking(key);
  }catch(e){
    // Fallback to localStorage for non-Claude environments
    try{
      localStorage.setItem('sleeve_'+key+'_entry',
        JSON.stringify({date,capital,entries}));
      document.getElementById('tmsg-'+key).textContent=
        '✅ Tracked '+entries.length+' (local)';
    }catch(e2){
      document.getElementById('tmsg-'+key).textContent='⚠ Storage unavailable';
    }
  }
}

async function loadTracking(key){
  let data = null;
  try{
    const stored = await window.storage.get('sleeve_'+key+'_entry');
    if(stored) data = JSON.parse(stored.value);
  }catch(e){
    try{
      const ls = localStorage.getItem('sleeve_'+key+'_entry');
      if(ls) data = JSON.parse(ls);
    }catch(e2){}
  }
  if(!data||!data.entries) return;

  const entryMap = {};
  data.entries.forEach(e=>entryMap[e.sym]=e);

  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  let plTotal=0; let plCount=0;
  const cur = getCurrency();
  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const entry = entryMap[sym];
    const plCell= row.querySelector('.pl-cell');
    if(!entry||!plCell){if(plCell)plCell.textContent='—';continue;}
    const cur   = parseFloat(row.dataset.price)||0;
    const plPct = ((cur-entry.entry_price)/entry.entry_price*100).toFixed(1);
    const plAmt = Math.round((cur-entry.entry_price)*entry.qty);
    plCell.textContent = plPct+'% ('+fmtNum(Math.abs(plAmt), cur)+')';
    plCell.className   = 'calc-cell pl-cell '+(parseFloat(plPct)>0?'pos-strong':'neg-strong');
    plTotal += plAmt;
    plCount++;
  }

  const edEl   = document.getElementById('edate-'+key);
  const plSumEl= document.getElementById('plsum-'+key);
  if(edEl)   edEl.textContent   = 'Entry: '+data.date;
  if(plSumEl){
    plSumEl.textContent = plCount>0 ? fmtNum(Math.abs(plTotal), cur) : '—';
    plSumEl.className   = plTotal>0 ? 'pos-strong' : 'neg-strong';
  }
}

async function clearTracking(key){
  if(!confirm('Clear tracking data for Sleeve '+key+'?')) return;
  try{ await window.storage.delete('sleeve_'+key+'_entry'); }catch(e){}
  try{ localStorage.removeItem('sleeve_'+key+'_entry'); }catch(e){}
  const tbl=document.getElementById('sleeve-'+key);
  if(tbl) for(const row of tbl.tBodies[0].rows){
    const c=row.querySelector('.pl-cell');
    if(c){c.textContent='—';c.className='calc-cell pl-cell';}
  }
  const edEl=document.getElementById('edate-'+key);
  const tmEl=document.getElementById('tmsg-'+key);
  if(edEl)edEl.textContent='';
  if(tmEl)tmEl.textContent='🗑 Cleared';
}

/* ── TRADINGVIEW HOVER PREVIEW  (v6.2/v6.3) ────────────────────────────────
   One hidden <iframe> created on page load — just swap src on hover.
   Fast: iframe stays warm, no script injection, no DOM thrashing.

   ┌─ SIZE CONFIG ──────────────────────────────────────────────────────────┐
   │  TV_PREVIEW_W  — total width of the floating window (px)              │
   │  TV_PREVIEW_H  — total height including header bar (px)               │
   │  TV_PREVIEW_HEADER_H — title bar height, usually leave at 30          │
   └────────────────────────────────────────────────────────────────────────┘ */
const TV_PREVIEW_W        = 720;   // px — preview box total width
const TV_PREVIEW_H        = 500;   // px — preview box total height (incl. header)
const TV_PREVIEW_HEADER_H = 30;    // px — header bar height
const TV_PREVIEW_OFFSET_X = 18;    // px — gap right of cursor
const TV_PREVIEW_OFFSET_Y = 10;    // px — gap below cursor
const TV_HIDE_DELAY_MS    = 120;   // ms — debounce before hiding

let _tvEnabled = true;
let _tvHideTimer = null;
let _tvBox = null;
let _tvIframe = null;
let _tvHeader = null;
let _tvFallback = null;
let _tvLastSym = '';
function _showTvFallback(tvSymbol){
  if(!_tvFallback)return;
  _tvIframe.style.display='none';
  _tvFallback.style.display='flex';
  const sym=tvSymbol.replace('%3A',':');
  const url='https://www.tradingview.com/chart/?symbol='+tvSymbol;
  const msg=document.getElementById('tv-fb-msg');
  const lnk=document.getElementById('tv-fb-link');
  if(msg)msg.textContent=sym+' — preview not available';
  if(lnk){lnk.href=url;lnk.textContent='Open '+sym+' in TradingView ↗';}
}

function _tvGetTheme(){
  const t = document.documentElement.getAttribute('data-theme') || 'dark';
  return (t === 'light') ? 'light' : 'dark';
}

function _tvBuildSrc(tvSymbol){
  // widgetembed = correct FREE embed URL for all exchanges globally.
  // advanced-chart is a paid/whitelisted widget that shows "only available at
  // TradingView" for non-partner sites — do NOT use it.
  // widgetembed also correctly re-loads when a new src is set via iframe swap.
  const sym = tvSymbol.replace('%3A',':');
  const theme = _tvGetTheme();
  return 'https://www.tradingview.com/widgetembed/?symbol=' + encodeURIComponent(sym)
    + '&interval=D&range=12M&theme=' + theme
    + '&style=1&locale=en&hide_side_toolbar=1&allow_symbol_change=0'
    + '&save_image=0&withdateranges=1';
}

function _tvMakeIframe(){
  // Create a FRESH iframe per symbol.
  // Reusing the same iframe + reassigning src does NOT reliably reload
  // TradingView's widgetembed — remove+recreate is the only reliable way.
  const h = TV_PREVIEW_H - TV_PREVIEW_HEADER_H;
  const fr = document.createElement('iframe');
  fr.id = 'tv-preview-iframe';
  fr.style.cssText = 'border:none;display:block;width:100%;height:' + h + 'px;';
  fr.setAttribute('sandbox',
    'allow-scripts allow-same-origin allow-popups allow-forms allow-top-navigation-by-user-activation');
  return fr;
}

function _tvInit(){
  _tvBox = document.createElement('div');
  _tvBox.id = 'tv-preview-box';
  _tvBox.style.width  = TV_PREVIEW_W + 'px';
  _tvBox.style.height = TV_PREVIEW_H + 'px';

  _tvHeader = document.createElement('div');
  _tvHeader.id = 'tv-preview-header';
  _tvHeader.textContent = 'TradingView';

  // _tvIframe starts null — created fresh on first hover
  _tvIframe = null;

  _tvFallback = document.createElement('div');
  _tvFallback.id = 'tv-preview-fallback';
  _tvFallback.style.cssText = 'display:none;width:100%;height:100%;flex-direction:column;'
    +'align-items:center;justify-content:center;gap:10px;'
    +'font-size:13px;color:#8b90a8;text-align:center;padding:20px;';
  _tvFallback.innerHTML = '<div style="font-size:22px">\U0001f4ca</div>'
    +'<div id="tv-fb-msg">Preview not available</div>'
    +'<a id="tv-fb-link" href="#" target="_blank" rel="noopener" '
    +'style="color:#5b8def;font-weight:600;padding:6px 14px;border:1px solid #5b8def;border-radius:8px;">Open in TradingView ↗</a>';
  _tvBox.appendChild(_tvHeader);
  _tvBox.appendChild(_tvFallback);
  document.body.appendChild(_tvBox);

  // postMessage listener: catch TV symbol-not-found events
  window.addEventListener('message',(e)=>{
    if(!e.origin.includes('tradingview.com')) return;
    const d = e.data;
    if(d && (d.name==='symbol-not-found' || d.type==='symbolNotFound')){
      _showTvFallback(_tvLastSym);
    }
  }, false);
  // No warm-load — pre-loading a different symbol causes the first real hover
  // to show the wrong chart until the iframe reloads.
}

function _tvShow(tvSymbol, displayName, mouseX, mouseY){
  if(!_tvEnabled || !_tvBox) return;
  clearTimeout(_tvHideTimer);

  if(tvSymbol !== _tvLastSym){
    // Remove old iframe entirely — src reassignment doesn't re-render TV
    if(_tvIframe && _tvIframe.parentNode){
      _tvIframe.parentNode.removeChild(_tvIframe);
    }
    if(_tvFallback) _tvFallback.style.display = 'none';
    // Insert fresh iframe before the fallback div
    _tvIframe = _tvMakeIframe();
    _tvBox.insertBefore(_tvIframe, _tvFallback);
    _tvIframe.src = _tvBuildSrc(tvSymbol);
    _tvLastSym = tvSymbol;
  }

  _tvHeader.textContent = '\U0001f4c8 ' + displayName + ' — Daily · 12M';
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = mouseX + TV_PREVIEW_OFFSET_X;
  let top  = mouseY + TV_PREVIEW_OFFSET_Y;
  if(left + TV_PREVIEW_W > vw - 8) left = mouseX - TV_PREVIEW_W - 8;
  if(top  + TV_PREVIEW_H > vh - 8) top  = mouseY - TV_PREVIEW_H - 8;
  _tvBox.style.left    = Math.max(4, left) + 'px';
  _tvBox.style.top     = Math.max(4, top)  + 'px';
  _tvBox.style.display = 'block';
}

function _tvHide(){
  _tvHideTimer = setTimeout(()=>{
    if(_tvBox) _tvBox.style.display = 'none';
  }, TV_HIDE_DELAY_MS);
}

function _tvMove(mouseX, mouseY){
  if(!_tvBox || _tvBox.style.display === 'none') return;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = mouseX + TV_PREVIEW_OFFSET_X;
  let top  = mouseY + TV_PREVIEW_OFFSET_Y;
  if(left + TV_PREVIEW_W > vw - 8) left = mouseX - TV_PREVIEW_W - 8;
  if(top  + TV_PREVIEW_H > vh - 8) top  = mouseY - TV_PREVIEW_H - 8;
  _tvBox.style.left = Math.max(4, left) + 'px';
  _tvBox.style.top  = Math.max(4, top)  + 'px';
}

function _tvToggle(){
  _tvEnabled = !_tvEnabled;
  const btn = document.getElementById('tv-preview-toggle');
  if(btn){
    btn.textContent = _tvEnabled ? '📈 Chart ON' : '📈 Chart OFF';
    btn.className   = _tvEnabled ? 'tv-on' : 'tv-off';
  }
  if(!_tvEnabled && _tvBox) _tvBox.style.display = 'none';
  try{ localStorage.setItem('tvPreviewOn', _tvEnabled ? '1' : '0'); }catch(e){}
}

function _tvAttachHovers(){
  document.querySelectorAll('a.tv-link[data-tv]').forEach(el => {
    if(el.dataset.tvBound) return;
    el.dataset.tvBound = '1';
    el.addEventListener('mouseenter', e => {
      clearTimeout(_tvHideTimer);
      _tvShow(el.dataset.tvPreview || el.dataset.tv, el.textContent.trim(), e.clientX, e.clientY);
    });
    el.addEventListener('mousemove', e => _tvMove(e.clientX, e.clientY));
    el.addEventListener('mouseleave', _tvHide);
  });
}

// Redefine showTab to also re-attach hovers after tab switch
function showTab(id){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
  localStorage.setItem('activeTab',id);
  setTimeout(_tvAttachHovers, 50);
}

// Local-time append: show visitor's timezone alongside UTC run time
(function(){
  const el = document.getElementById('run-meta');
  if(!el) return;
  try {
    const utcStr = el.dataset.utc; // e.g. "09 Jun 2026  14:35"
    // Parse the UTC string into a Date object
    const cleaned = utcStr.replace(/\s+/g,' ').trim();
    const d = new Date(cleaned + ' UTC');
    if(isNaN(d)) return;
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const local = d.toLocaleString(undefined,{
      day:'2-digit', month:'short', year:'numeric',
      hour:'2-digit', minute:'2-digit', timeZoneName:'short'
    });
    // Only append if local TZ differs meaningfully from UTC
    const offsetMins = -d.getTimezoneOffset();
    if(offsetMins === 0) return; // same as UTC, no need to show twice
    el.innerHTML += ` <span style="opacity:.7;font-size:10px;">(${local})</span>`;
  } catch(e){}
})();

// Single DOMContentLoaded — handles theme, sleeves, TV init
document.addEventListener('DOMContentLoaded', ()=>{
  _initThemeFont();
  const saved = localStorage.getItem('activeTab') || 'market';
  showTab(saved);
  document.querySelectorAll('[id^="sleeve-"]').forEach(tbl=>{
    const key = tbl.id.replace('sleeve-','');
    calcSleeve(key);
    loadTracking(key);
  });
  // TV preview
  _tvInit();
  const tvPref = localStorage.getItem('tvPreviewOn');
  if(tvPref === '0'){ _tvEnabled = false; }
  const btn = document.getElementById('tv-preview-toggle');
  if(btn){
    btn.textContent = _tvEnabled ? '📈 Chart ON' : '📈 Chart OFF';
    btn.className   = _tvEnabled ? 'tv-on' : 'tv-off';
  }
  _tvAttachHovers();

  // Default sort: RS22% descending for Market Breadth, Sector Performance, Sector Rotation, Industry Rotation
  ['tbl-breadth','tbl-secperf','tbl-secrot','tbl-indrot'].forEach(tid=>{
    const tbl=document.getElementById(tid); if(!tbl)return;
    const ths=Array.from(tbl.querySelectorAll('thead tr:first-child th'));
    const th=ths.find(h=>h.textContent.replace(/[↕↑↓\s]/g,'').toLowerCase()==='rs22%');
    if(!th)return;
    // Sort descending (highest RS22% on top)
    const tb=tbl.tBodies[0]; if(!tb)return;
    ths.forEach(h=>h.classList.remove('asc','desc'));
    th.classList.add('desc');
    Array.from(tb.rows).sort((a,b)=>{
      const ai=th.cellIndex;
      const av=parseFloat((a.cells[ai]?.textContent||'').replace(/[+%,]/g,''));
      const bv=parseFloat((b.cells[ai]?.textContent||'').replace(/[+%,]/g,''));
      if(!isNaN(av)&&!isNaN(bv))return bv-av;
      return 0;
    }).forEach(r=>tb.appendChild(r));
  });
});

window.addEventListener('scroll', _tvHide, {passive:true});
window.addEventListener('resize', _tvHide, {passive:true});
"""


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN BUILD FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def _build_screener_tab():
    """Screener tab — 23 screens in 4 categories, all JS-side against tbl-stocks."""
    q = "'"
    def card(key, icon, name, desc, cat):
        return (
            f'<div class="scr-card" onclick="runScreen(this,{q}{key}{q})" data-cat="{cat}">'
            f'<div class="scr-icon">{icon}</div>'
            f'<div class="scr-name">{name}</div>'
            f'<div class="scr-desc">{desc}</div></div>'
        )

    cat_btns = (
        "<button class=\"scr-cat-btn active\" onclick=\"filterScreenCat(this,'all')\">All</button>"
        "<button class=\"scr-cat-btn\" onclick=\"filterScreenCat(this,'signal')\">🎯 Signal</button>"
        "<button class=\"scr-cat-btn\" onclick=\"filterScreenCat(this,'fundamental')\">💰 Fundamental</button>"
        "<button class=\"scr-cat-btn\" onclick=\"filterScreenCat(this,'trend')\">📊 Trend &amp; Chart</button>"
        "<button class=\"scr-cat-btn\" onclick=\"filterScreenCat(this,'sector')\">🏭 Sector</button>"
    )

    sig = (
        card("rs30_buy",     "🟢", "RS30 Buy",          "RS30=Buy · RS_22d&gt;0 · Sales_QoQ&gt;15 · PAT_QoQ&gt;15", "signal") +
        card("mst_buy",      "📈", "MST Swing Buy",     "MST_Signal=Buy · Trend Bullish · RSI&gt;50", "signal") +
        card("lst_buy",      "🚀", "LST Long Buy",      "LST_Signal=Buy · SMA≥3 · RS_55d&gt;0", "signal") +
        card("prime",        "🌟", "Prime Setups",      "Signal=Prime/Triple · Sector-gated ✓ · SMA=4", "signal") +
        card("enhanced_buy", "✅",     "Enhanced Buy",      "Signal=Confirmed/Prime · Fin_Score≥4 · SMA≥3", "signal") +
        card("chart_vcp",    "📐", "VCP Pattern",       "Chart_Pattern contains VCP", "signal") +
        card("chart_pennant","🏳", "Pennant / Flag",    "Chart_Pattern: Pennant or Bull Flag", "signal") +
        card("chart_hs",     "🔄", "Inv H&amp;S",       "Chart_Pattern: Inverse Head &amp; Shoulders", "signal")
    )
    fund = (
        card("low_pe",        "💲", "Low P/E",           "P/E between 1–15 · PAT_YoY&gt;0", "fundamental") +
        card("low_de",        "🛡", "Low Debt (D/E)",    "D/E &lt; 0.3 · ROE &gt; 10", "fundamental") +
        card("high_roe",      "🏆", "High ROE",          "ROE &gt; 20 · D/E &lt; 1 · PAT_YoY &gt; 10", "fundamental") +
        card("pat_qoq200",    "💥", "PAT QoQ 200%",      "PAT_QoQ &gt; 200%", "fundamental") +
        card("pat_yoy200",    "💥", "PAT YoY 200%",      "PAT_YoY &gt; 200%", "fundamental") +
        card("sales_qoq200",  "📦", "Sales QoQ 200%",    "Sales_QoQ &gt; 200%", "fundamental") +
        card("sales_yoy200",  "📦", "Sales YoY 200%",    "Sales_YoY &gt; 200%", "fundamental") +
        card("high_eps",      "💰", "High EPS",          "EPS &gt; 10 · SMA≥2", "fundamental") +
        card("quality_growth","💎", "Quality + Growth",  "ROE&gt;15 · PAT_YoY&gt;15 · Sales_YoY&gt;10 · D/E&lt;1", "fundamental")
    )
    trend = (
        card("near52high",  "📈", "Near 52-Week High",  "Within 8% of 52W high · RS_22d&gt;0", "trend") +
        card("above200sma", "🟢", "Above 200 SMA",      "SMA_Score=4 (above all 4 SMAs)", "trend") +
        card("golden_cross","✨",     "Golden Cross Zone",  "Trend=Bullish · SMA=4 · RS_22d&gt;5", "trend") +
        card("vol_spike",   "🔥", "Volume Spike",       "Rel_Vol ≥ 3 · Signal not Avoid", "trend") +
        card("rsi_pullback","📉", "RSI Pullback Buy",   "RSI 35–50 · RS_22d&gt;0 · Trend Bullish", "trend") +
        card("momentum",    "🏁", "Momentum Leaders",   "Prime/Confirmed · RS_22d&gt;5 · SMA≥3 · RSI&gt;55", "trend")
    )
    sec = (
        card("sector_leader", "🎯", "Sector Leaders",      "Sec_Gated=✓ · RS_22d&gt;8 · RS_55d&gt;5 · SMA≥3", "sector") +
        card("rs_breakout",   "⚡",     "RS Breakout",         "RS_22d&gt;10 · RS_55d&gt;5 · Rel_Vol&gt;1.5 · Bullish", "sector") +
        card("dividend",      "💵", "Dividend + Stability","ROE&gt;12 · D/E&lt;0.5 · PAT_YoY&gt;5 · SMA≥2", "sector")
    )

    return (
        '<style>' +
        '.scr-cats{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;align-items:center;}' +
        '.scr-cat-btn{padding:8px 20px;border-radius:20px;border:2px solid var(--border);background:var(--bg2);color:var(--text2);cursor:pointer;font-size:13px;font-weight:700;transition:.15s;letter-spacing:.01em;}' +
        '.scr-cat-btn.active,.scr-cat-btn:hover{background:var(--accent);color:#fff;border-color:var(--accent);}' +
        '.scr-cat-label{font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin:14px 0 8px;border-left:3px solid var(--accent);padding-left:8px;}' +
        '</style>' +
        f'<p style="font-size:13px;color:var(--text2);margin-bottom:14px;">Click any screen to filter the <strong>All Stocks</strong> table. Click again to reset.</p>' +
        f'<div class="scr-cats">{cat_btns}</div>' +
        f'<div class="scr-cat-label" data-label="signal">🎯 Signal-Based</div>' +
        f'<div class="scr-grid">{sig}</div>' +
        f'<div class="scr-cat-label" data-label="fundamental">💰 Financial &amp; Value</div>' +
        f'<div class="scr-grid">{fund}</div>' +
        f'<div class="scr-cat-label" data-label="trend">📊 Trend &amp; Chart</div>' +
        f'<div class="scr-grid">{trend}</div>' +
        f'<div class="scr-cat-label" data-label="sector">🏭 Sector &amp; Composite</div>' +
        f'<div class="scr-grid">{sec}</div>' +
        '<div class="scr-status" id="scr-status" style="display:none">' +
        '  <span id="scr-status-text"></span>' +
        '  <button class="copy-btn sm" onclick="resetScreen()" style="margin-left:10px">✖ Reset</button>' +
        '  <button class="copy-btn sm" onclick="exportStocksTV(\'scr-result-tbl\')" style="margin-left:6px">📋 Copy TV</button>' +
        '  <button class="copy-btn sm" onclick="exportTableCSV(\'scr-result-tbl\')" style="margin-left:6px">⬇ CSV</button>' +
        '</div>' +
        '<div id="scr-result-wrap" style="display:none;margin-top:14px"></div>'
    )



# ─────────────────────────────────────────────────────────────────────────────
#  CHARTINK SCANS TAB  v1.0
#  Called from build_html_report() when scans_df is passed (India only).
#  scans_df columns: Scan_Group, Condition, Symbol, Company, Sector,
#                    Price, Chg_1D%, Signal_Label, RS_22d_Idx%, RSI_14,
#                    From_52W_High%, Rel_Vol, SMA_Score
# ─────────────────────────────────────────────────────────────────────────────

def _build_scans_tab(scans_df):
    if scans_df is None or scans_df.empty:
        return '<p class="empty">No Chartink scan data available.</p>'

    # ── Prefix → (Category label, sort-order) ─────────────────────────────
    _PREFIX = [
        ("BO_",  "📈 Breakout",   0),
        ("VOL_", "📊 Volume",     1),
        ("LT_",  "🔭 Long Setup", 2),
        ("MOM_", "⚡ Momentum",   3),
        ("CAN_", "🕯 Candle",     4),
        ("INT_", "⏱ Intraday",   5),
        ("BR_",  "🔻 Bearish",    6),
        ("",     "⬜ Other",      99),   # fallback — must be last
    ]

    def _parse(cname):
        """Return (category_label, sort_order, display_name) from a condition filename."""
        cu = cname.upper()
        for pfx, lbl, order in _PREFIX:
            if pfx and cu.startswith(pfx):
                display = cname[len(pfx):].replace("_", " ").strip()
                return lbl, order, display
        # no prefix match → clean up underscores
        return "⬜ Other", 99, cname.replace("_", " ").strip()

    # ── Columns to show ────────────────────────────────────────────────────
    SCAN_SHOW = [
        "Symbol", "Company", "Sector", "Price", "Chg_1D%",
        "Signal_Label", "RS_22d_Idx%", "RSI_14",
        "From_52W_High%", "Rel_Vol", "SMA_Score",
        "Sec_Gated", "Sec_Index",
    ]
    COL_LABELS = {
        "Symbol": "Symbol", "Company": "Company", "Sector": "Sector",
        "Price": "Price", "Chg_1D%": "Chg%", "Signal_Label": "Signal",
        "RS_22d_Idx%": "RS 22d%", "RSI_14": "RSI",
        "From_52W_High%": "52W Hi%", "Rel_Vol": "Rel Vol", "SMA_Score": "SMA",
        "Sec_Gated": "Sec✓", "Sec_Index": "Sec Idx",
    }
    cols = [c for c in SCAN_SHOW if c in scans_df.columns]

    # ── CSS (scoped to .sc- prefix — no clash with existing styles) ────────
    css = """<style>
.sc-meta{font-size:11px;color:var(--text3,#6b7280);margin-bottom:8px}
.sc-pills{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;align-items:center}
.sc-pill{padding:8px 22px;border-radius:20px;font-size:13px;font-weight:700;
  border:2px solid var(--border);background:var(--bg3);
  color:var(--text2);cursor:pointer;transition:.15s;letter-spacing:.01em}
.sc-pill.sc-on{background:var(--accent);color:#fff;border-color:var(--accent)}
.sc-pill[data-grp="Investment"]{border-color:#4fc3f7;color:#4fc3f7}
.sc-pill[data-grp="Investment"].sc-on{background:#4fc3f7;color:#0f1117}
.sc-pill[data-grp="Trading"]{border-color:#ffb74d;color:#ffb74d}
.sc-pill[data-grp="Trading"].sc-on{background:#ffb74d;color:#0f1117}
.sc-pill[data-grp="SwingTrade"]{border-color:#a5d6a7;color:#a5d6a7}
.sc-pill[data-grp="SwingTrade"].sc-on{background:#a5d6a7;color:#0f1117}
.sc-pane{display:none}
.sc-pane.sc-vis{display:block}
.sc-cat-hdr{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.07em;color:var(--text3);
  display:flex;align-items:center;gap:6px;margin:12px 0 5px}
.sc-cat-hdr::after{content:'';flex:1;height:1px;background:var(--border)}
.sc-cds{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:4px}
.sc-cd{padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600;
  border:1px solid var(--border);background:var(--bg3);
  color:var(--text);cursor:pointer;transition:.15s;white-space:nowrap}
.sc-cd:hover{border-color:var(--accent);color:var(--accent)}
.sc-cd.sc-active{border-color:var(--accent);color:var(--accent);
  background:rgba(79,195,247,.1);font-weight:700}
.sc-cnt-badge{font-size:9px;color:var(--text3,#6b7280);margin-left:3px}
.sc-tbl-hdr{display:flex;align-items:baseline;gap:10px;
  margin:14px 0 6px;padding-bottom:6px;
  border-bottom:1px solid var(--border)}
.sc-tbl-title{font-size:13px;font-weight:700;color:var(--text)}
.sc-tbl-sub{font-size:11px;color:var(--text3)}
.sc-row-hidden{display:none!important}
</style>"""

    # ── JS ─────────────────────────────────────────────────────────────────
    js = """<script>
function _scShowGrp(grp){
  document.querySelectorAll('.sc-pill').forEach(function(b){
    b.classList.toggle('sc-on',b.dataset.grp===grp);
  });
  document.querySelectorAll('.sc-pane').forEach(function(p){
    p.classList.toggle('sc-vis',p.id==='sc-pane-'+grp);
  });
}
function _scFilter(grp,cond,dispName){
  var pane=document.getElementById('sc-pane-'+grp);
  if(!pane)return;
  pane.querySelectorAll('.sc-cd').forEach(function(b){
    b.classList.toggle('sc-active',b.dataset.cond===cond);
  });
  var tbl=document.getElementById('sc-tbl-'+grp);
  var vis=0;
  if(tbl){
    tbl.querySelectorAll('tr.sc-row').forEach(function(r){
      var show=(r.dataset.cond===cond);
      r.classList.toggle('sc-row-hidden',!show);
      if(show)vis++;
    });
  }
  var ti=document.getElementById('sc-ti-'+grp);
  if(ti)ti.textContent=dispName;
  var ts=document.getElementById('sc-ts-'+grp);
  if(ts)ts.textContent=vis+' stocks';
  var rc=document.getElementById('sc-rc-'+grp);
  if(rc)rc.textContent=vis+' rows';
}
function _scResetFilter(grp){
  var tbl=document.getElementById('sc-tbl-'+grp);
  if(!tbl)return;
  var vis=0;
  tbl.querySelectorAll('tr.sc-row').forEach(function(r){
    r.classList.remove('sc-row-hidden');
    vis++;
  });
  var pane=document.getElementById('sc-pane-'+grp);
  if(pane)pane.querySelectorAll('.sc-cd').forEach(function(b){b.classList.remove('sc-active');});
  var ti=document.getElementById('sc-ti-'+grp);
  if(ti)ti.textContent='All Conditions';
  var ts=document.getElementById('sc-ts-'+grp);
  if(ts)ts.textContent=vis+' stocks';
  var rc=document.getElementById('sc-rc-'+grp);
  if(rc)rc.textContent=vis+' rows';
}
</script>"""

    # ── Build scan-group pills + panes ─────────────────────────────────────
    from collections import defaultdict
    import html as _hl

    groups = list(dict.fromkeys(scans_df["Scan_Group"].dropna().tolist()))
    GRP_ICON = {"Investment": "📈", "Trading": "⚡", "SwingTrade": "🌊"}

    pills_html = ""
    panes_html = ""

    for gi, grp in enumerate(groups):
        icon = GRP_ICON.get(grp, "📋")
        pills_html += (
            f'<button class="sc-pill{" sc-on" if gi==0 else ""}" '
            f'data-grp="{grp}" onclick="_scShowGrp(\'{grp}\')">{icon} {grp}</button>'
        )

    for gi, grp in enumerate(groups):
        grp_df = scans_df[scans_df["Scan_Group"] == grp].copy()
        cond_names = list(dict.fromkeys(grp_df["Condition"].dropna().tolist()))

        # Parse each condition → meta
        # If a "Category" column exists (subfolder mode), use it directly.
        # Otherwise fall back to _parse() prefix detection.
        has_category_col = "Category" in grp_df.columns
        cond_meta = {}   # cname → (cat_lbl, cat_order, disp_name, count)
        for i, cn in enumerate(cond_names):
            if has_category_col:
                # Get the category from the first row matching this condition
                _row = grp_df[grp_df["Condition"] == cn]
                _cat_val = _row["Category"].iloc[0] if not _row.empty else None
                if _cat_val and str(_cat_val).strip() and str(_cat_val) != "nan":
                    lbl   = str(_cat_val).strip()
                    order = i   # preserve folder/file order
                    disp  = cn.replace("_", " ").strip()
                else:
                    lbl, order, disp = _parse(cn)
            else:
                lbl, order, disp = _parse(cn)
            cnt = int((grp_df["Condition"] == cn).sum())
            cond_meta[cn] = (lbl, order, disp, cnt)

        # Group by category — use (order, lbl) key so subfolder order is stable
        cat_buckets = defaultdict(list)
        _seen_cat_order = {}
        for cn, (lbl, order, disp, cnt) in cond_meta.items():
            # normalise: same label → same sort key (take first seen order)
            key_order = _seen_cat_order.setdefault(lbl, order)
            cat_buckets[(key_order, lbl)].append((cn, disp, cnt))

        # Build condition cards
        first_cond = cond_names[0] if cond_names else ""
        first_disp = cond_meta[first_cond][2] if first_cond in cond_meta else first_cond
        first_cnt  = cond_meta[first_cond][3] if first_cond in cond_meta else 0

        cards_html = ""
        for (_, cat_lbl), conds in sorted(cat_buckets.items()):
            cards_html += f'<div class="sc-cat-hdr">{cat_lbl}</div><div class="sc-cds">'
            for cn, disp, cnt in sorted(conds, key=lambda x: x[1]):
                active = " sc-active" if cn == first_cond else ""
                cards_html += (
                    f'<button class="sc-cd{active}" data-cond="{_hl.escape(cn)}" '
                    f'onclick="_scFilter(\'{grp}\',\'{_hl.escape(cn)}\',\'{_hl.escape(disp)}\' )">'
                    f'{_hl.escape(disp)}'
                    f'<span class="sc-cnt-badge">{cnt}</span></button>'
                )
            cards_html += '</div>'

        # Build table header row
        ths = "".join(
            f'<th style="text-align:{"left" if c.lower() in _LEFT_COLS else "center"}">'
            f'{COL_LABELS.get(c,c)}</th>'
            for c in cols
        )

        # Build table rows
        rows_html = ""
        for _, row in grp_df.iterrows():
            cond    = str(row.get("Condition", ""))
            hidden  = "" if cond == first_cond else " sc-row-hidden"
            tds     = ""
            for c in cols:
                val   = row.get(c, "")
                align = "left" if c.lower() in _LEFT_COLS else "center"
                if c == "Symbol":
                    display = _tv_link(str(val), "INDIA")
                    cls     = ""
                elif c == "Signal_Label":
                    scls    = _signal_class(val)
                    display = f'<span class="{scls}">{_fmt(val)}</span>' if scls else _fmt(val)
                    cls     = ""
                else:
                    cls     = _cell_class(c, val, no_bg=True)
                    display = _fmt(val)
                ca = f' class="{cls}"' if cls else ""
                tds += f'<td{ca} style="text-align:{align}">{display}</td>'
            rows_html += (
                f'<tr class="sc-row{hidden}" data-cond="{_hl.escape(cond)}">{tds}</tr>'
            )

        tbl_html = (
            f'<div class="sc-tbl-hdr">'
            f'<span class="sc-tbl-title" id="sc-ti-{grp}">{_hl.escape(first_disp)}</span>'
            f'<span class="sc-tbl-sub" id="sc-ts-{grp}">{first_cnt} stocks</span>'
            f'<button class="copy-btn sm" onclick="_scResetFilter(\'{grp}\')" style="margin-left:10px">✖ Reset</button>'
            f'<button class="copy-btn sm" onclick="exportStocksTV(\'sc-tbl-{grp}\')" style="margin-left:6px">📋 Copy TV</button>'
            f'<button class="copy-btn sm" onclick="exportTableCSV(\'sc-tbl-{grp}\')" style="margin-left:6px">⬇ CSV</button>'
            f'</div>'
            f'<div class="tbl-wrap">'
            f'<table class="data-tbl" id="sc-tbl-{grp}">'
            f'<thead><tr>{ths}</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table></div>'
            f'<p class="row-count" id="sc-rc-{grp}">{first_cnt} rows</p>'
        )

        vis = " sc-vis" if gi == 0 else ""
        panes_html += (
            f'<div class="sc-pane{vis}" id="sc-pane-{grp}">'
            f'{cards_html}{tbl_html}</div>'
        )

    total_stocks = len(scans_df)
    total_conds  = scans_df["Condition"].nunique()
    run_ts       = datetime.now().strftime("%d %b %Y  %H:%M")

    return (
        css
        + f'<p class="sc-meta">Chartink live scans &nbsp;·&nbsp; '
          f'{total_stocks} total stocks &nbsp;·&nbsp; '
          f'{total_conds} conditions &nbsp;·&nbsp; {run_ts}</p>'
        + f'<div class="sc-pills">{pills_html}</div>'
        + panes_html
        + js
    )


def build_html_report(
    market, snapshot_df, sector_str_df, sector_rot_df, industry_rot_df,
    breadth_df, sector_perf_df, stock_str_df, top_buy_df, top_sell_df,
    chart_pat_df, trade_df, dashboard_df, sleeve_df,
    country_etf_df, commodity_df,
    output_path, run_time="", primary_rs=55,
    show_stats_bar=False,   # v6.3: False for individual market pages; True for index
    scans_df=None,         # India only: Chartink scans DataFrame → adds 📡 Scans tab
    enable_sector_strength=None,  # None = use module-level ENABLE_SECTOR_STRENGTH constant
    rrg_section=None,       # Optional RRG HTML snippet → adds 📡 RRG tab after Sectors
):
    run_time = run_time or datetime.now().strftime("%d %b %Y  %H:%M")
    global _CUR_MKT
    _CUR_MKT = market
    # ── Scans tab content built HERE so it's ready before tabs list & sections_html ──
    scans_content = (
        _build_scans_tab(scans_df)
        if (scans_df is not None and hasattr(scans_df, 'empty') and not scans_df.empty)
        else None
    )

    # Signal counts
    sl_col = "Signal_Label" if (stock_str_df is not None and not stock_str_df.empty
                                  and "Signal_Label" in stock_str_df.columns) else None
    at_col = "Action_Tier"  if (stock_str_df is not None and not stock_str_df.empty
                                  and "Action_Tier"  in stock_str_df.columns) else None
    def _cnt(e, av):
        if sl_col: return int(stock_str_df[sl_col].astype(str).str.startswith(e).sum())
        if at_col: return int((stock_str_df[at_col]==av).sum())
        return 0
    prime=_cnt("🌟","PRIME BUY"); conf=_cnt("✅","CONFIRMED BUY")
    rsbuy=_cnt("📈","RS BUY");    avoid=_cnt("🔴","AVOID")

    # Simplified stock view — #2: Sector moved after Trend, Industry added beside it
    MAIN_COLS = ["Symbol","Company","Price","Chg_1D%",
                 "Signal_Label","Sec_Gated","RS_22d_Idx%","RS_55d_Idx%",
                 "RSI_14","Trend","Sector","Industry","SMA_Score","Total_Score","Fin_Score",
                 "From_52W_High%","Rel_Vol",
                 "SL_Buy%","SL_Grade","SL_Buy_Price",
                 "Sales_QoQ%","Sales_YoY%","PAT_QoQ%","PAT_YoY%",
                 "ROE%","D/E","P/E","EPS","Mkt_Cap_B","Chart_Pattern",
                 "MST_Signal","LST_Signal","RS30_Signal"]
    if stock_str_df is not None and not stock_str_df.empty:
        stock_main = stock_str_df[[c for c in MAIN_COLS if c in stock_str_df.columns]]
    else:
        stock_main = stock_str_df

    # ── Tab definitions ────────────────────────────────────────────────────────
    tabs = [
        ("market",        "📸 Market"),
        ("sectors",       "🏭 Sectors"),
        *([("rrg",        "📡 RRG")]     if rrg_section else []),
        ("opportunities", "🎯 Opportunities"),
        ("stocks",        "📊 Stocks"),
        *([("scans", "📡 Scans")] if scans_content else []),
        ("screener",      "🔎 Screener"),
        ("patterns",      "📐 Patterns"),
        ("global",        "🌍 Global"),
        ("sleeves",       "📋 Sleeves"),
        ("guide",         "📚 Guide"),
        ("dashboard",     "📋 Dashboard"),
    ]
    tab_btns = "".join(
        (f'<button class="tab-btn" data-tab="{tid}" '
         f'onclick="showTab(\'{tid}\'){";rrgInit()" if tid=="rrg" else ""}">{lbl}</button>')
        for tid, lbl in tabs
    )

    def _sec(tid, title, content):
        return (f'<div class="tab-content" id="tab-{tid}">'
                f'<h2 class="sec-title">{title}</h2>{content}</div>')

    def _toggle(sid, default="cards"):
        return (f'<div class="view-toggle" id="{sid}">'
                f'<button class="vt-btn {"active" if default=="cards" else ""}" '
                f'data-mode="cards" onclick="toggleView(\'{sid}\',\'cards\')">Cards</button>'
                f'<button class="vt-btn {"active" if default=="table" else ""}" '
                f'data-mode="table" onclick="toggleView(\'{sid}\',\'table\')">Table</button>'
                f'</div>')

    # ── Tab content ────────────────────────────────────────────────────────────

    market_content = (
        _build_health_card(stock_str_df, sector_str_df, market) +
        '<h2 class="sec-title">Market Snapshot</h2>' +
        _build_snap_cards(snapshot_df) +
        '<h2 class="sec-title">Market Breadth</h2>' +
        _build_table(breadth_df, "tbl-breadth", searchable=False, pct_mode="breadth")
    )

    _show_str = ENABLE_SECTOR_STRENGTH if enable_sector_strength is None else enable_sector_strength
    _sector_strength_block = (
        '<h2 class="sec-title">Sector Strength</h2>'
        '<p class="sec-subtitle">ETF-based — each sector ETF\'s relative performance vs the benchmark index.</p>' +
        _build_sector_bars(sector_str_df)
    ) if _show_str else ""
    sector_content = (
        _sector_strength_block +
        '<h2 class="sec-title">Sector Performance</h2>'
        '<p class="sec-subtitle">Absolute and relative returns for each sector ETF over multiple time periods.</p>' +
        _build_table(sector_perf_df, "tbl-secperf", searchable=False) +
        '<h2 class="sec-title">Sector Rotation</h2>'
        '<p class="sec-subtitle">Breadth-based — percentage of individual stocks per sector above key technical levels (RS, RSI, SMA).</p>' +
        _build_table(sector_rot_df, "tbl-secrot", pct_mode="breadth") +
        '<h2 class="sec-title">Industry Rotation</h2>'
        '<p class="sec-subtitle">Breadth-based — same metrics broken down by industry within each sector.</p>' +
        _build_table(industry_rot_df, "tbl-indrot", pct_mode="breadth")
    )

    opp_cards  = _build_opportunity_cards(top_buy_df)
    # #1: both tables share one leading column layout (sector context first, then stock)
    _sec_rs_col = f"Sec_RS{primary_rs}d%"
    _opp_lead = ["Sec_Rank", "Sector", "Sec_Signal", "Rank", "Symbol", "Company",
                 "Price", "Chg_1D%", _sec_rs_col, "RS_22d_Idx%"]
    opp_table  = _build_table(_reorder_leading(top_buy_df,  _opp_lead), "tbl-opp-table", no_bg=True, groups=True)
    sell_table = _build_table(_reorder_leading(top_sell_df, _opp_lead), "tbl-sell",      no_bg=True, groups=True)
    opp_content = (
        _toggle("vt-opp", "table") +
        _OPP_PANEL +
        f'<div id="vt-opp-cards" style="display:none">{opp_cards}</div>' +
        f'<div id="vt-opp-table">{opp_table}</div>' +
        '<h2 class="sec-title">🔴 Sell Alerts</h2>' + sell_table
    )

    _sector_opts = ""
    if stock_main is not None and not stock_main.empty and "Sector" in stock_main.columns:
        _sectors = sorted(stock_main["Sector"].dropna().unique().tolist())
        _sector_opts = "".join(f'<option value="{s}">{s}</option>' for s in _sectors)
    _pattern_opts = ""
    if stock_main is not None and not stock_main.empty and "Chart_Pattern" in stock_main.columns:
        _patterns = sorted(stock_main["Chart_Pattern"].dropna().unique().tolist())
        _pattern_opts = "".join(f'<option value="{p}">{p}</option>' for p in _patterns if str(p).strip())
    _stock_toolbar = f'''
<div class="stock-toolbar">
  <div class="stock-toolbar-left">
    <select id="sector-filter" class="sector-sel" onchange="filterBySector(this.value,'tbl-stocks')" title="Filter by sector">
      <option value="">All Sectors</option>
      {_sector_opts}
    </select>
    <select id="signal-filter" class="sector-sel" onchange="filterBySignal(this.value,'tbl-stocks')" title="Filter by signal">
      <option value="">All Signals</option>
      <option value="Triple">🌟 Triple Confirmed</option>
      <option value="RS30">🌟 RS30 Leader / Swing</option>
      <option value="Long Momentum">✅ Long Momentum</option>
      <option value="Strong RS">✅ Strong RS</option>
      <option value="RS Leader">📈 RS Leader</option>
      <option value="Watch">👁 Watch / Building</option>
      <option value="Neutral">⬜ Neutral</option>
      <option value="Breakdown">🔴 RS Breakdown</option>
    </select>
    <select id="trend-filter" class="sector-sel" onchange="setDropFilter('tbl-stocks','trend',this.value,'contains')" title="Filter by trend">
      <option value="">Trend: All</option>
      <option value="Strong Bullish">💚 Strong Bullish</option>
      <option value="Bullish">📈 Bullish</option>
      <option value="Neutral">➡ Neutral</option>
      <option value="Bearish">📉 Bearish</option>
      <option value="Strong Bearish">🔴 Strong Bearish</option>
    </select>
    <select id="secgated-filter" class="sector-sel" onchange="setDropFilter('tbl-stocks','sec_gated',this.value,'contains')" title="Sector-gated pass/fail">
      <option value="">Sec Gated: All</option>
      <option value="✓">✓ Pass</option>
      <option value="✗">✗ Fail</option>
    </select>
    <select id="sma-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','sma_score','','');}}else{{var p=v.split(',');if(p.length===2){{setDropFilter('tbl-stocks','sma_score',v,'range');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','sma_score',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','sma_score',v.slice(1),'lte');}}}}}})(this.value)" title="SMA Score: how many of 5 SMAs price is above (0=weakest)">
      <option value="">SMA: All</option>
      <option value="+4">SMA ≥ 4 (Strong)</option>
      <option value="+3">SMA ≥ 3</option>
      <option value="-2">SMA ≤ 2 (Weak)</option>
      <option value="-1">SMA ≤ 1 (Very Weak)</option>
    </select>
    <select id="rs22-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','rs_22d_idx%','','');}}else{{var p=v.split(',');if(p.length===2){{setDropFilter('tbl-stocks','rs_22d_idx%',v,'range');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','rs_22d_idx%',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','rs_22d_idx%',v.slice(1),'lte');}}}}}})(this.value)" title="22-day Relative Strength vs Index">
      <option value="">RS 22d: All</option>
      <option value="+10">RS ≥ +10%</option>
      <option value="+5">RS ≥ +5%</option>
      <option value="+0">RS ≥ 0% (Outperforming)</option>
      <option value="-0.01">RS &lt; 0% (Underperforming)</option>
    </select>
    <select id="pattern-filter" class="sector-sel" onchange="setDropFilter('tbl-stocks','chart_pattern',this.value,'contains')" title="Filter by chart pattern">
      <option value="">Pattern: All</option>
      {_pattern_opts}
    </select>
    <select id="slgrade-filter" class="sector-sel" onchange="setDropFilter('tbl-stocks','sl_grade',this.value,'contains')" title="Stop-Loss Grade: A=tightest risk, F=widest">
      <option value="">SL Grade: All</option>
      <option value="A">A (Tightest)</option>
      <option value="B">B</option>
      <option value="C">C</option>
      <option value="D">D</option>
      <option value="F">F (Widest)</option>
    </select>
    <select id="finscore-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','fin_score','','');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','fin_score',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','fin_score',v.slice(1),'lte');}}}})(this.value)" title="Fundamental score (0–10)">
      <option value="">Fin Score: All</option>
      <option value="+7">≥ 7 (Strong)</option>
      <option value="+5">≥ 5</option>
      <option value="+3">≥ 3</option>
      <option value="-2">≤ 2 (Weak)</option>
    </select>
    <select id="salesqoq-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','sales_qoq%','','');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','sales_qoq%',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','sales_qoq%',v.slice(1),'lte');}}}})(this.value)" title="Sales growth quarter-on-quarter">
      <option value="">Sales QoQ: All</option>
      <option value="+20">≥ +20%</option>
      <option value="+10">≥ +10%</option>
      <option value="+0">≥ 0% (Growing)</option>
      <option value="-0.01">&lt; 0% (Declining)</option>
    </select>
    <select id="patqoq-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','pat_qoq%','','');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','pat_qoq%',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','pat_qoq%',v.slice(1),'lte');}}}})(this.value)" title="Profit after tax growth quarter-on-quarter">
      <option value="">PAT QoQ: All</option>
      <option value="+20">≥ +20%</option>
      <option value="+10">≥ +10%</option>
      <option value="+0">≥ 0% (Growing)</option>
      <option value="-0.01">&lt; 0% (Declining)</option>
    </select>
    <select id="roe-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','roe%','','');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','roe%',v.slice(1),'gte');}}else{{setDropFilter('tbl-stocks','roe%',v.slice(1),'lte');}}}})(this.value)" title="Return on Equity %">
      <option value="">ROE: All</option>
      <option value="+20">≥ 20% (Excellent)</option>
      <option value="+15">≥ 15%</option>
      <option value="+10">≥ 10%</option>
      <option value="-0.01">&lt; 0% (Negative)</option>
    </select>
    <select id="de-filter" class="sector-sel" onchange="(function(v){{if(!v){{setDropFilter('tbl-stocks','d_e','','');}}else if(v[0]==='+'){{setDropFilter('tbl-stocks','d_e',v.slice(1),'lte');}}else{{setDropFilter('tbl-stocks','d_e',v.slice(1),'gte');}}}})(this.value)" title="Debt-to-Equity ratio (lower = less debt)">
      <option value="">D/E: All</option>
      <option value="+0.5">≤ 0.5 (Low Debt)</option>
      <option value="+1">≤ 1</option>
      <option value="+2">≤ 2</option>
      <option value="-2.01">≥ 2 (High Debt)</option>
    </select>
  </div>
  <div class="stock-toolbar-right">
    <button class="copy-btn sm" onclick="resetStockFilters()" title="Clear all filters">✕ Reset</button>
    <button class="copy-btn sm" onclick="exportStocksTV('tbl-stocks')" title="Copy symbols for TradingView" style="display:none">📋 Copy TV</button>
    <button class="copy-btn sm" onclick="exportTableCSV('tbl-stocks')" title="Download CSV" style="display:none">⬇ CSV</button>
  </div>
</div>'''
    stock_content = _STOCK_PANEL + _stock_toolbar + _build_table(
        stock_main, "tbl-stocks", max_rows=500, no_bg=True, groups=True)

    # ── Patterns: enforce a hard recency cap (request #8). Keep only setups
    #    whose Date is within the last PATTERN_RECENT_DAYS days. Rows without a
    #    parseable date (e.g. the "no patterns" placeholder) are kept.
    chart_pat_recent = chart_pat_df
    if (chart_pat_df is not None and not chart_pat_df.empty
            and "Date" in chart_pat_df.columns):
        _d = pd.to_datetime(chart_pat_df["Date"], errors="coerce")
        _cutoff = pd.Timestamp(datetime.now().date()) - timedelta(days=PATTERN_RECENT_DAYS)
        chart_pat_recent = chart_pat_df[_d.isna() | (_d >= _cutoff)]

    patterns_content = (
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px;">'
        f'🗓 Showing only setups from the last {PATTERN_RECENT_DAYS} days. '
        'Quality-filtered: only setups that pass a trend + momentum + R:R gate are shown '
        '(★ = quality score). Sorted: Weekly → Bullish → Quality → Most recent.</p>' +
        _build_table(chart_pat_recent, "tbl-patterns", no_bg=True)
    )

    # Global ETF/commodity tickers are US-listed → link the "ETF" column with
    # market="US" so they aren't prefixed with the page's home exchange (#5).
    global_content = (
        '<h2 class="sec-title">🌍 Country ETFs (RS vs SPY)</h2>' +
        _build_table(_reorder_leading(country_etf_df, ["Country"]), "tbl-etfs", no_bg=True,
                     link_cols=("etf",), link_market="US", groups=True) +
        '<h2 class="sec-title">🏅 Commodities (RS vs GLD)</h2>' +
        _build_table(_reorder_leading(commodity_df, ["Commodity"]), "tbl-commod", no_bg=True,
                     link_cols=("etf",), link_market="US", groups=True)
    )

    sleeves_content = _build_sleeve_tables(sleeve_df, market)
    guide_content   = _build_guide()
    dash_content    = _build_dashboard(dashboard_df)

    sections_html = (
        _sec("market",        "📸 Market Overview",            market_content) +
        _sec("sectors",       "🏭 Sector Analysis",            sector_content) +
        (f'<div class="tab-content" id="tab-rrg">{rrg_section}</div>' if rrg_section else "") +
        _sec("opportunities", "🎯 Opportunities",              opp_content) +
        _sec("stocks",        "📊 All Stocks",                 stock_content) +
        (_sec("scans", "📡 India Scans", scans_content) if scans_content else "") +
        _sec("screener",      "🔎 Screener",                   _build_screener_tab()) +
        _sec("patterns",      "📐 Chart Patterns",             patterns_content) +
        _sec("global",        "🌍 Global Markets",             global_content) +
        _sec("sleeves",       "📋 RS Momentum Portfolios",     sleeves_content) +
        _sec("guide",         "📚 Signal Guide & Reference",   guide_content) +
        _sec("dashboard",     "📋 Run Summary & Methodology",  dash_content)
    )

    # ── Stats bar — built always (returned for index.html), shown conditionally ─
    stats_bar_html = (
        f'<div class="stats-bar">'
        f'<span class="sl-badge sl-triple">🌟 Prime {prime}</span>'
        f'<span class="sl-badge sl-confirmed">✅ Conf {conf}</span>'
        f'<span class="sl-badge sl-rsbuy">📈 RS {rsbuy}</span>'
        f'<span class="sl-badge sl-avoid">🔴 Avoid {avoid}</span>'
        f'</div>'
    )
    # Individual market pages: hide the stats bar (clutters the header).
    # Pass show_stats_bar=True when building an index/overview page.
    stats_bar_embed = stats_bar_html if show_stats_bar else ""

    # ── Country navigation: home link + dropdown to switch markets ──────────
    # Maps internal market code → (display name, flag, html filename)
    _COUNTRY_MAP = {
        # ── Original 9 ──
        "USA":       ("United States", "🇺🇸", "US.html"),
        "INDIA":     ("India",         "🇮🇳", "IN.html"),
        "UK":        ("United Kingdom","🇬🇧", "UK.html"),
        "CA":        ("Canada",        "🇨🇦", "CA.html"),
        "AU":        ("Australia",     "🇦🇺", "AU.html"),
        "DE":        ("Germany",       "🇩🇪", "DE.html"),
        "JP":        ("Japan",         "🇯🇵", "JP.html"),
        "FR":        ("France",        "🇫🇷", "FR.html"),
        "BR":        ("Brazil",        "🇧🇷", "BR.html"),
        # ── Batch 1: 8 countries (full-name HTML files) ──
        "CN":        ("China",         "🇨🇳", "CN.html"),
        "KR":        ("South Korea",   "🇰🇷", "KR.html"),
        "TW":        ("Taiwan",        "🇹🇼", "TW.html"),
        "CH":        ("Switzerland",   "🇨🇭", "CH.html"),
        "SA":        ("Saudi Arabia",  "🇸🇦", "SA.html"),
        "NL":        ("Netherlands",   "🇳🇱", "NL.html"),
        "ES":        ("Spain",         "🇪🇸", "ES.html"),
        "SE":        ("Sweden",        "🇸🇪", "SE.html"),
        # ── Batch 2: 11 countries (SHORT-CODE HTML files) ──
        "HK":        ("Hong Kong",     "🇭🇰", "HK.html"),
        "IT":        ("Italy",         "🇮🇹", "IT.html"),
        "SG":        ("Singapore",     "🇸🇬", "SG.html"),
        "ID":        ("Indonesia",     "🇮🇩", "ID.html"),
        "ZA":        ("South Africa",  "🇿🇦", "ZA.html"),
        "MX":        ("Mexico",        "🇲🇽", "MX.html"),
        "TH":        ("Thailand",      "🇹🇭", "TH.html"),
        "MY":        ("Malaysia",      "🇲🇾", "MY.html"),
        "AE":        ("UAE",           "🇦🇪", "AE.html"),
        "PL":        ("Poland",        "🇵🇱", "PL.html"),
        "TR":        ("Turkey",        "🇹🇷", "TR.html"),
    }
    _cur = str(market).upper()
    _opts = ['<option value="" disabled selected>🌍 Switch market…</option>']
    _opts.append('<option value="index.html">🏠 Home — All Markets</option>')
    for _code, (_nm, _flag, _file) in _COUNTRY_MAP.items():
        if _code == _cur:
            continue
        _opts.append(f'<option value="{_file}">{_flag} {_nm}</option>')
    country_nav = (
        f'<a href="index.html" class="home-link">🏠 All Markets</a>'
        f'<select class="country-nav-select" '
        f'onchange="if(this.value)window.location.href=this.value;">'
        + "".join(_opts) +
        f'</select>'
    )

    # ── Feedback form (Formspree) ────────────────────────────────────────────
    # To activate: create a free form at https://formspree.io and replace
    # FORMSPREE_ID below with your form ID (e.g. "xpwzjqkb").
    FORMSPREE_ID = "xpqeqokw"
    feedback_html = (
        '<div class="feedback-section" id="feedback">'
        '<h3 class="feedback-title">💬 Share Your Feedback</h3>'
        '<p class="feedback-sub">Found a bug? Have a suggestion? Tell us what would make TechnoFunda more useful for you.</p>'
        f'<form class="feedback-form" action="https://formspree.io/f/{FORMSPREE_ID}" method="POST">'
        '<div class="fb-row">'
        '<input type="text" name="name" placeholder="Your name (optional)" class="fb-input">'
        '<input type="email" name="email" placeholder="Email (optional — for reply)" class="fb-input">'
        '</div>'
        f'<input type="hidden" name="market" value="{market}">'
        '<textarea name="message" placeholder="Your feedback, idea, or question…" class="fb-textarea" required></textarea>'
        '<button type="submit" class="fb-btn">Send Feedback →</button>'
        '</form>'
        '</div>'
    )

    # ── Investment disclaimer footer (regulator-neutral, global) ────────────
    disclaimer_html = (
        '<div class="disclaimer-footer">'
        '<h4>⚠️ Important Disclaimer — Please Read</h4>'
        '<p><span class="df-brand">TechnoFunda</span> is an automated, educational '
        'market-analysis tool. All content on this page — including signals, scores, '
        'rankings, "Prime/Confirmed/RS" labels, trade setups and portfolio ideas — is '
        'provided for <strong>informational and educational purposes only</strong>, and '
        'must <strong>not</strong> be construed as investment advice, a research report, '
        'or a recommendation/solicitation to buy or sell any security.</p>'
        '<p>We are <strong>not</strong> registered with any financial regulator as an '
        'Investment Adviser or Research Analyst (including SEBI in India, the SEC/FINRA in '
        'the US, the FCA in the UK, or any equivalent authority in other jurisdictions). '
        'Nothing here is tailored to your personal financial situation, objectives, or '
        'risk tolerance.</p>'
        '<p><strong>Investments in securities markets are subject to market risks. '
        'Read all the related documents carefully before investing.</strong> Past '
        'performance is not indicative of future results. The data shown is sourced from '
        'third parties, may be delayed, inaccurate, or incomplete, and is presented '
        '"as is" without warranty of any kind.</p>'
        '<p>You are solely responsible for your own investment decisions. Always do your '
        'own research and consult a licensed, registered investment adviser or a qualified, '
        'licensed financial professional regulated in your own jurisdiction before making any investment '
        'decision. <span class="df-brand">TechnoFunda</span> and its creators accept no '
        'liability for any loss or damage arising from the use of this information.</p>'
        f'<p style="margin-top:12px;color:var(--text3);">© 2026 TechnoFunda · '
        f'[{market}] report generated {run_time} · Data delayed / end-of-day · '
        f'Not financial advice.</p>'
        '</div>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#0f1117">
  <title>TechnoFunda [{market}] — {run_time}</title>
  <style>{CSS}</style>
</head>
<body>
<header class="app-header">
  <div class="app-brand-row">
    <div>
      <div class="app-title">TechnoFunda [{market}]</div>
      <div class="app-meta" id="run-meta" data-utc="{run_time}">{run_time} · RS{primary_rs}d</div>
    </div>
    {country_nav}
  </div>
  <div class="hdr-controls">
    <button id="tv-preview-toggle" class="tv-on" onclick="_tvToggle()"
            title="Toggle TradingView chart preview on symbol hover">
      📈 Chart ON
    </button>
    <div class="ctrl-group">
      <label>Text</label>
      <button class="fs-btn" onclick="setFont(-1)" title="Smaller text">&minus;</button>
      <button class="fs-btn" onclick="setFont(1)" title="Larger text">+</button>
    </div>
    <div class="ctrl-group">
      <label>Theme</label>
      <select class="theme-select" id="theme-select" onchange="setTheme(this.value)">
        <option value="dark">🌙 Dark</option>
        <option value="light">☀️ Light</option>
        <option value="navy">🌊 Navy Trader</option>
      </select>
    </div>
  </div>
</header>

<nav class="tab-bar">{tab_btns}</nav>
<main>{sections_html}</main>
{feedback_html}
{stats_bar_embed}
<a href="#feedback" class="fb-float" title="Share feedback or suggestions">💬 Feedback</a>
<script>{JS}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    size_kb = os.path.getsize(output_path) // 1024
    print(f"  💾 HTML saved: {output_path}  ({size_kb} KB)")
