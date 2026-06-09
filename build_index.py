"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  build_index.py  — TechnoFunda Homepage Generator                          ║
║                                                                            ║
║  Reads each country's HTML report, extracts key metrics,                  ║
║  and builds a beautiful public homepage (index.html).                     ║
║                                                                            ║
║  Run after any country analysis completes, or add to GitHub Actions.      ║
║  Usage:  python build_index.py                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import os, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG: country definitions
# ─────────────────────────────────────────────────────────────────────────────
COUNTRIES = [
    # ── Original 9 ─────────────────────────────────────────────────────────
    {
        "id":        "usa",
        "flag":      "🇺🇸",
        "name":      "United States",
        "exchange":  "NYSE / NASDAQ",
        "html_file": "US.html",
        "index_name":"S&P 500",
        "timezone":  "ET",
        "tz_offset": -4,
    },
    {
        "id":        "india",
        "flag":      "🇮🇳",
        "name":      "India",
        "exchange":  "NSE / BSE",
        "html_file": "IN.html",
        "index_name":"NIFTY 50",
        "timezone":  "IST",
        "tz_offset": 5.5,
    },
    {
        "id":        "uk",
        "flag":      "🇬🇧",
        "name":      "United Kingdom",
        "exchange":  "London Stock Exchange",
        "html_file": "UK.html",
        "index_name":"FTSE 100",
        "timezone":  "GMT",
        "tz_offset": 0,
    },
    {
        "id":        "canada",
        "flag":      "🇨🇦",
        "name":      "Canada",
        "exchange":  "Toronto Stock Exchange",
        "html_file": "CA.html",
        "index_name":"S&P/TSX",
        "timezone":  "ET",
        "tz_offset": -4,
    },
    {
        "id":        "australia",
        "flag":      "🇦🇺",
        "name":      "Australia",
        "exchange":  "Australian Securities Exchange",
        "html_file": "AU.html",
        "index_name":"S&P/ASX 200",
        "timezone":  "AEST",
        "tz_offset": 10,
    },
    {
        "id":        "germany",
        "flag":      "🇩🇪",
        "name":      "Germany",
        "exchange":  "XETRA / Frankfurt",
        "html_file": "DE.html",
        "index_name":"DAX 40",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "japan",
        "flag":      "🇯🇵",
        "name":      "Japan",
        "exchange":  "Tokyo Stock Exchange",
        "html_file": "JP.html",
        "index_name":"Nikkei 225",
        "timezone":  "JST",
        "tz_offset": 9,
    },
    {
        "id":        "france",
        "flag":      "🇫🇷",
        "name":      "France",
        "exchange":  "Euronext Paris",
        "html_file": "FR.html",
        "index_name":"CAC 40",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "brazil",
        "flag":      "🇧🇷",
        "name":      "Brazil",
        "exchange":  "B3 - Bolsa Brasil",
        "html_file": "BR.html",
        "index_name":"Ibovespa",
        "timezone":  "BRT",
        "tz_offset": -3,
    },
    # ── New 8 countries ─────────────────────────────────────────────────────
    {
        "id":        "china",
        "flag":      "🇨🇳",
        "name":      "China",
        "exchange":  "Shanghai / Shenzhen",
        "html_file": "CN.html",
        "index_name":"CSI 300",
        "timezone":  "CST",
        "tz_offset": 8,
    },
    {
        "id":        "southkorea",
        "flag":      "🇰🇷",
        "name":      "South Korea",
        "exchange":  "Korea Exchange (KRX)",
        "html_file": "KR.html",
        "index_name":"KOSPI",
        "timezone":  "KST",
        "tz_offset": 9,
    },
    {
        "id":        "taiwan",
        "flag":      "🇹🇼",
        "name":      "Taiwan",
        "exchange":  "Taiwan Stock Exchange",
        "html_file": "TW.html",
        "index_name":"TAIEX",
        "timezone":  "CST",
        "tz_offset": 8,
    },
    {
        "id":        "switzerland",
        "flag":      "🇨🇭",
        "name":      "Switzerland",
        "exchange":  "SIX Swiss Exchange",
        "html_file": "CH.html",
        "index_name":"SMI",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "saudiarabia",
        "flag":      "🇸🇦",
        "name":      "Saudi Arabia",
        "exchange":  "Tadawul (Saudi Exchange)",
        "html_file": "SA.html",
        "index_name":"TASI (Tadawul)",
        "timezone":  "AST",
        "tz_offset": 3,
    },
    {
        "id":        "netherlands",
        "flag":      "🇳🇱",
        "name":      "Netherlands",
        "exchange":  "Euronext Amsterdam",
        "html_file": "NL.html",
        "index_name":"AEX",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "spain",
        "flag":      "🇪🇸",
        "name":      "Spain",
        "exchange":  "Bolsas y Mercados Espanoles",
        "html_file": "ES.html",
        "index_name":"IBEX 35",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "sweden",
        "flag":      "🇸🇪",
        "name":      "Sweden",
        "exchange":  "Nasdaq Stockholm",
        "html_file": "SE.html",
        "index_name":"OMX Stockholm 30",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    # ── Batch 2: 11 short-code countries ──
    {
        "id":        "hk",
        "flag":      "🇭🇰",
        "name":      "Hong Kong",
        "exchange":  "Hong Kong Stock Exchange",
        "html_file": "HK.html",
        "index_name":"Hang Seng",
        "timezone":  "HKT",
        "tz_offset": 8,
    },
    {
        "id":        "it",
        "flag":      "🇮🇹",
        "name":      "Italy",
        "exchange":  "Borsa Italiana",
        "html_file": "IT.html",
        "index_name":"FTSE MIB",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "sg",
        "flag":      "🇸🇬",
        "name":      "Singapore",
        "exchange":  "Singapore Exchange",
        "html_file": "SG.html",
        "index_name":"STI",
        "timezone":  "SGT",
        "tz_offset": 8,
    },
    {
        "id":        "id",
        "flag":      "🇮🇩",
        "name":      "Indonesia",
        "exchange":  "Indonesia Stock Exchange",
        "html_file": "ID.html",
        "index_name":"IDX Composite",
        "timezone":  "WIB",
        "tz_offset": 7,
    },
    {
        "id":        "za",
        "flag":      "🇿🇦",
        "name":      "South Africa",
        "exchange":  "Johannesburg Stock Exchange",
        "html_file": "ZA.html",
        "index_name":"JSE Top 40",
        "timezone":  "SAST",
        "tz_offset": 2,
    },
    {
        "id":        "mx",
        "flag":      "🇲🇽",
        "name":      "Mexico",
        "exchange":  "Bolsa Mexicana de Valores",
        "html_file": "MX.html",
        "index_name":"IPC Mexico",
        "timezone":  "CST",
        "tz_offset": -6,
    },
    {
        "id":        "th",
        "flag":      "🇹🇭",
        "name":      "Thailand",
        "exchange":  "Stock Exchange of Thailand",
        "html_file": "TH.html",
        "index_name":"SET Index",
        "timezone":  "ICT",
        "tz_offset": 7,
    },
    {
        "id":        "my",
        "flag":      "🇲🇾",
        "name":      "Malaysia",
        "exchange":  "Bursa Malaysia",
        "html_file": "MY.html",
        "index_name":"KLCI",
        "timezone":  "MYT",
        "tz_offset": 8,
    },
    {
        "id":        "uae",
        "flag":      "🇦🇪",
        "name":      "UAE",
        "exchange":  "Dubai / Abu Dhabi Exchange",
        "html_file": "UAE.html",
        "index_name":"DFM / ADX",
        "timezone":  "GST",
        "tz_offset": 4,
    },
    {
        "id":        "pl",
        "flag":      "🇵🇱",
        "name":      "Poland",
        "exchange":  "Warsaw Stock Exchange",
        "html_file": "PL.html",
        "index_name":"WIG20",
        "timezone":  "CET",
        "tz_offset": 1,
    },
    {
        "id":        "tr",
        "flag":      "🇹🇷",
        "name":      "Turkey",
        "exchange":  "Borsa Istanbul",
        "html_file": "TR.html",
        "index_name":"BIST 100",
        "timezone":  "TRT",
        "tz_offset": 3,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  HTML PARSING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def extract_text(html: str, pattern: str, default="—") -> str:
    """Extract first capture group from regex pattern."""
    m = re.search(pattern, html)
    return m.group(1).strip() if m else default


def parse_country_html(html_path: str, country: dict) -> dict:
    """
    Parse a country HTML report and extract key metrics.
    Returns a data dict suitable for the homepage card.
    """
    result = {
        **country,
        "status":       "coming",
        "mood":         "coming",
        "updated":      "Not yet configured",
        "index_price":  "—",
        "index_chg":    "—",
        "universe":     0,
        "signals":      {"prime": 0, "conf": 0, "rs": 0, "watch": 0, "avoid": 0},
        "top_sectors":  [],
    }

    if not os.path.exists(html_path):
        print(f"  ⏭  {country['name']}: HTML not found ({html_path})")
        return result

    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
    except Exception as e:
        print(f"  ❌  {country['name']}: Cannot read HTML — {e}")
        return result

    result["status"] = "live"

    # ── Title / run time ─────────────────────────────────────────
    title = extract_text(html, r'<title>([^<]+)</title>')
    # e.g. "TechnoFunda [US] — 03 Jun 2026  02:10 ET"
    date_match = re.search(r'(\d{2}\s+\w+\s+\d{4})\s+([\d:]+)\s+(\w+)', title)
    if date_match:
        result["updated"] = f"{date_match.group(1)} · {date_match.group(2)} {date_match.group(3)}"
    else:
        result["updated"] = datetime.now().strftime("%d %b %Y")

    # ── Universe size ─────────────────────────────────────────────
    univ_match = re.search(r'<div class="hc-block">.*?<div class="hc-label">Universe</div>\s*<div class="hc-value"[^>]*>(\d+)', html, re.DOTALL)
    if univ_match:
        result["universe"] = int(univ_match.group(1))
    else:
        # Fallback: count table rows in stocks tab
        result["universe"] = len(re.findall(r'<tr><td', html)) // 10 or 500

    # ── Signal counts from health-card inline badges ─────────────
    # Actual HTML: <div class="hc-value sl-triple-inline">6</div>
    prime_m = re.search(r'sl-triple-inline[^>]*>(\d+)', html)
    conf_m  = re.search(r'sl-confirmed-inline[^>]*>(\d+)', html)
    rs_m    = re.search(r'sl-rsbuy-inline[^>]*>(\d+)', html)
    watch_m = re.search(r'sl-watch-inline[^>]*>(\d+)', html)
    avoid_m = re.search(r'sl-avoid-inline[^>]*>(\d+)', html)

    result["signals"]["prime"] = int(prime_m.group(1)) if prime_m else 0
    result["signals"]["conf"]  = int(conf_m.group(1))  if conf_m  else 0
    result["signals"]["rs"]    = int(rs_m.group(1))    if rs_m    else 0
    result["signals"]["watch"] = int(watch_m.group(1)) if watch_m else 0
    result["signals"]["avoid"] = int(avoid_m.group(1)) if avoid_m else 0

    # ── Index price & change from snap-card ──────────────────────
    # Find the card that matches our index name
    index_pattern = rf'<div class="snap-name">{re.escape(country["index_name"])}</div>\s*<div class="snap-price">([^<]+)</div>\s*<div class="snap-chg[^"]*">([^<]+)</div>'
    idx_m = re.search(index_pattern, html, re.IGNORECASE | re.DOTALL)
    if idx_m:
        price_raw = idx_m.group(1).strip()
        chg_raw   = idx_m.group(2).strip()
        # Format price with comma separators if it's a number
        try:
            price_num = float(price_raw.replace(',', ''))
            if price_num > 1000:
                result["index_price"] = f"{price_num:,.0f}"
            elif price_num > 10:
                result["index_price"] = f"{price_num:,.2f}"
            else:
                result["index_price"] = f"{price_num:.2f}"
        except Exception:
            result["index_price"] = price_raw

        # Clean up chg: strip +/- for storage, keep sign info
        result["index_chg"] = chg_raw.replace('%', '').strip()

    # ── Market mood from health-card ─────────────────────────────
    mood_m = re.search(r'hc-value mood-[^"]*">([\w\s\-]+)</div>', html)
    if mood_m:
        mood_text = mood_m.group(1).lower()
        if "risk-on" in mood_text or "bull" in mood_text:
            result["mood"] = "bull"
        elif "risk-off" in mood_text or "bear" in mood_text:
            result["mood"] = "bear"
        else:
            result["mood"] = "mixed"
    else:
        # Derive from signals
        total_buy = result["signals"]["prime"] + result["signals"]["conf"] + result["signals"]["rs"]
        total_avoid = result["signals"]["avoid"]
        if total_avoid == 0: total_avoid = 1
        ratio = total_buy / (total_buy + total_avoid)
        result["mood"] = "bull" if ratio > 0.35 else ("bear" if ratio < 0.15 else "mixed")

    # ── Top / bottom sectors from sector-bars ────────────────────
    # Pattern: <div class="sec-name">✅ Technology</div>...<div class="sec-rs pos/neg">+17.6%</div>
    sector_pattern = r'sec-name">[^<]*?(\w[\w\s/&]+)</div>.*?sec-rs\s*(pos|neg)">([\+\-]?[\d\.]+)%'
    sector_matches = re.findall(sector_pattern, html)
    if sector_matches:
        sectors_clean = []
        for name, direction, pct in sector_matches[:6]:
            name = re.sub(r'^[✅🔴⚠️]\s*', '', name).strip()
            pct_f = float(pct) if pct else 0
            sectors_clean.append({
                "name": name,
                "pct":  f"+{pct}" if direction == "pos" else f"-{pct}" if not pct.startswith('-') else pct,
                "dir":  direction,
                "sort": pct_f if direction == "pos" else -pct_f
            })
        # Sort: top pos first, then bottom neg
        pos_sectors = sorted([s for s in sectors_clean if s["dir"] == "pos"], key=lambda x: x["sort"], reverse=True)
        neg_sectors = sorted([s for s in sectors_clean if s["dir"] == "neg"], key=lambda x: x["sort"])
        result["top_sectors"] = (pos_sectors[:2] + neg_sectors[:1])[:3]

    print(f"  ✅  {country['name']}: {result['status']} | mood={result['mood']} | prime={result['signals']['prime']} | updated={result['updated']}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  HTML TEMPLATE  (inline — no external dependencies)
# ─────────────────────────────────────────────────────────────────────────────

def render_homepage(markets: list, output_path: str):
    """Render the full homepage HTML from market data."""

    # Pre-compute totals
    live = [m for m in markets if m["status"] == "live"]
    total_prime  = sum(m["signals"]["prime"] for m in live)
    total_stocks = sum(m["universe"] for m in markets)
    total_countries = len(markets)
    gen_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    # Build JS data array
    def js_market(m):
        sectors_js = ",\n".join([
            f'      {{name:"{s["name"]}",pct:"{s["pct"]}",dir:"{s["dir"]}"}}'
            for s in m["top_sectors"]
        ])
        return f'''  {{
    id:         "{m["id"]}",
    flag:       "{m["flag"]}",
    name:       "{m["name"]}",
    exchange:   "{m["exchange"]}",
    url:        "{m["html_file"]}",
    status:     "{m["status"]}",
    mood:       "{m["mood"]}",
    updated:    "{m["updated"]}",
    index_name: "{m["index_name"]}",
    index_price:"{m["index_price"]}",
    index_chg:  "{m["index_chg"]}",
    universe:   {m["universe"]},
    signals:    {{prime:{m["signals"]["prime"]},conf:{m["signals"]["conf"]},rs:{m["signals"]["rs"]},avoid:{m["signals"]["avoid"]}}},
    top_sectors:[
{sectors_js}
    ]
  }}'''

    markets_js = "[\n" + ",\n".join(js_market(m) for m in markets) + "\n]"

    # Footer links
    footer_links = "\n".join([
        f'        <a href="{m["html_file"]}">{m["flag"]} {m["name"]} Report</a>'
        for m in markets
    ])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TechnoFunda — Global Market Intelligence</title>
<meta name="description" content="Daily RS Momentum Analysis across {total_countries} global stock markets. Free, automated, data-driven.">
<meta name="robots" content="index, follow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#080c14;--bg2:#0d1220;--bg3:#111827;
  --border:rgba(255,255,255,.07);--border2:rgba(255,255,255,.12);
  --gold:#f0b429;--gold2:#ffd666;
  --text:#f0f4ff;--text2:#8896b0;--text3:#7b87a8;
  --green:#10b981;--green-dim:rgba(16,185,129,.12);--green-glow:rgba(16,185,129,.25);
  --red:#ef4444;--red-dim:rgba(239,68,68,.12);
  --amber:#f59e0b;--amber-dim:rgba(245,158,11,.12);
  --blue:#3b82f6;
  --radius:14px;--radius-sm:8px;
  --shadow:0 4px 24px rgba(0,0,0,.4);--shadow-lg:0 12px 48px rgba(0,0,0,.6);
  --font-head:'DM Serif Display',Georgia,serif;
  --font-body:'DM Sans',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:var(--font-body);font-size:15px;line-height:1.6;min-height:100vh;overflow-x:hidden}}
body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 20% 0%,rgba(59,130,246,.06) 0%,transparent 60%),radial-gradient(ellipse 60% 40% at 80% 100%,rgba(240,180,41,.04) 0%,transparent 60%),radial-gradient(ellipse 100% 60% at 50% 50%,rgba(16,185,129,.02) 0%,transparent 70%);pointer-events:none;z-index:0}}
body::after{{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(255,255,255,.015) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.015) 1px,transparent 1px);background-size:60px 60px;pointer-events:none;z-index:0}}
.pw{{position:relative;z-index:1;max-width:1280px;margin:0 auto;padding:0 20px}}
.topnav{{display:flex;align-items:center;justify-content:space-between;padding:20px 0;border-bottom:1px solid var(--border)}}
.logo-wrap{{display:flex;align-items:center;gap:10px}}
.logo-icon{{width:36px;height:36px;background:linear-gradient(135deg,var(--gold),#e07b00);border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 0 16px rgba(240,180,41,.3)}}
.logo-text{{font-family:var(--font-head);font-size:20px;color:var(--text)}}
.logo-text span{{color:var(--gold)}}
.nav-tag{{font-size:11px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:var(--text2);background:var(--bg3);border:1px solid var(--border);padding:4px 10px;border-radius:20px}}
.nav-live{{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--green);font-family:var(--font-mono)}}
.live-dot{{width:7px;height:7px;background:var(--green);border-radius:50%;animation:pulse-green 2s ease-in-out infinite;box-shadow:0 0 6px var(--green)}}
@keyframes pulse-green{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.5;transform:scale(.85)}}}}
.hero{{text-align:center;padding:72px 0 56px}}
.hero-eyebrow{{display:inline-flex;align-items:center;gap:8px;font-size:11px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--gold);background:rgba(240,180,41,.08);border:1px solid rgba(240,180,41,.2);padding:6px 14px;border-radius:20px;margin-bottom:24px}}
.hero h1{{font-family:var(--font-head);font-size:clamp(38px,6vw,72px);font-weight:400;line-height:1.1;letter-spacing:-1px;margin-bottom:20px;background:linear-gradient(135deg,#fff 0%,rgba(255,255,255,.7) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.hero h1 em{{font-style:italic;background:linear-gradient(135deg,var(--gold) 0%,var(--gold2) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.hero-sub{{font-size:17px;color:var(--text2);max-width:560px;margin:0 auto 36px;line-height:1.7;font-weight:300}}
.hero-stats{{display:flex;justify-content:center;align-items:center;gap:32px;flex-wrap:wrap}}
.hs-item{{display:flex;flex-direction:column;align-items:center;gap:3px}}
.hs-num{{font-family:var(--font-mono);font-size:28px;font-weight:500;color:var(--text);line-height:1}}
.hs-num.gold{{color:var(--gold)}}.hs-num.green{{color:var(--green)}}
.hs-label{{font-size:11px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--text3)}}
.hs-sep{{width:1px;height:32px;background:var(--border)}}
.ticker-wrap{{overflow:hidden;background:var(--bg2);border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:10px 0;margin-bottom:60px}}
.ticker-inner{{display:flex;gap:48px;animation:ticker-scroll 40s linear infinite;width:max-content}}
@keyframes ticker-scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.ticker-item{{display:flex;align-items:center;gap:8px;white-space:nowrap;flex-shrink:0}}
.ticker-sym{{font-family:var(--font-mono);font-size:12px;font-weight:700;color:var(--text)}}
.ticker-price{{font-family:var(--font-mono);font-size:12px;color:var(--text2)}}
.ticker-chg{{font-family:var(--font-mono);font-size:11px;font-weight:600}}
.ticker-dot{{width:3px;height:3px;border-radius:50%;background:var(--border2)}}
.sec-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}}
.sec-title-wrap{{display:flex;flex-direction:column;gap:4px}}
.sec-label{{font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:var(--gold)}}
.sec-title{{font-family:var(--font-head);font-size:28px;font-weight:400;color:var(--text);letter-spacing:-.5px}}
.sec-updated{{font-size:12px;color:var(--text3);font-family:var(--font-mono)}}
.countries-section{{padding:0 0 80px}}
.countries-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px}}
.country-card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease;cursor:pointer;position:relative}}
.country-card:hover{{transform:translateY(-3px);border-color:var(--border2);box-shadow:var(--shadow-lg)}}
.active-card{{border-color:rgba(16,185,129,.3);box-shadow:0 0 0 1px rgba(16,185,129,.1),var(--shadow)}}
.inactive-card{{opacity:.65}}.inactive-card:hover{{opacity:.85}}
.cc-strip{{height:3px;width:100%}}
.strip-bull{{background:linear-gradient(90deg,var(--green),rgba(16,185,129,.2))}}
.strip-bear{{background:linear-gradient(90deg,var(--red),rgba(239,68,68,.2))}}
.strip-mixed{{background:linear-gradient(90deg,var(--amber),rgba(245,158,11,.2))}}
.strip-coming{{background:linear-gradient(90deg,var(--text3),transparent)}}
.cc-body{{padding:20px 22px 22px}}
.cc-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}}
.cc-country{{display:flex;align-items:center;gap:10px}}
.cc-flag{{font-size:28px;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,.3))}}
.cc-name-wrap{{display:flex;flex-direction:column;gap:1px}}
.cc-name{{font-weight:700;font-size:17px;color:var(--text);letter-spacing:-.2px}}
.cc-exchange{{font-size:11px;font-family:var(--font-mono);color:var(--text3);font-weight:500}}
.cc-mood{{display:flex;flex-direction:column;align-items:flex-end;gap:3px}}
.cc-mood-badge{{font-size:12px;font-weight:700;letter-spacing:.4px;padding:4px 10px;border-radius:20px}}
.mood-bull{{background:var(--green-dim);color:var(--green);border:1px solid var(--green-glow)}}
.mood-bear{{background:var(--red-dim);color:var(--red);border:1px solid rgba(239,68,68,.2)}}
.mood-mixed{{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)}}
.mood-coming{{background:var(--bg3);color:var(--text3);border:1px solid var(--border)}}
.cc-updated{{font-size:10px;color:var(--text3);font-family:var(--font-mono)}}
.cc-signals{{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:16px}}
.sig-pill{{display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:5px 10px;border-radius:var(--radius-sm);white-space:nowrap;border:1px solid transparent}}
.sig-prime{{background:linear-gradient(135deg,rgba(240,180,41,.15),rgba(240,180,41,.05));color:var(--gold);border-color:rgba(240,180,41,.2)}}
.sig-conf{{background:rgba(16,185,129,.12);color:var(--green);border-color:rgba(16,185,129,.2)}}
.sig-rs{{background:rgba(59,130,246,.10);color:#60a5fa;border-color:rgba(59,130,246,.15)}}
.sig-avoid{{background:rgba(239,68,68,.08);color:#f87171;border-color:rgba(239,68,68,.12)}}
.cc-metrics{{display:flex;gap:12px;margin-bottom:16px}}
.cc-metric{{flex:1;background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;display:flex;flex-direction:column;gap:4px}}
.cc-metric-label{{font-size:10px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--text3)}}
.cc-metric-value{{font-family:var(--font-mono);font-size:16px;font-weight:500;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cc-metric-sub{{font-size:11px;color:var(--text2)}}
.pos{{color:var(--green)!important}}.neg{{color:var(--red)!important}}
.cc-sectors-label{{font-size:10px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--text3);margin-bottom:8px}}
.cc-sector-rows{{display:flex;flex-direction:column;gap:5px}}
.cc-sec-row{{display:flex;align-items:center;gap:8px}}
.cc-sec-name{{font-size:12px;color:var(--text2);width:120px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cc-sec-bar-track{{flex:1;height:4px;background:var(--bg3);border-radius:2px;overflow:hidden}}
.cc-sec-bar-fill{{height:100%;border-radius:2px}}
.bar-pos{{background:linear-gradient(90deg,var(--green),rgba(16,185,129,.4))}}
.bar-neg{{background:linear-gradient(90deg,var(--red),rgba(239,68,68,.4))}}
.cc-sec-pct{{font-family:var(--font-mono);font-size:11px;width:46px;text-align:right;flex-shrink:0}}
.cc-cta{{display:flex;align-items:center;justify-content:space-between;margin-top:18px;padding-top:16px;border-top:1px solid var(--border)}}
.cc-universe{{font-size:11px;color:var(--text3);font-family:var(--font-mono)}}
.btn-report{{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--bg);background:linear-gradient(135deg,var(--gold),#e07b00);border:none;padding:8px 18px;border-radius:var(--radius-sm);cursor:pointer;text-decoration:none;transition:all .15s ease;box-shadow:0 2px 12px rgba(240,180,41,.25);white-space:nowrap}}
.btn-report:hover{{transform:scale(1.03);box-shadow:0 4px 20px rgba(240,180,41,.4)}}
.btn-coming{{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--text3);background:var(--bg3);border:1px solid var(--border);padding:8px 18px;border-radius:var(--radius-sm);white-space:nowrap}}
.cc-coming-overlay{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(8,12,20,.5);backdrop-filter:blur(2px);border-radius:var(--radius);gap:8px}}
.cc-coming-text{{font-size:13px;font-weight:600;color:var(--text3);letter-spacing:.5px}}
.cc-coming-eta{{font-size:11px;color:var(--text3);font-family:var(--font-mono)}}
.how-section{{border-top:1px solid var(--border);padding:64px 0}}
.how-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:32px;margin-top:40px}}
.how-item{{display:flex;flex-direction:column;gap:12px}}
.how-icon{{width:42px;height:42px;border-radius:10px;background:var(--bg2);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:20px}}
.how-title{{font-weight:700;font-size:15px;color:var(--text)}}
.how-desc{{font-size:13px;color:var(--text2);line-height:1.6}}
.legend-section{{border-top:1px solid var(--border);padding:64px 0}}
.legend-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:32px}}
.legend-item{{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-sm)}}
.legend-badge{{flex-shrink:0;font-size:11px;font-weight:700;padding:4px 8px;border-radius:6px;letter-spacing:.3px;white-space:nowrap}}
.legend-text{{font-size:13px;color:var(--text2);line-height:1.5}}
.legend-text strong{{color:var(--text);font-size:14px}}
.feedback-section-home{{border-top:1px solid var(--border);padding:64px 0}}
.fh-sub{{font-size:14px;color:var(--text2);margin:0 0 20px;}}
.feedback-form-home{{display:flex;flex-direction:column;gap:12px;max-width:640px}}
.fb-row-home{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.fb-input-home,.fb-textarea-home{{background:var(--bg2);border:1px solid var(--border);
  color:var(--text);border-radius:var(--radius-sm);padding:10px 14px;font-size:13px;
  font-family:inherit;outline:none;transition:border-color .15s;}}
.fb-input-home:focus,.fb-textarea-home:focus{{border-color:var(--gold);}}
.fb-textarea-home{{min-height:100px;resize:vertical;}}
.fb-btn-home{{align-self:flex-start;background:var(--gold);color:#000;border:none;
  border-radius:var(--radius-sm);padding:10px 22px;font-size:13px;font-weight:700;
  cursor:pointer;transition:opacity .15s;}}
.fb-btn-home:hover{{opacity:.85;}}
.fb-float-home{{position:fixed;bottom:24px;right:20px;z-index:200;background:var(--gold);
  color:#000;border-radius:20px;padding:9px 18px;font-size:12px;font-weight:700;
  text-decoration:none;box-shadow:0 3px 12px rgba(0,0,0,.25);
  display:flex;align-items:center;gap:5px;transition:opacity .15s;}}
.fb-float-home:hover{{opacity:.85;}}
.footer{{border-top:1px solid var(--border);padding:32px 0 48px}}
.footer-inner{{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;flex-wrap:wrap}}
.footer-brand{{display:flex;flex-direction:column;gap:10px;max-width:360px}}
.footer-logo{{font-family:var(--font-head);font-size:18px;color:var(--text)}}
.footer-logo span{{color:var(--gold)}}
.footer-disclaimer{{font-size:12px;color:var(--text3);line-height:1.6}}
.footer-links{{display:flex;flex-direction:column;gap:8px}}
.footer-link-title{{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--text2);margin-bottom:4px}}
.footer-links a{{font-size:13px;color:var(--text3);text-decoration:none;transition:color .15s}}
.footer-links a:hover{{color:var(--gold)}}
.footer-copy{{text-align:center;font-size:12px;color:var(--text3);margin-top:32px;padding-top:24px;border-top:1px solid var(--border)}}
@keyframes fadeInUp{{from{{opacity:0;transform:translateY(24px)}}to{{opacity:1;transform:translateY(0)}}}}
.animate-in{{animation:fadeInUp .5s ease forwards;opacity:0}}
.delay-1{{animation-delay:.1s}}.delay-2{{animation-delay:.2s}}.delay-3{{animation-delay:.3s}}
.delay-4{{animation-delay:.4s}}.delay-5{{animation-delay:.5s}}.delay-6{{animation-delay:.6s}}
@media(max-width:640px){{
  .hero{{padding:48px 0 40px}}.hero h1{{font-size:36px}}.hero-sub{{font-size:15px}}
  .hero-stats{{gap:16px}}.hs-sep{{display:none}}.hs-num{{font-size:22px}}
  .topnav .nav-tag{{display:none}}.countries-grid{{grid-template-columns:1fr}}
  .cc-metrics{{flex-direction:column}}.footer-inner{{flex-direction:column}}
}}
</style>
</head>
<body>

<div class="pw">
  <nav class="topnav">
    <div class="logo-wrap">
      <div class="logo-icon">📊</div>
      <span class="logo-text">Techno<span>Funda</span></span>
    </div>
    <div style="display:flex;align-items:center;gap:20px">
      <a href="about.html" style="font-size:13px;color:var(--text2);text-decoration:none;font-weight:500;transition:color .15s" onmouseover="this.style.color='var(--gold)'" onmouseout="this.style.color='var(--text2)'">About</a>
      <span class="nav-tag">Global Market Intelligence</span>
    </div>
    <div class="nav-live"><div class="live-dot"></div>Daily Updated</div>
  </nav>
</div>

<div class="pw">
  <section class="hero">
    <div class="hero-eyebrow animate-in">✦ RS Momentum Analysis — Updated Daily</div>
    <h1 class="animate-in delay-1">The Global Stock<br>Market, <em>Simplified</em></h1>
    <p class="hero-sub animate-in delay-2">Every day, our engine automatically analyses thousands of stocks across multiple countries — surfacing the strongest momentum opportunities so you don't have to.</p>
    <div class="hero-stats animate-in delay-3">
      <div class="hs-item"><span class="hs-num gold">{total_countries}</span><span class="hs-label">Markets</span></div>
      <div class="hs-sep"></div>
      <div class="hs-item"><span class="hs-num">{total_stocks:,}+</span><span class="hs-label">Stocks Tracked</span></div>
      <div class="hs-sep"></div>
      <div class="hs-item"><span class="hs-num green">{total_prime}</span><span class="hs-label">Prime Setups Today</span></div>
      <div class="hs-sep"></div>
      <div class="hs-item"><span class="hs-num">Daily</span><span class="hs-label">Updated</span></div>
    </div>
  </section>
</div>

<div class="ticker-wrap animate-in delay-4"><div class="ticker-inner" id="ticker"></div></div>

<div class="pw">
  <section class="countries-section">
    <div class="sec-head animate-in delay-1">
      <div class="sec-title-wrap">
        <span class="sec-label">Live Reports</span>
        <h2 class="sec-title">Choose Your Market</h2>
      </div>
      <span class="sec-updated" id="gen-time-label" data-utc="{gen_time}">Generated: {gen_time}</span>
    </div>
    <div class="countries-grid" id="countries-grid"></div>
  </section>

  <section class="how-section animate-in">
    <div class="sec-head"><div class="sec-title-wrap"><span class="sec-label">Methodology</span><h2 class="sec-title">How it Works</h2></div></div>
    <div class="how-grid">
      <div class="how-item"><div class="how-icon">📡</div><div class="how-title">Daily Data Collection</div><div class="how-desc">Every day after market close, our engine automatically downloads end-of-day price data for every stock in each country.</div></div>
      <div class="how-item"><div class="how-icon">⚙️</div><div class="how-title">RS Momentum Scoring</div><div class="how-desc">Each stock is scored on Relative Strength — how well it performs compared to its own sector and the overall market index.</div></div>
      <div class="how-item"><div class="how-icon">🏆</div><div class="how-title">Signal Classification</div><div class="how-desc">Stocks are classified from 🌟 Prime (Very Strong Bullish) through Confirmed and RS Bullish signals, down to 🔴 Bearish (breaking down vs market).</div></div>
      <div class="how-item"><div class="how-icon">📊</div><div class="how-title">Report Generation</div><div class="how-desc">Full interactive reports are built with sector rankings, top opportunities, chart patterns, and trade setups — all in one place.</div></div>
      <div class="how-item"><div class="how-icon">🌐</div><div class="how-title">Published Here</div><div class="how-desc">This page and all country reports are automatically published to the web every trading day — free, with no signup needed.</div></div>
    </div>
  </section>

  <section class="legend-section animate-in">
    <div class="sec-head"><div class="sec-title-wrap"><span class="sec-label">Understanding the Labels</span><h2 class="sec-title">What do the signals mean?</h2></div></div>
    <div class="legend-grid">
      <div class="legend-item"><span class="legend-badge sig-prime">🌟 Prime</span><div class="legend-text"><strong>Very Strong Bullish</strong><br>Strongest signal. Stock is outperforming on multiple timeframes with strong fundamentals. The best setups.</div></div>
      <div class="legend-item"><span class="legend-badge sig-conf">✅ Confirmed</span><div class="legend-text"><strong>Strong Bullish</strong><br>Stock is outperforming the market and sector consistently. Good momentum, consider for watchlist.</div></div>
      <div class="legend-item"><span class="legend-badge sig-rs">📈 RS Leader</span><div class="legend-text"><strong>Bullish Relative Strength</strong><br>Stock is showing positive RS vs market and sector. Early stage bullish momentum — watch for breakout.</div></div>
      <div class="legend-item"><span class="legend-badge" style="background:rgba(156,163,175,.1);color:#9ca3af;border:1px solid rgba(156,163,175,.15)">👁 Watch</span><div class="legend-text"><strong>Neutral — Setup Building</strong><br>Pre-conditions met but not yet confirmed. Stock is setting up — check back daily for progression.</div></div>
      <div class="legend-item"><span class="legend-badge" style="background:rgba(107,114,128,.1);color:#6b7280;border:1px solid rgba(107,114,128,.15)">⬜ Neutral</span><div class="legend-text"><strong>Neutral — No Signal</strong><br>Mixed signals — stock is neither a clear leader nor laggard vs the market right now.</div></div>
      <div class="legend-item"><span class="legend-badge sig-avoid">🔴 RS Breakdown</span><div class="legend-text"><strong>Bearish Relative Strength</strong><br>Stock is significantly underperforming both its sector and the market. Caution advised.</div></div>
    </div>
  </section>

  <section class="feedback-section-home animate-in" id="feedback">
    <div class="sec-head"><div class="sec-title-wrap"><span class="sec-label">We want to hear from you</span><h2 class="sec-title">💬 Share Your Feedback</h2></div></div>
    <p class="fh-sub">Found a bug? Have a suggestion? Tell us what would make TechnoFunda more useful.</p>
    <form class="feedback-form-home" action="https://formspree.io/f/xpqeqokw" method="POST">
      <div class="fb-row-home">
        <input type="text" name="name" placeholder="Your name (optional)" class="fb-input-home">
        <input type="email" name="email" placeholder="Email (optional — for reply)" class="fb-input-home">
      </div>
      <textarea name="message" placeholder="Your feedback, idea, or question…" class="fb-textarea-home" required></textarea>
      <button type="submit" class="fb-btn-home">Send Feedback →</button>
    </form>
  </section>

  <footer class="footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <span class="footer-logo">Techno<span>Funda</span></span>
        <p class="footer-disclaimer">⚠️ <strong>Disclaimer:</strong> All content on this website is for educational and informational purposes only. This is not financial advice. We are not registered investment advisers. Always do your own research and consult a qualified financial professional before making investment decisions. Past performance does not guarantee future results.</p>
      </div>
      <div class="footer-links">
        <div class="footer-link-title">Markets</div>
        {footer_links}
      </div>
      <div class="footer-links">
        <div class="footer-link-title">Info</div>
        <a href="about.html">ℹ️ About</a>
        <a href="#feedback">💬 Feedback</a>
      </div>
    </div>
    <p class="footer-copy">© 2026 TechnoFunda · Automated daily RS Momentum analysis · Data is delayed end-of-day · Not financial advice</p>
  </footer>
</div>

<a href="#feedback" class="fb-float-home" title="Share feedback or suggestions">💬 Feedback</a>

<script>
const MARKETS = {markets_js};
const TICKERS = [
  {{sym:"S&P 500",price:"7,609",chg:"+0.13%"}},
  {{sym:"NASDAQ",price:"30,660",chg:"+0.48%"}},
  {{sym:"NIFTY 50",price:"24,718",chg:"+0.42%"}},
  {{sym:"GOLD",price:"$4,504",chg:"+0.64%"}},
  {{sym:"WTI OIL",price:"$94.85",chg:"+2.92%"}},
  {{sym:"DOW",price:"51,307",chg:"+0.45%"}},
  {{sym:"RUSSELL",price:"2,931",chg:"+0.90%"}},
  {{sym:"VIX",price:"15.77",chg:"-1.74%"}},
  {{sym:"EUR/USD",price:"1.1597",chg:"-0.01%"}},
  {{sym:"DXY",price:"99.22",chg:"+0.02%"}},
  {{sym:"10Y YIELD",price:"4.45%",chg:"-0.45%"}},
  {{sym:"SILVER",price:"$75.00",chg:"-0.01%"}},
];
const MOOD={{
  bull:{{label:"Bullish 🟢",cls:"mood-bull",strip:"strip-bull"}},
  bear:{{label:"Bearish 🔴",cls:"mood-bear",strip:"strip-bear"}},
  mixed:{{label:"Mixed ⚠️",cls:"mood-mixed",strip:"strip-mixed"}},
  coming:{{label:"Coming Soon",cls:"mood-coming",strip:"strip-coming"}},
}};
function buildTicker(){{
  const all=[...TICKERS,...TICKERS];
  return all.map(t=>{{
    const c=t.chg.startsWith('+')?'pos':t.chg.startsWith('-')?'neg':'';
    return `<div class="ticker-item"><span class="ticker-sym">${{t.sym}}</span><span class="ticker-price">${{t.price}}</span><span class="ticker-chg ${{c}}">${{t.chg}}</span><div class="ticker-dot"></div></div>`;
  }}).join('');
}}
function buildSectors(s){{
  if(!s||!s.length) return '';
  const rows=s.map(x=>{{
    const w=Math.min(Math.abs(parseFloat(x.pct))*4,100);
    return `<div class="cc-sec-row"><span class="cc-sec-name">${{x.name}}</span><div class="cc-sec-bar-track"><div class="cc-sec-bar-fill ${{x.dir==='pos'?'bar-pos':'bar-neg'}}" style="width:${{w}}%"></div></div><span class="cc-sec-pct ${{x.dir==='pos'?'pos':'neg'}}">${{x.pct}}%</span></div>`;
  }}).join('');
  return `<div class="cc-sectors-label">Top / Bottom Sectors</div><div class="cc-sector-rows">${{rows}}</div>`;
}}
function buildSignals(s){{
  const p=[];
  if(s.prime>0)p.push(`<div class="sig-pill sig-prime">🌟 ${{s.prime}} Prime</div>`);
  if(s.conf>0) p.push(`<div class="sig-pill sig-conf">✅ ${{s.conf}} Confirmed</div>`);
  if(s.rs>0)   p.push(`<div class="sig-pill sig-rs">📈 ${{s.rs}} RS Bullish</div>`);
  return p.join('');
}}
function buildCards(){{
  return MARKETS.map((m,i)=>{{
    const mood=MOOD[m.mood];
    const isLive=m.status==='live';
    const delays=['delay-1','delay-2','delay-3','delay-4','delay-5','delay-6'];
    const d=delays[Math.min(i,5)];
    const chgIsPos=!m.index_chg.startsWith('-')&&m.index_chg!=='—';
    const chgCls=m.index_chg==='—'?'':(chgIsPos?'pos':'neg');
    const chgPfx=chgIsPos&&m.index_chg!=='—'?'+':'';
    const total=m.signals.prime+m.signals.conf+m.signals.rs;
    const overlay=!isLive?`<div class="cc-coming-overlay"><span class="cc-coming-text">⏳ Launching Soon</span><span class="cc-coming-eta">Add Google Sheet URL to activate</span></div>`:'';
    const cta=isLive?`<a href="${{m.url}}" class="btn-report">Open Report →</a>`:`<span class="btn-coming">Coming Soon</span>`;
    return `<div class="country-card ${{isLive?'active-card':'inactive-card'}} animate-in ${{d}}" onclick="${{isLive?`window.location='${{m.url}}'`:''}}"><div class="cc-strip ${{mood.strip}}"></div><div class="cc-body"><div class="cc-header"><div class="cc-country"><span class="cc-flag">${{m.flag}}</span><div class="cc-name-wrap"><span class="cc-name">${{m.name}}</span><span class="cc-exchange">${{m.exchange}}</span></div></div><div class="cc-mood"><span class="cc-mood-badge ${{mood.cls}}">${{mood.label}}</span><span class="cc-updated">${{m.updated}}</span></div></div>${{isLive?`<div class="cc-signals">${{buildSignals(m.signals)}}</div>`:''}}<div class="cc-metrics"><div class="cc-metric"><span class="cc-metric-label">${{m.index_name}}</span><span class="cc-metric-value">${{m.index_price}}</span><span class="cc-metric-sub ${{chgCls}}">${{chgPfx}}${{m.index_chg}}${{m.index_chg!=='—'?'%':''}} today</span></div><div class="cc-metric"><span class="cc-metric-label">Universe</span><span class="cc-metric-value">${{m.universe.toLocaleString()}}</span><span class="cc-metric-sub">stocks tracked</span></div></div>${{isLive?buildSectors(m.top_sectors):''}}<div class="cc-cta"><span class="cc-universe">${{isLive?`${{total}} opportunities`:'Not yet configured'}}</span>${{cta}}</div></div>${{overlay}}</div>`;
  }}).join('');
}}
document.addEventListener('DOMContentLoaded',()=>{{
  document.getElementById('ticker').innerHTML=buildTicker();
  document.getElementById('countries-grid').innerHTML=buildCards();
  // Append visitor local time next to UTC generated time
  (function(){{
    const el=document.getElementById('gen-time-label');
    if(!el)return;
    try{{
      const utcStr=el.dataset.utc.replace(/\s+/g,' ').trim();
      const d=new Date(utcStr+' UTC');
      if(isNaN(d))return;
      const offsetMins=-d.getTimezoneOffset();
      if(offsetMins===0)return;
      const local=d.toLocaleString(undefined,{{
        day:'2-digit',month:'short',year:'numeric',
        hour:'2-digit',minute:'2-digit',timeZoneName:'short'
      }});
      el.innerHTML+=' <span style="opacity:.65;font-size:11px;">('+local+')</span>';
    }}catch(e){{}}
  }})();
}});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n✅ Homepage written → {output_path}  ({size_kb:.1f} KB)")
    print(f"   Markets: {len(markets)} | Live: {len(live)} | Prime setups: {total_prime}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Determine the repo root directory
    script_dir = Path(__file__).parent.resolve()

    # Allow overriding repo root via CLI arg: python build_index.py /path/to/repo
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else script_dir

    print(f"\n{'═'*60}")
    print("  TechnoFunda Homepage Builder")
    print(f"  Repo root: {repo_root}")
    print(f"  Time:      {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'═'*60}\n")

    # Parse each country's HTML
    market_data = []
    for country in COUNTRIES:
        html_path = repo_root / country["html_file"]
        data = parse_country_html(str(html_path), country)
        market_data.append(data)

    # Generate homepage
    output_path = repo_root / "index.html"
    render_homepage(market_data, str(output_path))
    print(f"{'═'*60}\n")
