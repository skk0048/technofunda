"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHINA MARKET ANALYSIS — GOOGLE SHEETS EDITION  v1.0                ║
║  market_cn_gsht.py  — GitHub Actions compatible                  ║
║                                                                            ║
║  Universe  : cn_csi300list.csv                                         ║
║  Benchmark : 000300.SS                                                ║
║  Timezone  : CST                                                    ║
║  Sheet URL : GOOGLE_SHEET_URL_CN env var                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, warnings
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta, timezone
import gspread
import gspread.utils
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import tenacity
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData")
else:
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "SupportFiles", "IndexData")

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "cn_csi300list.csv")

MAX_STOCKS        = 150
PERIOD_DAYS       = 420
ENABLE_PATTERNS   = True
PATTERN_MAX       = 100
FETCH_FINANCIALS  = True
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 100
PRIMARY_RS_PERIOD = 22

CREDENTIALS_PATH = (
    os.environ.get("GOOGLE_CREDENTIALS_PATH")
    or os.path.join(SCRIPT_DIR, "google_credentials.json")
)
SHEET_URL = (
    os.environ.get("GOOGLE_SHEET_URL_CN")
    or "https://docs.google.com/spreadsheets/d/YOUR_CN_SHEET_ID/edit"
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
#  CHINA MARKET CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CN_INDEX          = "000300.SS"
CN_INDEX_FALLBACK = "^SSE"

CN_SECTORS = {
    "Financials":       {"yahoo": None, "csv": None},
    "Energy":           {"yahoo": None, "csv": None},
    "Materials":        {"yahoo": None, "csv": None},
    "Technology":       {"yahoo": None, "csv": None},
    "Healthcare":       {"yahoo": None, "csv": None},
    "Industrials":      {"yahoo": None, "csv": None},
    "ConsumerDisc":     {"yahoo": None, "csv": None},
    "Consumer Staples": {"yahoo": None, "csv": None},
    "Utilities":        {"yahoo": None, "csv": None},
    "CommServices":     {"yahoo": None, "csv": None},
    "RealEstate":       {"yahoo": None, "csv": None},
}

CN_INDUSTRY_TO_SECTOR = {
    "Financials": "Financials", "Banking": "Financials",
    "Insurance": "Financials", "Asset Management": "Financials",
    "Energy": "Energy", "Oil & Gas": "Energy",
    "Materials": "Materials", "Mining": "Materials",
    "Gold": "Materials", "Metals": "Materials", "Chemicals": "Materials",
    "Technology": "Technology", "Software": "Technology",
    "IT Services": "Technology", "Electronics": "Technology",
    "Semiconductors": "Technology",
    "Healthcare": "Healthcare", "Pharmaceuticals": "Healthcare",
    "Biotechnology": "Healthcare", "Medical Devices": "Healthcare",
    "Industrials": "Industrials", "Railways": "Industrials",
    "Aerospace": "Industrials", "Engineering": "Industrials",
    "Machinery": "Industrials", "Shipbuilding": "Industrials",
    "ConsumerDisc": "ConsumerDisc", "Retail": "ConsumerDisc",
    "Automotive": "ConsumerDisc", "Luxury": "ConsumerDisc",
    "Consumer Staples": "Consumer Staples", "Food & Beverage": "Consumer Staples",
    "Utilities": "Utilities", "Power": "Utilities",
    "CommServices": "CommServices", "Telecoms": "CommServices",
    "Media": "CommServices",
    "RealEstate": "RealEstate", "REITs": "RealEstate",
}

CN_BREADTH_INDICES = {
    "CSI 300": {"yahoo": "000300.SS", "csv": "cn_csi300list.csv"},
    "SSE Comp": {"yahoo": "^SSEC", "csv": None},
}

CN_SNAPSHOT_TICKERS = [
    {"name": "CSI 300",                 "ticker": "000300.SS",     "type": "Index"},
    {"name": "Shanghai Comp",           "ticker": "^SSEC",         "type": "Index"},
    {"name": "Hang Seng",               "ticker": "^HSI",          "type": "Index"},
    {"name": "CNY/USD",                 "ticker": "CNY=X",         "type": "Forex"},
    {"name": "USD/CNH",                 "ticker": "USDCNH=X",      "type": "Forex"},
    {"name": "DXY (USD Index)",         "ticker": "DX-Y.NYB",      "type": "Forex"},
    {"name": "10Y CGB Yield",           "ticker": "^TNX",          "type": "Bond"},
    {"name": "Gold",                    "ticker": "GC=F",          "type": "Commodity"},
    {"name": "Crude Brent",             "ticker": "BZ=F",          "type": "Commodity"},
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
    "sl_avoid":   {"red": 1.000, "green": 0.800, "blue": 0.800},
}

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

def gs_connect():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=GSCOPE)
    gc    = gspread.authorize(creds)
    return gc.open_by_url(SHEET_URL)


# ─────────────────────────────────────────────────────────────────────────────
#  UNIVERSE LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_cn_universe():
    csv_path = os.path.join(INDEX_DATA_DIR, "cn_csi300list.csv")
    if not os.path.exists(csv_path):
        csv_path = STOCK_CSV
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    rename = {
        "Company Name": "Company", "Symbol": "Yahoo",
        "Industry": "Sector", "Series": "Series",
    }
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    if "Yahoo" not in df.columns and "Symbol" in df.columns:
        df["Yahoo"] = df["Symbol"]
    if "Sector" not in df.columns and "Industry" in df.columns:
        df["Sector"] = df["Industry"]
    df["Sector"] = df["Sector"].map(CN_INDUSTRY_TO_SECTOR).fillna(df.get("Sector","General"))
    df = df.dropna(subset=["Yahoo"]).head(MAX_STOCKS)
    print(f"  ✅ Universe: {len(df)} stocks loaded")
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR PRICE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_cn_sector_prices():
    """Fetch CHINA sector ETF prices (returns empty dict — no local ETFs)."""
    sector_prices = {}
    for sec, cfg in CN_SECTORS.items():
        tkr = cfg.get("yahoo")
        if not tkr:
            continue
        try:
            end   = datetime.today() + timedelta(days=1)
            start = end - timedelta(days=PERIOD_DAYS + 5)
            raw   = yf.download(tkr, start=start.strftime("%Y-%m-%d"),
                                end=end.strftime("%Y-%m-%d"),
                                auto_adjust=True, progress=False)
            if not raw.empty:
                cl = raw["Close"]
                if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
                sector_prices[sec] = _normalize(cl.dropna())
        except Exception:
            pass
    return sector_prices


# ─────────────────────────────────────────────────────────────────────────────
#  MARKET SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def build_cn_snapshot():
    return build_market_snapshot(CN_SNAPSHOT_TICKERS, PERIOD_DAYS)


# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS WRITE HELPERS  (identical to FR pattern)
# ─────────────────────────────────────────────────────────────────────────────

@tenacity.retry(stop=tenacity.stop_after_attempt(4),
                wait=tenacity.wait_exponential(multiplier=2, min=4, max=30),
                retry=tenacity.retry_if_exception_type(Exception), reraise=True)
def _safe_write(ws, df):
    ws.clear()
    set_with_dataframe(ws, df, include_index=False)


def _get_or_create_ws(ss, title):
    try:    return ss.worksheet(title)
    except: return ss.add_worksheet(title=title, rows=2000, cols=50)


def _color_header(ws, color_key, df):
    try:
        c = GS_COLORS.get(color_key, GS_COLORS["navy"])
        ws.format("1:1", {"backgroundColor": c,
                            "textFormat": {"bold": True, "foregroundColor": GS_COLORS["white"]}})
    except Exception: pass


def write_tab(ss, title, df, color_key="navy"):
    if df is None or df.empty: return
    try:
        ws = _get_or_create_ws(ss, title)
        _safe_write(ws, df)
        _color_header(ws, color_key, df)
        print(f"  ✅ {title} → {len(df)} rows")
    except Exception as e:
        print(f"  ❌ {title}: {e}")


def write_dashboard_tab(ss, df, market_code):
    if df is None or df.empty: return
    title = f"📊 Dashboard"
    try:
        ws = _get_or_create_ws(ss, title)
        _safe_write(ws, df)
        _color_header(ws, "teal", df)
        print(f"  ✅ Dashboard → {len(df)} rows")
    except Exception as e:
        print(f"  ❌ Dashboard: {e}")


def write_sleeve_tab(ss, df, market_code):
    if df is None or df.empty: return
    title = "📋 RS Sleeves"
    try:
        ws = _get_or_create_ws(ss, title)
        _safe_write(ws, df)
        _color_header(ws, "sl_triple", df)
        print(f"  ✅ Sleeves → {len(df)} rows")
    except Exception as e:
        print(f"  ❌ Sleeves: {e}")


def add_macro_bias_row(df):
    if df is None or df.empty: return df
    idxs = [r for _, r in df.iterrows()
            if str(r.get("Type","")).lower() == "index"]
    pct_up = sum(1 for r in idxs if (r.get("Chg_1D%") or 0) > 0) / max(len(idxs),1) * 100
    bias   = "RISK-ON 🟢" if pct_up >= 60 else ("RISK-OFF 🔴" if pct_up <= 40 else "MIXED ⚠️")
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
    print(f"  CHINA MARKET — GOOGLE SHEETS EDITION  v1.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M CST')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("═"*68+"\n")
    t0 = time.time()

    print("🔐 Connecting …"); ss = gs_connect()
    print(f"📂 Loading China universe …"); universe = load_cn_universe()
    if universe.empty: print("❌ Empty universe — aborting."); return

    print(f"\n📡 Fetching index ({CN_INDEX}) …")
    end_dt  = datetime.today() + timedelta(days=1)
    start_dt= end_dt - timedelta(days=PERIOD_DAYS+5)
    raw = yf.download(CN_INDEX, start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  ⚠ {CN_INDEX} empty, trying {CN_INDEX_FALLBACK} …")
        raw = yf.download(CN_INDEX_FALLBACK, start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty: print(f"  ❌ Cannot fetch China index"); return
    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
    index_prices = _normalize(cl.dropna())
    print(f"  ✅ Index: {len(index_prices)} days")

    print(f"\n📡 China Sector ETFs …"); sector_prices = fetch_cn_sector_prices()

    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        print(f"\n📡 Fetching OHLCV for {max_ohlcv} stocks …")
        cands = [s for s in stock_syms if s in price_data.columns
                 and len(price_data[s].dropna()) >= 60][:max_ohlcv]
        try:    ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  ✅ OHLCV: {len(ohlcv_dict)} stocks")

    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        print("\n📐 Detecting chart patterns …")
        pat_dict = {k: v for k, v in ohlcv_dict.items() if len(v) >= 60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    tz_obj   = timezone(timedelta(hours=8))
    run_time = datetime.now(tz_obj).strftime(f"%d %B %Y %H:%M CST")

    print("\n📸 Market Snapshot …");   snap_df    = build_cn_snapshot()
    print("🏭 Sector Strength …");    sec_str_df = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df = build_market_breadth(
        price_data, index_prices, CN_BREADTH_INDICES, INDEX_DATA_DIR, market="CN")
    print("📈 Sector Performance …"); sec_perf_df= build_sector_performance(
        sector_prices, index_prices)
    print("📊 Stock Strength …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices, patterns_by_sym,
        market="CN", fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD)
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="CN", primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="CN", primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="CN")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="CN", primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR, market="CN", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df   = build_dashboard_df(stock_df, sec_str_df, "CN", run_time,
                                        primary_rs=PRIMARY_RS_PERIOD)

    # ── BUILD HTML ──────────────────────────────────────────────────────────
    print("\n🌐 Building China HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "China_Market_Analysis.html")
        build_html_report(
            market="CN", snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD)
        print(f"  ✅ HTML: {html_path}")
    except Exception as e:
        print(f"  ❌ HTML generation failed: {e}")
        import traceback; traceback.print_exc()

    TAB_DELAY = 8
    print("\n📊 Writing to Google Sheets …")
    write_dashboard_tab(ss, dashboard_df, "CN");             time.sleep(TAB_DELAY)
    write_tab(ss,"🎯 Opportunities",  top_buy_df,  "green");    time.sleep(TAB_DELAY)
    write_tab(ss,"🔴 Sell Alerts",    top_sell_df, "red");      time.sleep(TAB_DELAY)
    write_tab(ss,"🏭 Sectors",        sec_str_df,  "teal");     time.sleep(TAB_DELAY)
    write_tab(ss,"🔄 Rotation",       sec_rot_df,  "navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"📊 Stocks",         stock_df,    "navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"🎯 Trade Setups",   trade_df,    "navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"🌍 Global",         country_etf_df,"navy");   time.sleep(TAB_DELAY)
    write_tab(ss,"🏅 Commodities",    commodity_df,"navy");     time.sleep(TAB_DELAY)
    write_sleeve_tab(ss, sleeve_df, "CN");                   time.sleep(TAB_DELAY)
    write_tab(ss,"📊 Breadth",        breadth_df,  "green");    time.sleep(TAB_DELAY)
    write_tab(ss,"📈 Sector Perf",    sec_perf_df, "navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"📸 Snapshot",       snap_df,     "navy");     time.sleep(TAB_DELAY)
    write_tab(ss,"📐 Patterns",       chart_df,    "navy")

    elapsed = time.time() - t0
    print(f"\n{'═'*68}")
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  🔗 {SHEET_URL}")
    if not stock_df.empty:
        sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
        if sl_col:
            prime = int(stock_df[sl_col].astype(str).str.startswith("🌟").sum())
            conf  = int(stock_df[sl_col].astype(str).str.startswith("✅").sum())
            rsbuy = int(stock_df[sl_col].astype(str).str.startswith("📈").sum())
            watch = int(stock_df[sl_col].astype(str).str.startswith("👁").sum())
            avoid = int(stock_df[sl_col].astype(str).str.startswith("🔴").sum())
            print(f"  🌟 Prime:{prime} | ✅ Conf:{conf} | 📈 RS Buy:{rsbuy} | 👁 Watch:{watch} | 🔴 Avoid:{avoid}")
    if not trade_df.empty:
        buys  = (trade_df["Action"] == "BUY").sum()
        sells = (trade_df["Action"] == "SELL").sum()
        print(f"  🎯 Trade Setups: {buys} BUY | {sells} SELL | {len(trade_df)-buys-sells} WAIT")
    print("═"*68)


if __name__ == "__main__":
    main()
