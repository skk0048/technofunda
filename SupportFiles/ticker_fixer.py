"""
Universal Ticker Suffix Auto-Detector
=====================================
Intelligently adds Yahoo Finance suffixes only if not already present.

Usage in any market scanner:
    from SupportFiles.ticker_fixer import ensure_yahoo_suffix
    
    df["Yahoo"] = df["Symbol"].apply(lambda s: ensure_yahoo_suffix(s, "UK"))
    df["Yahoo"] = df["Symbol"].apply(lambda s: ensure_yahoo_suffix(s, "CA"))
    df["Yahoo"] = df["Symbol"].apply(lambda s: ensure_yahoo_suffix(s, "AU"))
    # etc.

Market Config:
    UK  = .L  suffix
    CA  = .TO suffix
    AU  = .AX suffix
    JP  = .T  suffix
    FR  = .PA suffix
    IT  = .MI suffix
    DE  = .DE suffix
    SG  = .SI suffix
    HK  = .HK suffix
    TH  = .BK suffix
    NL  = .AS suffix
    PL  = .WA suffix
    SE  = .ST suffix
    TR  = .IS suffix
    MX  = .MX suffix
    BR  = .SA suffix
    ZA  = .JO suffix
    KR  = .KS suffix
    TW  = .TW suffix
    MY  = .KL suffix
    ID  = .JK suffix
    USA = NO suffix (pass "USA")
    IND = .NS suffix
"""

import re

MARKET_SUFFIXES = {
    "UK":   ".L",
    "CA":   ".TO",
    "AU":   ".AX",
    "JP":   ".T",    # Tokyo Stock Exchange
    "FR":   ".PA",
    "IT":   ".MI",
    "DE":   ".DE",
    "SG":   ".SI",
    "HK":   ".HK",
    "TH":   ".BK",
    "NL":   ".AS",
    "PL":   ".WA",
    "SE":   ".ST",   # Stockholm OMX
    "TR":   ".IS",   # Istanbul BIST
    "MX":   ".MX",   # Mexico BMV
    "BR":   ".SA",   # Brazil B3
    "ZA":   ".JO",   # Johannesburg JSE
    "KR":   ".KS",   # Korea KRX
    "TW":   ".TW",   # Taiwan TWSE
    "MY":   ".KL",   # Malaysia Bursa
    "ID":   ".JK",   # Indonesia IDX
    "USA":  None,    # No suffix for USA
    "IND":  ".NS",   # India NSE
}

def ensure_yahoo_suffix(symbol, market):
    """
    Intelligently add Yahoo Finance suffix ONLY if not already present.
    
    Args:
        symbol (str): Stock symbol (e.g., "III.L", "III", "RY", "RY.TO")
        market (str): Market code (e.g., "UK", "CA", "AU", "FR", "IT", "USA")
    
    Returns:
        str: Yahoo-compatible ticker
    
    Examples:
        >>> ensure_yahoo_suffix("III.L", "UK")     # Already has .L → "III.L"
        >>> ensure_yahoo_suffix("III", "UK")       # No suffix → "III.L"
        >>> ensure_yahoo_suffix("RY", "CA")        # No suffix → "RY.TO"
        >>> ensure_yahoo_suffix("RY.TO", "CA")     # Already has .TO → "RY.TO"
        >>> ensure_yahoo_suffix("AAPL", "USA")     # USA needs NO suffix → "AAPL"
        >>> ensure_yahoo_suffix("G.MI", "IT")      # Already has .MI → "G.MI"
    """
    
    if not symbol or not isinstance(symbol, str):
        return symbol
    
    symbol = symbol.strip()
    
    # USA market: no suffix needed
    if market == "USA":
        return symbol
    
    # Get expected suffix for this market
    suffix = MARKET_SUFFIXES.get(market)
    if suffix is None:
        return symbol
    
    # Check if suffix already present (case-insensitive)
    if symbol.upper().endswith(suffix.upper()):
        return symbol
    
    # Check if symbol already has ANY dot (e.g., "G.MI" already formatted)
    # Allow adding suffix only if no dot present OR if it's a different suffix
    if "." in symbol:
        # Already has a dot - assume it's already formatted correctly
        return symbol
    
    # Safe to add suffix
    return symbol + suffix


def fix_market_dataframe(df, market, symbol_col="Symbol", yahoo_col="Yahoo"):
    """
    Fix an entire DataFrame's ticker symbols for a given market.
    
    Args:
        df (pd.DataFrame): Universe DataFrame
        market (str): Market code (UK, CA, AU, FR, IT, USA, etc.)
        symbol_col (str): Name of Symbol column
        yahoo_col (str): Name of Yahoo column to create/update
    
    Returns:
        pd.DataFrame: Updated DataFrame with corrected Yahoo column
    
    Example:
        >>> import pandas as pd
        >>> from SupportFiles.ticker_fixer import fix_market_dataframe
        >>> 
        >>> df = pd.read_csv("uk_ftse350list.csv")
        >>> df = fix_market_dataframe(df, "UK", symbol_col="Symbol", yahoo_col="Yahoo")
        >>> print(df[["Symbol", "Yahoo"]].head())
    """
    
    if symbol_col not in df.columns:
        print(f"❌ Column '{symbol_col}' not found in DataFrame")
        return df
    
    df = df.copy()
    df[yahoo_col] = df[symbol_col].astype(str).str.strip().apply(
        lambda s: ensure_yahoo_suffix(s, market)
    )
    
    return df


# ──────────────────────────────────────────────────────────────────────────
#  TESTING EXAMPLES
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("  TICKER SUFFIX AUTO-DETECTOR — Test Suite")
    print("=" * 70)
    
    test_cases = [
        # (symbol, market, expected_output, description)
        ("III.L", "UK", "III.L", "UK: Already has .L suffix"),
        ("III", "UK", "III.L", "UK: Missing .L suffix"),
        ("RY.TO", "CA", "RY.TO", "CA: Already has .TO suffix"),
        ("RY", "CA", "RY.TO", "CA: Missing .TO suffix"),
        ("ANZ.AX", "AU", "ANZ.AX", "AU: Already has .AX suffix"),
        ("ANZ", "AU", "ANZ.AX", "AU: Missing .AX suffix"),
        ("RMS.PA", "FR", "RMS.PA", "FR: Already has .PA suffix"),
        ("RMS", "FR", "RMS.PA", "FR: Missing .PA suffix"),
        ("G.MI", "IT", "G.MI", "IT: Already has .MI suffix"),
        ("G", "IT", "G.MI", "IT: Missing .MI suffix"),
        ("AAPL", "USA", "AAPL", "USA: No suffix needed"),
        ("AAPL.US", "USA", "AAPL.US", "USA: Already formatted (keep as-is)"),
        ("0001.HK", "HK", "0001.HK", "HK: Already has .HK suffix"),
        ("0001", "HK", "0001.HK", "HK: Missing .HK suffix"),
    ]
    
    passed = 0
    failed = 0
    
    for symbol, market, expected, description in test_cases:
        result = ensure_yahoo_suffix(symbol, market)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"\n  {status}")
        print(f"  Input:    {symbol} ({market})")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
        print(f"  {description}")
    
    print(f"\n{'=' * 70}")
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 70)
