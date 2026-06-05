"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  HTML REPORT GENERATOR  v6.2  —  market_html.py                           ║
║                                                                            ║
║  v6.2 additions:                                                           ║
║   • TradingView hover-preview on every Symbol link                         ║
║     – Fast: single pre-warmed hidden iframe, src-swap on hover             ║
║     – On/Off toggle button in the header controls bar                      ║
║     – Size config: TV_PREVIEW_W / TV_PREVIEW_H JS constants                ║
║     – Auto-detects theme (dark/light) to match report theme                ║
║                                                                            ║
║  v6.1 additions:                                                           ║
║   • Fix NameError: _sec/_toggle restored inside build_html_report          ║
║   • Sleeves tab: capital input + ATR-weighted qty + amount calculator      ║
║   • Sleeves tab: Zerodha basket CSV download (NSE/BSE, CNC, MARKET)        ║
║   • Sleeves tab: Entry tracking via window.storage (P&L on next run)       ║
║   • Chart Patterns: own dedicated tab, not buried in Global                ║
║   • 4 separate sleeve tables (A/B/C/D) with interactive calculator         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import pandas as pd
import os
import re
from datetime import datetime, timedelta

# Chart-pattern recency cap (days). Patterns older than this are hidden in the
# Patterns tab regardless of timeframe. See request #8.
PATTERN_RECENT_DAYS = 15


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL LABEL → CSS CLASS
# ─────────────────────────────────────────────────────────────────────────────

_SL_CLASS = {
    "🌟 Triple Confirmed": "sl-triple",
    "🌟 RS30 + Long":      "sl-triple",
    "🌟 RS30 + Swing":     "sl-prime",
    "🌟 RS30 Leader":      "sl-prime",
    "🌟 Long Momentum":    "sl-prime",
    "🌟 Prime Setup":      "sl-prime",
    "✅ Long Momentum":    "sl-confirmed",
    "✅ Strong RS":        "sl-confirmed",
    "📈 Swing Entry":      "sl-rsbuy",
    "📈 RS Leader":        "sl-rsbuy",
    "👁 Setup Building":   "sl-watch",
    "👁 RS30 Watch":       "sl-watch",
    "👁 LST Watch":        "sl-watch",
    "👁 MST Watch":        "sl-watch",
    "👁 Watch":            "sl-watch",
    "⬜ Neutral":          "sl-neutral",
    "🔴 RS Breakdown":     "sl-avoid",
}
_AT_CLASS = {
    "PRIME BUY":     "sl-prime",
    "CONFIRMED BUY": "sl-confirmed",
    "RS BUY":        "sl-rsbuy",
    "WATCH":         "sl-watch",
    "NEUTRAL":       "sl-neutral",
    "AVOID":         "sl-avoid",
}


def _signal_class(val):
    v = str(val or "")
    return _SL_CLASS.get(v) or _AT_CLASS.get(v) or ""


# Normalised lookup key: lowercase, strip spaces / underscores / '>' so that
# headers like "RS_22%", "% > SMA50", "AbvSMA50%", "1M_Score" all collapse to
# the same canonical token. Fixes breadth/rotation colours not firing (#6/#7).
def _norm_key(col):
    return re.sub(r"[\s_>]", "", str(col).lower().strip())

# 0-100 breadth / score columns → ≥60 green · 40-60 orange · <40 red.
_BREADTH_KEYS = {_norm_key(c) for c in (
    "rs22%", "rs55%", "rsi50%", "rsi>50%",
    "abvsma20%", "abvsma50%", "abvsma100%", "abvsma200%",
    "%>sma20", "%>sma50", "%>sma100", "%>sma200",
    "1m_score", "3m_score", "6m_score", "12m_score",
    "breadth%", "breadth_score", "momentum_score",
)}
# Return / change columns stay on the diverging (pos/neg) scale even inside a
# breadth-mode table — these are NOT 0-100 figures.
_RETURN_KEYS = {_norm_key(c) for c in (
    "chg1d%", "chg5d%",
    "rs22d%", "rs55d%", "rs120d%", "rs252d%",
    "rs22didx%", "rs55didx%", "rs120didx%", "rs252didx%",
    "rs22dsec%", "rs55dsec%",
    "1m%", "3m%", "6m%", "12m%", "ytd%",
    "salesyoy%", "patyoy%", "salesqoq%", "patqoq%",
    "roe%", "margin%", "wrs21%", "wrs30%", "mrs12%", "sleevers",
)}


def _is_breadth_col(col, pct_mode=None):
    """Should this column use the 60/40 green/amber/red breadth scale?"""
    k = _norm_key(col)
    if k in _RETURN_KEYS:
        return False
    if k in _BREADTH_KEYS:
        return True
    # score / breadth columns wherever they appear (sector & industry rotation)
    if ("score" in k or "breadth" in k or "percentile" in k) and "scorecard" not in k:
        return True
    # In a dedicated breadth table, treat every remaining percent column as 0-100
    if pct_mode == "breadth" and k.endswith("%"):
        return True
    return False


def _cell_class(col, val, pct_mode=None):
    # Breadth / rotation 0-100 colouring takes priority for the columns it owns.
    if _is_breadth_col(col, pct_mode):
        try:
            f = float(val)
            if f >= 60: return "bd-green"
            if f >= 40: return "bd-amber"
            return "bd-red"
        except: pass
    col = str(col).lower().strip()
    if col == "signal_label":  return _signal_class(val)
    if col == "action_tier":   return _signal_class(val)
    if col in ("signal","enhanced","sec_signal"):
        return {"Strong Buy":"sig-strongbuy","Buy":"sig-buy",
                "Sell":"sig-sell","Neutral":"sig-neutral"}.get(str(val),"")
    if col == "action":
        return {"BUY":"sig-buy","SELL":"sig-sell","WAIT":"sig-neutral"}.get(str(val),"")
    if col in ("mst_signal","lst_signal","rs30_signal"):
        return {"Buy":"sig-buy","Watch":"sig-neutral","Neutral":""}.get(str(val),"")
    if col == "supertrend":
        return {"Buy":"pos","Sell":"neg"}.get(str(val),"")
    if col == "trend":
        v = str(val)
        if "Bullish" in v or "BULLISH" in v: return "pos-strong"
        if "Bearish" in v or "BEARISH" in v: return "neg-strong"
        return ""
    if col == "sec_gated":
        return "pos-strong" if str(val) == "✓" else "dim"
    if col == "sl_grade":
        return {"A":"pos-strong","B":"pos","C":"pos-dim",
                "D":"neg-dim","F":"neg"}.get(str(val),"")
    if col in ("sl_buy%","sl%","sl_sell%"):
        try:
            f = float(val)
            if f <= 3:  return "pos-strong"
            if f <= 5:  return "pos"
            if f <= 8:  return "pos-dim"
            if f <= 12: return "neg-dim"
            return "neg"
        except: pass
    # (Breadth / rotation 0-100 colouring handled at the top of _cell_class.)
    # EPS: positive = green, negative = red (raw currency value, not %)
    if col == "eps":
        try:
            f = float(val)
            if f > 0:  return "pos"
            if f < 0:  return "neg-strong"
        except: pass
    pct_cols = {
        "chg_1d%","chg_5d%","rs_22d%","rs_55d%","rs_120d%","rs_252d%",
        "rs_22d_idx%","rs_55d_idx%","rs_120d_idx%","rs_252d_idx%",
        "1m%","3m%","6m%","12m%","ytd%","sales_yoy%","pat_yoy%",
        "sales_qoq%","pat_qoq%","roe%","margin%","w_rs21%","w_rs30%",
        "m_rs12%","sec_rs22d%","sec_rs55d%","sleeve_rs",
    }
    if col in pct_cols or col.endswith("%"):
        try:
            f = float(val)
            if f > 5:  return "pos-strong"
            if f > 0:  return "pos"
            if f < -5: return "neg-strong"
            if f < 0:  return "neg"
        except: pass
    return ""


def _fmt(val):
    if val is None: return ""
    if isinstance(val, float):
        if np.isnan(val): return ""
        if val == int(val) and abs(val) < 1e9: return str(int(val))
        return f"{val:.2f}"
    s = str(val)
    return "" if s in ("nan","None","") else s


_CUR_MKT = "INDIA"   # set per-report by build_html_report; used for TradingView links

# ── yfinance suffix  →  TradingView exchange prefix ──────────────────────────
# Sorted longest-first so ".TWO" is checked before ".T", ".KL" before ".L", etc.
_SUFFIX_MAP = {
    # India
    ".NS": "NSE",  ".BO": "BSE",
    # Saudi Arabia
    ".SR": "TADAWUL",
    # China
    ".SS": "SSE",  ".SH": "SSE",          # Shanghai (.SS = yfinance, .SH = other)
    ".SZ": "SZSE",                          # Shenzhen
    # Hong Kong
    ".HK": "HKEX",
    # Japan
    ".T":  "TSE",
    # South Korea
    ".KS": "KRX",  ".KQ": "KOSDAQ",
    # Taiwan
    ".TWO": "TPEX",  ".TW": "TWSE",
    # Australia
    ".AX": "ASX",
    # UK
    ".L":  "LSE",
    # Germany
    ".DE": "XETRA",  ".F": "FWB",
    # France / Netherlands (Euronext)
    ".PA": "EURONEXT",  ".AS": "EURONEXT",
    # Spain
    ".MC": "BME",
    # Italy
    ".MI": "MIL",
    # Sweden / Nordics
    ".ST": "OMX",
    # Switzerland
    ".SW": "SWX",
    # Canada
    ".TO": "TSX",  ".V": "TSXV",
    # Brazil
    ".SA": "BMFBOVESPA",
    # Singapore
    ".SI": "SGX",
    # Thailand
    ".BK": "SET",
    # Malaysia
    ".KL": "KLSE",
    # South Africa
    ".JO": "JSE",
    # Poland
    ".WA": "GPW",
    # Turkey  (yfinance uses .IS)
    ".IS": "BIST",
    # UAE
    ".DU": "DFM",  ".AD": "ADX",
    # Indonesia
    ".JK": "IDX",
    # Mexico
    ".MX": "BMV",
}
# Pre-sort by length descending once so the loop is always correct.
_SUFFIX_ITEMS = sorted(_SUFFIX_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# When a symbol has NO file-extension suffix, fall back to the market code.
_MARKET_EXCHANGE = {
    "INDIA": "NSE",
    "USA":   "",            # US: bare symbol; TV resolves it natively
    "UK":    "LSE",
    "DE":    "XETRA",
    "JP":    "TSE",
    "CN":    "SSE",
    "HK":    "HKEX",
    "KR":    "KRX",
    "TW":    "TWSE",
    "AU":    "ASX",
    "CA":    "TSX",
    "SA":    "TADAWUL",     # market code SA = Saudi Arabia
    "BR":    "BMFBOVESPA",
    "SG":    "SGX",
    "TH":    "SET",
    "MY":    "KLSE",
    "ZA":    "JSE",
    "PL":    "GPW",
    "TR":    "BIST",
    "AE":    "DFM",         # UAE default → Dubai Financial Market
    "ID":    "IDX",
    "MX":    "BMV",
    "CH":    "SWX",
    "FR":    "EURONEXT",
    "ES":    "BME",
    "IT":    "MIL",
    "NL":    "EURONEXT",
    "SE":    "OMX",
}


def _tv_link(sym, market=None):
    """Wrap a ticker in a TradingView chart hyperlink.

    Strips yfinance-style country suffixes (e.g. .SR, .SS, .SZ, .HK, .KS, .T …)
    and builds a correctly prefixed TradingView URL so Saudi, China, HK, Korea,
    Japan, etc. all resolve instead of showing a broken symbol page.
    Falls back to the market-code exchange when the symbol carries no suffix.
    """
    market = (market or _CUR_MKT).upper()
    s = str(sym).strip()
    if not s or s in ("—", "nan", "None"):
        return _fmt(sym)

    base = s
    exch = ""
    su   = s.upper()

    # 1. Try every known suffix (longest first avoids partial matches).
    for suf, tv_exch in _SUFFIX_ITEMS:
        if su.endswith(suf.upper()):
            base = s[: -len(suf)]
            exch = tv_exch
            break

    # 2. No suffix found — use market-level default.
    if exch == "" and base == s:
        exch = _MARKET_EXCHANGE.get(market, "")

    tv  = (exch + "%3A" + base) if exch else base
    url = "https://www.tradingview.com/chart/?symbol=" + tv
    return (f'<a href="{url}" target="_blank" rel="noopener" '
            f'class="tv-link" data-tv="{tv}" title="Open {base} in TradingView">{base}</a>')


# ─────────────────────────────────────────────────────────────────────────────
#  TABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

_SKIP_COLS = {"tv_symbol","_o","primary_rs_period"}
_LEFT_COLS = {"symbol","company","name","sector","industry","country","region",
              "commodity","group","chart_pattern","setup_desc","strategy","notes",
              "signal_type","trend","signal_label","etf"}


def _build_table(df, table_id, searchable=True, max_rows=2000, pct_mode=None):
    if df is None or df.empty:
        return '<p class="empty">No data available.</p>'
    df = df.head(max_rows).copy()
    cols = [c for c in df.columns if c.lower().strip() not in _SKIP_COLS]
    ths = "".join(
        f'<th style="text-align:{"left" if c.lower() in _LEFT_COLS else "center"}" '
        f'onclick="sortTable(this)">{c}</th>'
        for c in cols
    )
    rows_html = ""
    for _, row in df.iterrows():
        tds = ""
        for c in cols:
            val = row[c]; cls = _cell_class(c, val, pct_mode)
            display = _tv_link(val) if c.lower().strip() == "symbol" else _fmt(val)
            align = "left" if c.lower() in _LEFT_COLS else "center"
            ca = f' class="{cls}"' if cls else ""
            tds += f'<td{ca} style="text-align:{align}">{display}</td>'
        rows_html += f"<tr>{tds}</tr>"
    col_filter = ""
    if searchable:
        cfs = "".join(
            f'<th><input class="cf" data-col="{i}" '
            f'title="Filter: &gt;15  &lt;40  &gt;=60  10-20  or text" '
            f'oninput="filterColumn(this,\'{table_id}\')" placeholder="🔍"></th>'
            for i in range(len(cols))
        )
        col_filter = f'<tr class="col-filter">{cfs}</tr>'
    search = (f'<div class="tbl-search"><input type="text" placeholder="🔍 Filter all columns…  (per-column accepts &gt;15, &lt;40, 10-20)"'
              f' data-global-for="{table_id}" oninput="filterTable(this,\'{table_id}\')"></div>') if searchable else ""
    return (f'{search}<div class="tbl-wrap"><table id="{table_id}" class="data-tbl">'
            f'<thead><tr>{ths}</tr>{col_filter}</thead><tbody>{rows_html}</tbody></table></div>'
            f'<p class="row-count" id="{table_id}-count">{len(df)} rows</p>')


# ─────────────────────────────────────────────────────────────────────────────
#  MARKET HEALTH CARD
# ─────────────────────────────────────────────────────────────────────────────

def _build_health_card(stock_df, sector_str_df, market):
    if stock_df is None or stock_df.empty: return ""
    sl_col = "Signal_Label" if "Signal_Label" in stock_df.columns else None
    at_col = "Action_Tier"  if "Action_Tier"  in stock_df.columns else None
    def _cnt_sl(e):
        return int(stock_df[sl_col].astype(str).str.startswith(e).sum()) if sl_col else 0
    def _cnt_at(v):
        return int((stock_df[at_col] == v).sum()) if at_col else 0
    prime = _cnt_sl("🌟") or _cnt_at("PRIME BUY")
    conf  = _cnt_sl("✅") or _cnt_at("CONFIRMED BUY")
    rsbuy = _cnt_sl("📈") or _cnt_at("RS BUY")
    watch = _cnt_sl("👁") or _cnt_at("WATCH")
    avoid = _cnt_sl("🔴") or _cnt_at("AVOID")
    total = len(stock_df)
    buy_pct = round((prime+conf+rsbuy)/max(total,1)*100)
    mood, mcls = (("Risk-On 🟢","mood-on") if buy_pct>=50
                  else (("Mixed ⚪","mood-mix") if buy_pct>=25
                  else ("Risk-Off 🔴","mood-off")))
    top_secs = ""; worst_secs = ""
    if sector_str_df is not None and not sector_str_df.empty:
        for _, r in sector_str_df.head(3).iterrows():
            sig = r.get("Signal","")
            cls = "pos-strong" if sig=="Buy" else ("neg" if sig=="Sell" else "dim")
            rs  = r.get("RS_22d%", r.get("RS_55d%",0)) or 0
            top_secs += f'<span class="sec-pill {cls}">{r["Sector"]} {rs:+.1f}%</span>'
        # Worst 3 sectors (weakest first) — always shown in red
        worst = sector_str_df.tail(3).iloc[::-1]
        for _, r in worst.iterrows():
            rs = r.get("RS_22d%", r.get("RS_55d%",0)) or 0
            worst_secs += f'<span class="sec-pill neg">{r["Sector"]} {rs:+.1f}%</span>'
    return f"""<div class="health-card">
  <div class="hc-grid">
    <div class="hc-block"><div class="hc-label">Market Mood</div><div class="hc-value {mcls}">{mood}</div></div>
    <div class="hc-block"><div class="hc-label">Universe</div><div class="hc-value">{total}</div></div>
    <div class="hc-block"><div class="hc-label">Buy Setups</div><div class="hc-value pos-strong">{prime+conf+rsbuy} <span class="hc-sub">({buy_pct}%)</span></div></div>
    <div class="hc-block"><div class="hc-label">🌟 Prime</div><div class="hc-value sl-triple-inline">{prime}</div></div>
    <div class="hc-block"><div class="hc-label">✅ Confirmed</div><div class="hc-value sl-confirmed-inline">{conf}</div></div>
    <div class="hc-block"><div class="hc-label">📈 RS Buy</div><div class="hc-value sl-rsbuy-inline">{rsbuy}</div></div>
    <div class="hc-block"><div class="hc-label">👁 Watch</div><div class="hc-value sl-watch-inline">{watch}</div></div>
    <div class="hc-block"><div class="hc-label">🔴 Avoid</div><div class="hc-value sl-avoid-inline">{avoid}</div></div>
  </div>
  <div class="hc-sectors"><span class="hc-label">🟢 Top Sectors: </span>{top_secs}</div>
  <div class="hc-sectors"><span class="hc-label">🔴 Worst Sectors: </span>{worst_secs}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
#  SNAPSHOT CARDS
# ─────────────────────────────────────────────────────────────────────────────

def _build_snap_cards(snapshot_df):
    if snapshot_df is None or snapshot_df.empty: return ""
    cards = ""
    for _, row in snapshot_df.iterrows():
        name=_fmt(row.get("Name","")); price=_fmt(row.get("Price",""))
        chg1=row.get("Chg_1D%",""); trend=_fmt(row.get("Trend",""))
        if not name or "──" in name: continue
        try: cf=float(chg1); cls="pos" if cf>0 else ("neg" if cf<0 else ""); cs=f"{cf:+.2f}%"
        except: cls=""; cs=_fmt(chg1)
        tc="pos-strong" if "Bullish" in trend else ("neg-strong" if "Bearish" in trend else "dim")
        cards += (f'<div class="snap-card"><div class="snap-name">{name}</div>'
                  f'<div class="snap-price">{price}</div>'
                  f'<div class="snap-chg {cls}">{cs}</div>'
                  f'<div class="snap-trend {tc}">{trend}</div></div>')
    return f'<div class="snap-grid">{cards}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR BARS
# ─────────────────────────────────────────────────────────────────────────────

def _build_sector_bars(sector_df):
    if sector_df is None or sector_df.empty: return ""
    html = '<div class="sector-bars">'
    for _, row in sector_df.iterrows():
        sec=_fmt(row.get("Sector","")); sig=_fmt(row.get("Signal",""))
        rs22=row.get("RS_22d%",0); rs55=row.get("RS_55d%",0)
        rank=_fmt(row.get("Rank","")); rsi=_fmt(row.get("RSI_14",""))
        try: r22=float(rs22); r55=float(rs55)
        except: r22=0; r55=0
        bar_w=min(abs(r22)*3,100)
        icon="✅" if sig=="Buy" else ("🔴" if sig=="Sell" else "⬜")
        sc="sig-buy" if sig=="Buy" else ("sig-sell" if sig=="Sell" else "sig-neutral")
        rsi_cls="pos" if rsi and float(rsi)>50 else "neg" if rsi and float(rsi)<50 else ""
        html += (f'<div class="sec-row">'
                 f'<div class="sec-rank">#{rank}</div>'
                 f'<div class="sec-name">{icon} {sec}</div>'
                 f'<div class="sec-bar-wrap"><div class="sec-bar {"bar-pos" if r22>=0 else "bar-neg"}" style="width:{bar_w:.0f}%"></div></div>'
                 f'<div class="sec-rs {"" if r22>=0 else "neg"}">{r22:+.1f}%</div>'
                 f'<div class="sec-rs55 {"" if r55>=0 else "neg"}">{r55:+.1f}%</div>'
                 f'<div class="sec-rsi {rsi_cls}">RSI {rsi}</div>'
                 f'<div class="{sc} sec-sig-badge">{sig}</div></div>')
    return html + "</div>"


# ─────────────────────────────────────────────────────────────────────────────
#  OPPORTUNITY CARDS
# ─────────────────────────────────────────────────────────────────────────────

def _build_opportunity_cards(df):
    if df is None or df.empty: return ""
    if "Message" in df.columns:
        return f'<p class="empty">{df["Message"].iloc[0]}</p>'
    prev_sec=""; html=""
    for _, row in df.iterrows():
        sec=_fmt(row.get("Sector","")); sym=_fmt(row.get("Symbol",""))
        if not sym: continue
        if sec != prev_sec:
            sec_sig=_fmt(row.get("Sec_Signal",""))
            sec_rs=row.get("Sec_RS22d%",row.get("Sec_RS55d%",""))
            try: rs_s=f"{float(sec_rs):+.1f}%"
            except: rs_s=_fmt(sec_rs)
            sc="sig-buy" if sec_sig=="Buy" else ("sig-sell" if sec_sig=="Sell" else "sig-neutral")
            html += (f'<div class="opp-sec-hdr"><span>{sec}</span>'
                     f'<span class="{sc}">{sec_sig} {rs_s}</span></div>')
            prev_sec=sec
        sl=_fmt(row.get("Signal_Label",row.get("Action_Tier",""))); sl_c=_signal_class(sl)
        company=_fmt(row.get("Company","")); price=_fmt(row.get("Price",""))
        rs22=row.get("RS_22d_Idx%",""); rsi=_fmt(row.get("RSI_14",""))
        sl_pct=_fmt(row.get("SL_Buy%","")); sl_gr=_fmt(row.get("SL_Grade",""))
        score=_fmt(row.get("Total_Score","")); sal_yoy=_fmt(row.get("Sales_YoY%",""))
        pat_yoy=_fmt(row.get("PAT_YoY%","")); chart_p=_fmt(row.get("Chart_Pattern",""))
        try: rs_s=f"{float(rs22):+.1f}%"
        except: rs_s=_fmt(rs22)
        rs_cls="pos-strong" if rs_s.startswith("+") else "neg-strong"
        sl_g_cls={"A":"pos-strong","B":"pos","C":"pos-dim","D":"neg-dim","F":"neg"}.get(sl_gr,"")
        html += f"""<div class="opp-card">
  <div class="opp-head"><span class="opp-sym">{_tv_link(sym)}</span><span class="sl-badge {sl_c}">{sl}</span></div>
  <div class="opp-company">{company}</div>
  <div class="opp-metrics">
    <div class="m-row"><span class="ml">Price</span><span>{price}</span></div>
    <div class="m-row"><span class="ml">RS 22d</span><span class="{rs_cls}">{rs_s}</span></div>
    <div class="m-row"><span class="ml">RSI</span><span>{rsi}</span></div>
    <div class="m-row"><span class="ml">SL%</span><span>{sl_pct}% <span class="{sl_g_cls}">[{sl_gr}]</span></span></div>
    <div class="m-row"><span class="ml">Score</span><span class="pos">{score}</span></div>
    <div class="m-row"><span class="ml">Sales YoY</span><span>{sal_yoy}%</span></div>
    <div class="m-row"><span class="ml">PAT YoY</span><span>{pat_yoy}%</span></div>
  </div>
  {f'<div class="opp-pattern">{chart_p}</div>' if chart_p else ''}
  <button class="copy-btn sm" data-orig="📋" onclick="copyText(this,'{sym},')">📋 TV</button>
</div>"""
    return f'<div class="opp-cards">{html}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  SLEEVE TABLES  —  Interactive position sizing + Zerodha basket + tracking
# ─────────────────────────────────────────────────────────────────────────────

_SLEEVE_META = {
    "A":    ("sl-confirmed","Core — Large Cap",       "Monthly · Nifty 1–50"),
    "B":    ("sl-rsbuy",    "Growth — Mid-Large",     "Fortnightly · Nifty 51–200"),
    "C":    ("sl-watch",    "Aggressive — Small-Mid", "Weekly · Nifty 201–500"),
    "D":    ("sl-neutral",  "Global ETFs",            "Monthly · Country + Commodity"),
    "US_A": ("sl-confirmed","Mega Cap",               "Monthly · S&P Top 50"),
    "US_B": ("sl-rsbuy",    "Large Cap",              "Fortnightly · S&P 51–200"),
    "US_C": ("sl-watch",    "Mid Cap",                "Weekly · S&P 201–500"),
    "US_D": ("sl-neutral",  "Global ETFs",            "Monthly · Country + Commodity"),
}

# Columns to show in sleeve tables (will auto-filter to available ones)
_SLEEVE_SHOW = ["Rank","Symbol","Company","Sector","Signal_Label",
                "Price","Sleeve_RS","RS_22d_Idx%","RS_55d_Idx%",
                "SL_Buy%","SL_Grade","Equal_Wt%","ATR_Wt%",
                "Sales_YoY%","PAT_YoY%","ROE%"]


def _build_sleeve_tables(sleeve_df, market="INDIA"):
    """
    Parse combined sleeve_df → 4 separate interactive tables.
    Each table has:
      • Capital input + auto qty/amount/SL-price calculator
      • Zerodha basket CSV download (NSE/BSE)
      • 'Track Entry' button → saves prices to window.storage
      • P&L column loaded from storage on page open
    """
    if sleeve_df is None or sleeve_df.empty:
        return '<p class="empty">Sleeve data unavailable.</p>'

    # ── Parse sleeve sections from combined df ─────────────────────────────
    sections: dict = {}
    cur_key = None; cur_rows = []
    for _, row in sleeve_df.iterrows():
        rv = str(row.get("Rank","") or "")
        if rv.startswith("━━━") and "SLEEVE" in rv.upper():
            if cur_key and cur_rows: sections[cur_key] = cur_rows[:]
            cur_key = None; cur_rows = []
            for k in ["US_D","US_C","US_B","US_A","D","C","B","A"]:
                if f"SLEEVE {k}" in rv.upper(): cur_key=k; break
        elif cur_key and str(rv).strip().isdigit():
            cur_rows.append(dict(row))
    if cur_key and cur_rows: sections[cur_key] = cur_rows

    if not sections:
        # Flat fallback
        try:
            data = sleeve_df[sleeve_df["Rank"].astype(str).str.strip().str.isdigit()].copy()
            cols = [c for c in _SLEEVE_SHOW if c in data.columns]
            return _build_table(data[cols] if cols else data, "tbl-sleeve-all")
        except: return _build_table(sleeve_df, "tbl-sleeve-all")

    is_india = (market == "INDIA")
    currency  = "₹" if is_india else "$"
    default_capital = "1000000" if is_india else "50000"

    html = f"""<div class="sleeve-global-ctrl">
  <div class="ctrl-row">
    <div class="ctrl-field">
      <label class="ctrl-label">Portfolio Capital ({currency})</label>
      <input type="number" id="global-capital" class="cap-input"
             value="{default_capital}" placeholder="{default_capital}"
             oninput="recalcAll()">
    </div>
    <div class="ctrl-field">
      <label class="ctrl-label">Risk per stock (%&nbsp;of&nbsp;capital)</label>
      <input type="number" id="global-risk" class="cap-input" style="width:90px"
             value="1" min="0.1" max="5" step="0.1" oninput="recalcAll()">
    </div>
    <div class="ctrl-field">
      <label class="ctrl-label">Max SL cap (%)</label>
      <input type="number" id="global-sl-cap" class="cap-input" style="width:80px"
             value="5" min="1" max="15" step="0.5" oninput="recalcAll()">
    </div>
  </div>
  <div class="ctrl-formula">
    <strong>Formula:</strong>
    Qty&nbsp;=&nbsp;⌊ (Capital&nbsp;×&nbsp;Risk%) &nbsp;÷&nbsp; (Price&nbsp;×&nbsp;effective_SL%) ⌋
    &nbsp;·&nbsp;
    effective_SL&nbsp;=&nbsp;min(SL_Buy%,&nbsp;Max&nbsp;SL&nbsp;cap)
    &nbsp;·&nbsp;
    If SL_Buy% missing → uses Max SL cap as fallback
  </div>
</div>"""

    for key, rows in sections.items():
        if not rows: continue
        df_sec = pd.DataFrame(rows).reset_index(drop=True)
        meta   = _SLEEVE_META.get(key, ("sl-neutral", key, ""))
        badge_cls, label, subtitle = meta
        safe_key = key.lower().replace("_","")
        n = len(df_sec)

        # Build table rows with data-* attributes for JS
        risk_currency = "₹" if is_india else "$"
        thead_extra = (f"<th title='Risk-based quantity'>Qty</th>"
                       f"<th title='Qty × Price'>Amount ({currency})</th>"
                       f"<th title='Hard stop price'>SL Price</th>"
                       f"<th title='Max loss if stopped out'>Risk ({risk_currency})</th>"
                       f"<th title='Eff. SL% used'>eSL%</th>"
                       f"<th title='P&amp;L vs tracked entry'>P&amp;L</th>")
        show_cols = [c for c in _SLEEVE_SHOW if c in df_sec.columns]

        ths = "".join(
            f'<th style="text-align:{"left" if c.lower() in _LEFT_COLS else "center"}">{c}</th>'
            for c in show_cols
        ) + thead_extra

        tbody = ""
        for _, row in df_sec.iterrows():
            sym   = str(row.get("Symbol","") or "").replace(".NS","").replace(".BO","")
            price = _fmt(row.get("Price",""))
            atrwt = _fmt(row.get("ATR_Wt%", row.get("Equal_Wt%","")))
            sl_pct= _fmt(row.get("SL_Buy%",""))
            # data-* attributes for JS calculator
            attrs = (f'data-sym="{sym}" data-price="{price}" '
                     f'data-atrwt="{atrwt}" data-sl="{sl_pct}"')
            tds = ""
            for c in show_cols:
                val=row.get(c,""); cls=_cell_class(c,val)
                display=(_tv_link(val, "US" if key.startswith("US_") else _CUR_MKT)
                         if c.lower().strip()=="symbol" else _fmt(val))
                align="left" if c.lower() in _LEFT_COLS else "center"
                ca=f' class="{cls}"' if cls else ""
                tds += f'<td{ca} style="text-align:{align}">{display}</td>'
            # Calculator cells (filled by JS)
            tds += ('<td class="calc-cell qty-cell">—</td>'
                    '<td class="calc-cell amt-cell">—</td>'
                    '<td class="calc-cell slp-cell">—</td>'
                    '<td class="calc-cell rsk-cell">—</td>'
                    '<td class="calc-cell esl-cell">—</td>'
                    '<td class="calc-cell pl-cell">—</td>')
            tbody += f'<tr {attrs}>{tds}</tr>'

        # Broker buttons — Zerodha for India, IBKR for US (both shown for India as optional)
        is_us_sleeve = key.startswith("US_")
        if is_us_sleeve:
            broker_btns = (
                f'<button class="action-btn blue" onclick="downloadIBKR(\'{safe_key}\',\'False\')">'
                f'📥 IBKR Basket CSV</button>'
            )
        else:
            broker_btns = (
                f'<button class="action-btn orange" onclick="downloadZerodha(\'{safe_key}\')">'
                f'📥 Zerodha Basket JSON</button>'
                f'<button class="action-btn blue" onclick="downloadIBKR(\'{safe_key}\',\'True\')">'
                f'📥 IBKR Basket CSV</button>'
            )

        html += f"""<div class="sleeve-block">
  <div class="sleeve-header">
    <span class="sl-badge {badge_cls}">{key}</span>
    <div class="sleeve-title">{label}</div>
    <div class="sleeve-sub">{subtitle} · {n} stocks</div>
    <div class="sleeve-summary" id="sum-{safe_key}"></div>
  </div>

  <div class="sleeve-actions">
    <button class="action-btn green" onclick="calcSleeve('{safe_key}')">⚡ Recalculate</button>
    {broker_btns}
    <button class="action-btn amber" onclick="trackEntry('{safe_key}')">💾 Track Entry</button>
    <button class="action-btn grey"  onclick="clearTracking('{safe_key}')">🗑 Clear Tracking</button>
    <span class="track-msg" id="tmsg-{safe_key}"></span>
    <span class="entry-date" id="edate-{safe_key}"></span>
  </div>

  <div class="tbl-wrap">
    <table id="sleeve-{safe_key}" class="data-tbl sleeve-tbl">
      <thead><tr>{ths}</tr></thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
  <div class="sleeve-footer">
    Total Deployed: <strong id="total-{safe_key}">—</strong> &nbsp;|&nbsp;
    Total P&amp;L: <strong id="plsum-{safe_key}">—</strong>
  </div>
</div>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL GUIDE
# ─────────────────────────────────────────────────────────────────────────────

_GUIDE_ROWS = [
    ("🌟 Triple Confirmed","sl-triple",
     "RS30 + LST + MST all Buy. Highest conviction. All TFs aligned.",
     "Weekly RS30>0, monthly RS12>0, daily RS55>0. Price > 20d swing high."),
    ("🌟 RS30 Leader","sl-prime",
     "Weekly RS(30)>0 + EMA10>EMA30 + within 10% of 52W High + Sales QoQ≥15% + PAT QoQ≥15%.",
     "TechnoFunda weekly momentum strategy. Breakout above 20-day swing high required."),
    ("🌟 Long Momentum","sl-prime",
     "LST Buy + strong fundamentals (fin_score≥5). Monthly trend bullish. 60-120 day swing.",
     "Monthly RS12>0, RSI12>50, Revenue+, PAT+. Weekly RS21>0 + ST + EMA200."),
    ("✅ Long Momentum","sl-confirmed",
     "LST Buy. Monthly pre-conditions + weekly entry confirmed. 60-120 day swing.",
     "Monthly RS12>0 + RSI12>50. Weekly RS21>0 + RSI12>50 + Supertrend + EMA200."),
    ("✅ Strong RS","sl-confirmed",
     "All 5 peer filters: RS Buy + beats sector avg + beats industry avg + sector>0 + industry>0.",
     "Four RS checks positive + stock outperforms peers on RS_55d."),
    ("📈 Swing Entry","sl-rsbuy",
     "MST Buy. Weekly pre-cond + daily entry + 20d breakout. 20-60 day swing.",
     "Weekly RS21>0, RSI>50. Daily RS55>0, RSI>50, Supertrend=Buy, Close>EMA200, breakout."),
    ("📈 RS Leader","sl-rsbuy",
     "RS Buy: RS_22d>0 AND RS_55d>0 vs index AND sector. Awaiting TF confirmation.",
     "Four RS checks positive: 22d-idx, 55d-idx, 22d-sec, 55d-sec."),
    ("👁 Watch","sl-watch",
     "Pre-conditions met, no breakout yet. Wait for close above 20-day swing high.",
     "RS30/LST/MST Watch: technical setup building, entry trigger not yet fired."),
    ("⬜ Neutral","sl-neutral",
     "Mixed RS signals. No clear direction. Monitor only.", ""),
    ("🔴 RS Breakdown","sl-avoid",
     "All RS values negative. Stock lagging index and sector. Avoid or exit.",
     "RS_22d_Idx<0 + RS_55d_Idx<0 + RS_22d_Sec<0 + RS_55d_Sec<0."),
]


def _build_guide():
    rows = "".join(
        f'<div class="guide-row"><div class="guide-label-col"><span class="sl-badge {cls}">{lbl}</span></div>'
        f'<div class="guide-content"><div class="guide-summary">{s}</div>'
        f'{"<div class=guide-detail>"+d+"</div>" if d else ""}</div></div>'
        for lbl,cls,s,d in _GUIDE_ROWS
    )
    meta = """<div class="guide-meta">
  <h3>Score Formula</h3>
  <div class="guide-table">
    <div class="gt-row"><span class="gt-k">Total_Score</span><span>RS_Score×0.6 + Fin_Score×2 + SL_Bonus</span></div>
    <div class="gt-row"><span class="gt-k">RS_Score</span><span>RS_22d×35% + RS_55d×30% + RS_120d×20% + RS_252d×15%</span></div>
    <div class="gt-row"><span class="gt-k">Fin_Score</span><span>Sales_YoY≥15% +2 | PAT_YoY≥15% +2 | ROE≥15% +2 | Margin≥10% +1 | D/E&lt;1 +1</span></div>
    <div class="gt-row"><span class="gt-k">EPS</span><span>Trailing twelve-month Earnings Per Share (currency). Green = profitable, Red = loss-making.</span></div>
    <div class="gt-row"><span class="gt-k">SL_Bonus</span><span>A +4 | B +3 | C +2 | D +1 | R:R≥3× +2 | ≥2× +1</span></div>
  </div>
  <h3>SL Grade</h3>
  <div class="guide-table">
    <div class="gt-row"><span class="sl-badge sl-confirmed">A ≤3%</span><span>Ideal — tight stop</span></div>
    <div class="gt-row"><span class="sl-badge sl-confirmed">B ≤5%</span><span>Good — MST</span></div>
    <div class="gt-row"><span class="sl-badge sl-watch">C ≤8%</span><span>Acceptable — LST</span></div>
    <div class="gt-row"><span class="sl-badge sl-avoid">F &gt;12%</span><span>Too wide — skip</span></div>
  </div>
</div>"""
    return f'<div class="guide">{rows}{meta}</div>'


# ─────────────────────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def _build_dashboard(df):
    if df is None or df.empty: return ""
    html = ""
    for _, row in df.iterrows():
        k=_fmt(row.get("Key","")); v=_fmt(row.get("Value",""))
        if not k and not v: html += '<div class="dash-spacer"></div>'; continue
        if k.startswith("══") or k.startswith("──"):
            html += f'<div class="dash-section">{k}</div>'; continue
        is_tv = any(x in k.upper() for x in [
            "TV", "TRADINGVIEW", "WATCHLIST", "ALL BUY", "STRONG BUY",
            "PRIME BUY", "CONFIRMED BUY", "RS BUY", "MST", "LST", "RS30", "TOP-"
        ])
        # Any value that looks like a comma-separated symbol list is copyable,
        # so every watchlist row (Strong Buy / MST / LST / RS30 / All Buy /
        # Top-20 …) gets its own Copy button — not just "All Buy".
        looks_like_list = (v.count(",") >= 1)
        if (is_tv or looks_like_list) and v and len(v) > 3:
            v_html = (f'<span class="tv-list">{v[:200]}{"…" if len(v)>200 else ""}</span>'
                      f'<button class="copy-btn sm" data-orig="📋"'
                      f' onclick="copyText(this,\'{v.replace(chr(39),"")}\')">Copy</button>')
        else: v_html = v
        vcls = (" sl-triple-inline" if k.startswith("🌟") else
                " sl-confirmed-inline" if k.startswith("✅") else
                " sl-rsbuy-inline" if k.startswith("📈") else
                " sl-watch-inline" if k.startswith("👁") else
                " sl-avoid-inline" if k.startswith("🔴") else "")
        html += (f'<div class="dash-row"><div class="dash-key">{k}</div>'
                 f'<div class="dash-val{vcls}">{v_html}</div></div>')
    return html


# ─────────────────────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --bg:#0f1117;--bg2:#151820;--bg3:#1c1f2e;
  --border:rgba(255,255,255,0.07);
  --text:#e2e4ec;--text2:#8b90a8;--text3:#4d5268;
  --accent:#5b8def;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;
  --radius:10px;--shadow:0 2px 14px rgba(0,0,0,.4);
  --sl-triple-bg:#0d2b1a;--sl-triple-fg:#4ade80;
  --sl-prime-bg:#0f3024; --sl-prime-fg:#86efac;
  --sl-conf-bg:#c8e6c9;  --sl-conf-fg:#1b5e20;
  --sl-rsbuy-bg:#e8f5e9; --sl-rsbuy-fg:#1b5e20;
  --sl-watch-bg:#2d1b0d; --sl-watch-fg:#fde68a;
  --sl-neutral-bg:#374151;--sl-neutral-fg:#9ca3af;
  --sl-avoid-bg:#2d0d0d; --sl-avoid-fg:#fca5a5;
  /* Inline signal-count text colours — bright enough to read on dark/navy. */
  --ink-green:#34d399;--ink-amber:#fbbf24;--ink-red:#f87171;
}
html[data-theme="light"]{
  --bg:#f8fafc;--bg2:#fff;--bg3:#f1f5f9;
  --border:rgba(0,0,0,.07);--text:#1e293b;--text2:#64748b;--text3:#94a3b8;
  --sl-triple-bg:#dcfce7;--sl-triple-fg:#14532d;
  --sl-prime-bg:#d1fae5; --sl-prime-fg:#166534;
  --sl-watch-bg:#fefce8; --sl-watch-fg:#92400e;
  --sl-avoid-bg:#fef2f2; --sl-avoid-fg:#991b1b;
  --sl-neutral-bg:#f3f4f6;--sl-neutral-fg:#6b7280;
  /* Darker ink on the light theme so counts stay legible on white. */
  --ink-green:#15803d;--ink-amber:#b45309;--ink-red:#dc2626;
}
/* Navy / Blue Trader theme — overrides structural palette; signal colours
   inherit the dark defaults which read well on a deep-navy background. */
html[data-theme="navy"]{
  --bg:#0a1929;--bg2:#102a43;--bg3:#173a5e;
  --border:rgba(130,180,255,.14);
  --text:#e8f0fc;--text2:#a3bcd9;--text3:#5e7d9e;
  --accent:#4d9fff;--shadow:0 2px 16px rgba(0,18,46,.55);
}
*{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);font-size:15px;line-height:1.5;}
.app-header{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 16px;position:sticky;top:0;z-index:100;
  display:flex;align-items:center;justify-content:space-between;gap:10px;}
.app-title{font-size:15px;font-weight:700;color:var(--accent);}
.app-meta{font-size:11px;color:var(--text3);}
.app-brand-row{display:flex;align-items:center;gap:10px;}
.home-link{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;
  color:var(--text2);text-decoration:none;background:var(--bg3);border:1px solid var(--border);
  padding:5px 10px;border-radius:8px;transition:all .15s;white-space:nowrap;}
.home-link:hover{color:var(--accent);border-color:var(--accent);}
.country-nav-select{background:var(--bg3);border:1px solid var(--border);color:var(--text);
  font-size:12px;font-weight:600;padding:5px 8px;border-radius:8px;cursor:pointer;outline:none;}
.country-nav-select:focus{border-color:var(--accent);}
.disclaimer-footer{background:var(--bg2);border-top:2px solid var(--border);
  padding:20px clamp(12px,3vw,40px);margin-top:30px;font-size:11.5px;line-height:1.7;color:var(--text3);}
.disclaimer-footer h4{font-size:12px;font-weight:700;color:var(--text2);margin:0 0 8px;
  text-transform:uppercase;letter-spacing:.5px;}
.disclaimer-footer p{margin:0 0 8px;}
.disclaimer-footer strong{color:var(--text2);}
.disclaimer-footer .df-brand{color:var(--accent);font-weight:700;}
.disclaimer-footer a{color:var(--text2);text-decoration:underline;}
.sl-badge{display:inline-block;padding:3px 9px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap;}
.sl-triple{background:var(--sl-triple-bg);color:var(--sl-triple-fg);}
.sl-prime{background:var(--sl-prime-bg);color:var(--sl-prime-fg);}
.sl-confirmed{background:var(--sl-conf-bg);color:var(--sl-conf-fg);}
.sl-rsbuy{background:var(--sl-rsbuy-bg);color:var(--sl-rsbuy-fg);}
.sl-watch{background:var(--sl-watch-bg);color:var(--sl-watch-fg);}
.sl-neutral{background:var(--sl-neutral-bg);color:var(--sl-neutral-fg);}
.sl-avoid{background:var(--sl-avoid-bg);color:var(--sl-avoid-fg);}
.sl-triple-inline{color:var(--ink-green);font-weight:700;}
.sl-confirmed-inline{color:var(--ink-green);font-weight:600;}
.sl-rsbuy-inline{color:var(--ink-green);font-weight:600;}
.sl-watch-inline{color:var(--ink-amber);font-weight:600;}
.sl-avoid-inline{color:var(--ink-red);font-weight:600;}
.stats-bar{display:flex;gap:8px;padding:8px 12px;background:var(--bg2);
  border-bottom:1px solid var(--border);overflow-x:auto;scrollbar-width:none;}
.stats-bar::-webkit-scrollbar{display:none;}
.tab-bar{display:flex;overflow-x:auto;background:var(--bg2);
  border-bottom:1px solid var(--border);position:sticky;top:49px;z-index:99;scrollbar-width:none;}
.tab-bar::-webkit-scrollbar{display:none;}
.tab-btn{padding:10px 14px;font-size:13px;white-space:nowrap;border:none;
  background:none;color:var(--text2);cursor:pointer;
  border-bottom:2px solid transparent;transition:all .15s;flex-shrink:0;}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600;}
.tab-btn:hover{color:var(--text);}
.tab-content{display:none;padding:14px clamp(12px,3vw,40px);max-width:100%;margin:0 auto;}
.tab-content.active{display:block;}
.sec-title{font-size:14px;font-weight:600;color:var(--text);
  margin:18px 0 8px;border-left:3px solid var(--accent);padding-left:10px;}
.sec-title:first-child{margin-top:0;}
/* Health card */
.health-card{background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius);padding:16px;margin-bottom:16px;}
.hc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:12px;margin-bottom:12px;}
.hc-block{text-align:center;}
.hc-label{font-size:11px;color:var(--text3);margin-bottom:4px;}
.hc-value{font-size:18px;font-weight:700;}
.hc-sub{font-size:12px;font-weight:400;color:var(--text2);}
.hc-sectors{display:flex;flex-wrap:wrap;gap:6px;align-items:center;}
.sec-pill{padding:3px 8px;border-radius:8px;font-size:12px;font-weight:500;background:var(--bg3);color:var(--text2);}
.sec-pill.pos-strong{background:#0d3320;color:#4ade80;}
.sec-pill.neg{background:#2d0d0d;color:#fca5a5;}
.mood-on{color:#22c55e;}.mood-mix{color:var(--amber);}.mood-off{color:var(--red);}
/* Snapshot */
.snap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:16px;}
.snap-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;}
.snap-name{font-size:11px;color:var(--text3);margin-bottom:3px;}
.snap-price{font-size:15px;font-weight:700;}
.snap-chg{font-size:13px;font-weight:500;margin-top:2px;}
.snap-trend{font-size:11px;margin-top:3px;}
/* Sector bars */
.sector-bars{display:flex;flex-direction:column;gap:5px;margin-bottom:16px;}
.sec-row{display:grid;grid-template-columns:24px 1fr 80px 52px 52px 52px 56px;
  align-items:center;gap:6px;background:var(--bg2);border-radius:6px;
  padding:6px 10px;border:1px solid var(--border);}
.sec-rank{color:var(--text3);font-size:11px;}
.sec-name{font-size:13px;font-weight:500;}
.sec-bar-wrap{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;}
.sec-bar{height:100%;border-radius:3px;min-width:2px;}
.bar-pos{background:var(--green);}.bar-neg{background:var(--red);}
.sec-rs,.sec-rs55,.sec-rsi{font-size:12px;text-align:right;}
.sec-sig-badge{font-size:11px;font-weight:600;text-align:center;padding:2px 5px;border-radius:4px;}
.sig-buy{background:#c8e6c9;color:#1b5e20;}.sig-sell{background:#ffcdd2;color:#b71c1c;}
.sig-neutral{background:#fff9c4;color:#5d4037;}.sig-strongbuy{background:#006b3c;color:#fff;}
/* Opportunity cards */
.opp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-bottom:16px;}
.opp-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:12px 14px;transition:border-color .2s;}
.opp-card:hover{border-color:var(--accent);}
.opp-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;}
.opp-sym{font-size:17px;font-weight:700;}
.tv-link{color:var(--accent);text-decoration:none;font-weight:700;border-bottom:1px dotted var(--accent);}
.tv-link:hover{text-decoration:none;border-bottom-style:solid;}
.opp-sym .tv-link{color:inherit;border-bottom:none;}
.opp-company{font-size:12px;color:var(--text3);margin-bottom:8px;}
.opp-metrics{display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;margin-bottom:8px;}
.m-row{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border);}
.ml{color:var(--text2);}
.opp-pattern{font-size:11px;color:var(--accent);margin-bottom:6px;}
.opp-sec-hdr{display:flex;justify-content:space-between;align-items:center;
  font-size:13px;font-weight:600;padding:8px 4px;color:var(--text2);
  border-bottom:1px solid var(--border);margin-bottom:8px;grid-column:1/-1;}
/* Tables */
.tbl-search{margin-bottom:8px;}
.tbl-search input{width:100%;padding:8px 12px;border-radius:8px;
  border:1px solid var(--border);background:var(--bg2);color:var(--text);font-size:14px;outline:none;}
.tbl-search input:focus{border-color:var(--accent);}
.tbl-wrap{overflow-x:auto;border-radius:var(--radius);border:1px solid var(--border);margin-bottom:6px;}
table.data-tbl{border-collapse:collapse;width:100%;font-size:12px;min-width:400px;}
.data-tbl thead th{background:#0d1730;color:#90caf9;padding:8px 10px;
  font-weight:600;font-size:11px;white-space:nowrap;cursor:pointer;user-select:none;
  border-bottom:1px solid var(--border);position:sticky;top:0;}
.data-tbl thead th:hover{background:#1a2a4a;}
.data-tbl thead th::after{content:" ↕";opacity:.4;}
.data-tbl thead th.asc::after{content:" ↑";opacity:1;}
.data-tbl thead th.desc::after{content:" ↓";opacity:1;}
.data-tbl tbody tr:nth-child(even){background:var(--bg3);}
.data-tbl tbody tr:hover{background:rgba(91,141,239,.08);}
.data-tbl td{padding:6px 10px;border-bottom:1px solid var(--border);white-space:nowrap;}
.row-count{font-size:11px;color:var(--text3);margin-bottom:12px;}
.data-tbl td.sl-triple{background:var(--sl-triple-bg)!important;color:var(--sl-triple-fg)!important;font-weight:700;}
.data-tbl td.sl-prime{background:var(--sl-prime-bg)!important;color:var(--sl-prime-fg)!important;font-weight:700;}
.data-tbl td.sl-confirmed{background:var(--sl-conf-bg)!important;color:var(--sl-conf-fg)!important;font-weight:600;}
.data-tbl td.sl-rsbuy{background:var(--sl-rsbuy-bg)!important;color:var(--sl-rsbuy-fg)!important;}
.data-tbl td.sl-watch{background:var(--sl-watch-bg)!important;color:var(--sl-watch-fg)!important;}
.data-tbl td.sl-avoid{background:var(--sl-avoid-bg)!important;color:var(--sl-avoid-fg)!important;font-weight:600;}
.pos-strong{color:var(--green);font-weight:600;}.pos{color:#81c784;}
.pos-dim{color:#a5d6a7;}.neg-strong{color:var(--red);font-weight:600;}
.neg{color:#e57373;}.neg-dim{color:#ef9a9a;}.dim{color:var(--text3);}
/* Breadth / rotation 0-100 columns: ≥60 green · 40-60 orange · <40 red */
.data-tbl td.bd-green{background:rgba(34,197,94,.16)!important;color:#22c55e!important;font-weight:700;}
.data-tbl td.bd-amber{background:rgba(245,158,11,.16)!important;color:#f59e0b!important;font-weight:700;}
.data-tbl td.bd-red{background:rgba(239,68,68,.16)!important;color:#ef4444!important;font-weight:700;}
/* Sleeve calculator */
.sleeve-global-ctrl{background:var(--bg2);border:1px solid var(--accent);
  border-radius:var(--radius);padding:14px 16px;margin-bottom:16px;}
.ctrl-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:16px;margin-bottom:10px;}
.ctrl-field{display:flex;flex-direction:column;gap:4px;}
.ctrl-label{font-size:11px;font-weight:600;color:var(--text2);}
.ctrl-formula{font-size:11px;color:var(--text3);line-height:1.6;padding-top:6px;
  border-top:1px solid var(--border);}
.ctrl-formula strong{color:var(--accent);}
.cap-input{background:var(--bg3);border:1px solid var(--border);color:var(--text);
  padding:6px 10px;border-radius:6px;font-size:14px;width:150px;outline:none;}
.cap-input:focus{border-color:var(--accent);}
.sleeve-block{margin-bottom:28px;}
.sleeve-header{background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius) var(--radius) 0 0;padding:12px 16px;
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  border-bottom:2px solid var(--accent);}
.sleeve-title{font-size:14px;font-weight:600;}
.sleeve-sub{font-size:12px;color:var(--text2);}
.sleeve-summary{font-size:12px;color:var(--accent);margin-left:auto;}
.sleeve-actions{display:flex;flex-wrap:wrap;gap:8px;padding:10px 0;align-items:center;}
.action-btn{padding:6px 14px;border-radius:6px;font-size:12px;
  border:none;cursor:pointer;font-weight:600;transition:opacity .15s;}
.action-btn:hover{opacity:.85;}
.action-btn.green{background:#16a34a;color:#fff;}
.action-btn.blue{background:#1d4ed8;color:#fff;}
.action-btn.amber{background:#d97706;color:#fff;}
.action-btn.orange{background:#c2410c;color:#fff;}
.action-btn.grey{background:#374151;color:#9ca3af;}
.track-msg{font-size:12px;color:var(--green);margin-left:4px;}
.entry-date{font-size:11px;color:var(--text3);margin-left:8px;}
.calc-cell{font-size:12px;text-align:right!important;font-family:monospace;}
.sleeve-tbl .qty-cell{font-weight:700;color:var(--accent);}
.sleeve-tbl .amt-cell{color:var(--text2);}
.sleeve-tbl .slp-cell{color:var(--red);}
.sleeve-tbl .rsk-cell{color:var(--amber);}
.sleeve-tbl .pl-cell.pos-strong{color:var(--green);font-weight:700;}
.sleeve-tbl .pl-cell.neg-strong{color:var(--red);font-weight:700;}
.sleeve-footer{padding:8px 12px;font-size:13px;color:var(--text2);
  background:var(--bg2);border:1px solid var(--border);
  border-radius:0 0 var(--radius) var(--radius);border-top:none;}
/* Dashboard */
.dash-section{background:#0d47a1;color:#90caf9;padding:8px 12px;border-radius:6px;
  font-weight:600;font-size:13px;margin:10px 0 4px;}
.dash-row{display:grid;grid-template-columns:1fr 1fr;
  border-bottom:1px solid var(--border);padding:6px 4px;gap:8px;}
.dash-key{font-size:12px;font-weight:500;color:var(--text2);}
.dash-val{font-size:12px;color:var(--text);word-break:break-all;}
.dash-spacer{height:8px;}
.tv-list{font-size:11px;color:var(--text3);word-break:break-all;}
/* Guide */
.guide{display:flex;flex-direction:column;gap:10px;margin-bottom:16px;}
.guide-row{display:grid;grid-template-columns:200px 1fr;gap:12px;
  background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px;}
.guide-label-col{display:flex;align-items:flex-start;padding-top:2px;}
.guide-summary{font-size:13px;margin-bottom:4px;line-height:1.5;}
.guide-detail{font-size:11px;color:var(--text2);line-height:1.5;}
.guide-meta{margin-top:20px;display:flex;flex-direction:column;gap:16px;}
.guide-meta h3{font-size:13px;font-weight:600;color:var(--text2);margin-bottom:6px;}
.guide-table{display:flex;flex-direction:column;gap:4px;}
.gt-row{display:flex;gap:12px;font-size:12px;padding:5px 8px;border-radius:4px;background:var(--bg2);}
.gt-k{font-weight:600;color:var(--accent);min-width:140px;}
/* Toggle */
.view-toggle{display:flex;gap:6px;margin-bottom:10px;}
.vt-btn{padding:5px 14px;border-radius:6px;font-size:12px;
  border:1px solid var(--border);background:transparent;color:var(--text2);cursor:pointer;}
.vt-btn.active{background:var(--accent);color:#fff;border-color:var(--accent);}
/* Buttons */
.copy-btn{margin-top:8px;padding:5px 12px;border-radius:6px;
  border:1px solid var(--accent);background:transparent;color:var(--accent);
  font-size:12px;cursor:pointer;transition:all .15s;}
.copy-btn:hover{background:var(--accent);color:#fff;}
.copy-btn.sm{padding:3px 8px;font-size:11px;margin-top:6px;}
.copy-btn.copied{background:#16a34a;border-color:var(--green);color:#fff;}
.empty{color:var(--text3);font-size:13px;padding:20px 0;text-align:center;}
@media(max-width:640px){
  .sec-row{grid-template-columns:20px 1fr 44px 44px;}.sec-bar-wrap,.sec-rs55,.sec-rsi{display:none;}
  .opp-cards{grid-template-columns:1fr;}
  .snap-grid{grid-template-columns:repeat(2,1fr);}
  .guide-row{grid-template-columns:1fr;}.guide-label-col{margin-bottom:6px;}
  .dash-row{grid-template-columns:1fr;}
  .hc-grid{grid-template-columns:repeat(4,1fr);}
  .sleeve-global-ctrl{flex-direction:column;align-items:flex-start;}
}
/* ── #8 Header controls: theme selector + font scaling ────────────────── */
.hdr-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;}
.ctrl-group{display:flex;align-items:center;gap:5px;background:var(--bg3);
  border:1px solid var(--border);border-radius:8px;padding:3px 7px;}
.ctrl-group label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;}
.theme-select{background:var(--bg2);color:var(--text);border:1px solid var(--border);
  border-radius:6px;font-size:12px;padding:4px 6px;cursor:pointer;outline:none;}
.fs-btn{width:26px;height:26px;border:none;border-radius:6px;background:var(--bg2);
  color:var(--text);font-size:15px;font-weight:700;cursor:pointer;line-height:1;}
.fs-btn:hover{background:var(--accent);color:#fff;}
/* ── #8 Per-column filter row (turns each table into a scanner) ───────── */
.data-tbl thead tr.col-filter th{padding:3px 4px;background:var(--bg2);}
.col-filter input{width:100%;min-width:52px;box-sizing:border-box;font-size:11px;
  padding:3px 5px;border:1px solid var(--border);border-radius:5px;
  background:var(--bg);color:var(--text);outline:none;}
.col-filter input:focus{border-color:var(--accent);}
/* ── #8 Responsive ────────────────────────────────────────────────────── */
@media(max-width:640px){
  .tab-content{padding:10px 8px;}
  .app-title{font-size:13px;}
  .hdr-controls{gap:5px;}
  .ctrl-group label{display:none;}
  table.data-tbl{font-size:11px;}
}

/* ── TradingView Hover Preview (v6.2) ──────────────────────────────────── */
/* The preview box — always in DOM, shown/hidden by JS                      */
#tv-preview-box {
  position: fixed;
  display: none;
  z-index: 9999;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.45);
  overflow: hidden;
  pointer-events: none;   /* lets mouse pass through so hover doesn't flicker */
}
#tv-preview-header {
  height: 30px;
  line-height: 30px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  background: var(--bg3);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
#tv-preview-iframe {
  width: 100%;
  border: none;
  display: block;
}
/* The toggle button reuses the existing ctrl-group style */
#tv-preview-toggle {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--text2);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
#tv-preview-toggle.tv-on  { background: var(--accent); color: #fff; border-color: var(--accent); }
#tv-preview-toggle.tv-off { background: var(--bg3);    color: var(--text3); }
"""

# ─────────────────────────────────────────────────────────────────────────────
#  JAVASCRIPT
# ─────────────────────────────────────────────────────────────────────────────

JS = r"""
/* ── TAB SWITCHING ─────────────────────────────────────────────────────── */
function showTab(id){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
  localStorage.setItem('activeTab',id);
}

/* ── THEME + FONT SCALING (#8) ─────────────────────────────────────────── */
function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  try{localStorage.setItem('theme',t);}catch(e){}
  const sel=document.getElementById('theme-select'); if(sel)sel.value=t;
}
function setFont(delta){
  let z=parseFloat(localStorage.getItem('fontZoom')||'1');
  z=Math.min(1.6,Math.max(0.8,z+delta*0.1));
  document.documentElement.style.zoom=z;
  try{localStorage.setItem('fontZoom',String(z));}catch(e){}
}
function _initThemeFont(){
  setTheme(localStorage.getItem('theme')||'light');
  document.documentElement.style.zoom=parseFloat(localStorage.getItem('fontZoom')||'1');
}

/* ── TABLE FILTER — global box + per-column scanner inputs (#8) ───────────
   Per-column inputs accept logical/numeric operators in addition to text:
     >15   <40   >=60   <=5   =12   !=0   10-20 (range)   10..20 (range)
   Anything else is treated as a plain text (substring) match.            */
function _cellNum(text){
  const m = String(text).replace(/[,\s₹$%]/g,'').match(/-?\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : NaN;
}
function matchFilter(text, qRaw){
  const q = (qRaw||'').trim();
  if(!q) return true;
  // operator: >, <, >=, <=, =, ==, !=
  const op = q.match(/^(>=|<=|!=|==|=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
  if(op){
    const num = _cellNum(text);
    if(isNaN(num)) return false;
    const val = parseFloat(op[2]);
    switch(op[1]){
      case '>':  return num >  val;
      case '<':  return num <  val;
      case '>=': return num >= val;
      case '<=': return num <= val;
      case '=':
      case '==': return num === val;
      case '!=': return num !== val;
    }
  }
  // range: a-b or a..b (both ends numeric)
  const rng = q.match(/^(-?\d+(?:\.\d+)?)\s*(?:\.\.|-)\s*(-?\d+(?:\.\d+)?)$/);
  if(rng){
    const num = _cellNum(text);
    if(isNaN(num)) return false;
    const lo = parseFloat(rng[1]), hi = parseFloat(rng[2]);
    return num >= Math.min(lo,hi) && num <= Math.max(lo,hi);
  }
  // fallback: plain text substring match
  return String(text).toLowerCase().includes(q.toLowerCase());
}
function applyFilters(tableId){
  const table=document.getElementById(tableId); if(!table)return;
  const tb=table.tBodies[0]; if(!tb)return;
  const filters=[];
  table.querySelectorAll('thead tr.col-filter input').forEach(inp=>{
    const v=inp.value.trim();
    if(v)filters.push([parseInt(inp.dataset.col,10),v]);
  });
  const g=document.querySelector('[data-global-for="'+tableId+'"]');
  const gq=g?g.value.trim().toLowerCase():'';
  let vis=0;
  for(const row of tb.rows){
    let show=true;
    if(gq && !row.textContent.toLowerCase().includes(gq))show=false;
    if(show){
      for(const f of filters){
        const cell=row.cells[f[0]];
        if(!cell || !matchFilter(cell.textContent, f[1])){show=false;break;}
      }
    }
    row.style.display=show?'':'none';
    if(show)vis++;
  }
  const cnt=document.getElementById(tableId+'-count');
  if(cnt)cnt.textContent=vis+' rows';
}
function filterTable(input,tableId){applyFilters(tableId);}
function filterColumn(input,tableId){applyFilters(tableId);}

/* ── TABLE SORT ────────────────────────────────────────────────────────── */
function sortTable(th){
  const table=th.closest('table');
  const tb=table.tBodies[0];
  const col=th.cellIndex;
  const asc=!th.classList.contains('asc');
  table.querySelectorAll('th').forEach(h=>h.classList.remove('asc','desc'));
  th.classList.add(asc?'asc':'desc');
  Array.from(tb.rows).sort((a,b)=>{
    let av=a.cells[col]?.textContent.trim()||'';
    let bv=b.cells[col]?.textContent.trim()||'';
    const af=parseFloat(av.replace(/[+%,]/g,''));
    const bf=parseFloat(bv.replace(/[+%,]/g,''));
    if(!isNaN(af)&&!isNaN(bf))return asc?af-bf:bf-af;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  }).forEach(r=>tb.appendChild(r));
}

/* ── COPY ──────────────────────────────────────────────────────────────── */
function copyText(btn,text){
  const orig=btn.dataset.orig||btn.textContent;
  navigator.clipboard.writeText(text).then(()=>{
    btn.textContent='✅ Copied!';btn.classList.add('copied');
    setTimeout(()=>{btn.textContent=orig;btn.classList.remove('copied');},2000);
  }).catch(()=>{
    const el=document.createElement('textarea');
    el.value=text;document.body.appendChild(el);
    el.select();document.execCommand('copy');document.body.removeChild(el);
    btn.textContent='✅ Copied!';
    setTimeout(()=>{btn.textContent=orig;},2000);
  });
}

/* ── VIEW TOGGLE ───────────────────────────────────────────────────────── */
function toggleView(sid,mode){
  document.querySelectorAll('#'+sid+' .vt-btn').forEach(b=>b.classList.remove('active'));
  document.querySelector('#'+sid+' [data-mode="'+mode+'"]').classList.add('active');
  const cv=document.getElementById(sid+'-cards');
  const tv=document.getElementById(sid+'-table');
  if(cv)cv.style.display=mode==='cards'?'':'none';
  if(tv)tv.style.display=mode==='table'?'':'none';
}

/* ── SLEEVE CALCULATOR ─────────────────────────────────────────────────────
   Formula:  Qty = floor( (Capital × Risk%) / (Price × effective_SL%) )
   effective_SL = min(SL_Buy% from engine, Max SL cap input)
   If SL_Buy% is missing/zero → uses Max SL cap as fallback
   This is pure risk-based sizing — ATR_Wt% is NOT used for qty.
   ─────────────────────────────────────────────────────────────────────── */
function fmtNum(n, currency){
  const c = currency || '₹';
  if(isNaN(n) || n === 0) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if(abs >= 10000000) return sign + c + (abs/10000000).toFixed(2) + 'Cr';
  if(abs >= 100000)   return sign + c + (abs/100000).toFixed(2) + 'L';
  if(abs >= 1000)     return sign + c + Math.round(abs).toLocaleString('en-IN');
  return sign + c + abs.toFixed(2);
}

function getCurrency(){
  // Detect currency symbol from capital input label
  const lbl = document.querySelector('.ctrl-label');
  return (lbl && lbl.textContent.includes('$')) ? '$' : '₹';
}

function recalcAll(){
  document.querySelectorAll('[id^="sleeve-"]').forEach(tbl => {
    calcSleeve(tbl.id.replace('sleeve-', ''));
  });
}

function calcSleeve(key){
  const capital  = parseFloat(document.getElementById('global-capital')?.value) || 0;
  const riskPct  = parseFloat(document.getElementById('global-risk')?.value)    || 1;
  const slCap    = parseFloat(document.getElementById('global-sl-cap')?.value)  || 5;
  const tbl      = document.getElementById('sleeve-' + key);
  if(!tbl || capital <= 0) return;

  const cur      = getCurrency();
  let totalDeployed = 0;
  let totalRisk     = 0;
  let n             = 0;

  for(const row of tbl.tBodies[0].rows){
    const price = parseFloat(row.dataset.price) || 0;
    const slRaw = parseFloat(row.dataset.sl)    || 0;  // SL_Buy% from engine

    const qCell   = row.querySelector('.qty-cell');
    const aCell   = row.querySelector('.amt-cell');
    const slpCell = row.querySelector('.slp-cell');
    const rCell   = row.querySelector('.rsk-cell');
    const eslCell = row.querySelector('.esl-cell');

    if(price <= 0){
      if(qCell)   qCell.textContent   = '—';
      if(aCell)   aCell.textContent   = '—';
      if(slpCell) slpCell.textContent = '—';
      if(rCell)   rCell.textContent   = '—';
      if(eslCell) eslCell.textContent = '—';
      continue;
    }

    // effective SL: use engine value if available, cap at slCap, fallback to slCap
    const effectiveSL = (slRaw > 0) ? Math.min(slRaw, slCap) : slCap;

    // Risk-based position sizing
    const riskAmount = capital * riskPct / 100;          // e.g. 1% of 10L = ₹10,000
    const riskPerShr = price   * effectiveSL / 100;      // e.g. ₹1000 × 5% = ₹50
    const qty        = riskPerShr > 0 ? Math.floor(riskAmount / riskPerShr) : 0;
    const amount     = qty * price;
    const slPrice    = price * (1 - effectiveSL / 100);
    const actualRisk = qty * riskPerShr;                  // should ≈ riskAmount

    if(qCell)   qCell.textContent   = qty > 0 ? qty.toLocaleString('en-IN') : '—';
    if(aCell)   aCell.textContent   = qty > 0 ? fmtNum(amount, cur) : '—';
    if(slpCell) slpCell.textContent = qty > 0 ? slPrice.toFixed(2) : '—';
    if(rCell)   rCell.textContent   = qty > 0 ? fmtNum(actualRisk, cur) : '—';
    if(eslCell){
      eslCell.textContent = effectiveSL.toFixed(1) + '%';
      // Highlight if SL was capped (engine SL was wider than cap)
      eslCell.style.color = (slRaw > slCap && slRaw > 0) ? '#f59e0b' : '';
      eslCell.title = slRaw > 0
        ? `Engine SL: ${slRaw.toFixed(1)}% → capped to ${effectiveSL.toFixed(1)}%`
        : `No SL data → using fallback ${effectiveSL.toFixed(1)}%`;
    }

    totalDeployed += amount;
    totalRisk     += actualRisk;
    if(qty > 0) n++;
  }

  const sumEl = document.getElementById('sum-'  + key);
  const totEl = document.getElementById('total-' + key);
  if(sumEl) sumEl.textContent =
    n + ' stocks · Deployed ' + fmtNum(totalDeployed, cur) +
    ' · Total Risk ' + fmtNum(totalRisk, cur) +
    ' (' + (capital > 0 ? (totalRisk/capital*100).toFixed(1) : '0') + '% of capital)';
  if(totEl) totEl.textContent = fmtNum(totalDeployed, cur);
}

/* ── ZERODHA BASKET JSON ─────────────────────────────────────────────────
   Format matches Zerodha's basket order import exactly.
   Based on the official Zerodha basket JSON structure (array of order objects).
   ⚠ instrumentToken is set to 0 — Zerodha resolves by tradingsymbol+exchange.
   In Zerodha Kite: Orders → Basket Orders → Import from file
   ─────────────────────────────────────────────────────────────────────── */
function downloadZerodha(key){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  const basket = [];
  let weight = 0;

  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const price = parseFloat(row.dataset.price)||0;
    const qty   = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    if(!sym||qty<=0) continue;

    // Limit price = current price + 0.5% buffer (rounded to nearest 0.05 tick)
    const rawLimit   = price * 1.005;
    const limitPrice = Math.round(rawLimit / 0.05) * 0.05;
    const lp         = parseFloat(limitPrice.toFixed(2));

    basket.push({
      id: Date.now() + weight,
      instrument: {
        tradingsymbol:  sym,
        scripCode:      "",
        type:           "EQ",
        symbol:         sym,
        segment:        "NSE",
        exchange:       "NSE",
        tickSize:       0.05,
        lotSize:        1,
        company:        sym,
        tradable:       true,
        precision:      2,
        fullName:       sym,
        niceName:       sym,
        niceNameHTML:   sym,
        stockWidget:    true,
        exchangeToken:  0,
        instrumentToken:0,
        isin:           "",
        related:        [],
        underlying:     null,
        auctionNumber:  null,
        isEquity:       true,
        isWeekly:       false
      },
      weight: weight,
      params: {
        transactionType:  "BUY",
        product:          "CNC",
        orderType:        "LIMIT",
        validity:         "DAY",
        validityTTL:      1,
        quantity:         qty,
        price:            lp,
        triggerPrice:     0,
        disclosedQuantity:0,
        lastPrice:        parseFloat(price.toFixed(2)),
        variety:          "regular",
        tags:             []
      }
    });
    weight++;
  }

  if(basket.length===0){
    alert('Calculate quantities first (click ⚡ Recalculate)');return;
  }

  const blob = new Blob([JSON.stringify(basket,null,2)],{type:'application/json'});
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `sleeve_${key}_zerodha_basket.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ── IBKR BASKET CSV ─────────────────────────────────────────────────────
   Format: TWS BasketTrader CSV (all retail IBKR accounts support this).
   How to use in TWS: File → Open → Basket Trader → Import from File
   Or: Orders menu → Import from File
   ─────────────────────────────────────────────────────────────────────── */
function downloadIBKR(key, isIndia){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  const isInd = (isIndia==='True');
  const exchange = isInd ? 'NSE'   : 'SMART';
  const currency = isInd ? 'INR'   : 'USD';

  // IBKR basket file header updated to your exact sequence
  const HEADER = [
    'Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 
    'Currency', 'TimeInForce', 'OrderType', 'LmtPrice'
  ];
  let csv = HEADER.join(',') + '\n';
  let count = 0;

  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const price = parseFloat(row.dataset.price)||0;
    const qty   = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    if(!sym||qty<=0) continue;

    // Limit price = current price + 0.5% buffer
    const lmtPrice = parseFloat((price * 1.005).toFixed(isInd ? 2 : 2));

    const fields = [
      'BUY',        // Action
      qty,          // Quantity
      sym,          // Symbol
      'STK',        // SecType
      exchange,     // Exchange
      currency,     // Currency
      'DAY',        // TimeInForce
      'LMT',        // OrderType
      lmtPrice      // LmtPrice
    ];
    csv += fields.join(',') + '\n';
    count++;
  }

  if(count===0){
    alert('Calculate quantities first (click ⚡ Recalculate)');return;
  }

  const blob = new Blob([csv],{type:'text/csv'});
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `sleeve_${key}_ibkr_basket.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ── ENTRY TRACKING (window.storage) ───────────────────────────────────── */
async function trackEntry(key){
  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl){return;}
  const date    = new Date().toISOString().split('T')[0];
  const capital = parseFloat(document.getElementById('global-capital')?.value)||0;
  const entries = [];
  for(const row of tbl.tBodies[0].rows){
    const sym  = (row.dataset.sym||'').trim();
    const price= parseFloat(row.dataset.price)||0;
    const qty  = parseInt(row.querySelector('.qty-cell')?.textContent)||0;
    const sl   = parseFloat(row.dataset.sl)||0;
    if(sym && qty>0){
      entries.push({sym,entry_price:price,qty,sl_pct:sl,entry_date:date});
    }
  }
  if(entries.length===0){
    document.getElementById('tmsg-'+key).textContent='⚠ Calculate quantities first';
    return;
  }
  try{
    await window.storage.set('sleeve_'+key+'_entry',
      JSON.stringify({date,capital,entries}));
    document.getElementById('tmsg-'+key).textContent=
      '✅ Tracked '+entries.length+' positions on '+date;
    document.getElementById('edate-'+key).textContent='Entry: '+date;
    loadTracking(key);
  }catch(e){
    // Fallback to localStorage for non-Claude environments
    try{
      localStorage.setItem('sleeve_'+key+'_entry',
        JSON.stringify({date,capital,entries}));
      document.getElementById('tmsg-'+key).textContent=
        '✅ Tracked '+entries.length+' (local)';
    }catch(e2){
      document.getElementById('tmsg-'+key).textContent='⚠ Storage unavailable';
    }
  }
}

async function loadTracking(key){
  let data = null;
  try{
    const stored = await window.storage.get('sleeve_'+key+'_entry');
    if(stored) data = JSON.parse(stored.value);
  }catch(e){
    try{
      const ls = localStorage.getItem('sleeve_'+key+'_entry');
      if(ls) data = JSON.parse(ls);
    }catch(e2){}
  }
  if(!data||!data.entries) return;

  const entryMap = {};
  data.entries.forEach(e=>entryMap[e.sym]=e);

  const tbl = document.getElementById('sleeve-'+key);
  if(!tbl) return;

  let plTotal=0; let plCount=0;
  const cur = getCurrency();
  for(const row of tbl.tBodies[0].rows){
    const sym   = (row.dataset.sym||'').trim();
    const entry = entryMap[sym];
    const plCell= row.querySelector('.pl-cell');
    if(!entry||!plCell){if(plCell)plCell.textContent='—';continue;}
    const cur   = parseFloat(row.dataset.price)||0;
    const plPct = ((cur-entry.entry_price)/entry.entry_price*100).toFixed(1);
    const plAmt = Math.round((cur-entry.entry_price)*entry.qty);
    plCell.textContent = plPct+'% ('+fmtNum(Math.abs(plAmt), cur)+')';
    plCell.className   = 'calc-cell pl-cell '+(parseFloat(plPct)>0?'pos-strong':'neg-strong');
    plTotal += plAmt;
    plCount++;
  }

  const edEl   = document.getElementById('edate-'+key);
  const plSumEl= document.getElementById('plsum-'+key);
  if(edEl)   edEl.textContent   = 'Entry: '+data.date;
  if(plSumEl){
    plSumEl.textContent = plCount>0 ? fmtNum(Math.abs(plTotal), cur) : '—';
    plSumEl.className   = plTotal>0 ? 'pos-strong' : 'neg-strong';
  }
}

async function clearTracking(key){
  if(!confirm('Clear tracking data for Sleeve '+key+'?')) return;
  try{ await window.storage.delete('sleeve_'+key+'_entry'); }catch(e){}
  try{ localStorage.removeItem('sleeve_'+key+'_entry'); }catch(e){}
  const tbl=document.getElementById('sleeve-'+key);
  if(tbl) for(const row of tbl.tBodies[0].rows){
    const c=row.querySelector('.pl-cell');
    if(c){c.textContent='—';c.className='calc-cell pl-cell';}
  }
  const edEl=document.getElementById('edate-'+key);
  const tmEl=document.getElementById('tmsg-'+key);
  if(edEl)edEl.textContent='';
  if(tmEl)tmEl.textContent='🗑 Cleared';
}

/* ── TRADINGVIEW HOVER PREVIEW  (v6.2) ─────────────────────────────────────
   Strategy: one hidden <iframe> is created on page load and kept alive.
   On hover we just swap its src — no script injection, no DOM thrashing.
   The iframe stays warm between hovers so subsequent loads are much faster.

   ┌─ SIZE CONFIG ──────────────────────────────────────────────────────────┐
   │  Change TV_PREVIEW_W and TV_PREVIEW_H to resize the floating window.  │
   │  TV_PREVIEW_HEADER_H is the title-bar height (usually leave at 30).   │
   └────────────────────────────────────────────────────────────────────────┘ */
const TV_PREVIEW_W        = 420;   // px — preview box total width
const TV_PREVIEW_H        = 300;   // px — preview box total height (incl. header)
const TV_PREVIEW_HEADER_H = 30;    // px — header bar height
const TV_PREVIEW_OFFSET_X = 18;    // px — gap right of cursor
const TV_PREVIEW_OFFSET_Y = 10;    // px — gap below cursor
const TV_HIDE_DELAY_MS    = 120;   // ms — debounce before hiding (avoids flicker)

let _tvEnabled = true;             // toggled by the header button
let _tvHideTimer = null;
let _tvBox = null;
let _tvIframe = null;
let _tvHeader = null;
let _tvLastSym = '';               // avoid redundant src swaps

function _tvGetTheme(){
  // Match the report's current theme so the chart looks consistent
  const t = document.documentElement.getAttribute('data-theme') || 'dark';
  return (t === 'light') ? 'light' : 'dark';
}

function _tvBuildSrc(tvSymbol){
  // TradingView advanced chart mini embed — loads fast, no JS injection needed
  const theme = _tvGetTheme();
  const params = new URLSearchParams({
    symbol:      tvSymbol.replace('%3A', ':'),
    interval:    'D',
    range:       '6M',
    theme:       theme,
    style:       '1',
    locale:      'en',
    hide_top_toolbar: '0',
    hide_legend:      '1',
    hide_side_toolbar:'1',
    allow_symbol_change: '0',
    save_image:  '0',
    calendar:    '0',
    hide_volume: '1',
  });
  return 'https://s.tradingview.com/widgetembed/?' + params.toString();
}

function _tvInit(){
  // Build the preview box once and keep it in the DOM forever
  _tvBox = document.createElement('div');
  _tvBox.id = 'tv-preview-box';
  _tvBox.style.width  = TV_PREVIEW_W + 'px';
  _tvBox.style.height = TV_PREVIEW_H + 'px';

  _tvHeader = document.createElement('div');
  _tvHeader.id = 'tv-preview-header';
  _tvHeader.textContent = 'TradingView';

  _tvIframe = document.createElement('iframe');
  _tvIframe.id = 'tv-preview-iframe';
  _tvIframe.height = (TV_PREVIEW_H - TV_PREVIEW_HEADER_H) + 'px';
  _tvIframe.setAttribute('loading', 'lazy');
  _tvIframe.setAttribute('sandbox',
    'allow-scripts allow-same-origin allow-popups allow-forms');

  _tvBox.appendChild(_tvHeader);
  _tvBox.appendChild(_tvIframe);
  document.body.appendChild(_tvBox);

  // Warm the iframe immediately with a neutral page so the TradingView
  // domain connection is established before the first real hover.
  _tvIframe.src = 'https://s.tradingview.com/widgetembed/?symbol=NSE%3ANIFTY&interval=D&theme=dark&style=1&locale=en&hide_top_toolbar=0&hide_volume=1';
}

function _tvShow(tvSymbol, displayName, mouseX, mouseY){
  if(!_tvEnabled || !_tvBox) return;
  clearTimeout(_tvHideTimer);

  // Swap src only when symbol actually changes
  if(tvSymbol !== _tvLastSym){
    _tvIframe.src = _tvBuildSrc(tvSymbol);
    _tvLastSym = tvSymbol;
  }

  // Update header label (decode %3A → : for display)
  _tvHeader.textContent = '📈 ' + displayName + ' — TradingView';

  // Position: keep box fully inside viewport
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = mouseX + TV_PREVIEW_OFFSET_X;
  let top  = mouseY + TV_PREVIEW_OFFSET_Y;
  if(left + TV_PREVIEW_W > vw - 8) left = mouseX - TV_PREVIEW_W - 8;
  if(top  + TV_PREVIEW_H > vh - 8) top  = mouseY - TV_PREVIEW_H - 8;

  _tvBox.style.left    = Math.max(4, left) + 'px';
  _tvBox.style.top     = Math.max(4, top)  + 'px';
  _tvBox.style.display = 'block';
}

function _tvHide(){
  _tvHideTimer = setTimeout(()=>{
    if(_tvBox) _tvBox.style.display = 'none';
  }, TV_HIDE_DELAY_MS);
}

function _tvMove(mouseX, mouseY){
  if(!_tvBox || _tvBox.style.display === 'none') return;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = mouseX + TV_PREVIEW_OFFSET_X;
  let top  = mouseY + TV_PREVIEW_OFFSET_Y;
  if(left + TV_PREVIEW_W > vw - 8) left = mouseX - TV_PREVIEW_W - 8;
  if(top  + TV_PREVIEW_H > vh - 8) top  = mouseY - TV_PREVIEW_H - 8;
  _tvBox.style.left = Math.max(4, left) + 'px';
  _tvBox.style.top  = Math.max(4, top)  + 'px';
}

function _tvToggle(){
  _tvEnabled = !_tvEnabled;
  const btn = document.getElementById('tv-preview-toggle');
  if(btn){
    btn.textContent = _tvEnabled ? '📈 Chart Preview ON' : '📈 Chart Preview OFF';
    btn.className   = _tvEnabled ? 'tv-on' : 'tv-off';
  }
  if(!_tvEnabled && _tvBox) _tvBox.style.display = 'none';
  try{ localStorage.setItem('tvPreviewOn', _tvEnabled ? '1' : '0'); }catch(e){}
}

function _tvAttachHovers(){
  // Attach to every .tv-link that has a data-tv attribute
  document.querySelectorAll('a.tv-link[data-tv]').forEach(el => {
    // Avoid double-binding if tabs re-use the same DOM
    if(el.dataset.tvBound) return;
    el.dataset.tvBound = '1';

    el.addEventListener('mouseenter', e => {
      clearTimeout(_tvHideTimer);
      _tvShow(el.dataset.tv, el.textContent.trim(), e.clientX, e.clientY);
    });
    el.addEventListener('mousemove', e => _tvMove(e.clientX, e.clientY));
    el.addEventListener('mouseleave', _tvHide);
  });
}

// Initialise on DOM ready
document.addEventListener('DOMContentLoaded', ()=>{
  _initThemeFont();
  const saved = localStorage.getItem('activeTab') || 'market';
  showTab(saved);
  document.querySelectorAll('[id^="sleeve-"]').forEach(tbl=>{
    const key = tbl.id.replace('sleeve-','');
    calcSleeve(key);
    loadTracking(key);
  });

  // TV preview init
  _tvInit();
  // Restore user preference
  const tvPref = localStorage.getItem('tvPreviewOn');
  if(tvPref === '0'){ _tvEnabled = false; }
  const btn = document.getElementById('tv-preview-toggle');
  if(btn){
    btn.textContent = _tvEnabled ? '📈 Chart Preview ON' : '📈 Chart Preview OFF';
    btn.className   = _tvEnabled ? 'tv-on' : 'tv-off';
  }
  _tvAttachHovers();
});

// Re-attach after tab switch (content is already in DOM, just need to bind)
// showTab is redefined here to add _tvAttachHovers call after switching tabs.
function showTab(id){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(e=>e.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
  localStorage.setItem('activeTab',id);
  // Re-bind any newly visible tv-link elements
  setTimeout(_tvAttachHovers, 50);
}

// Hide on scroll/resize
window.addEventListener('scroll', _tvHide, {passive:true});
window.addEventListener('resize', _tvHide, {passive:true});
"""


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN BUILD FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def build_html_report(
    market, snapshot_df, sector_str_df, sector_rot_df, industry_rot_df,
    breadth_df, sector_perf_df, stock_str_df, top_buy_df, top_sell_df,
    chart_pat_df, trade_df, dashboard_df, sleeve_df,
    country_etf_df, commodity_df,
    output_path, run_time="", primary_rs=55,
):
    run_time = run_time or datetime.now().strftime("%d %b %Y  %H:%M")
    global _CUR_MKT
    _CUR_MKT = market

    # Signal counts
    sl_col = "Signal_Label" if (stock_str_df is not None and not stock_str_df.empty
                                  and "Signal_Label" in stock_str_df.columns) else None
    at_col = "Action_Tier"  if (stock_str_df is not None and not stock_str_df.empty
                                  and "Action_Tier"  in stock_str_df.columns) else None
    def _cnt(e, av):
        if sl_col: return int(stock_str_df[sl_col].astype(str).str.startswith(e).sum())
        if at_col: return int((stock_str_df[at_col]==av).sum())
        return 0
    prime=_cnt("🌟","PRIME BUY"); conf=_cnt("✅","CONFIRMED BUY")
    rsbuy=_cnt("📈","RS BUY");    avoid=_cnt("🔴","AVOID")

    # Simplified stock view
    MAIN_COLS = ["Symbol","Company","Sector","Price","Chg_1D%",
                 "Signal_Label","Sec_Gated","RS_22d_Idx%","RS_55d_Idx%",
                 "RSI_14","Trend","SMA_Score","Total_Score","Fin_Score",
                 "SL_Buy%","SL_Grade","SL_Buy_Price",
                 "Sales_YoY%","PAT_YoY%","ROE%","D/E","EPS","Mkt_Cap_B","Chart_Pattern"]
    if stock_str_df is not None and not stock_str_df.empty:
        stock_main = stock_str_df[[c for c in MAIN_COLS if c in stock_str_df.columns]]
    else:
        stock_main = stock_str_df

    # ── Tab definitions ────────────────────────────────────────────────────────
    tabs = [
        ("market",        "📸 Market"),
        ("sectors",       "🏭 Sectors"),
        ("opportunities", "🎯 Opportunities"),
        ("stocks",        "📊 Stocks"),
        ("patterns",      "📐 Patterns"),
        ("global",        "🌍 Global"),
        ("sleeves",       "📋 Sleeves"),
        ("guide",         "📚 Guide"),
        ("dashboard",     "📋 Dashboard"),
    ]
    tab_btns = "".join(
        f'<button class="tab-btn" data-tab="{tid}" onclick="showTab(\'{tid}\')">{lbl}</button>'
        for tid, lbl in tabs
    )

    def _sec(tid, title, content):
        return (f'<div class="tab-content" id="tab-{tid}">'
                f'<h2 class="sec-title">{title}</h2>{content}</div>')

    def _toggle(sid, default="cards"):
        return (f'<div class="view-toggle" id="{sid}">'
                f'<button class="vt-btn {"active" if default=="cards" else ""}" '
                f'data-mode="cards" onclick="toggleView(\'{sid}\',\'cards\')">Cards</button>'
                f'<button class="vt-btn {"active" if default=="table" else ""}" '
                f'data-mode="table" onclick="toggleView(\'{sid}\',\'table\')">Table</button>'
                f'</div>')

    # ── Tab content ────────────────────────────────────────────────────────────

    market_content = (
        _build_health_card(stock_str_df, sector_str_df, market) +
        '<h2 class="sec-title">Market Snapshot</h2>' +
        _build_snap_cards(snapshot_df) +
        '<h2 class="sec-title">Market Breadth</h2>' +
        _build_table(breadth_df, "tbl-breadth", searchable=False, pct_mode="breadth")
    )

    sector_content = (
        '<h2 class="sec-title">Sector Strength</h2>' +
        _build_sector_bars(sector_str_df) +
        '<h2 class="sec-title">Sector Performance</h2>' +
        _build_table(sector_perf_df, "tbl-secperf", searchable=False) +
        '<h2 class="sec-title">Sector Rotation</h2>' +
        _build_table(sector_rot_df, "tbl-secrot", pct_mode="breadth") +
        '<h2 class="sec-title">Industry Rotation</h2>' +
        _build_table(industry_rot_df, "tbl-indrot", pct_mode="breadth")
    )

    opp_cards  = _build_opportunity_cards(top_buy_df)
    opp_table  = _build_table(top_buy_df, "tbl-opp-table")
    sell_table = _build_table(top_sell_df, "tbl-sell")
    opp_content = (
        _toggle("vt-opp", "table") +
        f'<div id="vt-opp-cards" style="display:none">{opp_cards}</div>' +
        f'<div id="vt-opp-table">{opp_table}</div>' +
        '<h2 class="sec-title">🔴 Sell Alerts</h2>' + sell_table
    )

    stock_content = _build_table(stock_main, "tbl-stocks", max_rows=500)

    # ── Patterns: enforce a hard recency cap (request #8). Keep only setups
    #    whose Date is within the last PATTERN_RECENT_DAYS days. Rows without a
    #    parseable date (e.g. the "no patterns" placeholder) are kept.
    chart_pat_recent = chart_pat_df
    if (chart_pat_df is not None and not chart_pat_df.empty
            and "Date" in chart_pat_df.columns):
        _d = pd.to_datetime(chart_pat_df["Date"], errors="coerce")
        _cutoff = pd.Timestamp(datetime.now().date()) - timedelta(days=PATTERN_RECENT_DAYS)
        chart_pat_recent = chart_pat_df[_d.isna() | (_d >= _cutoff)]

    patterns_content = (
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px;">'
        f'🗓 Showing only setups from the last {PATTERN_RECENT_DAYS} days. '
        'Quality-filtered: only setups that pass a trend + momentum + R:R gate are shown '
        '(★ = quality score). Sorted: Weekly → Bullish → Quality → Most recent.</p>' +
        _build_table(chart_pat_recent, "tbl-patterns")
    )

    global_content = (
        '<h2 class="sec-title">🌍 Country ETFs (RS vs SPY)</h2>' +
        _build_table(country_etf_df, "tbl-etfs") +
        '<h2 class="sec-title">🏅 Commodities (RS vs GLD)</h2>' +
        _build_table(commodity_df, "tbl-commod")
    )

    sleeves_content = _build_sleeve_tables(sleeve_df, market)
    guide_content   = _build_guide()
    dash_content    = _build_dashboard(dashboard_df)

    sections_html = (
        _sec("market",        "📸 Market Overview",            market_content) +
        _sec("sectors",       "🏭 Sector Analysis",            sector_content) +
        _sec("opportunities", "🎯 Opportunities",              opp_content) +
        _sec("stocks",        "📊 All Stocks",                 stock_content) +
        _sec("patterns",      "📐 Chart Patterns",             patterns_content) +
        _sec("global",        "🌍 Global Markets",             global_content) +
        _sec("sleeves",       "📋 RS Momentum Portfolios",     sleeves_content) +
        _sec("guide",         "📚 Signal Guide & Reference",   guide_content) +
        _sec("dashboard",     "📋 Run Summary & Methodology",  dash_content)
    )

    stats_bar = (
        f'<div class="stats-bar">'
        f'<span class="sl-badge sl-triple">🌟 Prime {prime}</span>'
        f'<span class="sl-badge sl-confirmed">✅ Conf {conf}</span>'
        f'<span class="sl-badge sl-rsbuy">📈 RS {rsbuy}</span>'
        f'<span class="sl-badge sl-avoid">🔴 Avoid {avoid}</span>'
        f'</div>'
    )

    # ── Country navigation: home link + dropdown to switch markets ──────────
    # Maps internal market code → (display name, flag, html filename)
    _COUNTRY_MAP = {
        # ── Original 9 ──
        "USA":       ("United States", "🇺🇸", "US.html"),
        "INDIA":     ("India",         "🇮🇳", "IN.html"),
        "UK":        ("United Kingdom","🇬🇧", "UK.html"),
        "CA":        ("Canada",        "🇨🇦", "CA.html"),
        "AU":        ("Australia",     "🇦🇺", "AU.html"),
        "DE":        ("Germany",       "🇩🇪", "DE.html"),
        "JP":        ("Japan",         "🇯🇵", "JP.html"),
        "FR":        ("France",        "🇫🇷", "FR.html"),
        "BR":        ("Brazil",        "🇧🇷", "BR.html"),
        # ── Batch 1: 8 countries (full-name HTML files) ──
        "CN":        ("China",         "🇨🇳", "CN.html"),
        "KR":        ("South Korea",   "🇰🇷", "KR.html"),
        "TW":        ("Taiwan",        "🇹🇼", "TW.html"),
        "CH":        ("Switzerland",   "🇨🇭", "CH.html"),
        "SA":        ("Saudi Arabia",  "🇸🇦", "SA.html"),
        "NL":        ("Netherlands",   "🇳🇱", "NL.html"),
        "ES":        ("Spain",         "🇪🇸", "ES.html"),
        "SE":        ("Sweden",        "🇸🇪", "SE.html"),
        # ── Batch 2: 11 countries (SHORT-CODE HTML files) ──
        "HK":        ("Hong Kong",     "🇭🇰", "HK.html"),
        "IT":        ("Italy",         "🇮🇹", "IT.html"),
        "SG":        ("Singapore",     "🇸🇬", "SG.html"),
        "ID":        ("Indonesia",     "🇮🇩", "ID.html"),
        "ZA":        ("South Africa",  "🇿🇦", "ZA.html"),
        "MX":        ("Mexico",        "🇲🇽", "MX.html"),
        "TH":        ("Thailand",      "🇹🇭", "TH.html"),
        "MY":        ("Malaysia",      "🇲🇾", "MY.html"),
        "AE":        ("UAE",           "🇦🇪", "UAE.html"),
        "PL":        ("Poland",        "🇵🇱", "PL.html"),
        "TR":        ("Turkey",        "🇹🇷", "TR.html"),
    }
    _cur = str(market).upper()
    _opts = ['<option value="" disabled selected>🌍 Switch market…</option>']
    _opts.append('<option value="index.html">🏠 Home — All Markets</option>')
    for _code, (_nm, _flag, _file) in _COUNTRY_MAP.items():
        if _code == _cur:
            continue
        _opts.append(f'<option value="{_file}">{_flag} {_nm}</option>')
    country_nav = (
        f'<a href="index.html" class="home-link">🏠 All Markets</a>'
        f'<select class="country-nav-select" '
        f'onchange="if(this.value)window.location.href=this.value;">'
        + "".join(_opts) +
        f'</select>'
    )

    # ── Investment disclaimer footer (regulator-neutral, global) ────────────
    disclaimer_html = (
        '<div class="disclaimer-footer">'
        '<h4>⚠️ Important Disclaimer — Please Read</h4>'
        '<p><span class="df-brand">TechnoFunda</span> is an automated, educational '
        'market-analysis tool. All content on this page — including signals, scores, '
        'rankings, "Prime/Confirmed/RS" labels, trade setups and portfolio ideas — is '
        'provided for <strong>informational and educational purposes only</strong>, and '
        'must <strong>not</strong> be construed as investment advice, a research report, '
        'or a recommendation/solicitation to buy or sell any security.</p>'
        '<p>We are <strong>not</strong> registered with any financial regulator as an '
        'Investment Adviser or Research Analyst (including SEBI in India, the SEC/FINRA in '
        'the US, the FCA in the UK, or any equivalent authority in other jurisdictions). '
        'Nothing here is tailored to your personal financial situation, objectives, or '
        'risk tolerance.</p>'
        '<p><strong>Investments in securities markets are subject to market risks. '
        'Read all the related documents carefully before investing.</strong> Past '
        'performance is not indicative of future results. The data shown is sourced from '
        'third parties, may be delayed, inaccurate, or incomplete, and is presented '
        '"as is" without warranty of any kind.</p>'
        '<p>You are solely responsible for your own investment decisions. Always do your '
        'own research and consult a licensed, registered investment adviser or a qualified, '
        'licensed financial professional regulated in your own jurisdiction before making any investment '
        'decision. <span class="df-brand">TechnoFunda</span> and its creators accept no '
        'liability for any loss or damage arising from the use of this information.</p>'
        f'<p style="margin-top:12px;color:var(--text3);">© 2026 TechnoFunda · '
        f'[{market}] report generated {run_time} · Data delayed / end-of-day · '
        f'Not financial advice.</p>'
        '</div>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#0f1117">
  <title>TechnoFunda [{market}] — {run_time}</title>
  <style>{CSS}</style>
</head>
<body>
<header class="app-header">
  <div class="app-brand-row">
    <div>
      <div class="app-title">TechnoFunda [{market}]</div>
      <div class="app-meta">{run_time} · RS{primary_rs}d</div>
    </div>
    {country_nav}
  </div>
  <div class="hdr-controls">
    <button id="tv-preview-toggle" class="tv-on" onclick="_tvToggle()"
            title="Toggle TradingView chart preview on symbol hover">
      📈 Chart Preview ON
    </button>
    <div class="ctrl-group">
      <label>Text</label>
      <button class="fs-btn" onclick="setFont(-1)" title="Smaller text">&minus;</button>
      <button class="fs-btn" onclick="setFont(1)" title="Larger text">+</button>
    </div>
    <div class="ctrl-group">
      <label>Theme</label>
      <select class="theme-select" id="theme-select" onchange="setTheme(this.value)">
        <option value="dark">🌙 Dark</option>
        <option value="light">☀️ Light</option>
        <option value="navy">🌊 Navy Trader</option>
      </select>
    </div>
  </div>
</header>
{stats_bar}
<nav class="tab-bar">{tab_btns}</nav>
<main>{sections_html}</main>
{disclaimer_html}
<script>{JS}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) // 1024
    print(f"  💾 HTML saved: {output_path}  ({size_kb} KB)")
    return output_path
