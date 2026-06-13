"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TECHNOFUNDA — COUNTRY CONFIG  v1.0                                        ║
║  country_config.py  — Centralised per-country settings for all 16 markets  ║
║                                                                            ║
║  HOW TO USE                                                                ║
║  ─────────                                                                 ║
║  In each market_XX_gsht.py, replace inline config variables with:          ║
║                                                                            ║
║      from country_config import get_country_config                         ║
║      cfg = get_country_config("CA")                                        ║
║      XX_INDEX          = cfg["index"]                                      ║
║      XX_INDEX_FALLBACK = cfg["index_fallback"]                             ║
║      XX_SECTORS        = cfg["sectors"]                                    ║
║      XX_BREADTH_INDICES= cfg["breadth_indices"]                            ║
║      XX_SNAPSHOT_TICKERS = cfg["snapshot_tickers"]                         ║
║                                                                            ║
║  ADDING A NEW COUNTRY                                                      ║
║  ──────────────────────                                                    ║
║  1. Copy the CA block below as a template.                                 ║
║  2. Replace tickers, currency, timezone, exchange_name, stock_csv.         ║
║  3. Add the country code key to COUNTRY_CONFIG.                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────────────────
#  COMMON GLOBAL SNAPSHOT TICKERS  (appear on every country page)
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_MACRO = [
    {"name": "S&P 500",         "ticker": "^GSPC",    "type": "Index"},
    {"name": "Gold",            "ticker": "GC=F",     "type": "Commodity"},
    {"name": "Crude Oil WTI",   "ticker": "CL=F",     "type": "Commodity"},
    {"name": "DXY (USD Index)", "ticker": "DX-Y.NYB", "type": "Forex"},
    {"name": "Natural Gas",     "ticker": "NG=F",     "type": "Commodity"},
    {"name": "Copper",          "ticker": "HG=F",     "type": "Commodity"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  COUNTRY CONFIGURATIONS
# ─────────────────────────────────────────────────────────────────────────────

COUNTRY_CONFIG = {

    # ──────────────────────────────────────────────────
    #  CA — CANADA (TSX)
    # ──────────────────────────────────────────────────
    "CA": {
        "name":          "Canada",
        "exchange_name": "TSX",
        "currency":      "CAD",
        "timezone":      "America/Toronto",   # ET — market close 16:00
        "stock_csv":     "ca_tsxlist.csv",
        "yahoo_suffix":  ".TO",
        "index":          "XIU.TO",
        "index_fallback": "^GSPTSE",

        "sectors": {
            "Financials":       {"yahoo": "XFN.TO",  "csv": None},
            "Energy":           {"yahoo": "XEG.TO",  "csv": None},
            "Materials":        {"yahoo": "XMA.TO",  "csv": None},
            "Technology":       {"yahoo": "XIT.TO",  "csv": None},
            "Healthcare":       {"yahoo": "XHC.TO",  "csv": None},
            "Industrials":      {"yahoo": "XIN.TO",  "csv": None},
            "ConsumerDisc":     {"yahoo": "XCD.TO",  "csv": None},
            "Consumer Staples": {"yahoo": "XST.TO",  "csv": None},
            "Utilities":        {"yahoo": "XUT.TO",  "csv": None},
            "CommServices":     {"yahoo": "XCO.TO",  "csv": None},
            "RealEstate":       {"yahoo": "XRE.TO",  "csv": None},
        },

        "breadth_indices": {
            "S&P/TSX 60":    {"yahoo": "^GSPTSE", "csv": None},
            "TSX Composite": {"yahoo": "^GSPTSE", "csv": "ca_tsxlist.csv"},
            "TSX SmallCap":  {"yahoo": "^TSXV",   "csv": None},
        },

        "snapshot_tickers": [
            {"name": "S&P/TSX Composite", "ticker": "^GSPTSE",  "type": "Index"},
            {"name": "iShares TSX 60",    "ticker": "XIU.TO",   "type": "ETF"},
            {"name": "TSX Venture",       "ticker": "^TSXV",    "type": "Index"},
            {"name": "S&P 500",           "ticker": "^GSPC",    "type": "Index"},
            {"name": "CAD/USD",           "ticker": "CADUSD=X", "type": "Forex"},
            {"name": "CAD/EUR",           "ticker": "CADEUR=X", "type": "Forex"},
            {"name": "DXY (USD Index)",   "ticker": "DX-Y.NYB", "type": "Forex"},
            {"name": "10Y Canada Bond",   "ticker": "^TNX",     "type": "Bond"},
            {"name": "Gold",              "ticker": "GC=F",     "type": "Commodity"},
            {"name": "Crude Oil WTI",     "ticker": "CL=F",     "type": "Commodity"},
            {"name": "Natural Gas",       "ticker": "NG=F",     "type": "Commodity"},
            {"name": "Copper",            "ticker": "HG=F",     "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  US — UNITED STATES (NYSE / NASDAQ)
    # ──────────────────────────────────────────────────
    "US": {
        "name":          "United States",
        "exchange_name": "NYSE/NASDAQ",
        "currency":      "USD",
        "timezone":      "America/New_York",  # ET — market close 16:00
        "stock_csv":     "us_stocklist.csv",
        "yahoo_suffix":  "",                  # no suffix for US tickers
        "index":          "SPY",
        "index_fallback": "^GSPC",

        "sectors": {
            "Technology":             {"yahoo": "XLK",  "csv": "us_sector_technology.csv"},
            "Healthcare":             {"yahoo": "XLV",  "csv": "us_sector_healthcare.csv"},
            "Financials":             {"yahoo": "XLF",  "csv": "us_sector_financials.csv"},
            "Consumer Discretionary": {"yahoo": "XLY",  "csv": "us_sector_consumer_discretionary.csv"},
            "Consumer Staples":       {"yahoo": "XLP",  "csv": "us_sector_consumer_staples.csv"},
            "Energy":                 {"yahoo": "XLE",  "csv": "us_sector_energy.csv"},
            "Industrials":            {"yahoo": "XLI",  "csv": "us_sector_industrials.csv"},
            "Materials":              {"yahoo": "XLB",  "csv": "us_sector_materials.csv"},
            "Utilities":              {"yahoo": "XLU",  "csv": "us_sector_utilities.csv"},
            "Real Estate":            {"yahoo": "XLRE", "csv": "us_sector_real_estate.csv"},
            "Communication Services": {"yahoo": "XLC",  "csv": "us_sector_communication_services.csv"},
        },

        "breadth_indices": {
            "S&P 500":    {"yahoo": "^GSPC",  "csv": "us_sp500.csv"},
            "NASDAQ 100": {"yahoo": "^NDX",   "csv": None},
            "Russell 2000":{"yahoo": "^RUT",  "csv": None},
        },

        "snapshot_tickers": [
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "NASDAQ 100",     "ticker": "^NDX",    "type": "Index"},
            {"name": "Dow Jones",      "ticker": "^DJI",    "type": "Index"},
            {"name": "Russell 2000",   "ticker": "^RUT",    "type": "Index"},
            {"name": "VIX",            "ticker": "^VIX",    "type": "Index"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y US Bond",    "ticker": "^TNX",    "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil WTI",  "ticker": "CL=F",    "type": "Commodity"},
            {"name": "Natural Gas",    "ticker": "NG=F",    "type": "Commodity"},
            {"name": "Copper",         "ticker": "HG=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  IN — INDIA (NSE / BSE)
    # ──────────────────────────────────────────────────
    "IN": {
        "name":          "India",
        "exchange_name": "NSE",
        "currency":      "INR",
        "timezone":      "Asia/Kolkata",      # IST — market close 15:30
        "stock_csv":     "in_niftylist.csv",
        "yahoo_suffix":  ".NS",
        "index":          "^NSEI",
        "index_fallback": "^BSESN",

        "sectors": {
            "Technology":       {"yahoo": "^CNXIT",  "csv": None},
            "Financials":       {"yahoo": "^CNXBANK", "csv": None},
            "Energy":           {"yahoo": "^CNXENERGY","csv": None},
            "Materials":        {"yahoo": "^CNXMETAL", "csv": None},
            "Healthcare":       {"yahoo": "^CNXPHARMA","csv": None},
            "Industrials":      {"yahoo": "^CNXINFRA", "csv": None},
            "ConsumerDisc":     {"yahoo": "^CNXAUTO",  "csv": None},
            "Consumer Staples": {"yahoo": "^CNXFMCG",  "csv": None},
            "RealEstate":       {"yahoo": "^CNXREALTY","csv": None},
            "Utilities":        {"yahoo": "^CNXPSUBANK","csv": None},
        },

        "breadth_indices": {
            "Nifty 50":     {"yahoo": "^NSEI",    "csv": "in_niftylist.csv"},
            "Nifty 500":    {"yahoo": "^NSEI",    "csv": "in_nifty500.csv"},
            "BSE Sensex":   {"yahoo": "^BSESN",   "csv": None},
        },

        "snapshot_tickers": [
            {"name": "Nifty 50",       "ticker": "^NSEI",    "type": "Index"},
            {"name": "BSE Sensex",     "ticker": "^BSESN",   "type": "Index"},
            {"name": "Nifty Bank",     "ticker": "^CNXBANK", "type": "Index"},
            {"name": "Nifty IT",       "ticker": "^CNXIT",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",    "type": "Index"},
            {"name": "USD/INR",        "ticker": "INR=X",    "type": "Forex"},
            {"name": "EUR/INR",        "ticker": "EURINR=X", "type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB", "type": "Forex"},
            {"name": "10Y India Bond", "ticker": "IN10Y=RR", "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",     "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",     "type": "Commodity"},
            {"name": "Copper",         "ticker": "HG=F",     "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  GB — UNITED KINGDOM (LSE)
    # ──────────────────────────────────────────────────
    "GB": {
        "name":          "United Kingdom",
        "exchange_name": "LSE",
        "currency":      "GBP",
        "timezone":      "Europe/London",     # GMT/BST — market close 16:30
        "stock_csv":     "gb_ftse350list.csv",
        "yahoo_suffix":  ".L",
        "index":          "^FTSE",
        "index_fallback": "ISF.L",

        "sectors": {
            "Financials":       {"yahoo": "IUKF.L",  "csv": None},
            "Energy":           {"yahoo": "IUKY.L",  "csv": None},
            "Materials":        {"yahoo": "IUKM.L",  "csv": None},
            "Technology":       {"yahoo": "IITU.L",  "csv": None},
            "Healthcare":       {"yahoo": "IUKH.L",  "csv": None},
            "Industrials":      {"yahoo": "IUKI.L",  "csv": None},
            "ConsumerDisc":     {"yahoo": "IUKD.L",  "csv": None},
            "Consumer Staples": {"yahoo": "IUKS.L",  "csv": None},
            "Utilities":        {"yahoo": "IUKU.L",  "csv": None},
            "RealEstate":       {"yahoo": "IUKREIT.L","csv": None},
        },

        "breadth_indices": {
            "FTSE 100":  {"yahoo": "^FTSE",  "csv": "gb_ftse100.csv"},
            "FTSE 250":  {"yahoo": "^FTMC",  "csv": "gb_ftse250.csv"},
            "FTSE 350":  {"yahoo": "^FTLC",  "csv": "gb_ftse350list.csv"},
        },

        "snapshot_tickers": [
            {"name": "FTSE 100",       "ticker": "^FTSE",   "type": "Index"},
            {"name": "FTSE 250",       "ticker": "^FTMC",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "GBP/USD",        "ticker": "GBPUSD=X","type": "Forex"},
            {"name": "GBP/EUR",        "ticker": "GBPEUR=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y UK Gilt",    "ticker": "^TNX",    "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
            {"name": "Natural Gas",    "ticker": "NG=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  AU — AUSTRALIA (ASX)
    # ──────────────────────────────────────────────────
    "AU": {
        "name":          "Australia",
        "exchange_name": "ASX",
        "currency":      "AUD",
        "timezone":      "Australia/Sydney",  # AEST — market close 16:00
        "stock_csv":     "au_asxlist.csv",
        "yahoo_suffix":  ".AX",
        "index":          "^AXJO",
        "index_fallback": "IOZ.AX",

        "sectors": {
            "Financials":       {"yahoo": "OZF.AX",  "csv": None},
            "Materials":        {"yahoo": "OZR.AX",  "csv": None},
            "Energy":           {"yahoo": "OZE.AX",  "csv": None},
            "Healthcare":       {"yahoo": "OZH.AX",  "csv": None},
            "Technology":       {"yahoo": "TECH.AX", "csv": None},
            "Industrials":      {"yahoo": "OZI.AX",  "csv": None},
            "ConsumerDisc":     {"yahoo": "OZD.AX",  "csv": None},
            "Consumer Staples": {"yahoo": "OZS.AX",  "csv": None},
            "Utilities":        {"yahoo": "OZU.AX",  "csv": None},
            "RealEstate":       {"yahoo": "OZP.AX",  "csv": None},
        },

        "breadth_indices": {
            "ASX 200":   {"yahoo": "^AXJO",  "csv": "au_asx200.csv"},
            "ASX 300":   {"yahoo": "^AXKO",  "csv": "au_asxlist.csv"},
            "ASX SmCap": {"yahoo": "^AXSO",  "csv": None},
        },

        "snapshot_tickers": [
            {"name": "ASX 200",        "ticker": "^AXJO",   "type": "Index"},
            {"name": "ASX All Ords",   "ticker": "^AORD",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "AUD/USD",        "ticker": "AUDUSD=X","type": "Forex"},
            {"name": "AUD/JPY",        "ticker": "AUDJPY=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y Aust Bond",  "ticker": "^TABI",   "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Iron Ore (Proxy)","ticker": "BHP.AX", "type": "Commodity"},
            {"name": "Crude Oil WTI",  "ticker": "CL=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  DE — GERMANY (XETRA / FSE)
    # ──────────────────────────────────────────────────
    "DE": {
        "name":          "Germany",
        "exchange_name": "XETRA",
        "currency":      "EUR",
        "timezone":      "Europe/Berlin",     # CET/CEST — market close 17:30
        "stock_csv":     "de_daxlist.csv",
        "yahoo_suffix":  ".DE",
        "index":          "^GDAXI",
        "index_fallback": "EXS1.DE",

        "sectors": {
            "Technology":       {"yahoo": "EXV5.DE", "csv": None},
            "Financials":       {"yahoo": "EXV1.DE", "csv": None},
            "Healthcare":       {"yahoo": "EXV4.DE", "csv": None},
            "Industrials":      {"yahoo": "EXV6.DE", "csv": None},
            "Energy":           {"yahoo": "EXV2.DE", "csv": None},
            "Materials":        {"yahoo": "EXV3.DE", "csv": None},
            "ConsumerDisc":     {"yahoo": "EXV8.DE", "csv": None},
            "Consumer Staples": {"yahoo": "EXV7.DE", "csv": None},
            "Utilities":        {"yahoo": "EXV9.DE", "csv": None},
            "RealEstate":       {"yahoo": "EXSI.DE", "csv": None},
        },

        "breadth_indices": {
            "DAX 40":   {"yahoo": "^GDAXI",  "csv": "de_dax40.csv"},
            "MDAX":     {"yahoo": "^MDAXI",  "csv": "de_mdax.csv"},
            "SDAX":     {"yahoo": "^SDAXI",  "csv": None},
        },

        "snapshot_tickers": [
            {"name": "DAX 40",         "ticker": "^GDAXI",  "type": "Index"},
            {"name": "MDAX",           "ticker": "^MDAXI",  "type": "Index"},
            {"name": "Euro Stoxx 50",  "ticker": "^STOXX50E","type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "EUR/USD",        "ticker": "EURUSD=X","type": "Forex"},
            {"name": "EUR/GBP",        "ticker": "EURGBP=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y Bund",       "ticker": "^TNX",    "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  JP — JAPAN (TSE / Tokyo)
    # ──────────────────────────────────────────────────
    "JP": {
        "name":          "Japan",
        "exchange_name": "TSE",
        "currency":      "JPY",
        "timezone":      "Asia/Tokyo",        # JST — market close 15:30
        "stock_csv":     "jp_nikkeilist.csv",
        "yahoo_suffix":  ".T",
        "index":          "^N225",
        "index_fallback": "1306.T",           # TOPIX ETF

        "sectors": {
            "Technology":       {"yahoo": "1621.T", "csv": None},
            "Financials":       {"yahoo": "1615.T", "csv": None},
            "Healthcare":       {"yahoo": "1622.T", "csv": None},
            "ConsumerDisc":     {"yahoo": "1620.T", "csv": None},
            "Industrials":      {"yahoo": "1617.T", "csv": None},
            "Materials":        {"yahoo": "1616.T", "csv": None},
            "Energy":           {"yahoo": "1618.T", "csv": None},
            "Consumer Staples": {"yahoo": "1619.T", "csv": None},
            "Utilities":        {"yahoo": "1623.T", "csv": None},
            "RealEstate":       {"yahoo": "1624.T", "csv": None},
        },

        "breadth_indices": {
            "Nikkei 225": {"yahoo": "^N225",  "csv": "jp_nikkei225.csv"},
            "TOPIX":      {"yahoo": "^TOPX",  "csv": "jp_topix.csv"},
            "JPX 400":    {"yahoo": "^JPX400","csv": None},
        },

        "snapshot_tickers": [
            {"name": "Nikkei 225",     "ticker": "^N225",   "type": "Index"},
            {"name": "TOPIX",          "ticker": "^TOPX",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "USD/JPY",        "ticker": "USDJPY=X","type": "Forex"},
            {"name": "EUR/JPY",        "ticker": "EURJPY=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y JGB",        "ticker": "^TNX",    "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil WTI",  "ticker": "CL=F",    "type": "Commodity"},
            {"name": "Copper",         "ticker": "HG=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  SG — SINGAPORE (SGX)
    # ──────────────────────────────────────────────────
    "SG": {
        "name":          "Singapore",
        "exchange_name": "SGX",
        "currency":      "SGD",
        "timezone":      "Asia/Singapore",    # SGT — market close 17:00
        "stock_csv":     "sg_sgxlist.csv",
        "yahoo_suffix":  ".SI",
        "index":          "^STI",
        "index_fallback": "ES3.SI",           # SPDR STI ETF

        "sectors": {
            "Financials":  {"yahoo": "G13.SI",  "csv": None},  # proxy stock
            "RealEstate":  {"yahoo": "C38U.SI", "csv": None},
            "Industrials": {"yahoo": "C6L.SI",  "csv": None},
            "Technology":  {"yahoo": "U11.SI",  "csv": None},
            "Consumer":    {"yahoo": "F99.SI",  "csv": None},
        },

        "breadth_indices": {
            "STI":       {"yahoo": "^STI",  "csv": "sg_sti.csv"},
            "SGX 300":   {"yahoo": "^STI",  "csv": "sg_sgxlist.csv"},
        },

        "snapshot_tickers": [
            {"name": "STI",            "ticker": "^STI",    "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "Hang Seng",      "ticker": "^HSI",    "type": "Index"},
            {"name": "SGD/USD",        "ticker": "SGDUSD=X","type": "Forex"},
            {"name": "USD/SGD",        "ticker": "SGD=X",   "type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  HK — HONG KONG (HKEX)
    # ──────────────────────────────────────────────────
    "HK": {
        "name":          "Hong Kong",
        "exchange_name": "HKEX",
        "currency":      "HKD",
        "timezone":      "Asia/Hong_Kong",    # HKT — market close 16:00
        "stock_csv":     "hk_hkexlist.csv",
        "yahoo_suffix":  ".HK",
        "index":          "^HSI",
        "index_fallback": "2800.HK",          # Tracker Fund of HK

        "sectors": {
            "Financials":   {"yahoo": "2388.HK", "csv": None},
            "RealEstate":   {"yahoo": "1997.HK", "csv": None},
            "Technology":   {"yahoo": "3033.HK", "csv": None},  # CSOP HSTECH ETF
            "Industrials":  {"yahoo": "0003.HK", "csv": None},
            "Energy":       {"yahoo": "0857.HK", "csv": None},
            "Consumer":     {"yahoo": "0291.HK", "csv": None},
        },

        "breadth_indices": {
            "Hang Seng":      {"yahoo": "^HSI",   "csv": "hk_hsi50.csv"},
            "Hang Seng Tech": {"yahoo": "^HSTECH","csv": None},
            "HKEX Main":      {"yahoo": "^HSI",   "csv": "hk_hkexlist.csv"},
        },

        "snapshot_tickers": [
            {"name": "Hang Seng",      "ticker": "^HSI",    "type": "Index"},
            {"name": "HS Tech",        "ticker": "^HSTECH", "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "HKD/USD",        "ticker": "HKDUSD=X","type": "Forex"},
            {"name": "USD/CNY",        "ticker": "USDCNY=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  NZ — NEW ZEALAND (NZX)
    # ──────────────────────────────────────────────────
    "NZ": {
        "name":          "New Zealand",
        "exchange_name": "NZX",
        "currency":      "NZD",
        "timezone":      "Pacific/Auckland",  # NZST — market close 17:00
        "stock_csv":     "nz_nzxlist.csv",
        "yahoo_suffix":  ".NZ",
        "index":          "^NZ50",
        "index_fallback": "FNZ.NZ",

        "sectors": {
            "Financials":   {"yahoo": "FBU.NZ",  "csv": None},
            "Utilities":    {"yahoo": "MEL.NZ",  "csv": None},
            "RealEstate":   {"yahoo": "PCT.NZ",  "csv": None},
            "Consumer":     {"yahoo": "SKC.NZ",  "csv": None},
            "Industrials":  {"yahoo": "ATM.NZ",  "csv": None},
        },

        "breadth_indices": {
            "NZX 50":   {"yahoo": "^NZ50",  "csv": "nz_nzx50.csv"},
            "NZX All":  {"yahoo": "^NZ50",  "csv": "nz_nzxlist.csv"},
        },

        "snapshot_tickers": [
            {"name": "NZX 50",         "ticker": "^NZ50",   "type": "Index"},
            {"name": "ASX 200",        "ticker": "^AXJO",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "NZD/USD",        "ticker": "NZDUSD=X","type": "Forex"},
            {"name": "NZD/AUD",        "ticker": "NZDAUD=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil WTI",  "ticker": "CL=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  FR — FRANCE (Euronext Paris)
    # ──────────────────────────────────────────────────
    "FR": {
        "name":          "France",
        "exchange_name": "Euronext Paris",
        "currency":      "EUR",
        "timezone":      "Europe/Paris",      # CET/CEST — market close 17:30
        "stock_csv":     "fr_cac40list.csv",
        "yahoo_suffix":  ".PA",
        "index":          "^FCHI",
        "index_fallback": "CACC.PA",

        "sectors": {
            "Technology":       {"yahoo": "TNO.PA",  "csv": None},
            "Financials":       {"yahoo": "BNP.PA",  "csv": None},
            "Healthcare":       {"yahoo": "SAN.PA",  "csv": None},
            "Energy":           {"yahoo": "TTE.PA",  "csv": None},
            "Industrials":      {"yahoo": "AIR.PA",  "csv": None},
            "ConsumerDisc":     {"yahoo": "MC.PA",   "csv": None},
            "Consumer Staples": {"yahoo": "OR.PA",   "csv": None},
            "Materials":        {"yahoo": "AI.PA",   "csv": None},
            "Utilities":        {"yahoo": "ENGI.PA", "csv": None},
        },

        "breadth_indices": {
            "CAC 40":    {"yahoo": "^FCHI",  "csv": "fr_cac40.csv"},
            "SBF 120":   {"yahoo": "^SBF120","csv": "fr_cac40list.csv"},
        },

        "snapshot_tickers": [
            {"name": "CAC 40",         "ticker": "^FCHI",   "type": "Index"},
            {"name": "Euro Stoxx 50",  "ticker": "^STOXX50E","type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "EUR/USD",        "ticker": "EURUSD=X","type": "Forex"},
            {"name": "EUR/GBP",        "ticker": "EURGBP=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "10Y OAT",        "ticker": "^TNX",    "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  IT — ITALY (Borsa Italiana / Euronext Milan)
    # ──────────────────────────────────────────────────
    "IT": {
        "name":          "Italy",
        "exchange_name": "Borsa Italiana",
        "currency":      "EUR",
        "timezone":      "Europe/Rome",       # CET/CEST — market close 17:35
        "stock_csv":     "it_ftsmiblist.csv",
        "yahoo_suffix":  ".MI",
        "index":          "FTSEMIB.MI",
        "index_fallback": "^FTSEMIB",

        "sectors": {
            "Financials":   {"yahoo": "ISP.MI",  "csv": None},
            "Energy":       {"yahoo": "ENI.MI",  "csv": None},
            "Utilities":    {"yahoo": "ENEL.MI", "csv": None},
            "Industrials":  {"yahoo": "STM.MI",  "csv": None},
            "Consumer":     {"yahoo": "LUX.MI",  "csv": None},
            "Technology":   {"yahoo": "RACE.MI", "csv": None},
        },

        "breadth_indices": {
            "FTSE MIB":   {"yahoo": "FTSEMIB.MI","csv": "it_ftsmib40.csv"},
            "FTSE Italia":{"yahoo": "FTSEMIB.MI","csv": "it_ftsmiblist.csv"},
        },

        "snapshot_tickers": [
            {"name": "FTSE MIB",       "ticker": "FTSEMIB.MI","type": "Index"},
            {"name": "Euro Stoxx 50",  "ticker": "^STOXX50E", "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",    "type": "Index"},
            {"name": "EUR/USD",        "ticker": "EURUSD=X", "type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB", "type": "Forex"},
            {"name": "10Y BTP",        "ticker": "^TNX",     "type": "Bond"},
            {"name": "Gold",           "ticker": "GC=F",     "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",     "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  BR — BRAZIL (B3)
    # ──────────────────────────────────────────────────
    "BR": {
        "name":          "Brazil",
        "exchange_name": "B3",
        "currency":      "BRL",
        "timezone":      "America/Sao_Paulo", # BRT — market close 17:55
        "stock_csv":     "br_ibovlist.csv",
        "yahoo_suffix":  ".SA",
        "index":          "^BVSP",
        "index_fallback": "BOVA11.SA",

        "sectors": {
            "Financials":   {"yahoo": "BPAC11.SA", "csv": None},
            "Energy":       {"yahoo": "PETR4.SA",  "csv": None},
            "Materials":    {"yahoo": "VALE3.SA",  "csv": None},
            "Consumer":     {"yahoo": "MGLU3.SA",  "csv": None},
            "Utilities":    {"yahoo": "ELET3.SA",  "csv": None},
            "Industrials":  {"yahoo": "EMBRAER.SA","csv": None},
        },

        "breadth_indices": {
            "Ibovespa":    {"yahoo": "^BVSP",   "csv": "br_ibov.csv"},
            "IBRX 100":    {"yahoo": "^BVSP",   "csv": "br_ibovlist.csv"},
        },

        "snapshot_tickers": [
            {"name": "Ibovespa",       "ticker": "^BVSP",   "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "USD/BRL",        "ticker": "USDBRL=X","type": "Forex"},
            {"name": "EUR/BRL",        "ticker": "EURBRL=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
            {"name": "Iron Ore (Proxy)","ticker": "VALE3.SA","type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  ZA — SOUTH AFRICA (JSE)
    # ──────────────────────────────────────────────────
    "ZA": {
        "name":          "South Africa",
        "exchange_name": "JSE",
        "currency":      "ZAR",
        "timezone":      "Africa/Johannesburg",  # SAST — market close 17:00
        "stock_csv":     "za_jselist.csv",
        "yahoo_suffix":  ".JO",
        "index":          "^J203.JO",
        "index_fallback": "STX40.JO",

        "sectors": {
            "Materials":    {"yahoo": "STXRES.JO", "csv": None},
            "Financials":   {"yahoo": "STXFIN.JO", "csv": None},
            "Consumer":     {"yahoo": "STXCON.JO", "csv": None},
            "Industrials":  {"yahoo": "STXIND.JO", "csv": None},
            "Technology":   {"yahoo": "STXSWX.JO", "csv": None},
        },

        "breadth_indices": {
            "JSE Top 40":   {"yahoo": "^J203.JO", "csv": "za_jse40.csv"},
            "JSE All Share":{"yahoo": "^J203.JO", "csv": "za_jselist.csv"},
        },

        "snapshot_tickers": [
            {"name": "JSE All Share",  "ticker": "^J203.JO","type": "Index"},
            {"name": "JSE Top 40",     "ticker": "STX40.JO","type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "USD/ZAR",        "ticker": "USDZAR=X","type": "Forex"},
            {"name": "EUR/ZAR",        "ticker": "EURZAR=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Platinum",       "ticker": "PL=F",    "type": "Commodity"},
            {"name": "Crude Oil Brent","ticker": "BZ=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  MX — MEXICO (BMV)
    # ──────────────────────────────────────────────────
    "MX": {
        "name":          "Mexico",
        "exchange_name": "BMV",
        "currency":      "MXN",
        "timezone":      "America/Mexico_City",  # CST — market close 15:00
        "stock_csv":     "mx_bmvlist.csv",
        "yahoo_suffix":  ".MX",
        "index":          "^MXX",
        "index_fallback": "NAFTRAC.MX",

        "sectors": {
            "Financials":   {"yahoo": "GFNORTEO.MX","csv": None},
            "Consumer":     {"yahoo": "AMXL.MX",    "csv": None},
            "Materials":    {"yahoo": "CEMEXCPO.MX", "csv": None},
            "Industrials":  {"yahoo": "GMEXICOB.MX", "csv": None},
            "Energy":       {"yahoo": "PEMEX.MX",    "csv": None},
        },

        "breadth_indices": {
            "IPC (BMV)":  {"yahoo": "^MXX",  "csv": "mx_ipc35.csv"},
            "BMV All":    {"yahoo": "^MXX",  "csv": "mx_bmvlist.csv"},
        },

        "snapshot_tickers": [
            {"name": "IPC (BMV)",      "ticker": "^MXX",    "type": "Index"},
            {"name": "S&P 500",        "ticker": "^GSPC",   "type": "Index"},
            {"name": "USD/MXN",        "ticker": "USDMXN=X","type": "Forex"},
            {"name": "EUR/MXN",        "ticker": "EURMXN=X","type": "Forex"},
            {"name": "DXY (USD Index)","ticker": "DX-Y.NYB","type": "Forex"},
            {"name": "Gold",           "ticker": "GC=F",    "type": "Commodity"},
            {"name": "Crude Oil WTI",  "ticker": "CL=F",    "type": "Commodity"},
            {"name": "Silver",         "ticker": "SI=F",    "type": "Commodity"},
        ],
    },

    # ──────────────────────────────────────────────────
    #  AE — UAE / SAUDI (Tadawul / ADX / DFM)
    # ──────────────────────────────────────────────────
    "AE": {
        "name":          "UAE / Saudi",
        "exchange_name": "Tadawul / ADX",
        "currency":      "USD",               # GCC pegged to USD
        "timezone":      "Asia/Dubai",        # GST — market close 15:00
        "stock_csv":     "ae_tadawullist.csv",
        "yahoo_suffix":  ".SR",               # Saudi; .AE for Abu Dhabi
        "index":          "^TASI.SR",
        "index_fallback": "^DFM",

        "sectors": {
            "Energy":       {"yahoo": "2222.SR",   "csv": None},  # Aramco
            "Financials":   {"yahoo": "1120.SR",   "csv": None},
            "Materials":    {"yahoo": "2010.SR",   "csv": None},
            "Utilities":    {"yahoo": "4200.SR",   "csv": None},
            "Consumer":     {"yahoo": "4003.SR",   "csv": None},
            "RealEstate":   {"yahoo": "4020.SR",   "csv": None},
        },

        "breadth_indices": {
            "Tadawul All": {"yahoo": "^TASI.SR", "csv": "ae_tadawullist.csv"},
            "DFM General": {"yahoo": "^DFM",     "csv": "ae_dfm.csv"},
        },

        "snapshot_tickers": [
            {"name": "Tadawul (TASI)",  "ticker": "^TASI.SR", "type": "Index"},
            {"name": "DFM General",     "ticker": "^DFM",     "type": "Index"},
            {"name": "S&P 500",         "ticker": "^GSPC",    "type": "Index"},
            {"name": "USD/SAR",         "ticker": "USDSAR=X", "type": "Forex"},
            {"name": "DXY (USD Index)", "ticker": "DX-Y.NYB", "type": "Forex"},
            {"name": "Brent Crude",     "ticker": "BZ=F",     "type": "Commodity"},
            {"name": "Gold",            "ticker": "GC=F",     "type": "Commodity"},
        ],
    },

}

# ─────────────────────────────────────────────────────────────────────────────
#  ACCESSOR
# ─────────────────────────────────────────────────────────────────────────────

def get_country_config(code: str) -> dict:
    """
    Return the config dict for the given country code (e.g. 'CA', 'US').
    Raises KeyError with a helpful message if the code is not found.
    """
    code = code.upper().strip()
    if code not in COUNTRY_CONFIG:
        available = ", ".join(sorted(COUNTRY_CONFIG.keys()))
        raise KeyError(
            f"Country code '{code}' not found in country_config.py. "
            f"Available codes: {available}"
        )
    return COUNTRY_CONFIG[code]


def list_countries() -> list[dict]:
    """
    Return a list of {code, name, exchange, currency, timezone} for all countries.
    Useful for build_index.py to enumerate available markets.
    """
    return [
        {
            "code":     code,
            "name":     cfg["name"],
            "exchange": cfg["exchange_name"],
            "currency": cfg["currency"],
            "timezone": cfg["timezone"],
        }
        for code, cfg in COUNTRY_CONFIG.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  QUICK SANITY CHECK  (run directly: python country_config.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"  {len(COUNTRY_CONFIG)} countries configured\n")
    for row in list_countries():
        print(
            f"  {row['code']:3}  {row['name']:<22} "
            f"{row['exchange']:<20} {row['currency']}  {row['timezone']}"
        )

    # Test accessor
    ca = get_country_config("CA")
    print(f"\n  CA index       : {ca['index']}")
    print(f"  CA sectors     : {list(ca['sectors'].keys())}")
    print(f"  CA snapshot Δ  : {len(ca['snapshot_tickers'])} tickers")
