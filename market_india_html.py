"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  INDIA MARKET ANALYSIS — HTML-ONLY EDITION  v6.0                      ║
║  market_india_gsht.py  — GitHub Actions compatible                        ║
║                                                                            ║
║  v6.0 changes:                                                             ║
║   • Sheet order redesigned to match market_excel.py v6.0                  ║
║   • "🎯 Opportunities" replaces "🏆 Top Picks - Buy"                      ║
║   • Dashboard uses new Signal_Label section layout                         ║
║   • primary_rs passed through all calls (was missing in some paths)        ║
║   • timezone import fixed (was missing from datetime imports)              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, warnings
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta, timezone
warnings.filterwarnings("ignore")
import logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('peewee').setLevel(logging.CRITICAL)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData")
else:
    INDEX_DATA_DIR = r"C:\Users\sudhi\Documents\Trading\SectorRotation\IndexData"

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "ind_niftytotalmarket_list.csv")

MAX_STOCKS        = 500
PERIOD_DAYS       = 600
ENABLE_PATTERNS   = True
PATTERN_MAX       = 400
FETCH_FINANCIALS  = True
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 1400
PRIMARY_RS_PERIOD = 22   # ← change to 55 or 120 to test other RS periods


sys.path.insert(0, SCRIPT_DIR)
# ── #10 support-files layout: import modules from ./SupportFiles and prefer
#    ./SupportFiles/IndexData when present (all no-ops if the layout is flat)
_SUPPORT_DIR = os.path.join(SCRIPT_DIR, "SupportFiles")
if os.path.isdir(_SUPPORT_DIR) and _SUPPORT_DIR not in sys.path:
    sys.path.insert(0, _SUPPORT_DIR)
if os.path.isdir(os.path.join(_SUPPORT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(_SUPPORT_DIR, "IndexData")
from market_signals import build_dashboard_df
from market_engine import (
    INDIA_INDEX, INDIA_SECTORS, INDIA_INDUSTRY_TO_SECTOR, INDIA_BREADTH_INDICES,
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
#  GOOGLE SHEETS COLOUR PALETTE
# ─────────────────────────────────────────────────────────────────────────────


# Signal_Label → GS colour key


# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS API HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_india_universe():
    for path in [STOCK_CSV,
                 os.path.join(SCRIPT_DIR,"ind_nifty500list.csv"),
                 os.path.join(INDEX_DATA_DIR,"ind_niftytotalmarket_list.csv")]:
        if os.path.exists(path): break
    else: print("  ❌ Universe CSV not found"); sys.exit(1)
    df = pd.read_csv(path); df.columns = df.columns.str.strip()
    for old,new in [(df.columns[2],"Symbol"),(df.columns[1],"Industry"),(df.columns[0],"Company Name")]:
        if new not in df.columns: df = df.rename(columns={old:new})
    df["Symbol"]       = df["Symbol"].str.strip()
    df["Industry"]     = df["Industry"].str.strip()
    df["Company Name"] = df["Company Name"].str.strip()
    df["Yahoo"]        = df["Symbol"] + ".NS"
    df["Sector"]       = df["Industry"].map(INDIA_INDUSTRY_TO_SECTOR).fillna("Finance")
    if MAX_STOCKS > 0: df = df.head(MAX_STOCKS)
    print(f"  ✅ Universe: {len(df)} stocks | {df['Sector'].nunique()} sectors")
    return df


def fetch_india_sector_prices(universe=None):
    result = {}
    for sname, cfg in INDIA_SECTORS.items():
        ysym = cfg.get("yahoo")
        if ysym:
            try:
                raw = yf.download(ysym, period=f"{PERIOD_DAYS}d", auto_adjust=True, progress=False)
                if not raw.empty and len(raw) >= 22:
                    cl = raw["Close"]
                    if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
                    result[sname] = _normalize(cl.dropna()); continue
            except: pass
        csv_f = cfg.get("csv")
        if csv_f:
            for base in [INDEX_DATA_DIR, SCRIPT_DIR]:
                path = os.path.join(base, csv_f)
                if os.path.exists(path):
                    syms = load_csv_constituents(path, is_nse=True)
                    if syms:
                        try:
                            raw = yf.download(syms[:30], period=f"{PERIOD_DAYS}d",
                                              auto_adjust=True, progress=False)
                            cls = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
                            cls = cls.dropna(how="all")
                            if len(cls) >= 22:
                                norm = cls/cls.iloc[0]*1000; result[sname]=_normalize(norm.mean(axis=1))
                        except: pass
                    break
    print(f"  ✅ Sector prices: {len(result)}/{len(INDIA_SECTORS)}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS
    _mode = _me.prompt_run_mode(ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS)
    ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS = (
        _mode["patterns"], _mode["financials"], _mode["signals"])
    print("\n"+"═"*68)
    print("  INDIA MARKET — HTML-ONLY EDITION  v6.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M IST')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("═"*68+"\n")
    t0 = time.time()

    print("📂 Loading universe …");           universe = load_india_universe()

    print(f"\n📡 Fetching index ({INDIA_INDEX}) …")
    raw = yf.download(INDIA_INDEX, period=f"{PERIOD_DAYS}d", auto_adjust=True, progress=False)
    if raw.empty: print("  ❌ Cannot fetch index"); return
    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame):
        cl = cl.iloc[:, 0] if cl.shape[1] >= 1 else cl.squeeze()
    cl = pd.Series(cl).dropna()
    index_prices = _normalize(cl)
    print(f"  ✅ Index: {len(index_prices)} days")

    print("\n📡 Sector indices …"); sector_prices = fetch_india_sector_prices(universe)

    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        print(f"\n📡 Fetching OHLCV for {max_ohlcv} stocks …")
        cands = [s for s in stock_syms
                 if s in price_data.columns and len(price_data[s].dropna())>=60][:max_ohlcv]
        try:    ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  ✅ OHLCV: {len(ohlcv_dict)} stocks")

    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        print("\n📐 Detecting chart patterns …")
        pat_dict = {k:v for k,v in ohlcv_dict.items() if len(v)>=60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    # IST timestamp for dashboard
    ist_tz   = timezone(timedelta(hours=5, minutes=30))
    run_time = datetime.now(ist_tz).strftime("%d %B %Y %H:%M IST")

    print("\n📸 Market Snapshot …");   snap_df     = build_market_snapshot("INDIA")
    print("🏭 Sector Strength …");    sec_str_df  = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df  = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df  = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df  = build_market_breadth(
        price_data, index_prices, INDIA_BREADTH_INDICES, INDEX_DATA_DIR, market="INDIA")
    print("📈 Sector Performance …"); sec_perf_df = build_sector_performance(
        sector_prices, index_prices)
    print("📊 Stock Strength + Signals + Financials …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices,
        patterns_by_sym, market="INDIA",
        fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD,
    )
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="INDIA", primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="INDIA", primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="INDIA")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="INDIA", primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR,
        market="INDIA", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)

    dashboard_df = build_dashboard_df(stock_df, sec_str_df, "INDIA", run_time,
                                      primary_rs=PRIMARY_RS_PERIOD)

    print("\n🌐 Building India HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "IN.html")
        build_html_report(
            market="INDIA",
            snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD,
        )
        print(f"  ✅ HTML: {html_path}")
    except Exception as e:
        print(f"  ⚠ HTML skipped: {e}")

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed = time.time()-t0
    print(f"\n{'═'*68}")
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  📄 IN.html")
    if not stock_df.empty:
        sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
        if sl_col:
            prime = int(stock_df[sl_col].astype(str).str.startswith("🌟").sum())
            conf  = int(stock_df[sl_col].astype(str).str.startswith("✅").sum())
            rsbuy = int(stock_df[sl_col].astype(str).str.startswith("📈").sum())
            watch = int(stock_df[sl_col].astype(str).str.startswith("👁").sum())
            avoid = int(stock_df[sl_col].astype(str).str.startswith("🔴").sum())
            print(f"  🌟 Prime:{prime} | ✅ Conf:{conf} | 📈 RS Buy:{rsbuy} | 👁 Watch:{watch} | 🔴 Avoid:{avoid}")
        else:
            b  = (stock_df["Signal"]=="Buy").sum()
            s  = (stock_df["Signal"]=="Sell").sum()
            sb = (stock_df["Enhanced"]=="Strong Buy").sum()
            print(f"  ⭐ Strong Buy:{sb} | ✅ Buy:{b} | 🔴 Sell:{s}")
    if not trade_df.empty:
        buys  = (trade_df["Action"]=="BUY").sum()
        sells = (trade_df["Action"]=="SELL").sum()
        print(f"  🎯 Trade Setups: {buys} BUY | {sells} SELL | {len(trade_df)-buys-sells} WAIT")
    print("═"*68)


if __name__ == "__main__":
    main()
