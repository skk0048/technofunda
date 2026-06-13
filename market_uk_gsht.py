"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  UK MARKET ANALYSIS — HTML-ONLY EDITION  v1.0                         ║
║  market_uk_gsht.py  — GitHub Actions compatible                           ║
║                                                                            ║
║  Universe  : uk_ftse350list.csv  (FTSE 350 stocks, Yahoo suffix .L)       ║
║  Benchmark : iShares FTSE 100 ETF (ISF.L) → falls back to ^FTSE           ║
║  Sectors   : 10 iShares UK sector ETFs                                     ║
║  Timezone  : GMT/BST  (market close 16:30 London)                         ║
║                                                                            ║
║  SHEETS WRITTEN (15 tabs — same order as India v6.0):                     ║
║   0.  📋 Dashboard          8.  🎯 Trade Setups                            ║
║   1.  🎯 Opportunities      9.  🌍 Global                                  ║
║   2.  🔴 Sell Alerts        10. 🏅 Commodities                             ║
║   3.  🏭 Sectors            11. 📋 RS Sleeves                              ║
║   4.  🔄 Rotation           12. 📊 Breadth                                 ║
║   5.  📊 Stocks             13. 📈 Sector Perf                             ║
║   6.  🏭 Industry Rotation  14. 📸 Snapshot                               ║
║   7.  📐 Patterns           15. 🔬 Signal Detail                           ║
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

# ── Path resolution (same logic as India/USA scripts) ────────────────────────
if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData")
else:
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "SupportFiles", "IndexData")

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "uk_all_stocks_master.csv")

# ── Tunable constants ─────────────────────────────────────────────────────────
MAX_STOCKS        = 500
PERIOD_DAYS       = 504
ENABLE_PATTERNS   = True
PATTERN_MAX       = 300
FETCH_FINANCIALS  = True
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 500
PRIMARY_RS_PERIOD = 22   # ← 22 / 55 / 120

# ── Google Sheets auth ────────────────────────────────────────────────────────

# ── Support-files path setup ──────────────────────────────────────────────────
sys.path.insert(0, SCRIPT_DIR)
_SUPPORT_DIR = os.path.join(SCRIPT_DIR, "SupportFiles")
if os.path.isdir(_SUPPORT_DIR) and _SUPPORT_DIR not in sys.path:
    sys.path.insert(0, _SUPPORT_DIR)
if os.path.isdir(os.path.join(_SUPPORT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(_SUPPORT_DIR, "IndexData")

from market_signals import build_dashboard_df
from market_engine import (
    RS_PERIODS, SIGNAL_PERIODS, fetch_close_batch, fetch_ohlcv_batch,
    fetch_ohlcv_with_cache, _normalize, calc_rs, calc_rsi, build_sector_strength,
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
#  UK MARKET CONFIG
# ─────────────────────────────────────────────────────────────────────────────

UK_INDEX = "ISF.L"          # iShares Core FTSE 100 ETF — liquid, clean closes
UK_INDEX_FALLBACK = "^FTSE" # fallback if ISF.L fails

# iShares UK sector ETFs (Yahoo Finance tickers, .L suffix)
UK_SECTORS = {
    "Financials":             {"yahoo": "IUKF.L",  "csv": None},
    "Health Care":            {"yahoo": "IUHC.L",  "csv": None},
    "Energy":                 {"yahoo": "IUEL.L",  "csv": None},
    "Materials":              {"yahoo": "IUMB.L",  "csv": None},
    "Consumer Staples":       {"yahoo": "IUCS.L",  "csv": None},
    "Consumer Discretionary": {"yahoo": "IUCD.L",  "csv": None},
    "Technology":             {"yahoo": "IUIT.L",  "csv": None},
    "Industrials":            {"yahoo": "IUIN.L",  "csv": None},
    "Utilities":              {"yahoo": "IUUT.L",  "csv": None},
    "Communication Services": {"yahoo": "IUCT.L",  "csv": None},
    "Real Estate":            {"yahoo": "IUPR.L",  "csv": None},
}

UK_INDUSTRY_TO_SECTOR = {
    "Financials": "Financials", "Banking": "Financials",
    "Insurance": "Financials", "Asset Management": "Financials",
    "Healthcare": "Health Care", "Pharmaceuticals": "Health Care",
    "Biotechnology": "Health Care", "Medical Devices": "Health Care",
    "Energy": "Energy", "Oil & Gas": "Energy",
    "Materials": "Materials", "Mining": "Materials",
    "Metals": "Materials", "Chemicals": "Materials",
    "Consumer Staples": "Consumer Staples", "Food & Beverage": "Consumer Staples",
    "Tobacco": "Consumer Staples", "Household Products": "Consumer Staples",
    "ConsumerDisc": "Consumer Discretionary", "Retail": "Consumer Discretionary",
    "Leisure": "Consumer Discretionary", "Travel": "Consumer Discretionary",
    "Technology": "Technology", "Software": "Technology",
    "IT Services": "Technology",
    "Industrials": "Industrials", "Aerospace": "Industrials",
    "Defence": "Industrials", "Engineering": "Industrials",
    "Utilities": "Utilities", "Water": "Utilities", "Gas": "Utilities",
    "CommServices": "Communication Services", "Telecoms": "Communication Services",
    "Media": "Communication Services",
    "RealEstate": "Real Estate", "Property": "Real Estate", "REITs": "Real Estate",
}

UK_BREADTH_INDICES = {
    "FTSE 100":  {"yahoo": "^FTSE",  "csv": None},
    "FTSE 250":  {"yahoo": "^FTMC",  "csv": None},
    "FTSE 350":  {"yahoo": "^FTLC",  "csv": "uk_ftse350list.csv"},
    "FTSE AIM":  {"yahoo": "^FTAI",  "csv": None},
}

UK_SNAPSHOT_TICKERS = [
    {"name": "FTSE 100",          "ticker": "^FTSE",    "type": "Index"},
    {"name": "FTSE 250",          "ticker": "^FTMC",    "type": "Index"},
    {"name": "FTSE All-Share",    "ticker": "^FTAS",    "type": "Index"},
    {"name": "UK VIX",            "ticker": "^VFTSE",   "type": "Volatility"},
    {"name": "iShares FTSE 100",  "ticker": "ISF.L",    "type": "ETF"},
    {"name": "GBP/USD",           "ticker": "GBPUSD=X", "type": "Forex"},
    {"name": "GBP/EUR",           "ticker": "GBPEUR=X", "type": "Forex"},
    {"name": "EUR/GBP",           "ticker": "EURGBP=X", "type": "Forex"},
    {"name": "DXY (USD Index)",   "ticker": "DX-Y.NYB", "type": "Forex"},
    {"name": "10Y Gilt Yield",    "ticker": "^TNX",     "type": "Bond"},
    {"name": "Gold",              "ticker": "GC=F",     "type": "Commodity"},
    {"name": "Crude Oil Brent",   "ticker": "BZ=F",     "type": "Commodity"},
    {"name": "Natural Gas",       "ticker": "NG=F",     "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS COLOUR PALETTE  (same as India v6.0)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS API HELPERS  (identical pattern to India/USA scripts)
# ─────────────────────────────────────────────────────────────────────────────

def load_uk_universe():
    """
    Load the FTSE 350 stock universe from CSV.
    Adds .L suffix for Yahoo Finance, maps industry → sector.
    Returns a DataFrame with columns: Symbol, Yahoo, Company, Industry, Sector
    """
    if not os.path.exists(STOCK_CSV):
        print(f"  ❌ Universe CSV not found: {STOCK_CSV}")
        return pd.DataFrame()

    df = pd.read_csv(STOCK_CSV)
    df.columns = df.columns.str.strip()

    if "Symbol" not in df.columns:
        print("  ❌ 'Symbol' column missing from UK CSV")
        return pd.DataFrame()

    # Filter equity series only
    if "Series" in df.columns:
        df = df[df["Series"].str.strip().str.upper().isin(["EQ", ""])]

    df = df.head(MAX_STOCKS).copy()
    df["Symbol"]   = df["Symbol"].str.strip()
    df["Yahoo"]    = df["Symbol"] # + ".L"          # FTSE tickers need .L suffix
    df["Company"]  = df.get("Company Name", df["Symbol"])
    df["Industry"] = df.get("Industry", "").fillna("").str.strip()
    df["Sector"]   = df["Industry"].map(UK_INDUSTRY_TO_SECTOR).fillna(df["Industry"])
    df["Sector"]   = df["Sector"].replace("", "Other").fillna("Other")

    print(f"  ✅ UK Universe: {len(df)} stocks loaded")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR PRICE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_uk_sector_prices():
    """
    Fetch UK sector ETF price series.
    Falls back to computing equal-weight sector composites from stock prices
    if ETF data is unavailable (common for some iShares .L ETFs on Yahoo).
    """
    result = {}
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS + 5)

    for sec_name, cfg in UK_SECTORS.items():
        ticker = cfg.get("yahoo")
        if not ticker:
            continue
        try:
            raw = yf.download(ticker,
                              start=start.strftime("%Y-%m-%d"),
                              end=end.strftime("%Y-%m-%d"),
                              auto_adjust=True, progress=False)
            if raw.empty:
                continue
            cl = raw["Close"]
            if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
            s = _normalize(cl.dropna())
            if len(s) >= 22:
                result[sec_name] = s
        except Exception:
            pass

    print(f"  ✅ UK Sector prices: {len(result)}/{len(UK_SECTORS)} from ETFs")
    return result


def fill_missing_sector_prices(universe, price_data, sector_prices, sectors_cfg):
    """Build synthetic equal-weight composites for any sector missing an ETF price series."""
    added = []
    for sector in sectors_cfg:
        if sector in sector_prices:
            continue
        syms = universe[universe["Sector"] == sector]["Yahoo"].tolist()
        valid = [s for s in syms if s in price_data.columns
                 and len(price_data[s].dropna()) >= 22]
        if len(valid) < 2:
            continue
        composite = price_data[valid].dropna(how="all").mean(axis=1).dropna()
        if len(composite) >= 22:
            sector_prices[sector] = _normalize(composite)
            added.append(sector)
    if added:
        print(f"  ✅ Synthetic sector prices built for: {added}")
    return sector_prices


# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT  (UK-specific tickers)
# ─────────────────────────────────────────────────────────────────────────────

def build_uk_snapshot():
    """Build market snapshot using UK-specific tickers."""
    from market_engine import pct_change_n, safe_download
    import numpy as np

    syms = [t["ticker"] for t in UK_SNAPSHOT_TICKERS]
    try:
        raw = safe_download(syms, days=10, auto_adjust=True, progress=False)
        cdf = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex) and len(syms) == 1:
            cdf.columns = syms
    except Exception:
        cdf = pd.DataFrame()

    rows = []
    for t in UK_SNAPSHOT_TICKERS:
        sym = t["ticker"]
        price = chg1 = chg5 = np.nan
        trend = "N/A"
        try:
            if sym in cdf.columns:
                col = cdf[sym].dropna()
                if len(col) >= 2:
                    price = round(float(col.iloc[-1]), 2)
                    chg1  = round(pct_change_n(col, 1), 2)
                if len(col) >= 5:
                    chg5 = round(pct_change_n(col, 4), 2)
                if not np.isnan(chg1) and not np.isnan(chg5):
                    if   chg1 > 0 and chg5 > 0: trend = "↑ Bullish"
                    elif chg1 < 0 and chg5 < 0: trend = "↓ Bearish"
                    elif chg5 > 0:               trend = "→ Recovering"
                    else:                        trend = "→ Pulling Back"
        except Exception:
            pass
        rows.append({"Name": t["name"], "Type": t["type"],
                     "Price": price, "Chg_1D%": chg1, "Chg_5D%": chg5, "Trend": trend})

    df = pd.DataFrame(rows)
    idxs    = df[df["Type"] == "Index"]["Chg_1D%"].dropna()
    pct_up  = (idxs > 0).mean() * 100 if len(idxs) > 0 else 50
    bias    = "BULLISH" if pct_up >= 70 else ("BEARISH" if pct_up < 40 else "MIXED")
    summary = pd.DataFrame([{
        "Name": f"── MACRO BIAS: {bias} ({len(idxs)} indices, {pct_up:.0f}% green) ──",
        "Type": "Summary", "Price": np.nan, "Chg_1D%": np.nan, "Chg_5D%": np.nan, "Trend": bias
    }])
    return pd.concat([df, summary], ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS
    _mode = _me.prompt_run_mode(ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS)
    ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS = (
        _mode["patterns"], _mode["financials"], _mode["signals"])

    print("\n" + "═" * 68)
    print("  UK MARKET — HTML-ONLY EDITION  v1.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M GMT')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("═" * 68 + "\n")
    t0 = time.time()

    # ── Connect ────────────────────────────────────────────────────────────────

    # ── Universe ───────────────────────────────────────────────────────────────
    print("📂 Loading UK universe …"); universe = load_uk_universe()
    if universe.empty:
        print("❌ Empty universe — aborting."); return

    # ── Index prices ───────────────────────────────────────────────────────────
    print(f"\n📡 Fetching index ({UK_INDEX}) …")
    end_dt   = datetime.today() + timedelta(days=1)
    start_dt = end_dt - timedelta(days=PERIOD_DAYS + 5)
    raw = yf.download(UK_INDEX,
                      start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"),
                      auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  ⚠ {UK_INDEX} empty, trying fallback {UK_INDEX_FALLBACK} …")
        raw = yf.download(UK_INDEX_FALLBACK,
                          start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"),
                          auto_adjust=True, progress=False)
    if raw.empty:
        print("  ❌ Cannot fetch UK index"); return

    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame): cl = cl.squeeze()
    index_prices = _normalize(cl.dropna())
    print(f"  ✅ Index: {len(index_prices)} days")

    # ── Sector prices ──────────────────────────────────────────────────────────
    print("\n📡 UK Sector ETFs …"); sector_prices = fetch_uk_sector_prices()

    # ── Stock closes ───────────────────────────────────────────────────────────
    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    # Fill any sector missing an ETF with equal-weight stock composite
    print("📡 Filling missing sector prices from stock composites …")
    sector_prices = fill_missing_sector_prices(universe, price_data, sector_prices, UK_SECTORS)

    # ── OHLCV ──────────────────────────────────────────────────────────────────
    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        print(f"\n📡 Fetching OHLCV for {max_ohlcv} stocks …")
        cands = [s for s in stock_syms
                 if s in price_data.columns and len(price_data[s].dropna()) >= 60][:max_ohlcv]
        try:    ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  ✅ OHLCV: {len(ohlcv_dict)} stocks")

    # ── Chart patterns ─────────────────────────────────────────────────────────
    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        print("\n📐 Detecting chart patterns …")
        pat_dict = {k: v for k, v in ohlcv_dict.items() if len(v) >= 60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    # ── Timestamp ──────────────────────────────────────────────────────────────
    gmt_tz   = timezone(timedelta(hours=0))
    run_time = datetime.now(gmt_tz).strftime("%d %B %Y %H:%M GMT")

    # ── Build all DataFrames ───────────────────────────────────────────────────
    print("\n📸 Market Snapshot …");   snap_df     = build_uk_snapshot()
    print("🏭 Sector Strength …");    sec_str_df  = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df  = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df  = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df  = build_market_breadth(
        price_data, index_prices, UK_BREADTH_INDICES, INDEX_DATA_DIR, market="UK")
    print("📈 Sector Performance …"); sec_perf_df = build_sector_performance(
        sector_prices, index_prices)
    print("📊 Stock Strength + Signals + Financials …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices,
        patterns_by_sym, market="UK",
        fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD,
    )
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="UK", primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="UK", primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="UK")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="UK", primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR,
        market="UK", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)

    dashboard_df = build_dashboard_df(stock_df, sec_str_df, "UK", run_time,
                                      primary_rs=PRIMARY_RS_PERIOD)

    rrg_html = None
    try:
        from market_rrg import build_rrg_data, build_rrg_section, make_sector_colors as _rrg_colors
        _rrg_d = build_rrg_data(sector_prices, index_prices)
        _sl = list((_rrg_d.get("weekly") or _rrg_d.get("daily", {})))
        rrg_html = build_rrg_section(_rrg_d, _sl, _rrg_colors(_sl), market_code="UK")
    except Exception as _e:
        print(f"  RRG skipped: {_e}")

    print("\n🌐 Building UK HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "UK.html")
        build_html_report(
            market="UK",
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
        print(f"  ✅ HTML: {html_path}")
    except Exception as e:
        print(f"  ⚠ HTML skipped: {e}")

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'═' * 68}")
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  📄 UK.html")
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
    print("═" * 68)


if __name__ == "__main__":
    main()
