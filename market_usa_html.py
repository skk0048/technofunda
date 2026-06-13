"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  US MARKET ANALYSIS — HTML-ONLY EDITION  v5.4                         ║
║  market_usa_gsht.py  — GitHub Actions compatible                          ║
║                                                                            ║
║  Exact US counterpart of India_market_india_gsht.py v5.4.                 ║
║   • Benchmark : S&P 500 via SPY ETF                                        ║
║   • Universe  : us_sp500list.csv  (must be sorted by mkt cap, largest 1st)║
║   • Sectors   : 11 SPDR ETFs  (XLK, XLF, XLV, XLY, XLI …)               ║
║   • Sleeves   : US_A (Top 50, Monthly) · US_B (51-200, Ftn) ·             ║
║                 US_C (201-500, Weekly)                                     ║
║   • Timezone  : ET  (GitHub Actions UTC label)                             ║
║                                                                            ║
║  HOW TO AUTHENTICATE:                                                      ║
║   GitHub Secrets:                                                          ║
║     GOOGLE_CREDENTIALS    → contents of service account JSON               ║
║   (can share the same service-account JSON as the India sheet)             ║
║                                                                            ║
║  GitHub Actions writes the JSON to /tmp/creds.json and sets               ║
║                                                                            ║
║  SHEETS WRITTEN (13 tabs):                                                 ║
║   0. 📋 Dashboard        7. 📊 Stock Strength                              ║
║   1. 📸 Market Snapshot  8. 🏆 Top Picks - Buy                             ║
║   2. 🏭 Sector Strength  9. 🔴 Top Picks - Sell                            ║
║   3. 🔄 Sector Rotation  10. 📐 Chart Patterns                             ║
║   4. 🏭 Industry Rotat.  11. 🎯 Trade Setups                               ║
║   5. 📊 Market Breadth   12. 📋 RS Sleeve Lists                            ║
║   6. 📈 Sector Perf.                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, warnings
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")
import logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('peewee').setLevel(logging.CRITICAL)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Dynamic Path for GitHub vs Local ──
if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData") # GitHub Actions
else:
    INDEX_DATA_DIR = r"C:\Users\sudhi\Documents\Trading\SectorRotation\IndexData" # Local

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "us_all_stocks_master.csv")

# ── Tunable constants ─────────────────────────────────────────────────────────
MAX_STOCKS        = 1500
PERIOD_DAYS       = 500   # 420 calendar days covers RS_252d & 12M%
ENABLE_PATTERNS   = False
PATTERN_MAX       = 800
FETCH_FINANCIALS  = True   # always True in cloud — no cache
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 2400
# ── Primary RS period for sector ranking & rotation ──────────────────────────
# Options: 22, 55, 120  (120 only works in Strength, not Rotation)
# Change this one number to switch which RS period drives all sector decisions.
PRIMARY_RS_PERIOD = 22   # ← change to 55 or 120 to test other RS periods

# ── Google Sheets auth ────────────────────────────────────────────────────────

sys.path.insert(0, SCRIPT_DIR)
# ── #10 support-files layout: import modules from ./SupportFiles and prefer
#    ./SupportFiles/IndexData when present (all no-ops if the layout is flat)
_SUPPORT_DIR = os.path.join(SCRIPT_DIR, "SupportFiles")
if os.path.isdir(_SUPPORT_DIR) and _SUPPORT_DIR not in sys.path:
    sys.path.insert(0, _SUPPORT_DIR)
if os.path.isdir(os.path.join(_SUPPORT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(_SUPPORT_DIR, "IndexData")
from market_signals import build_dashboard_df
try:
    from market_rrg import build_rrg_data, build_rrg_section, make_sector_colors as _rrg_colors
    _RRG_AVAILABLE = True
except Exception:
    _RRG_AVAILABLE = False
from market_engine import (
    US_INDEX, US_SECTORS, US_INDUSTRY_TO_SECTOR, US_BREADTH_INDICES,
    RS_PERIODS, SIGNAL_PERIODS, fetch_close_batch, fetch_ohlcv_batch,
    fetch_ohlcv_with_cache, _normalize, calc_rs, calc_rsi,
    build_market_snapshot, build_sector_strength,
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
#  GOOGLE SHEETS HELPERS
#  (identical to India gsheet — shared colour palette, formatting, API wrapper)
# ─────────────────────────────────────────────────────────────────────────────


def load_us_universe():
    """
    Load S&P 500 universe from CSV.
    Detects column names flexibly (Symbol/Ticker, GICS Sector/Sector/Industry,
    Company Name/Security/Name).
    IMPORTANT: us_sp500list.csv must be sorted by market cap descending so that
    row ranges correctly separate Mega (0-49) / Large (50-199) / Mid (200-499).
    """
    for path in [STOCK_CSV,
                 os.path.join(SCRIPT_DIR,    "us_sp500list.csv"),
                 os.path.join(INDEX_DATA_DIR, "us_sp500list.csv")]:
        if os.path.exists(path):
            break
    else:
        print("  ❌ us_sp500list.csv not found"); sys.exit(1)

    df = pd.read_csv(path); df.columns = df.columns.str.strip()
    cm = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    sc = next((cm[k] for k in ["symbol", "ticker", "sym"]         if k in cm), df.columns[0])
    ic = next((cm[k] for k in ["gicssector", "sector", "industry"] if k in cm), df.columns[1])
    nc = next((cm[k] for k in ["companyname", "security", "name", "company"] if k in cm),
              df.columns[2])
    df = df.rename(columns={sc: "Symbol", ic: "Industry", nc: "Company Name"})
    df["Symbol"]       = df["Symbol"].astype(str).str.strip()
    df["Industry"]     = df["Industry"].astype(str).str.strip()
    df["Company Name"] = df["Company Name"].astype(str).str.strip()
    df["Yahoo"]        = df["Symbol"]   # US tickers have no suffix
    df["Sector"]       = df["Industry"].map(US_INDUSTRY_TO_SECTOR).fillna("Technology")
    if MAX_STOCKS > 0:
        df = df.head(MAX_STOCKS)
    print(f"  ✅ Universe: {len(df)} stocks | {df['Sector'].nunique()} sectors "
          f"| {df['Industry'].nunique()} industries")
    return df


def fetch_us_sector_prices():
    """
    Fetch US sector prices via SPDR ETFs (XLK, XLF, XLV …).
    US sectors have direct Yahoo tickers — no constituent-avg fallback needed.
    """
    result = {}
    for sname, cfg in US_SECTORS.items():
        ysym = cfg.get("yahoo")
        if not ysym:
            continue
        try:
            raw = yf.download(ysym, period=f"{PERIOD_DAYS}d",
                              auto_adjust=True, progress=False)
            if not raw.empty and len(raw) >= 22:
                cl = raw["Close"]
                if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
                result[sname] = _normalize(cl.dropna())
                print(f"    ✓ {sname:<22} {ysym}")
            else:
                print(f"    ✗ {sname:<22} (no data)")
        except Exception as e:
            print(f"    ✗ {sname:<22} {e}")
    print(f"  ✅ Sector ETFs: {len(result)}/{len(US_SECTORS)}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS
    _mode = _me.prompt_run_mode(ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS)
    ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS = (
        _mode["patterns"], _mode["financials"], _mode["signals"])
    print("\n" + "═" * 68)
    print("  US MARKET — HTML-ONLY EDITION  v5.4")
    # GitHub Actions runs UTC; label as ET so the dashboard shows the right timezone
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M ET')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}")
    print("═" * 68 + "\n")
    t0 = time.time()

    # ── Connect ───────────────────────────────────────────────────────────────

    # ── Universe ──────────────────────────────────────────────────────────────
    print("📂 Loading universe …"); universe = load_us_universe()

    # ── Index prices ──────────────────────────────────────────────────────────
    print(f"\n📡 Fetching index ({US_INDEX}) …")
    raw = yf.download(US_INDEX, period=f"{PERIOD_DAYS}d", auto_adjust=True, progress=False)
    if raw.empty:
        print("  ❌ Cannot fetch index"); return
    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame):
        cl = cl.iloc[:, 0] if cl.shape[1] >= 1 else cl.squeeze()
    cl = pd.Series(cl).dropna()
    index_prices = _normalize(cl)
    print(f"  ✅ Index: {len(index_prices)} days")

    # ── Sector prices ─────────────────────────────────────────────────────────
    print("\n📡 Sector ETFs …"); sector_prices = fetch_us_sector_prices()

    # ── Stock closes ──────────────────────────────────────────────────────────
    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    # ── OHLCV for patterns + signals ──────────────────────────────────────────
    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        print(f"\n📡 Fetching OHLCV for {max_ohlcv} stocks …")
        cands = [s for s in stock_syms
                 if s in price_data.columns and len(price_data[s].dropna()) >= 60
                 ][:max_ohlcv]
        try:
            ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except Exception:
            ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  ✅ OHLCV: {len(ohlcv_dict)} stocks")

    # ── Chart patterns ────────────────────────────────────────────────────────
    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        print("\n📐 Detecting chart patterns …")
        pat_dict = {k: v for k, v in ohlcv_dict.items() if len(v) >= 60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    # ── Build all DataFrames ──────────────────────────────────────────────────
    # NOTE: run_time label is ET — GitHub Actions runs UTC so we label it
    #       explicitly. The strftime clock itself is UTC/server-local but
    #       marking it ET communicates the intended trading timezone to readers.
    run_time = datetime.now().strftime("%d %b %Y  %H:%M ET")

    print("\n📸 Market Snapshot …");   snap_df     = build_market_snapshot("US")
    print("🏭 Sector Strength …");    sec_str_df  = build_sector_strength(
                                          universe, price_data, index_prices, sector_prices,
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df  = build_sector_rotation(
                                          universe, price_data, index_prices,
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df  = build_industry_rotation(
                                          universe, price_data, index_prices,
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df  = build_market_breadth(
                                          price_data, index_prices,
                                          US_BREADTH_INDICES, INDEX_DATA_DIR,
                                          market="US")
    print("📈 Sector Performance …"); sec_perf_df = build_sector_performance(
                                          sector_prices, index_prices)
    print("📊 Stock Strength + Signals + Financials …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices,
        patterns_by_sym, market="US",
        fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD,
    )
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
                                          stock_df, sec_str_df, market="US",
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
                                          stock_df, sec_str_df, market="US",
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
                                          patterns_list, stock_df, market="US")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
                                          stock_df, sec_str_df, market="US",
                                          primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
                                          stock_df, universe, INDEX_DATA_DIR,
                                          market="US", run_time=run_time,
                                          index_prices=index_prices,
                                          price_data=price_data,
                                          ohlcv_dict=ohlcv_dict,
                                          primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df = build_dashboard_df(stock_df, sec_str_df, "US", run_time,
                                      primary_rs=PRIMARY_RS_PERIOD)

    print("\n🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("\n🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS,
                                         primary_rs=PRIMARY_RS_PERIOD)

    # ── RRG tab ─────────────────────────────────────────────────────────────────
    rrg_html = None
    if _RRG_AVAILABLE and sector_prices:
        try:
            print("📡 Building RRG chart data …")
            rrg_data = build_rrg_data(sector_prices, index_prices)
            sec_list = [n for n in rrg_data["weekly"] or rrg_data["daily"]]
            rrg_html = build_rrg_section(
                rrg_data       = rrg_data,
                sector_list    = sec_list,
                sector_colors  = _rrg_colors(sec_list),
                market_name    = "US",
                benchmark_name = "S&P 500 (SPY)",
            )
            print(f"  ✅ RRG: {len(sec_list)} sectors")
        except Exception as _e:
            print(f"  ⚠ RRG skipped: {_e}")

    print("\n🌐 Building US HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "US.html")
        build_html_report(
            market="US",
            snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD,
            rrg_section=rrg_html,
        )
        print(f"  ✅ HTML generated successfully at: {html_path}")
    except Exception as e:
        print(f"  ⚠ HTML report generation skipped/failed: {e}")

    # ── Console summary ───────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'═'*68}")
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  📄 US.html")
    if not stock_df.empty:
        b   = (stock_df["Signal"]  == "Buy").sum()
        s   = (stock_df["Signal"]  == "Sell").sum()
        sb  = (stock_df["Enhanced"]== "Strong Buy").sum()
        mst = (stock_df.get("MST_Signal",  pd.Series()) == "Buy").sum()
        lst = (stock_df.get("LST_Signal",  pd.Series()) == "Buy").sum()
        r30 = (stock_df.get("RS30_Signal", pd.Series()) == "Buy").sum()
        print(f"  ⭐ Strong Buy:{sb} | ✅ Buy:{b} | 🔴 Sell:{s}")
        print(f"  📅 MST Buy:{mst} | 📆 LST Buy:{lst} | 📊 RS30 Buy:{r30}")
    if not trade_df.empty:
        buys  = (trade_df["Action"] == "BUY").sum()
        sells = (trade_df["Action"] == "SELL").sum()
        print(f"  🎯 Trade Setups: {buys} BUY | {sells} SELL | {len(trade_df)-buys-sells} WAIT")
    if not sleeve_df.empty:
        data_rows = sleeve_df[
            ~sleeve_df["Rank"].astype(str).str.startswith("━") &
            (sleeve_df["Rank"].astype(str).str.strip() != "") &
            sleeve_df["Rank"].astype(str).str.match(r'^\d+$')
        ]
        print(f"  📋 RS Sleeves: {len(data_rows)} stocks across US_A/B/C")
    print("═" * 68)


if __name__ == "__main__":
    main()
