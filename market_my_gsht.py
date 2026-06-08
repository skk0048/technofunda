"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MALAYSIA MARKET ANALYSIS — HTML-ONLY EDITION  v1.0                            ║
║  market_my_gsht.py  — NO Google Sheets, generates MY.html only       ║
║                                                                              ║
║  Universe  : my_klcilist.csv                                                           ║
║  Benchmark : ^KLSE                                                         ║
║  Timezone  : MYT                                                            ║
║  Output    : MY.html                                                    ║
║                                                                              ║
║  This is a Sheets-free variant: it runs the full RS/trend/financial          ║
║  analysis and writes ONLY the HTML report. No credentials required.          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, warnings, logging
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta, timezone
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('peewee').setLevel(logging.CRITICAL)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists(os.path.join(SCRIPT_DIR, "IndexData")):
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "IndexData")
else:
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "SupportFiles", "IndexData")

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "my_all_stocks_master.csv")

MAX_STOCKS        = 500
PERIOD_DAYS       = 504
ENABLE_PATTERNS   = True
PATTERN_MAX       = 300
FETCH_FINANCIALS  = True
ENABLE_SIGNALS    = True
SIGNAL_MAX_STOCKS = 500
PRIMARY_RS_PERIOD = 22

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
    load_csv_constituents, build_sector_strength,
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
#  MALAYSIA MARKET CONFIG
# ─────────────────────────────────────────────────────────────────────────────

MY_INDEX          = "^KLSE"
MY_INDEX_FALLBACK = "^KLCI"

MY_INDUSTRY_TO_SECTOR = {
    "Financials":"Financials","Banking":"Financials","Insurance":"Financials",
    "Asset Management":"Financials","Energy":"Energy","Oil & Gas":"Energy",
    "Materials":"Materials","Mining":"Materials","Gold":"Materials",
    "Metals":"Materials","Chemicals":"Materials","Technology":"Technology",
    "Software":"Technology","IT Services":"Technology","Electronics":"Technology",
    "Semiconductors":"Technology","Healthcare":"Healthcare",
    "Pharmaceuticals":"Healthcare","Biotechnology":"Healthcare",
    "Medical Devices":"Healthcare","Industrials":"Industrials",
    "Railways":"Industrials","Aerospace":"Industrials","Engineering":"Industrials",
    "Machinery":"Industrials","Shipbuilding":"Industrials",
    "ConsumerDisc":"ConsumerDisc","Retail":"ConsumerDisc",
    "Automotive":"ConsumerDisc","Luxury":"ConsumerDisc",
    "Consumer Staples":"Consumer Staples","Food & Beverage":"Consumer Staples",
    "Utilities":"Utilities","Power":"Utilities","CommServices":"CommServices",
    "Telecoms":"CommServices","Media":"CommServices","RealEstate":"RealEstate",
    "REITs":"RealEstate",
}

MY_BREADTH_INDICES = {
    "KLCI": {"yahoo": "^KLSE", "csv": "my_klcilist.csv"},
}

MY_SNAPSHOT_TICKERS = [
    {"name": "KLCI",                    "ticker": "^KLSE",         "type": "Index"},
    {"name": "Straits Times",           "ticker": "^STI",          "type": "Index"},
    {"name": "Jakarta Comp",            "ticker": "^JKSE",         "type": "Index"},
    {"name": "MYR/USD",                 "ticker": "MYR=X",         "type": "Forex"},
    {"name": "USD/MYR",                 "ticker": "USDMYR=X",      "type": "Forex"},
    {"name": "DXY (USD Index)",         "ticker": "DX-Y.NYB",      "type": "Forex"},
    {"name": "10Y MGS Yield",           "ticker": "^TNX",          "type": "Bond"},
    {"name": "Gold",                    "ticker": "GC=F",          "type": "Commodity"},
    {"name": "Crude Brent",             "ticker": "BZ=F",          "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  UNIVERSE LOADER  (France pattern — keeps Industry + Symbol + Yahoo + Sector)
# ─────────────────────────────────────────────────────────────────────────────

def load_my_universe():
    csv_path = os.path.join(INDEX_DATA_DIR, "my_klcilist.csv")
    if not os.path.exists(csv_path):
        csv_path = STOCK_CSV
    if not os.path.exists(csv_path):
        print(f"  \u274c Universe CSV not found: {csv_path}"); return pd.DataFrame()
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = df.columns.str.strip()
    if "Symbol" not in df.columns:
        print("  \u274c 'Symbol' column missing"); return pd.DataFrame()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip().str.upper().isin(["EQ", ""])]
    df = df.head(MAX_STOCKS).copy()
    df["Symbol"]   = df["Symbol"].astype(str).str.strip()
    df["Yahoo"]    = df["Symbol"]
    df["Company"]  = df.get("Company Name", df["Symbol"])
    df["Industry"] = df.get("Industry", "").astype(str).fillna("").str.strip()
    df["Sector"]   = df["Industry"].map(MY_INDUSTRY_TO_SECTOR).fillna("Other")
    df = df.dropna(subset=["Yahoo"])
    print(f"  \u2705 Universe: {len(df)} stocks loaded")
    return df.reset_index(drop=True)


# Malaysia sector ETFs — no liquid Yahoo-accessible ETFs; synthetic composites via fill_missing_sector_prices
MY_SECTORS = {
    "Financials":             {"yahoo": None, "csv": None},
    "Energy":                 {"yahoo": None, "csv": None},
    "Materials":              {"yahoo": None, "csv": None},
    "Technology":             {"yahoo": None, "csv": None},
    "Health Care":            {"yahoo": None, "csv": None},
    "Industrials":            {"yahoo": None, "csv": None},
    "Consumer Discretionary": {"yahoo": None, "csv": None},
    "Consumer Staples":       {"yahoo": None, "csv": None},
    "Utilities":              {"yahoo": None, "csv": None},
    "Communication Services": {"yahoo": None, "csv": None},
    "Real Estate":            {"yahoo": None, "csv": None},
}

def fetch_my_sector_prices():
    result = {}
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS + 5)
    for sec_name, cfg in MY_SECTORS.items():
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
    print(f"  ✅ Malaysia Sector prices: {len(result)}/{len(MY_SECTORS)}")
    return result

def fill_missing_sector_prices(universe, price_data, sector_prices, sectors_cfg):
    """
    For every sector in sectors_cfg that is missing from sector_prices,
    build a synthetic equal-weight composite from constituent stocks.
    """
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



def build_my_snapshot():
    from market_engine import pct_change_n, safe_download
    syms = [t["ticker"] for t in MY_SNAPSHOT_TICKERS]
    try:
        raw = safe_download(syms, days=10, auto_adjust=True, progress=False)
        cdf = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex) and len(syms)==1: cdf.columns=syms
    except Exception: cdf = pd.DataFrame()
    rows = []
    for t in MY_SNAPSHOT_TICKERS:
        sym = t["ticker"]; price=chg1=chg5=np.nan; trend="N/A"
        try:
            if sym in cdf.columns:
                col=cdf[sym].dropna()
                if len(col)>=2: price=round(float(col.iloc[-1]),2); chg1=round(pct_change_n(col,1),2)
                if len(col)>=5: chg5=round(pct_change_n(col,4),2)
                if not np.isnan(chg1) and not np.isnan(chg5):
                    if   chg1>0 and chg5>0: trend="\u2191 Bullish"
                    elif chg1<0 and chg5<0: trend="\u2193 Bearish"
                    elif chg5>0:            trend="\u2192 Recovering"
                    else:                   trend="\u2192 Pulling Back"
        except Exception: pass
        rows.append({"Name":t["name"],"Type":t["type"],"Price":price,"Chg_1D%":chg1,"Chg_5D%":chg5,"Trend":trend})
    df     = pd.DataFrame(rows)
    idxs   = df[df["Type"]=="Index"]["Chg_1D%"].dropna()
    pct_up = (idxs>0).mean()*100 if len(idxs)>0 else 50
    bias   = "BULLISH" if pct_up>=70 else ("BEARISH" if pct_up<40 else "MIXED")
    return pd.concat([df, pd.DataFrame([{
        "Name":f"\u2500\u2500 MACRO BIAS: {bias} ({len(idxs)} indices, {pct_up:.0f}% green) \u2500\u2500",
        "Type":"Summary","Price":np.nan,"Chg_1D%":np.nan,"Chg_5D%":np.nan,"Trend":bias
    }])], ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN  (HTML-only — no Google Sheets)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS
    try:
        _mode = _me.prompt_run_mode(ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS)
        ENABLE_PATTERNS, FETCH_FINANCIALS, ENABLE_SIGNALS = (
            _mode["patterns"], _mode["financials"], _mode["signals"])
    except Exception:
        pass
    print("\n" + "="*68)
    print(f"  MALAYSIA MARKET — HTML-ONLY EDITION  v1.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M MYT')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("="*68+"\n")
    t0 = time.time()

    print(f"\U0001F4C2 Loading Malaysia universe …"); universe = load_my_universe()
    if universe.empty: print("\u274c Empty universe — aborting."); return

    print(f"\n\U0001F4E1 Fetching index ({MY_INDEX}) …")
    end_dt  = datetime.today() + timedelta(days=1)
    start_dt= end_dt - timedelta(days=PERIOD_DAYS+5)
    raw = yf.download(MY_INDEX, start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  \u26a0 {MY_INDEX} empty, trying {MY_INDEX_FALLBACK} …")
        raw = yf.download(MY_INDEX_FALLBACK, start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty: print(f"  \u274c Cannot fetch Malaysia index"); return
    cl = raw["Close"]
    # squeeze only columns (axis=1) — never rows — so a 1-row result stays a Series
    if isinstance(cl, pd.DataFrame):
        cl = cl.iloc[:, 0] if cl.shape[1] >= 1 else cl.squeeze()
    cl = pd.Series(cl).dropna()
    index_prices = _normalize(cl)
    print(f"  \u2705 Index: {len(index_prices)} days")

    print(f"\n\U0001F4E1 Malaysia Sector ETFs …"); sector_prices = fetch_my_sector_prices()

    stock_syms = universe["Yahoo"].tolist()
    print(f"\n\U0001F4E1 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  \u2705 Stocks: {len(price_data.columns)} loaded")
    # Fill any sector missing an ETF with equal-weight stock composite
    print("📡 Filling missing sector prices from stock composites …")
    sector_prices = fill_missing_sector_prices(universe, price_data, sector_prices, MY_SECTORS)

    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        print(f"\n\U0001F4E1 Fetching OHLCV for {max_ohlcv} stocks …")
        cands = [s for s in stock_syms if s in price_data.columns
                 and len(price_data[s].dropna()) >= 60][:max_ohlcv]
        try:    ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  \u2705 OHLCV: {len(ohlcv_dict)} stocks")

    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        print("\n\U0001F4D0 Detecting chart patterns …")
        pat_dict = {k: v for k, v in ohlcv_dict.items() if len(v) >= 60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    tz_obj   = timezone(timedelta(hours=8))
    run_time = datetime.now(tz_obj).strftime(f"%d %B %Y %H:%M MYT")

    print("\n\U0001F4F8 Market Snapshot …");   snap_df    = build_my_snapshot()
    print("\U0001F3ED Sector Strength …");    sec_str_df = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F504 Sector Rotation …");    sec_rot_df = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F3ED Industry Rotation …");  ind_rot_df = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F4CA Market Breadth …");     breadth_df = build_market_breadth(
        price_data, index_prices, MY_BREADTH_INDICES, INDEX_DATA_DIR, market="my")
    print("\U0001F4C8 Sector Performance …"); sec_perf_df= build_sector_performance(
        sector_prices, index_prices)
    print("\U0001F4CA Stock Strength …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices, patterns_by_sym,
        market="my", fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F3C6 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="my", primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F534 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="my", primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F4D0 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="my")
    print("\U0001F3AF Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="my", primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F4CB RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR, market="my", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F30D Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("\U0001F3C5 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df   = build_dashboard_df(stock_df, sec_str_df, "my", run_time,
                                        primary_rs=PRIMARY_RS_PERIOD)

    # ── BUILD HTML (the only output) ──────────────────────────────────────
    print("\n\U0001F310 Building Malaysia HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "MY.html")
        build_html_report(
            market="my", snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD)
        print(f"  \u2705 HTML: {html_path}")
    except Exception as e:
        print(f"  \u274c HTML generation failed: {e}")
        import traceback; traceback.print_exc()

    elapsed = time.time() - t0
    print(f"\n{'='*68}")
    print(f"  \u2705  COMPLETE!  |  \u23f1 {elapsed:.0f}s  |  \U0001F4C4 MY.html")
    if not stock_df.empty:
        sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
        if sl_col:
            prime = int(stock_df[sl_col].astype(str).str.startswith("\U0001F31F").sum())
            conf  = int(stock_df[sl_col].astype(str).str.startswith("\u2705").sum())
            rsbuy = int(stock_df[sl_col].astype(str).str.startswith("\U0001F4C8").sum())
            watch = int(stock_df[sl_col].astype(str).str.startswith("\U0001F441").sum())
            avoid = int(stock_df[sl_col].astype(str).str.startswith("\U0001F534").sum())
            print(f"  Prime:{prime} | Conf:{conf} | RS Buy:{rsbuy} | Watch:{watch} | Avoid:{avoid}")
    print("="*68)


if __name__ == "__main__":
    main()
