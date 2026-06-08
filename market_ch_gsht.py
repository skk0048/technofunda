"""
SWITZERLAND MARKET ANALYSIS — HTML-ONLY EDITION  v2.0
market_ch_gsht.py  — NO Google Sheets, generates CH.html only

Universe  : ch_smilist.csv
Benchmark : ^SSMI
Timezone  : CET
Output    : CH.html

Sheets-free variant: runs full RS/trend/financial analysis, writes ONLY HTML.
No Google credentials required. Runs in ~1-2 minutes.
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

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "ch_all_stocks_master.csv")

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
    build_sector_strength, build_sector_rotation, build_industry_rotation,
    build_market_breadth, build_sector_performance, build_stock_strength,
    build_top_picks_buy, build_top_picks_sell, build_chart_patterns_df,
    build_trade_setups, run_pattern_detection, build_rs_sleeve_list,
    build_country_etf_df, build_commodity_df,
)
import market_engine as _me
try:
    from price_cache import CACHE_DIR as _CACHE_DIR
    _me.set_cache_dir(_CACHE_DIR)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
#  SWITZERLAND CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CH_INDEX          = "^SSMI"
CH_INDEX_FALLBACK = "^SMI"

CH_INDUSTRY_TO_SECTOR = {
    "Financials": "Financials", "Banking": "Financials",
    "Insurance": "Financials", "Asset Management": "Financials",
    "Energy": "Energy", "Oil & Gas": "Energy",
    "Materials": "Materials", "Mining": "Materials",
    "Gold": "Materials", "Metals": "Materials", "Chemicals": "Materials",
    "Technology": "Technology", "Software": "Technology",
    "IT Services": "Technology", "Electronics": "Technology",
    "Semiconductors": "Technology",
    "Healthcare": "Health Care", "Pharmaceuticals": "Health Care",
    "Biotechnology": "Health Care", "Medical Devices": "Health Care",
    "Industrials": "Industrials", "Railways": "Industrials",
    "Aerospace": "Industrials", "Engineering": "Industrials",
    "Machinery": "Industrials", "Shipbuilding": "Industrials",
    "ConsumerDisc": "Consumer Discretionary", "Retail": "Consumer Discretionary",
    "Automotive": "Consumer Discretionary", "Luxury": "Consumer Discretionary",
    "Consumer Staples": "Consumer Staples", "Food & Beverage": "Consumer Staples",
    "Utilities": "Utilities", "Power": "Utilities",
    "CommServices": "Communication Services", "Telecoms": "Communication Services",
    "Media": "Communication Services",
    "RealEstate": "Real Estate", "REITs": "Real Estate",
}

CH_BREADTH_INDICES = {
    "SMI": {"yahoo": "^SSMI", "csv": "ch_smilist.csv"},
    "Euro Stoxx": {"yahoo": "^STOXX50E", "csv": None},
}

CH_SNAPSHOT_TICKERS = [
    {"name": "SMI",                     "ticker": "^SSMI",         "type": "Index"},
    {"name": "Euro Stoxx 50",           "ticker": "^STOXX50E",     "type": "Index"},
    {"name": "DAX 40",                  "ticker": "^GDAXI",        "type": "Index"},
    {"name": "CHF/USD",                 "ticker": "CHF=X",         "type": "Forex"},
    {"name": "EUR/CHF",                 "ticker": "EURCHF=X",      "type": "Forex"},
    {"name": "DXY (USD Index)",         "ticker": "DX-Y.NYB",      "type": "Forex"},
    {"name": "10Y Swiss Yield",         "ticker": "^TNX",          "type": "Bond"},
    {"name": "Gold",                    "ticker": "GC=F",          "type": "Commodity"},
    {"name": "Crude Brent",             "ticker": "BZ=F",          "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  UNIVERSE LOADER  (France pattern — keeps Industry + Symbol + Yahoo + Sector)
# ─────────────────────────────────────────────────────────────────────────────

def load_ch_universe():
    csv_path = os.path.join(INDEX_DATA_DIR, "ch_smilist.csv")
    if not os.path.exists(csv_path):
        csv_path = STOCK_CSV
    if not os.path.exists(csv_path):
        print(f"  Universe CSV not found: {csv_path}"); return pd.DataFrame()
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = df.columns.str.strip()
    if "Symbol" not in df.columns:
        print("  'Symbol' column missing"); return pd.DataFrame()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip().str.upper().isin(["EQ", ""])]
    df = df.head(MAX_STOCKS).copy()
    df["Symbol"]   = df["Symbol"].astype(str).str.strip()
    df["Yahoo"]    = df["Symbol"]
    df["Company"]  = df.get("Company Name", df["Symbol"])
    df["Industry"] = df.get("Industry", "").astype(str).fillna("").str.strip()
    df["Sector"]   = df["Industry"].map(CH_INDUSTRY_TO_SECTOR).fillna("Other")
    df = df.dropna(subset=["Yahoo"])
    print(f"  Universe: {len(df)} stocks loaded")
    return df.reset_index(drop=True)


# Switzerland sector ETFs — no liquid Yahoo-accessible ETFs; synthetic composites via fill_missing_sector_prices
CH_SECTORS = {
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

def fetch_ch_sector_prices():
    result = {}
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS + 5)
    for sec_name, cfg in CH_SECTORS.items():
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
    print(f"  ✅ Switzerland Sector prices: {len(result)}/{len(CH_SECTORS)}")
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



def build_ch_snapshot():
    from market_engine import pct_change_n, safe_download
    syms = [t["ticker"] for t in CH_SNAPSHOT_TICKERS]
    try:
        raw = safe_download(syms, days=10, auto_adjust=True, progress=False)
        cdf = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex) and len(syms)==1: cdf.columns=syms
    except Exception: cdf = pd.DataFrame()
    rows = []
    for t in CH_SNAPSHOT_TICKERS:
        sym = t["ticker"]; price=chg1=chg5=np.nan; trend="N/A"
        try:
            if sym in cdf.columns:
                col=cdf[sym].dropna()
                if len(col)>=2: price=round(float(col.iloc[-1]),2); chg1=round(pct_change_n(col,1),2)
                if len(col)>=5: chg5=round(pct_change_n(col,4),2)
                if not np.isnan(chg1) and not np.isnan(chg5):
                    if   chg1>0 and chg5>0: trend="Bullish"
                    elif chg1<0 and chg5<0: trend="Bearish"
                    elif chg5>0:            trend="Recovering"
                    else:                   trend="Pulling Back"
        except Exception: pass
        rows.append({"Name":t["name"],"Type":t["type"],"Price":price,"Chg_1D%":chg1,"Chg_5D%":chg5,"Trend":trend})
    df     = pd.DataFrame(rows)
    idxs   = df[df["Type"]=="Index"]["Chg_1D%"].dropna()
    pct_up = (idxs>0).mean()*100 if len(idxs)>0 else 50
    bias   = "BULLISH" if pct_up>=70 else ("BEARISH" if pct_up<40 else "MIXED")
    return pd.concat([df, pd.DataFrame([{
        "Name":f"MACRO BIAS: {bias} ({len(idxs)} indices, {pct_up:.0f}% green)",
        "Type":"Summary","Price":np.nan,"Chg_1D%":np.nan,"Chg_5D%":np.nan,"Trend":bias
    }])], ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN  (HTML-only)
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
    print(f"  SWITZERLAND MARKET — HTML-ONLY  v2.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M CET')}")
    print("="*68+"\n")
    t0 = time.time()

    print(f"Loading Switzerland universe ..."); universe = load_ch_universe()
    if universe.empty: print("Empty universe — aborting."); return

    print(f"Fetching index ({CH_INDEX}) ...")
    end_dt  = datetime.today() + timedelta(days=1)
    start_dt= end_dt - timedelta(days=PERIOD_DAYS+5)
    raw = yf.download(CH_INDEX, start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  {CH_INDEX} empty, trying {CH_INDEX_FALLBACK} ...")
        raw = yf.download(CH_INDEX_FALLBACK, start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty: print(f"  Cannot fetch Switzerland index"); return
    cl = raw["Close"]
    # squeeze only columns (axis=1) — never rows — so a 1-row result stays a Series
    if isinstance(cl, pd.DataFrame):
        cl = cl.iloc[:, 0] if cl.shape[1] >= 1 else cl.squeeze()
    cl = pd.Series(cl).dropna()
    index_prices = _normalize(cl)
    print(f"  Index: {len(index_prices)} days")

    sector_prices = fetch_ch_sector_prices()
    stock_syms = universe["Yahoo"].tolist()
    print(f"Fetching {len(stock_syms)} stock closes ...")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  Stocks: {len(price_data.columns)} loaded")
    # Fill any sector missing an ETF with equal-weight stock composite
    print("📡 Filling missing sector prices from stock composites …")
    sector_prices = fill_missing_sector_prices(universe, price_data, sector_prices, CH_SECTORS)

    ohlcv_dict = {}
    max_ohlcv  = max(PATTERN_MAX, SIGNAL_MAX_STOCKS if ENABLE_SIGNALS else 0)
    if max_ohlcv > 0:
        cands = [s for s in stock_syms if s in price_data.columns
                 and len(price_data[s].dropna()) >= 60][:max_ohlcv]
        try:    ohlcv_dict = fetch_ohlcv_with_cache(cands, days=PERIOD_DAYS)
        except: ohlcv_dict = fetch_ohlcv_batch(cands, days=PERIOD_DAYS)
        print(f"  OHLCV: {len(ohlcv_dict)} stocks")

    patterns_by_sym = {}; patterns_list = []
    if ENABLE_PATTERNS:
        pat_dict = {k: v for k, v in ohlcv_dict.items() if len(v) >= 60}
        patterns_by_sym, patterns_list = run_pattern_detection(pat_dict)

    tz_obj   = timezone(timedelta(hours=1))
    run_time = datetime.now(tz_obj).strftime(f"%d %B %Y %H:%M CET")

    snap_df    = build_ch_snapshot()
    sec_str_df = build_sector_strength(universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    sec_rot_df = build_sector_rotation(universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    ind_rot_df = build_industry_rotation(universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    breadth_df = build_market_breadth(price_data, index_prices, CH_BREADTH_INDICES, INDEX_DATA_DIR, market="ch")
    sec_perf_df= build_sector_performance(sector_prices, index_prices)
    stock_df = build_stock_strength(universe, price_data, index_prices, sector_prices, patterns_by_sym,
        market="ch", fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {}, primary_rs=PRIMARY_RS_PERIOD)
    top_buy_df  = build_top_picks_buy(stock_df, sec_str_df, market="ch", primary_rs=PRIMARY_RS_PERIOD)
    top_sell_df = build_top_picks_sell(stock_df, sec_str_df, market="ch", primary_rs=PRIMARY_RS_PERIOD)
    chart_df    = build_chart_patterns_df(patterns_list, stock_df, market="ch")
    trade_df    = build_trade_setups(stock_df, sec_str_df, market="ch", primary_rs=PRIMARY_RS_PERIOD)
    sleeve_df   = build_rs_sleeve_list(stock_df, universe, INDEX_DATA_DIR, market="ch", run_time=run_time,
        index_prices=index_prices, price_data=price_data, ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df   = build_dashboard_df(stock_df, sec_str_df, "ch", run_time, primary_rs=PRIMARY_RS_PERIOD)

    print("Building Switzerland HTML report ...")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "CH.html")
        build_html_report(
            market="ch", snapshot_df=snap_df, sector_str_df=sec_str_df,
            sector_rot_df=sec_rot_df, industry_rot_df=ind_rot_df,
            breadth_df=breadth_df, sector_perf_df=sec_perf_df, stock_str_df=stock_df,
            top_buy_df=top_buy_df, top_sell_df=top_sell_df,
            chart_pat_df=chart_df, trade_df=trade_df,
            dashboard_df=dashboard_df, sleeve_df=sleeve_df,
            country_etf_df=country_etf_df, commodity_df=commodity_df,
            output_path=html_path, run_time=run_time, primary_rs=PRIMARY_RS_PERIOD)
        print(f"  HTML: {html_path}")
    except Exception as e:
        print(f"  HTML generation failed: {e}")
        import traceback; traceback.print_exc()

    elapsed = time.time() - t0
    print(f"\n{'='*68}")
    print(f"  COMPLETE!  |  {elapsed:.0f}s  |  CH.html")
    print("="*68)


if __name__ == "__main__":
    main()
