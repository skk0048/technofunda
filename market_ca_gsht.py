"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CANADA MARKET ANALYSIS — HTML-ONLY EDITION  v1.0                     ║
║  market_ca_gsht.py  — GitHub Actions compatible                           ║
║                                                                            ║
║  Universe  : ca_tsxlist.csv  (TSX stocks, Yahoo suffix .TO)               ║
║  Benchmark : iShares S&P/TSX 60 ETF (XIU.TO)                              ║
║  Sectors   : iShares TSX sector ETFs                                       ║
║  Timezone  : ET  (TSX market close 16:00 ET)                              ║
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
    INDEX_DATA_DIR = os.path.join(SCRIPT_DIR, "SupportFiles", "IndexData")

STOCK_CSV = os.path.join(INDEX_DATA_DIR, "ca_all_stocks_master.csv")

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
#  CANADA MARKET CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CA_INDEX          = "XIU.TO"      # iShares S&P/TSX 60 ETF — clean, liquid
CA_INDEX_FALLBACK = "^GSPTSE"     # S&P/TSX Composite fallback

# iShares TSX sector ETFs — keys MUST match values produced by CA_INDUSTRY_TO_SECTOR below.
# Using full GICS sector names for consistency.
CA_SECTORS = {
    "Financials":             {"yahoo": "XFN.TO",  "csv": None},
    "Energy":                 {"yahoo": "XEG.TO",  "csv": None},
    "Materials":              {"yahoo": "XMA.TO",  "csv": None},
    "Technology":             {"yahoo": "XIT.TO",  "csv": None},
    "Health Care":            {"yahoo": "XHC.TO",  "csv": None},
    "Industrials":            {"yahoo": "XIN.TO",  "csv": None},
    "Consumer Discretionary": {"yahoo": "XCD.TO",  "csv": None},
    "Consumer Staples":       {"yahoo": "XST.TO",  "csv": None},
    "Utilities":              {"yahoo": "XUT.TO",  "csv": None},
    "Communication Services": {"yahoo": "XCO.TO",  "csv": None},
    "Real Estate":            {"yahoo": "XRE.TO",  "csv": None},
}

# Maps every Industry label that may appear in ca_tsxlist.csv → CA_SECTORS key.
# Covers: GICS exact names, Yahoo Finance names, S&P/TSX classifications,
#         common abbreviations, and alternative spellings.
CA_INDUSTRY_TO_SECTOR = {
    # ── Financials ────────────────────────────────────────────────────────────
    "Financials":                      "Financials",
    "Financial Services":              "Financials",
    "Banking":                         "Financials",
    "Banks":                           "Financials",
    "Insurance":                       "Financials",
    "Life & Health Insurance":         "Financials",
    "Property & Casualty Insurance":   "Financials",
    "Asset Management":                "Financials",
    "Capital Markets":                 "Financials",
    "Diversified Financials":          "Financials",
    "Investment Management":           "Financials",
    "Mortgage Finance":                "Financials",
    "Consumer Finance":                "Financials",
    "Diversified Banks":               "Financials",
    "Financial":                       "Financials",
    # ── Energy ───────────────────────────────────────────────────────────────
    "Energy":                          "Energy",
    "Oil & Gas":                       "Energy",
    "Oil, Gas & Consumable Fuels":     "Energy",
    "Oil Gas & Consumable Fuels":      "Energy",
    "Integrated Oil & Gas":            "Energy",
    "Exploration & Production":        "Energy",
    "Oil & Gas E&P":                   "Energy",
    "Oil & Gas Refining & Marketing":  "Energy",
    "Coal & Consumable Fuels":         "Energy",
    "Natural Gas":                     "Energy",
    # ── Materials ────────────────────────────────────────────────────────────
    "Materials":                       "Materials",
    "Basic Materials":                 "Materials",
    "Mining":                          "Materials",
    "Metals & Mining":                 "Materials",
    "Gold":                            "Materials",
    "Gold Mining":                     "Materials",
    "Silver":                          "Materials",
    "Silver Mining":                   "Materials",
    "Uranium":                         "Materials",
    "Uranium Mining":                  "Materials",
    "Copper":                          "Materials",
    "Metals":                          "Materials",
    "Diversified Metals":              "Materials",
    "Steel":                           "Materials",
    "Iron & Steel":                    "Materials",
    "Chemicals":                       "Materials",
    "Specialty Chemicals":             "Materials",
    "Fertilizers":                     "Materials",
    "Paper & Forest Products":         "Materials",
    "Lumber & Wood Products":          "Materials",
    "Potash":                          "Materials",
    # ── Technology ───────────────────────────────────────────────────────────
    "Technology":                      "Technology",
    "Information Technology":          "Technology",
    "Software":                        "Technology",
    "IT Services":                     "Technology",
    "Semiconductors":                  "Technology",
    "Electronic Equipment":            "Technology",
    "Computer Hardware":               "Technology",
    "Tech Hardware & Equipment":       "Technology",
    "Technology Hardware":             "Technology",
    "Internet Software & Services":    "Technology",
    "Application Software":            "Technology",
    "Systems Software":                "Technology",
    # ── Health Care ──────────────────────────────────────────────────────────
    "Health Care":                     "Health Care",
    "Healthcare":                      "Health Care",
    "Pharmaceuticals":                 "Health Care",
    "Biotechnology":                   "Health Care",
    "Medical Devices":                 "Health Care",
    "Life Sciences Tools":             "Health Care",
    "Managed Health Care":             "Health Care",
    "Health Care Equipment":           "Health Care",
    "Pharma":                          "Health Care",
    "Cannabis":                        "Health Care",
    # ── Industrials ──────────────────────────────────────────────────────────
    "Industrials":                     "Industrials",
    "Railways":                        "Industrials",
    "Railroads":                       "Industrials",
    "Aerospace":                       "Industrials",
    "Aerospace & Defense":             "Industrials",
    "Engineering":                     "Industrials",
    "Industrial Machinery":            "Industrials",
    "Machinery":                       "Industrials",
    "Construction & Engineering":      "Industrials",
    "Building Products":               "Industrials",
    "Commercial Services":             "Industrials",
    "Business Services":               "Industrials",
    "Transportation":                  "Industrials",
    "Air Freight":                     "Industrials",
    "Trucking":                        "Industrials",
    "Marine":                          "Industrials",
    "Waste Management":                "Industrials",
    "Environmental Services":          "Industrials",
    "Human Resource Services":         "Industrials",
    # ── Consumer Discretionary ───────────────────────────────────────────────
    "Consumer Discretionary":          "Consumer Discretionary",
    "ConsumerDisc":                    "Consumer Discretionary",
    "Consumer Cyclical":               "Consumer Discretionary",
    "Retail":                          "Consumer Discretionary",
    "Specialty Retail":                "Consumer Discretionary",
    "Multiline Retail":                "Consumer Discretionary",
    "Internet Retail":                 "Consumer Discretionary",
    "Automotive":                      "Consumer Discretionary",
    "Auto Parts":                      "Consumer Discretionary",
    "Hotels, Restaurants & Leisure":   "Consumer Discretionary",
    "Leisure":                         "Consumer Discretionary",
    "Restaurants":                     "Consumer Discretionary",
    "Textiles, Apparel & Luxury":      "Consumer Discretionary",
    "Homebuilding":                    "Consumer Discretionary",
    "Home Furnishings":                "Consumer Discretionary",
    # ── Consumer Staples ─────────────────────────────────────────────────────
    "Consumer Staples":                "Consumer Staples",
    "Consumer Defensive":              "Consumer Staples",
    "Food & Beverage":                 "Consumer Staples",
    "Food & Staples Retailing":        "Consumer Staples",
    "Beverages":                       "Consumer Staples",
    "Food Products":                   "Consumer Staples",
    "Tobacco":                         "Consumer Staples",
    "Household Products":              "Consumer Staples",
    "Personal Products":               "Consumer Staples",
    "Agriculture":                     "Consumer Staples",
    # ── Utilities ────────────────────────────────────────────────────────────
    "Utilities":                       "Utilities",
    "Electric Utilities":              "Utilities",
    "Power":                           "Utilities",
    "Gas Utilities":                   "Utilities",
    "Multi-Utilities":                 "Utilities",
    "Water Utilities":                 "Utilities",
    "Renewable Energy":                "Utilities",
    "Independent Power":               "Utilities",
    # ── Communication Services ───────────────────────────────────────────────
    "Communication Services":          "Communication Services",
    "CommServices":                    "Communication Services",
    "Telecoms":                        "Communication Services",
    "Telecommunications":              "Communication Services",
    "Wireless Telecom Services":       "Communication Services",
    "Telecom Services":                "Communication Services",
    "Media":                           "Communication Services",
    "Entertainment":                   "Communication Services",
    "Broadcasting":                    "Communication Services",
    "Interactive Media":               "Communication Services",
    # ── Real Estate ──────────────────────────────────────────────────────────
    "Real Estate":                     "Real Estate",
    "RealEstate":                      "Real Estate",
    "REITs":                           "Real Estate",
    "Diversified REITs":               "Real Estate",
    "Retail REITs":                    "Real Estate",
    "Office REITs":                    "Real Estate",
    "Industrial REITs":                "Real Estate",
    "Residential REITs":               "Real Estate",
    "Mortgage REITs":                  "Real Estate",
    "Real Estate Management":          "Real Estate",
    "Property":                        "Real Estate",
}

CA_BREADTH_INDICES = {
    "S&P/TSX 60":        {"yahoo": "^GSPTSE", "csv": None},
    "TSX Composite":     {"yahoo": "^GSPTSE", "csv": "ca_tsxlist.csv"},
    "TSX SmallCap":      {"yahoo": "^TSXV",   "csv": None},
}

CA_SNAPSHOT_TICKERS = [
    {"name": "S&P/TSX Composite",  "ticker": "^GSPTSE",  "type": "Index"},
    {"name": "iShares TSX 60",     "ticker": "XIU.TO",   "type": "ETF"},
    {"name": "TSX Venture",        "ticker": "^TSXV",    "type": "Index"},
    {"name": "S&P 500",            "ticker": "^GSPC",    "type": "Index"},
    {"name": "CAD/USD",            "ticker": "CADUSD=X", "type": "Forex"},
    {"name": "CAD/EUR",            "ticker": "CADEUR=X", "type": "Forex"},
    {"name": "DXY (USD Index)",    "ticker": "DX-Y.NYB", "type": "Forex"},
    {"name": "10Y Canada Bond",    "ticker": "^TNX",     "type": "Bond"},
    {"name": "Gold",               "ticker": "GC=F",     "type": "Commodity"},
    {"name": "Crude Oil WTI",      "ticker": "CL=F",     "type": "Commodity"},
    {"name": "Natural Gas",        "ticker": "NG=F",     "type": "Commodity"},
    {"name": "Copper",             "ticker": "HG=F",     "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS COLOUR PALETTE
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS HELPERS  (identical to UK/India/USA)
# ─────────────────────────────────────────────────────────────────────────────

def load_ca_universe():
    """
    Load Canada universe from ca_tsxlist.csv.
    Industry column is mapped → CA_SECTORS key via CA_INDUSTRY_TO_SECTOR.
    Unmapped industries fall to 'Other' (add them to CA_INDUSTRY_TO_SECTOR if seen).
    """
    if not os.path.exists(STOCK_CSV):
        print(f"  ❌ Universe CSV not found: {STOCK_CSV}"); return pd.DataFrame()
    df = pd.read_csv(STOCK_CSV, dtype=str)
    df.columns = df.columns.str.strip()
    if "Symbol" not in df.columns:
        print("  ❌ 'Symbol' column missing"); return pd.DataFrame()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip().str.upper().isin(["EQ", ""])]
    df = df.head(MAX_STOCKS).copy()
    df["Symbol"]  = df["Symbol"].astype(str).str.strip()
    df["Company"] = df.get("Company Name", df["Symbol"]).fillna(df["Symbol"])
    from ticker_fixer import ensure_yahoo_suffix
    df["Yahoo"]   = df["Symbol"].apply(lambda s: ensure_yahoo_suffix(s, "CA"))
    df["Industry"] = df["Industry"].astype(str).str.strip() if "Industry" in df.columns else ""
    df["Sector"]   = df["Industry"].map(CA_INDUSTRY_TO_SECTOR).fillna("Other")
    df = df[df["Yahoo"].astype(str).str.len() >= 2].copy().reset_index(drop=True)

    sectors = df["Sector"].value_counts()
    unmapped = df[df["Sector"] == "Other"]["Industry"].value_counts()
    print(f"  ✅ CA Universe: {len(df)} stocks | {len(sectors)} sectors")
    for sec, cnt in sectors.items():
        print(f"      {cnt:3d}  {sec}")
    if not unmapped.empty:
        print(f"  ⚠️  Unmapped industries ({len(unmapped)} types) → add to CA_INDUSTRY_TO_SECTOR:")
        for ind, cnt in unmapped.items():
            print(f"      {cnt:3d}  {ind}")
    return df

# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR PRICE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ca_sector_prices():
    result = {}
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS + 5)
    for sec_name, cfg in CA_SECTORS.items():
        ticker = cfg.get("yahoo")
        if not ticker: continue
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
    print(f"  ✅ Canada Sector prices: {len(result)}/{len(CA_SECTORS)}")
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

# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def build_ca_snapshot():
    from market_engine import pct_change_n, safe_download
    syms = [t["ticker"] for t in CA_SNAPSHOT_TICKERS]
    try:
        raw = safe_download(syms, days=10, auto_adjust=True, progress=False)
        cdf = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex) and len(syms)==1: cdf.columns=syms
    except Exception: cdf = pd.DataFrame()
    rows = []
    for t in CA_SNAPSHOT_TICKERS:
        sym = t["ticker"]; price=chg1=chg5=np.nan; trend="N/A"
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
    print("  CANADA MARKET — HTML-ONLY EDITION  v1.0")
    print(f"  {datetime.now().strftime('%d %b %Y  %H:%M ET')}")
    print(f"  Stocks:{MAX_STOCKS}  Patterns:{PATTERN_MAX}  Signals:{SIGNAL_MAX_STOCKS}  RS:{PRIMARY_RS_PERIOD}d")
    print("═"*68+"\n")
    t0 = time.time()

    print("📂 Loading Canada universe …"); universe = load_ca_universe()
    if universe.empty: print("❌ Empty universe — aborting."); return

    print(f"\n📡 Fetching index ({CA_INDEX}) …")
    end_dt=datetime.today()+timedelta(days=1); start_dt=end_dt-timedelta(days=PERIOD_DAYS+5)
    raw = yf.download(CA_INDEX, start=start_dt.strftime("%Y-%m-%d"),
                      end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        print(f"  ⚠ {CA_INDEX} empty, trying {CA_INDEX_FALLBACK} …")
        raw = yf.download(CA_INDEX_FALLBACK, start=start_dt.strftime("%Y-%m-%d"),
                          end=end_dt.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty: print("  ❌ Cannot fetch Canada index"); return
    cl = raw["Close"]
    if isinstance(cl, pd.DataFrame): cl=cl.squeeze()
    index_prices = _normalize(cl.dropna())
    print(f"  ✅ Index: {len(index_prices)} days")

    print("\n📡 Canada Sector ETFs …"); sector_prices = fetch_ca_sector_prices()

    stock_syms = universe["Yahoo"].tolist()
    print(f"\n📡 Fetching {len(stock_syms)} stock closes …")
    price_data = fetch_close_batch(stock_syms, PERIOD_DAYS)
    print(f"  ✅ Stocks: {len(price_data.columns)} loaded")

    # Fill any sector missing an ETF with equal-weight stock composite
    print("📡 Filling missing sector prices from stock composites …")
    sector_prices = fill_missing_sector_prices(universe, price_data, sector_prices, CA_SECTORS)

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

    run_time = datetime.now().strftime("%d %B %Y %H:%M ET")

    print("\n📸 Market Snapshot …");   snap_df    = build_ca_snapshot()
    print("🏭 Sector Strength …");    sec_str_df = build_sector_strength(
        universe, price_data, index_prices, sector_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🔄 Sector Rotation …");    sec_rot_df = build_sector_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("🏭 Industry Rotation …");  ind_rot_df = build_industry_rotation(
        universe, price_data, index_prices, primary_rs=PRIMARY_RS_PERIOD)
    print("📊 Market Breadth …");     breadth_df = build_market_breadth(
        price_data, index_prices, CA_BREADTH_INDICES, INDEX_DATA_DIR, market="CA")
    print("📈 Sector Performance …"); sec_perf_df= build_sector_performance(
        sector_prices, index_prices)
    print("📊 Stock Strength …")
    stock_df = build_stock_strength(
        universe, price_data, index_prices, sector_prices, patterns_by_sym,
        market="CA", fetch_financials=FETCH_FINANCIALS,
        ohlcv_dict=ohlcv_dict if ENABLE_SIGNALS else {},
        primary_rs=PRIMARY_RS_PERIOD)
    print("🏆 Top Picks – Buy …");    top_buy_df  = build_top_picks_buy(
        stock_df, sec_str_df, market="CA", primary_rs=PRIMARY_RS_PERIOD)
    print("🔴 Top Picks – Sell …");   top_sell_df = build_top_picks_sell(
        stock_df, sec_str_df, market="CA", primary_rs=PRIMARY_RS_PERIOD)
    print("📐 Chart Patterns …");     chart_df    = build_chart_patterns_df(
        patterns_list, stock_df, market="CA")
    print("🎯 Trade Setups …");       trade_df    = build_trade_setups(
        stock_df, sec_str_df, market="CA", primary_rs=PRIMARY_RS_PERIOD)
    print("📋 RS Sleeve Lists …");    sleeve_df   = build_rs_sleeve_list(
        stock_df, universe, INDEX_DATA_DIR, market="CA", run_time=run_time,
        index_prices=index_prices, price_data=price_data,
        ohlcv_dict=ohlcv_dict, primary_rs=PRIMARY_RS_PERIOD)
    print("🌍 Country ETF Strength …")
    country_etf_df = build_country_etf_df(index_prices, period_days=PERIOD_DAYS,
                                           primary_rs=PRIMARY_RS_PERIOD)
    print("🏅 Commodity Strength …")
    commodity_df   = build_commodity_df(period_days=PERIOD_DAYS, primary_rs=PRIMARY_RS_PERIOD)
    dashboard_df   = build_dashboard_df(stock_df, sec_str_df, "CA", run_time,
                                        primary_rs=PRIMARY_RS_PERIOD)

    print("\n🌐 Building Canada HTML report …")
    try:
        from market_html import build_html_report
        html_path = os.path.join(SCRIPT_DIR, "CA.html")
        build_html_report(
            market="CA", snapshot_df=snap_df, sector_str_df=sec_str_df,
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
    print(f"  ✅  COMPLETE!  |  ⏱ {elapsed:.0f}s  |  📄 CA.html")
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
