"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AUSTRALIA MARKET ANALYSIS — GOOGLE SHEETS EDITION  v1.0                  ║
║  market_au_gsht.py  — GitHub Actions compatible                           ║
║                                                                            ║
║  Universe  : au_asx300list.csv  (ASX 300 stocks, Yahoo suffix .AX)        ║
║  Benchmark : iShares Core S&P/ASX 200 ETF (IOZ.AX)                        ║
║  Sectors   : SPDR ASX sector ETFs                                          ║
║  Timezone  : AEST (ASX market close 16:00 AEST = 06:00 UTC)               ║
║  Sheet URL : GOOGLE_SHEET_URL_AU env var                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, warnings
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta, timezone
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import tenacity
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData")
else:
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "SupportFiles", "IndexData")

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "au_asx300list.csv")

MAX_STOCKS        = 300
PERIOD_DAYS       = 420
ENABLE_PATTERNS   = True
PATTERN_MAX       = 200
FETCH_FINANCIALS  = True
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 200
PRIMARY_RS_PERIOD = 22

CREDENTIALS_PATH = (
    os.environ.get("GOOGLE_CREDENTIALS_PATH")
    or os.path.join(SCRIPT_DIR, "google_credentials.json")
)
SHEET_URL = (
    os.environ.get("GOOGLE_SHEET_URL_AU")
    or "https://docs.google.com/spreadsheets/d/YOUR_AU_SHEET_ID/edit"
)
GSCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

sys.path.insert(0, SCRIPT_DIR)
_SUPPORT_DIR = os.path.join(SCRIPT_DIR, "SupportFiles")
if os.path.isdir(_SUPPORT_DIR) and _SUPPORT_DIR not in sys.path:
    sys.path.insert(0, _SUPPORT_DIR)
if os.path.isdir(os.path.join(_SUPPORT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(_SUPPORT_DIR, "IndexData")

from market_signals import build_dashboard_df
from market_engine import (
    RS_PERIODS, SIGNAL_PERIODS, fetch_close_batch, fetch_ohlcv_batch,
    fetch_ohlcv_with_cache, _normalize, calc_rs, calc_rsi,
    load_csv_constituents, build_market_snapshot, build_sector_strength,
    build_sector_rotation, build_industry_rotation, build_market_breadth,
    build_sector_performance, build_stock_strength, build_top_picks_buy,
    build_top_picks_sell, build_chart_patterns_df, build_trade_setups,
    run_pattern_detection, build_rs_sleeve_list,
    build_country_etf_df, build_commodity_df,
)
import market_engine as _me
try:
    from price_cache import CACHE_DIR as _CACHE_DIR
    _me.set_cache_dir(_CACHE_DIR)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
#  AUSTRALIA MARKET CONFIG
# ─────────────────────────────────────────────────────────────────────────────

AU_INDEX          = "IOZ.AX"    # iShares Core S&P/ASX 200 — clean EOD prices
AU_INDEX_FALLBACK = "^AXJO"     # S&P/ASX 200 fallback

# SPDR ASX sector ETFs
AU_SECTORS = {
    "Financials":       {"yahoo": "OZF.AX",  "csv": None},
    "Materials":        {"yahoo": "OZR.AX",  "csv": None},
    "Healthcare":       {"yahoo": "OZL.AX",  "csv": None},
    "Energy":           {"yahoo": "OZE.AX",  "csv": None},
    "Industrials":      {"yahoo": "OZA.AX",  "csv": None},
    "ConsumerDisc":     {"yahoo": "OZD.AX",  "csv": None},
    "Consumer Staples": {"yahoo": "OZS.AX",  "csv": None},
    "Technology":       {"yahoo": "OZT.AX",  "csv": None},
    "Utilities":        {"yahoo": "OZU.AX",  "csv": None},
    "CommServices":     {"yahoo": "OZC.AX",  "csv": None},
    "RealEstate":       {"yahoo": "SLF.AX",  "csv": None},
}

AU_INDUSTRY_TO_SECTOR = {
    "Financials": "Financials", "Banking": "Financials",
    "Insurance": "Financials", "Asset Management": "Financials",
    "Materials": "Materials", "Mining": "Materials",
    "Gold": "Materials", "Iron Ore": "Materials",
    "Metals": "Materials", "Steel": "Materials",
    "Healthcare": "Healthcare", "Pharmaceuticals": "Healthcare",
    "Biotechnology": "Healthcare", "Medical Devices": "Healthcare",
    "Energy": "Energy", "Oil & Gas": "Energy", "LNG": "Energy",
    "Industrials": "Industrials", "Infrastructure": "Industrials",
    "Engineering": "Industrials", "Transport": "Industrials",
    "ConsumerDisc": "ConsumerDisc", "Retail": "ConsumerDisc",
    "Automotive": "ConsumerDisc",
    "Consumer Staples": "Consumer Staples", "Food & Beverage": "Consumer Staples",
    "Supermarkets": "Consumer Staples",
    "Technology": "Technology", "Software": "Technology",
    "IT Services": "Technology", "Fintech": "Technology",
    "Utilities": "Utilities", "Power": "Utilities",
    "CommServices": "CommServices", "Telecoms": "CommServices",
    "Media": "CommServices",
    "RealEstate": "RealEstate", "REITs": "RealEstate",
    "Property": "RealEstate",
}

AU_BREADTH_INDICES = {
    "S&P/ASX 200":    {"yahoo": "^AXJO",  "csv": None},
    "S&P/ASX 300":    {"yahoo": "^AXSO",  "csv": "au_asx300list.csv"},
    "S&P/ASX Small":  {"yahoo": "^AXSO",  "csv": None},
}

AU_SNAPSHOT_TICKERS = [
    {"name": "S&P/ASX 200",       "ticker": "^AXJO",    "type": "Index"},
    {"name": "S&P/ASX 300",       "ticker": "^AXSO",    "type": "Index"},
    {"name": "S&P/ASX All Ords",  "ticker": "^AORD",    "type": "Index"},
    {"name": "iShares ASX 200",   "ticker": "IOZ.AX",   "type": "ETF"},
    {"name": "AUD/USD",           "ticker": "AUDUSD=X", "type": "Forex"},
    {"name": "AUD/JPY",           "ticker": "AUDJPY=X", "type": "Forex"},
    {"name": "DXY (USD Index)",   "ticker": "DX-Y.NYB", "type": "Forex"},
    {"name": "10Y Australia Bond","ticker": "^TNX",     "type": "Bond"},
    {"name": "Gold",              "ticker": "GC=F",     "type": "Commodity"},
    {"name": "Crude Oil WTI",     "ticker": "CL=F",     "type": "Commodity"},
    {"name": "Iron Ore",          "ticker": "TIO=F",    "type": "Commodity"},
    {"name": "Copper",            "ticker": "HG=F",     "type": "Commodity"},
    {"name": "Natural Gas",       "ticker": "NG=F",     "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS COLOUR PALETTE
# ─────────────────────────────────────────────────────────────────────────────
GS_COLORS = {
    "navy":       {"red": 0.051, "green": 0.129, "blue": 0.216},
    "teal":       {"red": 0.000, "green": 0.537, "blue": 0.482},
    "green":      {"red": 0.106, "green": 0.365, "blue": 0.165},
    "red":        {"red": 0.835, "green": 0.153, "blue": 0.157},
    "white":      {"red": 1.000, "green": 1.000, "blue": 1.000},
    "lt_green":   {"red": 0.784, "green": 0.902, "blue": 0.788},
    "lt_red":     {"red": 1.000, "green": 0.800, "blue": 0.800},
    "amber":      {"red": 1.000, "green": 0.973, "blue": 0.769},
    "lt_blue":    {"red": 0.878, "green": 0.937, "blue": 1.000},
    "sl_triple":  {"red": 0.051, "green": 0.169, "blue": 0.102},
    "sl_prime":   {"red": 0.082, "green": 0.251, "blue": 0.153},
    "sl_confirmed":{"red": 0.784, "green": 0.902, "blue": 0.788},
    "sl_rsbuy":   {"red": 0.910, "green": 0.961, "blue": 0.914},
    "sl_watch":   {"red": 1.000, "green": 0.973, "blue": 0.769},
    "sl_neutral": {"red": 0.957, "green": 0.957, "blue": 0.957},
    "sl_avoid":   {"red": 1.000, "green": 0.800, "blue": 0.800},
}

_SL_GS_MAP = {
    "🌟 Triple Confirmed": "sl_triple",  "🌟 RS30 + Long":   "sl_triple",
    "🌟 RS30 + Swing":     "sl_prime",   "🌟 RS30 Leader":   "sl_prime",
    "🌟 Long Momentum":    "sl_prime",   "🌟 Prime Setup":   "sl_prime",
    "✅ Long Momentum":    "sl_confirmed","✅ Strong RS":     "sl_confirmed",
    "📈 Swing Entry":      "sl_rsbuy",   "📈 RS Leader":     "sl_rsbuy",
    "👁 Setup Building":   "sl_watch",   "👁 RS30 Watch":    "sl_watch",
    "👁 LST Watch":        "sl_watch",   "👁 MST Watch":     "sl_watch",
    "👁 Watch":            "sl_watch",   "⬜ Neutral":       "sl_neutral",
    "🔴 RS Breakdown":     "sl_avoid",
}

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def gs_connect():
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(f"Credentials not found: {CREDENTIALS_PATH}")
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=GSCOPE)
    gc    = gspread.authorize(creds)
    ss    = gc.open_by_url(SHEET_URL)
    print(f"  ✅ Connected: '{ss.title}'")
    return ss

def _get_ws(ss, title, rows=3000, cols=60):
    try:    return ss.worksheet(title)
    except: return ss.add_worksheet(title=title, rows=rows, cols=cols)

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=5, max=120)
         + tenacity.wait_random(0, 3),
    stop=tenacity.stop_after_attempt(7),
    retry=tenacity.retry_if_exception_type(
        (gspread.exceptions.APIError, ConnectionError)),
    reraise=True,
)
def _api(fn, *args, **kwargs):
    return fn(*args, **kwargs)

def _cell_bg(val, col_name):
    col = str(col_name).lower()
    if col == "signal_label":
        key = _SL_GS_MAP.get(str(val or ""))
        return GS_COLORS.get(key) if key else None
    if col in ("signal","enhanced","action","sec_signal","rs_signal",
               "mst_signal","lst_signal","rs30_signal","supertrend",
               "supertrend_w","st_daily","st_week"):
        v = str(val or "")
        if v in ("Strong Buy","BUY","Buy"): return GS_COLORS["lt_green"]
        if v in ("Sell","SELL"):            return GS_COLORS["lt_red"]
        if v in ("Neutral","WAIT","NA"):    return GS_COLORS["amber"]
        if v == "Watch":                     return GS_COLORS["lt_blue"]
    if "trend" in col or "_zone" in col:
        v = str(val or "").lower()
        if "bullish" in v or "recovering" in v: return GS_COLORS["lt_green"]
        if "bearish" in v or "pulling"    in v: return GS_COLORS["lt_red"]
        if "neutral" in v or "mixed"      in v: return GS_COLORS["amber"]
    if col.startswith("abv_") or "beats" in col:
        if str(val) == "✓": return GS_COLORS["lt_green"]
        if str(val) == "✗": return GS_COLORS["lt_red"]
    if col == "sl_grade":
        return {"A": GS_COLORS["lt_green"],"B": GS_COLORS["lt_green"],
                "C": GS_COLORS["amber"],   "D": GS_COLORS["lt_red"],
                "F": GS_COLORS["lt_red"]}.get(str(val), None)
    pct_cols = {"chg_1d%","chg_5d%","rs_22d%","rs_55d%","rs_22d_idx%",
                "rs_55d_idx%","rs_score","total_score","1m%","3m%","6m%","12m%",
                "from_52w_high%","sales_qoq%","pat_qoq%","fin_score"}
    if col in pct_cols or col.endswith("%"):
        try:
            v = float(val or 0)
            if v > 0: return GS_COLORS["lt_green"]
            if v < 0: return GS_COLORS["lt_red"]
        except: pass
    return None

def write_tab(ss, title, df, hdr_bg="navy", skip_cols=None):
    if df is None or (hasattr(df, "empty") and df.empty):
        ws = _get_ws(ss, title); _api(ws.clear)
        _api(ws.update, "A1", [["No data available."]]); return
    display_cols = [c for c in df.columns if not c.startswith("_")]
    if skip_cols:
        display_cols = [c for c in display_cols if c not in skip_cols]
    df_out = df[display_cols].copy().replace([float("inf"), float("-inf")], "").fillna("")
    ws = _get_ws(ss, title, rows=max(3000, len(df_out)+10), cols=max(60, len(display_cols)+5))
    _api(ws.clear)
    _api(set_with_dataframe, ws, df_out, include_index=False, resize=True)
    nrows, ncols = len(df_out)+1, len(display_cols)
    bg_color = GS_COLORS.get(hdr_bg, GS_COLORS["navy"])
    hdr_fmt  = {"backgroundColor": bg_color,
                "textFormat": {"bold": True, "foregroundColor": GS_COLORS["white"]},
                "horizontalAlignment": "CENTER"}
    requests = [{"repeatCell": {
        "range": {"sheetId": ws.id,"startRowIndex": 0,"endRowIndex": 1,
                  "startColumnIndex": 0,"endColumnIndex": ncols},
        "cell": {"userEnteredFormat": hdr_fmt},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
    }}]
    fmt_map = {}
    for ri, row in df_out.iterrows():
        for ci, col in enumerate(display_cols):
            bg = _cell_bg(row[col], col)
            if bg:
                key = str(bg)
                if key not in fmt_map: fmt_map[key] = {"bg": bg, "cells": []}
                fmt_map[key]["cells"].append((ri+1, ci))
    for key, info in fmt_map.items():
        for r, c in info["cells"]:
            requests.append({"repeatCell": {
                "range": {"sheetId": ws.id,"startRowIndex": r,"endRowIndex": r+1,
                          "startColumnIndex": c,"endColumnIndex": c+1},
                "cell": {"userEnteredFormat": {"backgroundColor": info["bg"]}},
                "fields": "userEnteredFormat.backgroundColor"
            }})
    if requests:
        try:   _api(ss.batch_update, {"requests": requests})
        except Exception as e: print(f"    ⚠ Formatting skipped: {e}")
    print(f"  ✅ '{title}': {len(df_out)} rows × {ncols} cols")

def write_dashboard_tab(ss, dashboard_df, market):
    write_tab(ss, "📋 Dashboard", dashboard_df, hdr_bg="navy")

def write_sleeve_tab(ss, sleeve_df, market):
    if sleeve_df is None or (hasattr(sleeve_df,"empty") and sleeve_df.empty):
        ws = _get_ws(ss, "📋 RS Sleeves"); _api(ws.clear)
        _api(ws.update, "A1", [["No sleeve data."]]); return
    write_tab(ss, "📋 RS Sleeves", sleeve_df, hdr_bg="navy")

# ─────────────────────────────────────────────────────────────────────────────
#  UNIVERSE LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_au_universe():
    if not os.path.exists(STOCK_CSV):
        print(f"  ❌ Universe CSV not found: {STOCK_CSV}"); return pd.DataFrame()
    df = pd.read_csv(STOCK_CSV)
    df.columns = df.columns.str.strip()
    if "Symbol" not in df.columns:
        print("  ❌ 'Symbol' column missing"); return pd.DataFrame()
    if "Series" in df.columns:
        df = df[df["Series"].str.strip().str.upper().isin(["EQ",""])]
    df = df.head(MAX_STOCKS).copy()
    df["Symbol"]   = df["Symbol"].str.strip()
    df["Yahoo"]    = df["Symbol"] + ".AX"    # ASX tickers need .AX suffix
    df["Company"]  = df.get("Company Name", df["Symbol"])
    df["Industry"] = df.get("Industry", "").fillna("").str.strip()
    df["Sector"]   = df["Industry"].map(AU_INDUSTRY_TO_SECTOR).fillna("Other")
    print(f"  ✅ Australia Universe: {len(df)} stocks loaded")
    return df.reset_index(drop=True)

# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR PRICE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_au_sector_prices():
    result = {}
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS + 5)
    for sec_name, cfg in AU_SECTORS.items():
        ticker = cfg.get("yahoo")
        if not ticker: continue
        try:
            raw = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                              end=end.strftime("%Y-%m-%d"),
                              auto_adjust=True, progress=False)
            if raw.empty: continue
            cl = raw["Close"]
            if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
            s = _normalize(cl.dropna())
            if len(s) >= 22: result[sec_name] = s
        except Exception: pass
    print(f"  ✅ Australia Sector prices: {len(result)}/{len(AU_SECTORS)}")
    return result

# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def build_au_snapshot():
    from market_engine import pct_change_n, safe_download
    syms = [t["ticker"] for t in AU_SNAPSHOT_TICKERS]
    try:
        raw = safe_download(syms, days=10, auto_adjust=True, progress=False)
        cdf = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex) and len(syms)==1: cdf.columns=syms
    except Exception: cdf = pd.DataFrame()
    rows = []
    for t in AU_SNAPSHOT_TICKERS:
        sym=t["ticker"]; price=chg1=chg5=np.nan; trend="N/A"
        try:
            if sym in cdf.columns:
                col=cdf[sym].dropna()
                if len(col)>=2: price=round(float(col.iloc[-1]),2); chg1=round(pct_change_n(col,1),2)
                if len(col)>=5: chg5=round(pct_change_n(col,4),2)
                if not np.isnan(chg1) and not np.isnan(chg5):
                    if   chg1>0 and chg5>0: trend="↑ Bullish"
                    elif chg1<0 and chg5<0: trend="↓ Bearish"
                    elif chg5>0:            trend="→ Recovering"
                    else:                   trend="→ Pulling Back"
        except Exception: pass
        rows.append({"Name":t["name"],"Type":t["type"],"Price":price,"Chg_1D%":chg1,"Chg_5D%":chg5,"Trend":trend})
    df     = pd.DataFrame(rows)
    idxs   = df[df["Type"]=="Index"]["Chg_1D%"].dropna()
    pct_up = (idxs>0).mean()*100 if len(idxs)>0 else 50
    bias   = "BULLISH" if pct_up>=70 else ("BEARISH" if pct_up<40 else "MIXED")
    return pd.concat([df, pd.DataFrame([{
        "Name":f"── MACRO BIAS: {bias} ({len(idxs)} indices, {pct_up:.0f}% green) ──",
        "Type":"Summary","Price":np.nan,"Chg_1D%":np.nan,"Chg_5D%":np.nan,"Trend":bias
    }])], ignore_index=True)

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS
    _mode = _me.prompt_run_mode(ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS)
    ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS = (
        _mode["patterns"], _mode["financials"], _mode["signals"])
    print("\n" + "═"*68)
    print("  AUSTRALIA MARKET — GOOGLE SHEETS EDITION  v1.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M AEST')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("═"*68+"\n")
    t0 = time.time()

    print("🔐 Connecting …"); ss = gs_connect()
    print("📂 Loading Australia universe …"); universe = load_au_universe()
    if universe.empty: print("❌ Empty universe — aborting."); return

    print(f"\n📡 Fetching index ({AU_INDEX}) …")
    end_dt=datetime.today()+timedelta(days=1); start_dt=end_dt-timedelta(days=PERIOD_DAYS+5)
    raw = yf.download(AU_INDEX, start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  ⚠ {AU_INDEX} empty, trying {AU_INDEX_FALLBACK} …")
        raw = yf.download(AU_INDEX_FALLBACK, start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty: print("  ❌ Cannot fetch Australia index"); return
    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame): cl=cl.squeeze()
    index_prices = _normalize(cl.dropna())
    print(f"  ✅ Index: {len(index_prices)} days")

    print("\n📡 Australia Sector ETFs …"); sector_prices = fetch_au_sector_prices()

    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    ohlcv_dict={}
    max_ohlcv=max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv>0:
        print(f"\n📡 Fetching OHLCV for {max_ohlcv} stocks …")
        cands=[s for s in stock_syms if s in price_data.columns and len(price_data[s].dropna())>=60][:max_ohlcv]
        try:    ohlcv_dict=fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict=fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  ✅ OHLCV: {len(ohlcv_dict)} stocks")

    patterns_by_sym={}; patterns_list=[]
    if ENABLE_PATTERNS:
        print("\n📐 Detecting chart patterns …")
        pat_dict={k:v for k,v in ohlcv_dict.items() if len(v)>=60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    # AEST = UTC+10
    aest_tz  = timezone(timedelta(hours=10))
    run_time = datetime.now(aest_tz).strftime("%d %B %Y %H:%M AEST")

    print("\n📸 Market Snapshot …");   snap_df    = build_au_snapshot()
    print("🏭 Sector Strength …");    sec_str_df = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df = build_market_breadth(
        price_data, index_prices, AU_BREADTH_INDICES, INDEX_DATA_DIR, market="AU")
    print("📈 Sector Performance …"); sec_perf_df= build_sector_performance(
        sector_prices, index_prices)
    print("📊 Stock Strength …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices, patterns_by_sym,
        market="AU", fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD)
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="AU", primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="AU", primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="AU")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="AU", primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR, market="AU", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df   = build_dashboard_df(stock_df, sec_str_df, "AU", run_time,
                                        primary_rs=PRIMARY_RS_PERIOD)

    TAB_DELAY = 8
    print("\n📊 Writing to Google Sheets …")
    write_dashboard_tab(ss, dashboard_df, "AU");                  time.sleep(TAB_DELAY)
    write_tab(ss,"🎯 Opportunities",  top_buy_df,  "green");      time.sleep(TAB_DELAY)
    write_tab(ss,"🔴 Sell Alerts",    top_sell_df, "red");        time.sleep(TAB_DELAY)
    write_tab(ss,"🏭 Sectors",        sec_str_df,  "teal");       time.sleep(TAB_DELAY)
    write_tab(ss,"🔄 Rotation",       sec_rot_df,  "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"📊 Stocks",         stock_df,    "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"🎯 Trade Setups",   trade_df,    "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"🌍 Global",         country_etf_df,"navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"🏅 Commodities",    commodity_df,"navy");       time.sleep(TAB_DELAY)
    write_sleeve_tab(ss, sleeve_df, "AU");                        time.sleep(TAB_DELAY)
    write_tab(ss,"📊 Breadth",        breadth_df,  "green");      time.sleep(TAB_DELAY)
    write_tab(ss,"📈 Sector Perf",    sec_perf_df, "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"📸 Snapshot",       snap_df,     "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"📐 Patterns",       chart_df,    "navy");       time.sleep(TAB_DELAY)
    write_tab(ss,"🔬 Signal Detail",  stock_df,    "navy")

    print("\n🌐 Building Australia HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "Australia_Market_Analysis.html")
        build_html_report(
            market="AU", snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD)
        print(f"  ✅ HTML: {html_path}")
    except Exception as e: print(f"  ⚠ HTML skipped: {e}")

    elapsed = time.time()-t0
    print(f"\n{'═'*68}")
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  🔗 {SHEET_URL}")
    if not stock_df.empty:
        sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
        if sl_col:
            prime=int(stock_df[sl_col].astype(str).str.startswith("🌟").sum())
            conf =int(stock_df[sl_col].astype(str).str.startswith("✅").sum())
            rsbuy=int(stock_df[sl_col].astype(str).str.startswith("📈").sum())
            watch=int(stock_df[sl_col].astype(str).str.startswith("👁").sum())
            avoid=int(stock_df[sl_col].astype(str).str.startswith("🔴").sum())
            print(f"  🌟 Prime:{prime} | ✅ Conf:{conf} | 📈 RS Buy:{rsbuy} | 👁 Watch:{watch} | 🔴 Avoid:{avoid}")
    if not trade_df.empty:
        buys=(trade_df["Action"]=="BUY").sum(); sells=(trade_df["Action"]=="SELL").sum()
        print(f"  🎯 Trade Setups: {buys} BUY | {sells} SELL | {len(trade_df)-buys-sells} WAIT")
    print("═"*68)

if __name__ == "__main__":
    main()
