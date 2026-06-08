"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  INDIVIDUAL STOCK PAGE GENERATOR  v1.0  —  generate_stock_page.py         ║
║                                                                            ║
║  Generates a rich, self-contained HTML page for a single stock.            ║
║  Uses yfinance for all data. TradingView chart embed included.             ║
║                                                                            ║
║  Usage:                                                                    ║
║    python generate_stock_page.py RELIANCE.NS IN                            ║
║    python generate_stock_page.py AAPL US                                   ║
║                                                                            ║
║  Output: <COUNTRY>_<SYMBOL>.html  (e.g. IN_RELIANCE.html)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ── Optional yfinance import ─────────────────────────────────────────────────
try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("yfinance not installed — run: pip install yfinance")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v, decimals=2, suffix=""):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:,.{decimals}f}{suffix}"
    return str(v)

def _fmt_large(v):
    """Format large numbers: 1.2B, 345M, etc."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    try:
        v = float(v)
        if abs(v) >= 1e12: return f"{v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"{v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"{v/1e6:.2f}M"
        if abs(v) >= 1e3:  return f"{v/1e3:.1f}K"
        return f"{v:.2f}"
    except: return "—"

def _pct(v, decimals=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    try: return f"{float(v)*100:.{decimals}f}%"
    except: return "—"

def _color_pct(v):
    """Return CSS class for a percentage value."""
    try:
        f = float(v)
        if f > 10:  return "pos-strong"
        if f > 2:   return "pos"
        if f > 0:   return "pos-dim"
        if f < -10: return "neg-strong"
        if f < -2:  return "neg"
        if f < 0:   return "neg-dim"
        return ""
    except: return ""

def _safe(info, *keys, default=None):
    for k in keys:
        v = info.get(k)
        if v is not None and v != "N/A":
            return v
    return default

def calc_rs(prices, index_prices, period):
    try:
        if len(prices) < period or len(index_prices) < period:
            return float('nan')
        s = prices.iloc[-period]
        e = prices.iloc[-1]
        si = index_prices.iloc[-period]
        ei = index_prices.iloc[-1]
        if s <= 0 or si <= 0: return float('nan')
        return ((e/s) - (ei/si)) * 100
    except: return float('nan')

def calc_rsi(prices, period=14):
    try:
        delta = prices.diff().dropna()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 1)
    except: return float('nan')

def calc_sma(prices, period):
    try:
        if len(prices) < period: return float('nan')
        return round(float(prices.rolling(period).mean().iloc[-1]), 2)
    except: return float('nan')

def prices_to_json(series, max_points=365):
    """Convert price series to JSON for the sparkline chart."""
    if series is None or series.empty:
        return "[]"
    s = series.dropna()
    if len(s) > max_points:
        s = s.iloc[-max_points:]
    data = [{"t": str(d.date()), "v": round(float(v), 2)}
            for d, v in zip(s.index, s.values)]
    return json.dumps(data)


# ─────────────────────────────────────────────────────────────────────────────
#  DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_stock_data(ticker_yf, country_code):
    """Fetch all available data for a single stock from yfinance."""
    print(f"  Fetching {ticker_yf}...")
    t = yf.Ticker(ticker_yf)

    # Price history
    hist = t.history(period="2y", interval="1d", auto_adjust=True)
    hist_1y = hist.iloc[-252:] if len(hist) >= 252 else hist

    fast = {}
    try:
        fi = t.fast_info
        fast = {
            "last_price":     getattr(fi, "last_price", None),
            "prev_close":     getattr(fi, "previous_close", None),
            "day_high":       getattr(fi, "day_high", None),
            "day_low":        getattr(fi, "day_low", None),
            "year_high":      getattr(fi, "year_high", None),
            "year_low":       getattr(fi, "year_low", None),
            "market_cap":     getattr(fi, "market_cap", None),
            "shares":         getattr(fi, "shares", None),
            "volume":         getattr(fi, "last_volume", None),
            "avg_vol_10d":    getattr(fi, "ten_day_average_volume", None),
            "avg_vol_3mo":    getattr(fi, "three_month_average_volume", None),
            "fifty_day_avg":  getattr(fi, "fifty_day_average", None),
            "twohun_day_avg": getattr(fi, "two_hundred_day_average", None),
            "year_change":    getattr(fi, "year_change", None),
            "currency":       getattr(fi, "currency", ""),
            "exchange":       getattr(fi, "exchange", ""),
        }
    except Exception as e:
        print(f"    fast_info error: {e}")

    info = {}
    try:
        info = t.info or {}
    except Exception as e:
        print(f"    info error: {e}")

    # Financials
    fin_data = {}
    try:
        q_fin = t.quarterly_financials
        a_fin = t.financials
        q_bs  = t.quarterly_balance_sheet
        a_bs  = t.balance_sheet

        if q_fin is not None and not q_fin.empty:
            rev_rows = [r for r in q_fin.index if "revenue" in str(r).lower() or "total revenue" in str(r).lower()]
            if rev_rows:
                rev = q_fin.loc[rev_rows[0]]
                if len(rev) >= 2:
                    fin_data["rev_qoq"] = (rev.iloc[0]/rev.iloc[1] - 1) * 100 if rev.iloc[1] else None
                if len(rev) >= 5:
                    fin_data["rev_yoy"] = (rev.iloc[0]/rev.iloc[4] - 1) * 100 if rev.iloc[4] else None

            inc_rows = [r for r in q_fin.index if "net income" in str(r).lower()]
            if inc_rows:
                inc = q_fin.loc[inc_rows[0]]
                if len(inc) >= 2:
                    fin_data["pat_qoq"] = (inc.iloc[0]/inc.iloc[1] - 1) * 100 if inc.iloc[1] else None
                if len(inc) >= 5:
                    fin_data["pat_yoy"] = (inc.iloc[0]/inc.iloc[4] - 1) * 100 if inc.iloc[4] else None
    except Exception as e:
        print(f"    financials error: {e}")

    # Key stats from info
    pe      = _safe(info, "trailingPE", "forwardPE")
    eps     = _safe(info, "trailingEps")
    roe     = _safe(info, "returnOnEquity")
    de      = _safe(info, "debtToEquity")
    div_yld = _safe(info, "dividendYield", "trailingAnnualDividendYield")
    beta    = _safe(info, "beta")
    sector  = _safe(info, "sector", default="—")
    industry= _safe(info, "industry", default="—")
    name    = _safe(info, "longName", "shortName", default=ticker_yf)
    summary = _safe(info, "longBusinessSummary", default="")
    employees = _safe(info, "fullTimeEmployees")
    website = _safe(info, "website", default="")
    country_info = _safe(info, "country", default="")
    float_shares = _safe(info, "floatShares")
    short_ratio  = _safe(info, "shortRatio")
    peg_ratio    = _safe(info, "pegRatio")
    price_to_book= _safe(info, "priceToBook")
    ev_ebitda    = _safe(info, "enterpriseToEbitda")
    profit_margin= _safe(info, "profitMargins")
    op_margin    = _safe(info, "operatingMargins")
    rev_growth   = _safe(info, "revenueGrowth")
    earn_growth  = _safe(info, "earningsGrowth")
    curr_ratio   = _safe(info, "currentRatio")
    quick_ratio  = _safe(info, "quickRatio")

    # Compute technicals from history
    prices = hist["Close"].dropna() if not hist.empty else pd.Series(dtype=float)
    rsi14 = calc_rsi(prices) if len(prices) >= 14 else float('nan')
    sma20  = calc_sma(prices, 20)
    sma50  = calc_sma(prices, 50)
    sma100 = calc_sma(prices, 100)
    sma200 = calc_sma(prices, 200)
    cur_price = float(prices.iloc[-1]) if len(prices) > 0 else None

    above_sma = {
        20:  cur_price > sma20  if cur_price and not math.isnan(sma20)  else False,
        50:  cur_price > sma50  if cur_price and not math.isnan(sma50)  else False,
        100: cur_price > sma100 if cur_price and not math.isnan(sma100) else False,
        200: cur_price > sma200 if cur_price and not math.isnan(sma200) else False,
    }
    sma_score = sum(above_sma.values())

    # Changes
    def pct_chg(n):
        if len(prices) <= n: return float('nan')
        return ((prices.iloc[-1] / prices.iloc[-n]) - 1) * 100

    chg_1d  = pct_chg(1)
    chg_1w  = pct_chg(5)
    chg_1m  = pct_chg(21)
    chg_3m  = pct_chg(63)
    chg_6m  = pct_chg(126)
    chg_1y  = pct_chg(252)

    # Rel vol
    if "Volume" in hist.columns and len(hist) >= 21:
        vols = hist["Volume"].dropna()
        avg20 = float(vols.iloc[-21:-1].mean())
        rel_vol = round(float(vols.iloc[-1]) / avg20, 2) if avg20 > 0 else float('nan')
    else:
        rel_vol = float('nan')

    # From 52W high/low
    y_high = fast.get("year_high") or (prices.iloc[-252:].max() if len(prices) >= 252 else prices.max())
    y_low  = fast.get("year_low")  or (prices.iloc[-252:].min() if len(prices) >= 252 else prices.min())
    from_52h = ((cur_price / y_high) - 1) * 100 if cur_price and y_high else float('nan')
    from_52l = ((cur_price / y_low) - 1) * 100  if cur_price and y_low  else float('nan')

    # Price series JSON for chart
    price_json = prices_to_json(prices)

    # Recent news
    news = []
    try:
        raw_news = t.news or []
        for n in raw_news[:6]:
            news.append({
                "title": n.get("content", {}).get("title") or n.get("title", ""),
                "url":   n.get("content", {}).get("canonicalUrl", {}).get("url") or n.get("link", "#"),
                "pub":   n.get("content", {}).get("pubDate") or n.get("providerPublishTime", ""),
                "source":n.get("content", {}).get("provider", {}).get("displayName") or n.get("publisher", ""),
            })
    except Exception as e:
        print(f"    news error: {e}")

    # Earnings dates
    earnings_dates = []
    try:
        cal = t.calendar
        if cal is not None and not cal.empty:
            for col in cal.columns:
                earnings_dates.append(str(cal[col].iloc[0]) if len(cal) > 0 else "")
    except: pass

    # Analyst recommendations
    analyst = {}
    try:
        rec = t.recommendations_summary
        if rec is not None and not rec.empty:
            latest = rec.iloc[0]
            analyst = {
                "strongBuy":  int(latest.get("strongBuy", 0)),
                "buy":        int(latest.get("buy", 0)),
                "hold":       int(latest.get("hold", 0)),
                "sell":       int(latest.get("sell", 0)),
                "strongSell": int(latest.get("strongSell", 0)),
            }
    except: pass

    # Holders
    inst_holders = []
    try:
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            for _, row in ih.head(5).iterrows():
                inst_holders.append({
                    "name": str(row.get("Holder","—")),
                    "pct":  float(row.get("% Out", 0)) * 100 if row.get("% Out") else 0,
                    "shares": int(row.get("Shares", 0)) if row.get("Shares") else 0,
                })
    except: pass

    return {
        "ticker":       ticker_yf,
        "country":      country_code,
        "name":         name,
        "sector":       sector,
        "industry":     industry,
        "summary":      summary,
        "employees":    employees,
        "website":      website,
        "currency":     fast.get("currency", ""),
        "exchange":     fast.get("exchange", ""),

        "price":        cur_price,
        "prev_close":   fast.get("prev_close"),
        "day_high":     fast.get("day_high"),
        "day_low":      fast.get("day_low"),
        "year_high":    y_high,
        "year_low":     y_low,
        "from_52h":     from_52h,
        "from_52l":     from_52l,
        "market_cap":   fast.get("market_cap"),
        "volume":       fast.get("volume"),
        "avg_vol_3mo":  fast.get("avg_vol_3mo"),
        "rel_vol":      rel_vol,
        "float_shares": float_shares,

        "chg_1d":  chg_1d,  "chg_1w":  chg_1w,
        "chg_1m":  chg_1m,  "chg_3m":  chg_3m,
        "chg_6m":  chg_6m,  "chg_1y":  chg_1y,

        "rsi14":      rsi14,
        "sma20":      sma20,  "sma50":    sma50,
        "sma100":     sma100, "sma200":   sma200,
        "above_sma":  above_sma,
        "sma_score":  sma_score,

        "pe":           pe,
        "eps":          eps,
        "roe":          roe,
        "de":           de,
        "div_yld":      div_yld,
        "beta":         beta,
        "peg":          peg_ratio,
        "pb":           price_to_book,
        "ev_ebitda":    ev_ebitda,
        "profit_margin":profit_margin,
        "op_margin":    op_margin,
        "rev_growth":   rev_growth,
        "earn_growth":  earn_growth,
        "curr_ratio":   curr_ratio,
        "quick_ratio":  quick_ratio,
        "short_ratio":  short_ratio,

        "rev_qoq":  fin_data.get("rev_qoq"),
        "rev_yoy":  fin_data.get("rev_yoy"),
        "pat_qoq":  fin_data.get("pat_qoq"),
        "pat_yoy":  fin_data.get("pat_yoy"),

        "price_json":   price_json,
        "news":         news,
        "analyst":      analyst,
        "inst_holders": inst_holders,
        "earnings_dates": earnings_dates,
        "generated_at": datetime.now().strftime("%d %b %Y %H:%M"),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HTML BUILDER
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
:root{
  --bg:#0f1117;--bg2:#151820;--bg3:#1c1f2e;
  --border:rgba(255,255,255,0.07);
  --text:#e2e4ec;--text2:#8b90a8;--text3:#4d5268;
  --accent:#5b8def;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;
  --radius:10px;--shadow:0 2px 14px rgba(0,0,0,.4);
}
html[data-theme="light"]{
  --bg:#f8fafc;--bg2:#fff;--bg3:#f1f5f9;
  --border:rgba(0,0,0,.07);--text:#1e293b;--text2:#64748b;--text3:#94a3b8;
}
html[data-theme="navy"]{
  --bg:#0a1929;--bg2:#102a43;--bg3:#173a5e;
  --border:rgba(130,180,255,.14);
  --text:#e8f0fc;--text2:#a3bcd9;--text3:#5e7d9e;
  --accent:#4d9fff;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;}
a{color:var(--accent);text-decoration:none;}a:hover{text-decoration:underline;}
.hdr{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;}
.hdr-left{display:flex;align-items:center;gap:12px;}
.back-btn{background:var(--bg3);border:1px solid var(--border);color:var(--text2);
  padding:5px 12px;border-radius:8px;font-size:12px;cursor:pointer;text-decoration:none;
  transition:all .15s;}
.back-btn:hover{border-color:var(--accent);color:var(--accent);}
.hdr-ticker{font-size:18px;font-weight:800;color:var(--accent);}
.hdr-name{font-size:13px;color:var(--text2);}
.theme-btn{background:var(--bg3);border:1px solid var(--border);color:var(--text2);
  padding:5px 10px;border-radius:8px;font-size:12px;cursor:pointer;}
.page{max-width:1200px;margin:0 auto;padding:20px;}
/* Hero row */
.hero{display:grid;grid-template-columns:1fr 340px;gap:16px;margin-bottom:20px;}
.hero-main{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:20px;}
.hero-price{font-size:36px;font-weight:800;margin-bottom:4px;}
.hero-chg{font-size:16px;font-weight:600;margin-bottom:12px;}
.hero-meta{font-size:12px;color:var(--text2);display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;}
.hero-chgs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
.chg-card{background:var(--bg3);border-radius:8px;padding:8px 12px;text-align:center;}
.chg-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px;}
.chg-val{font-size:14px;font-weight:700;}
/* Sidebar */
.hero-side{display:flex;flex-direction:column;gap:10px;}
.kv-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;}
.kv-title{font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.05em;margin-bottom:10px;}
.kv-row{display:flex;justify-content:space-between;padding:5px 0;
  border-bottom:1px solid var(--border);font-size:12px;}
.kv-row:last-child{border-bottom:none;}
.kv-label{color:var(--text2);}
.kv-val{font-weight:600;}
/* Chart area */
.chart-section{background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius);margin-bottom:16px;overflow:hidden;}
.chart-title-row{display:flex;justify-content:space-between;align-items:center;
  padding:12px 16px;border-bottom:1px solid var(--border);}
.chart-title{font-size:14px;font-weight:700;}
.tv-open-btn{background:var(--accent);color:#fff;border:none;
  border-radius:8px;padding:6px 14px;font-size:12px;font-weight:600;cursor:pointer;}
.tv-frame{width:100%;height:500px;border:none;display:block;}
/* Sparkline */
.sparkline-wrap{padding:12px 16px;}
canvas#sparkline{width:100%;height:120px;display:block;}
/* Sections */
.section-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;}
.section-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:16px;}
.section-title{font-size:13px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.05em;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);}
/* SMA gauge */
.sma-bars{display:flex;flex-direction:column;gap:6px;}
.sma-row{display:flex;align-items:center;gap:8px;font-size:12px;}
.sma-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
.sma-dot.above{background:var(--green);}
.sma-dot.below{background:var(--red);}
.sma-label{min-width:50px;color:var(--text2);}
.sma-price{font-weight:600;}
.sma-dist{color:var(--text3);font-size:11px;}
/* Analyst bar */
.analyst-bar{display:flex;height:10px;border-radius:5px;overflow:hidden;margin:10px 0;}
.ab-sb{background:#15803d;}.ab-b{background:#22c55e;}.ab-h{background:#f59e0b;}
.ab-s{background:#f97316;}.ab-ss{background:#ef4444;}
.analyst-labels{display:flex;justify-content:space-between;font-size:11px;color:var(--text3);}
/* News */
.news-list{display:flex;flex-direction:column;gap:8px;}
.news-item{padding:8px 0;border-bottom:1px solid var(--border);}
.news-item:last-child{border-bottom:none;}
.news-title{font-size:13px;font-weight:500;margin-bottom:3px;}
.news-meta{font-size:11px;color:var(--text3);}
/* Colour classes */
.pos-strong{color:#4ade80;font-weight:700;}
.pos{color:#22c55e;font-weight:600;}
.pos-dim{color:#86efac;}
.neg-strong{color:#f87171;font-weight:700;}
.neg{color:#ef4444;font-weight:600;}
.neg-dim{color:#fca5a5;}
/* 52W slider */
.range-bar-wrap{margin:10px 0;}
.range-bar{position:relative;height:6px;background:linear-gradient(to right,var(--red),var(--amber),var(--green));
  border-radius:3px;margin:6px 0;}
.range-dot{position:absolute;top:-4px;width:14px;height:14px;border-radius:50%;
  background:var(--text);border:2px solid var(--bg);transform:translateX(-50%);}
.range-labels{display:flex;justify-content:space-between;font-size:11px;color:var(--text3);}
/* Description */
.summary-text{font-size:13px;line-height:1.7;color:var(--text2);
  max-height:100px;overflow:hidden;transition:max-height .3s;}
.summary-text.expanded{max-height:none;}
.expand-btn{font-size:12px;color:var(--accent);cursor:pointer;margin-top:6px;display:inline-block;}
/* Holders */
.holder-row{display:flex;align-items:center;gap:8px;padding:5px 0;
  border-bottom:1px solid var(--border);font-size:12px;}
.holder-row:last-child{border-bottom:none;}
.holder-name{flex:1;color:var(--text);}
.holder-bar-wrap{width:80px;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;}
.holder-bar{height:100%;background:var(--accent);border-radius:3px;}
.holder-pct{min-width:36px;text-align:right;font-weight:600;color:var(--accent);}
/* Disclaimer */
.disclaimer{font-size:11px;color:var(--text3);padding:16px 0;border-top:1px solid var(--border);
  margin-top:20px;line-height:1.7;}
@media(max-width:768px){
  .hero{grid-template-columns:1fr;}
  .section-grid{grid-template-columns:1fr;}
  .hero-chgs{grid-template-columns:repeat(2,1fr);}
}
"""

_THEME_JS = """
function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  localStorage.setItem('tf_theme',t);
}
(function(){const t=localStorage.getItem('tf_theme');if(t)document.documentElement.setAttribute('data-theme',t);})();
"""

_SPARKLINE_JS = """
function drawSparkline(data){
  const canvas=document.getElementById('sparkline');
  if(!canvas||!data.length)return;
  const ctx=canvas.getContext('2d');
  const W=canvas.offsetWidth||canvas.parentElement.offsetWidth||800;
  const H=130;
  canvas.width=W; canvas.height=H;
  const vals=data.map(d=>d.v);
  const min=Math.min(...vals), max=Math.max(...vals);
  const range=max-min||1;
  const px=(v)=>((v-min)/range)*(H-20)+10;
  const py=(i)=>(i/(vals.length-1))*(W-20)+10;
  // Gradient fill
  const grad=ctx.createLinearGradient(0,0,0,H);
  grad.addColorStop(0,'rgba(91,141,239,0.3)');
  grad.addColorStop(1,'rgba(91,141,239,0)');
  ctx.beginPath();
  ctx.moveTo(py(0),H-px(vals[0]));
  for(let i=1;i<vals.length;i++) ctx.lineTo(py(i),H-px(vals[i]));
  ctx.lineTo(py(vals.length-1),H);ctx.lineTo(py(0),H);ctx.closePath();
  ctx.fillStyle=grad; ctx.fill();
  // Line
  ctx.beginPath();
  ctx.strokeStyle='#5b8def'; ctx.lineWidth=1.5;
  ctx.moveTo(py(0),H-px(vals[0]));
  for(let i=1;i<vals.length;i++) ctx.lineTo(py(i),H-px(vals[i]));
  ctx.stroke();
}
"""

def _chg_html(label, val):
    if val is None or math.isnan(val):
        return f'<div class="chg-card"><div class="chg-label">{label}</div><div class="chg-val">—</div></div>'
    cls = _color_pct(val)
    sign = "+" if val > 0 else ""
    return f'<div class="chg-card"><div class="chg-label">{label}</div><div class="chg-val {cls}">{sign}{val:.1f}%</div></div>'

def _kv(label, val, cls=""):
    return f'<div class="kv-row"><span class="kv-label">{label}</span><span class="kv-val {cls}">{val}</span></div>'

def _news_html(news):
    if not news:
        return '<p style="color:var(--text3);font-size:13px;">No recent news available.</p>'
    items = ""
    for n in news:
        title = n.get("title", "")
        url   = n.get("url", "#")
        src   = n.get("source", "")
        pub   = n.get("pub", "")
        if isinstance(pub, (int, float)):
            try:
                pub = datetime.fromtimestamp(int(pub)).strftime("%d %b %Y")
            except: pub = ""
        elif isinstance(pub, str) and pub:
            try:
                pub = pub[:10]
            except: pass
        items += f'''<div class="news-item">
  <div class="news-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
  <div class="news-meta">{src} · {pub}</div>
</div>'''
    return f'<div class="news-list">{items}</div>'

def _analyst_html(analyst):
    total = sum(analyst.values()) if analyst else 0
    if not total:
        return '<p style="color:var(--text3);font-size:13px;">No analyst data.</p>'
    def pct(k): return analyst.get(k, 0) / total * 100
    bars = (
        f'<div class="analyst-bar">'
        f'<div class="ab-sb" style="width:{pct("strongBuy"):.0f}%"></div>'
        f'<div class="ab-b"  style="width:{pct("buy"):.0f}%"></div>'
        f'<div class="ab-h"  style="width:{pct("hold"):.0f}%"></div>'
        f'<div class="ab-s"  style="width:{pct("sell"):.0f}%"></div>'
        f'<div class="ab-ss" style="width:{pct("strongSell"):.0f}%"></div>'
        f'</div>'
        f'<div class="analyst-labels">'
        f'<span>Strong Buy ({analyst.get("strongBuy",0)})</span>'
        f'<span>Buy ({analyst.get("buy",0)})</span>'
        f'<span>Hold ({analyst.get("hold",0)})</span>'
        f'<span>Sell ({analyst.get("sell",0)})</span>'
        f'<span>Strong Sell ({analyst.get("strongSell",0)})</span>'
        f'</div>'
    )
    return bars

def _holders_html(holders):
    if not holders:
        return '<p style="color:var(--text3);font-size:13px;">No holder data.</p>'
    rows = ""
    max_pct = max(h.get("pct", 0) for h in holders) or 1
    for h in holders:
        pct = h.get("pct", 0)
        bar_w = int(pct / max_pct * 100)
        rows += f'''<div class="holder-row">
  <span class="holder-name">{h["name"]}</span>
  <div class="holder-bar-wrap"><div class="holder-bar" style="width:{bar_w}%"></div></div>
  <span class="holder-pct">{pct:.1f}%</span>
</div>'''
    return rows

def _52w_slider(cur, low, high):
    if not cur or not low or not high or low >= high:
        return ""
    pct = (cur - low) / (high - low) * 100
    pct = max(0, min(100, pct))
    return f'''<div class="range-bar-wrap">
  <div class="range-bar"><div class="range-dot" style="left:{pct:.0f}%"></div></div>
  <div class="range-labels"><span>{_fmt(low)}</span><span>52W Range</span><span>{_fmt(high)}</span></div>
</div>'''

def _sma_bars(d):
    cur = d["price"]
    rows = ""
    for period, label in [(20,"SMA 20"),(50,"SMA 50"),(100,"SMA 100"),(200,"SMA 200")]:
        sma = d[f"sma{period}"]
        above = d["above_sma"].get(period, False)
        cls = "above" if above else "below"
        dist = ""
        if cur and not math.isnan(sma):
            diff = (cur / sma - 1) * 100
            sign = "+" if diff > 0 else ""
            dist = f"({sign}{diff:.1f}%)"
        rows += f'''<div class="sma-row">
  <div class="sma-dot {cls}"></div>
  <span class="sma-label">{label}</span>
  <span class="sma-price">{_fmt(sma)}</span>
  <span class="sma-dist">{dist}</span>
</div>'''
    return f'<div class="sma-bars">{rows}</div>'


def build_html(d):
    ticker  = d["ticker"]
    country = d["country"]
    name    = d["name"]
    cur     = d["price"]
    chg1d   = d["chg_1d"]
    sign    = "+" if (chg1d or 0) > 0 else ""
    chg_cls = _color_pct(chg1d) if chg1d is not None and not math.isnan(chg1d) else ""

    # TradingView symbol (strip .NS, .BO, etc. for some markets)
    tv_sym = ticker.replace(".NS","").replace(".BO","").replace(".AX","")
    tv_exchange_map = {
        "IN": "NSE", "US": "NASDAQ", "AU": "ASX", "UK": "LSE",
        "JP": "TYO", "HK": "HKEX", "KR": "KRX", "DE": "XETRA",
    }
    tv_exchange = tv_exchange_map.get(country, "")
    tv_full = f"{tv_exchange}:{tv_sym}" if tv_exchange else tv_sym

    # Currency
    cur_sym = {"USD":"$","INR":"₹","GBP":"£","EUR":"€","JPY":"¥","AUD":"A$",
               "HKD":"HK$","KRW":"₩","CAD":"C$"}.get(d.get("currency",""), "")

    price_str = f"{cur_sym}{_fmt(cur)}" if cur else "—"
    chg_str   = f"{sign}{_fmt(chg1d,2)}%" if chg1d is not None and not math.isnan(chg1d) else "—"

    # RSI color
    rsi = d["rsi14"]
    rsi_cls = "pos" if (rsi and rsi > 50) else "neg" if (rsi and rsi < 40) else ""
    rsi_str = _fmt(rsi, 1) if rsi and not math.isnan(rsi) else "—"

    # 52W from high
    f52h = d.get("from_52h")
    f52h_cls = ""
    if f52h and not math.isnan(f52h):
        if f52h >= -3:   f52h_cls = "pos-strong"
        elif f52h >= -8: f52h_cls = "pos"
        elif f52h >= -15:f52h_cls = "pos-dim"
        elif f52h >= -25:f52h_cls = "neg-dim"
        else:            f52h_cls = "neg"

    sma_score = d.get("sma_score", 0)
    sma_cls = "pos-strong" if sma_score == 4 else ("pos" if sma_score >= 3 else
              ("pos-dim" if sma_score >= 2 else "neg-dim"))

    rel_vol = d.get("rel_vol")
    rv_str = _fmt(rel_vol, 2) if rel_vol and not math.isnan(rel_vol) else "—"
    rv_cls = "pos-strong" if (rel_vol and rel_vol >= 2) else ("pos" if (rel_vol and rel_vol >= 1.5) else "")

    # Valuation
    pe_val = d.get("pe")
    pe_str = _fmt(pe_val, 1) if pe_val and not math.isnan(float(pe_val)) else "—"

    roe_val = d.get("roe")
    roe_str = _pct(roe_val) if roe_val else "—"
    roe_cls = "pos-strong" if (roe_val and float(roe_val) > 0.2) else ("pos" if (roe_val and float(roe_val) > 0.1) else "")

    de_val = d.get("de")
    de_str = _fmt(de_val, 2) if de_val and not math.isnan(float(de_val)) else "—"
    de_cls = "pos" if (de_val and float(de_val) < 0.5) else ("neg-dim" if (de_val and float(de_val) > 2) else "")

    div_val = d.get("div_yld")
    div_str = _pct(div_val) if div_val else "0%"

    # Quarterly financials
    def _qpct(v):
        if v is None: return "—", ""
        sign = "+" if v > 0 else ""
        cls = "pos" if v > 0 else "neg"
        return f"{sign}{v:.1f}%", cls

    revqoq_str, revqoq_cls = _qpct(d.get("rev_qoq"))
    revyoy_str, revyoy_cls = _qpct(d.get("rev_yoy"))
    patqoq_str, patqoq_cls = _qpct(d.get("pat_qoq"))
    patyoy_str, patyoy_cls = _qpct(d.get("pat_yoy"))

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{name} ({ticker}) — Stock analysis, price, fundamentals, technicals, news. TechnoFunda.">
<title>{ticker} — {name} | TechnoFunda</title>
<style>{_CSS}</style>
<script>{_THEME_JS}</script>
</head>
<body>

<!-- HEADER -->
<header class="hdr">
  <div class="hdr-left">
    <a href="/{country}.html" class="back-btn">← {country} Market</a>
    <div>
      <div class="hdr-ticker">{ticker}</div>
      <div class="hdr-name">{name}</div>
    </div>
  </div>
  <div style="display:flex;gap:6px">
    <button class="theme-btn" onclick="setTheme('dark')">🌙</button>
    <button class="theme-btn" onclick="setTheme('light')">☀️</button>
    <button class="theme-btn" onclick="setTheme('navy')">🌊</button>
  </div>
</header>

<div class="page">

  <!-- HERO -->
  <div class="hero">
    <div class="hero-main">
      <div class="hero-price">{price_str}</div>
      <div class="hero-chg {chg_cls}">{chg_str} today</div>
      <div class="hero-meta">
        <span>📍 {d.get('sector','—')}</span>
        <span>🏭 {d.get('industry','—')}</span>
        <span>💰 Mkt Cap: {_fmt_large(d.get('market_cap'))}</span>
        <span>🔄 Vol: {_fmt_large(d.get('volume'))}</span>
        <span>📅 {d.get('generated_at','')}</span>
      </div>
      <div class="hero-chgs">
        {_chg_html("1 Day", d.get("chg_1d"))}
        {_chg_html("1 Week", d.get("chg_1w"))}
        {_chg_html("1 Month", d.get("chg_1m"))}
        {_chg_html("3 Months", d.get("chg_3m"))}
        {_chg_html("6 Months", d.get("chg_6m"))}
        {_chg_html("1 Year", d.get("chg_1y"))}
      </div>
    </div>

    <div class="hero-side">
      <div class="kv-card">
        <div class="kv-title">Key Stats</div>
        {_kv("RSI (14)", rsi_str, rsi_cls)}
        {_kv("SMA Score", f"{sma_score}/4", sma_cls)}
        {_kv("Rel Volume", rv_str, rv_cls)}
        {_kv("From 52W High", f"{_fmt(d.get('from_52h'),1)}%" if d.get('from_52h') and not math.isnan(d['from_52h']) else "—", f52h_cls)}
        {_kv("Beta", _fmt(d.get('beta'),2))}
        {_kv("52W High", f"{cur_sym}{_fmt(d.get('year_high'))}")}
        {_kv("52W Low", f"{cur_sym}{_fmt(d.get('year_low'))}")}
        {_kv("Avg Vol (3M)", _fmt_large(d.get('avg_vol_3mo')))}
      </div>
      <div class="kv-card">
        <div class="kv-title">Valuation</div>
        {_kv("P/E", pe_str)}
        {_kv("P/B", _fmt(d.get('pb'),2))}
        {_kv("PEG", _fmt(d.get('peg'),2))}
        {_kv("EV/EBITDA", _fmt(d.get('ev_ebitda'),1))}
        {_kv("EPS (TTM)", _fmt(d.get('eps'),2))}
        {_kv("Dividend Yield", div_str)}
        {_kv("ROE", roe_str, roe_cls)}
        {_kv("D/E Ratio", de_str, de_cls)}
      </div>
    </div>
  </div>

  <!-- 52W RANGE BAR -->
  {_52w_slider(cur, d.get('year_low'), d.get('year_high'))}

  <!-- TV CHART -->
  <div class="chart-section">
    <div class="chart-title-row">
      <span class="chart-title">📊 TradingView Chart — {ticker}</span>
      <a href="https://www.tradingview.com/chart/?symbol={tv_full}" target="_blank">
        <button class="tv-open-btn">Open Full Chart ↗</button>
      </a>
    </div>
    <iframe class="tv-frame"
      src="https://s.tradingview.com/widgetembed/?frameElementId=tv_chart_{ticker.replace('.','_')}&symbol={tv_full}&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=0&toolbarbg=f1f3f6&studies=RSI@tv-basicstudies&theme=dark&style=1&timezone=exchange&withdateranges=1&showpopupbutton=1"
      allowtransparency="true" allowfullscreen></iframe>
  </div>

  <!-- SPARKLINE (1Y) -->
  <div class="chart-section">
    <div class="chart-title-row"><span class="chart-title">📉 1-Year Price History</span></div>
    <div class="sparkline-wrap"><canvas id="sparkline"></canvas></div>
  </div>

  <!-- TECHNICALS + FUNDAMENTALS -->
  <div class="section-grid">
    <div class="section-card">
      <div class="section-title">Moving Averages</div>
      {_sma_bars(d)}
      <div style="margin-top:10px;font-size:12px;color:var(--text2);">
        SMA Score: <strong class="{sma_cls}">{sma_score}/4</strong> —
        {"All above 4 MAs" if sma_score==4 else f"{sma_score} of 4 MAs above price" if sma_score>0 else "Below all key MAs"}
      </div>
    </div>

    <div class="section-card">
      <div class="section-title">Growth & Profitability</div>
      {_kv("Revenue QoQ", revqoq_str, revqoq_cls)}
      {_kv("Revenue YoY", revyoy_str, revyoy_cls)}
      {_kv("Net Profit QoQ", patqoq_str, patqoq_cls)}
      {_kv("Net Profit YoY", patyoy_str, patyoy_cls)}
      {_kv("Revenue Growth (TTM)", _pct(d.get('rev_growth')), _color_pct((d.get('rev_growth') or 0)*100))}
      {_kv("Earnings Growth (TTM)", _pct(d.get('earn_growth')), _color_pct((d.get('earn_growth') or 0)*100))}
      {_kv("Profit Margin", _pct(d.get('profit_margin')))}
      {_kv("Operating Margin", _pct(d.get('op_margin')))}
    </div>

    <div class="section-card">
      <div class="section-title">Financial Health</div>
      {_kv("Current Ratio", _fmt(d.get('curr_ratio'),2))}
      {_kv("Quick Ratio", _fmt(d.get('quick_ratio'),2))}
      {_kv("D/E Ratio", de_str, de_cls)}
      {_kv("ROE", roe_str, roe_cls)}
      {_kv("Short Ratio", _fmt(d.get('short_ratio'),1))}
      {_kv("Float", _fmt_large(d.get('float_shares')))}
      {_kv("Employees", _fmt(d.get('employees'),0) if d.get('employees') else "—")}
      {_kv("Website", f'<a href="{d.get("website","")}" target="_blank">↗ Visit</a>' if d.get("website") else "—")}
    </div>

    <div class="section-card">
      <div class="section-title">Analyst Ratings</div>
      {_analyst_html(d.get("analyst",{}))}
    </div>
  </div>

  <!-- NEWS + SHAREHOLDERS -->
  <div class="section-grid">
    <div class="section-card">
      <div class="section-title">Recent News</div>
      {_news_html(d.get("news",[]))}
    </div>

    <div class="section-card">
      <div class="section-title">Top Institutional Holders</div>
      {_holders_html(d.get("inst_holders",[]))}
    </div>
  </div>

  <!-- ABOUT -->
  {'<div class="section-card" style="margin-bottom:16px"><div class="section-title">About ' + name + '</div><div class="summary-text" id="sum-text">' + (d.get("summary","") or "") + '</div><span class="expand-btn" onclick="expandSum()">Read more ▾</span></div>' if d.get("summary") else ""}

  <div class="disclaimer">
    <strong>Disclaimer:</strong> This page is generated automatically for informational and educational purposes only.
    It does not constitute investment advice. Data sourced from public market feeds. Always do your own research.
    TechnoFunda · Generated {d.get('generated_at','')}
  </div>

</div><!-- /page -->

<script>
{_SPARKLINE_JS}
// Load sparkline
const priceData = {d['price_json']};
window.addEventListener('load', ()=>drawSparkline(priceData));
window.addEventListener('resize', ()=>drawSparkline(priceData));

function expandSum(){{
  const el=document.getElementById('sum-text');
  el.classList.toggle('expanded');
  this.textContent=el.classList.contains('expanded')?'Show less ▴':'Read more ▾';
}}
</script>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def generate(ticker_yf, country_code, output_dir=None):
    print(f"\nGenerating stock page: {ticker_yf} [{country_code}]")
    data = fetch_stock_data(ticker_yf, country_code)
    html = build_html(data)

    # Build filename: e.g. IN_RELIANCE.html
    sym_clean = ticker_yf.split(".")[0].upper()
    filename  = f"{country_code}_{sym_clean}.html"
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, filename)
    else:
        out_path = filename

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ Saved: {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_stock_page.py <TICKER.SUFFIX> <COUNTRY> [output_dir]")
        print("  e.g.  python generate_stock_page.py RELIANCE.NS IN")
        print("  e.g.  python generate_stock_page.py AAPL US ./stocks/")
        sys.exit(1)
    ticker   = sys.argv[1]
    country  = sys.argv[2].upper()
    out_dir  = sys.argv[3] if len(sys.argv) > 3 else None
    generate(ticker, country, out_dir)
