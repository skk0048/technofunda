# ─────────────────────────────────────────────────────────────────────────────
#  CHART PATTERNS  v6.1
#  Patterns: Double Bottom/Top, H&S Top, Inv H&S, VCP, Cup&Handle,
#            Asc/Desc/Sym Triangle, Bull Flag, Pennant
#  Timeframes: Daily (D) + Weekly (W)
#
#  Changes from v6.0 — see CHANGELOG at bottom of file.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Pattern dataclass
#    atr        — 14-period ATR at signal date (context for stop sizing)
#    trend_ok   — whether prior trend context is confirmed (True/False)
#    conf_score — NEW v6.1: numeric 0-100 confidence (downstream scoring uses
#                 this; the `confidence` string remains for display only).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Pattern:
    symbol:    str
    pattern:   str
    direction: str
    date:      str
    entry:     float
    stop:      float
    target:    float
    rr:        float
    confidence: str
    notes:     str       = ""
    timeframe: str       = "D"
    atr:       float     = 0.0    # 14-period ATR at signal bar
    trend_ok:  bool      = False  # prior-trend context confirmed
    conf_score: float    = 0.0    # NEW v6.1: numeric confidence 0-100


# ─────────────────────────────────────────────────────────────────────────────
#  Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _near(a: float, b: float, tol: float = 0.03) -> bool:
    """True if a and b are within `tol` of each other (ratio-based).
    Uses the larger absolute value as denominator to handle asymmetry.
    Safe for zero: denominator floored at 1e-9.
    """
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= tol


def _atr14(high: np.ndarray, low: np.ndarray, close: np.ndarray,
           end_idx: int, period: int = 14) -> float:
    """Compute a simple `period`-bar ATR ending at end_idx (inclusive).
    Returns 0.0 if there is not enough data.
    """
    start = max(0, end_idx - period)
    h = high[start: end_idx + 1]
    l = low[start:  end_idx + 1]
    c = close[start: end_idx + 1]
    if len(h) < 2:
        return 0.0
    prev_c = c[:-1]
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(np.abs(h[1:] - prev_c),
                    np.abs(l[1:] - prev_c)))
    return float(np.mean(tr)) if len(tr) > 0 else 0.0


def _slope(arr: np.ndarray) -> float:
    """Return the normalised linear-regression slope of arr.
    Normalised = slope / mean(arr), so it is scale-independent.
    """
    if len(arr) < 2:
        return 0.0
    x = np.arange(len(arr), dtype=float)
    slope = float(np.polyfit(x, arr, 1)[0])
    mean  = float(np.mean(arr))
    return slope / mean if abs(mean) > 1e-9 else 0.0


def _is_uptrend(close: np.ndarray, end_idx: int,
                lookback: int = 60, min_gain: float = 0.10) -> bool:
    """True if price gained at least min_gain over `lookback` bars ending at
    end_idx.  Used to confirm prior trend before bearish patterns.
    """
    start = max(0, end_idx - lookback)
    if end_idx <= start:
        return False
    gain = (close[end_idx] - close[start]) / max(abs(close[start]), 1e-9)
    return gain >= min_gain


def _is_downtrend(close: np.ndarray, end_idx: int,
                  lookback: int = 60, min_loss: float = 0.10) -> bool:
    """True if price fell at least min_loss over `lookback` bars ending at
    end_idx.  Used to confirm prior trend before bullish patterns.
    """
    start = max(0, end_idx - lookback)
    if end_idx <= start:
        return False
    loss = (close[start] - close[end_idx]) / max(abs(close[start]), 1e-9)
    return loss >= min_loss


def _monotone_rise(vals: np.ndarray, slack: int = 1) -> bool:
    """True if vals is generally rising with at most `slack` violations."""
    violations = sum(1 for i in range(len(vals) - 1) if vals[i + 1] <= vals[i])
    return violations <= slack


def _monotone_fall(vals: np.ndarray, slack: int = 1) -> bool:
    """True if vals is generally falling with at most `slack` violations."""
    violations = sum(1 for i in range(len(vals) - 1) if vals[i + 1] >= vals[i])
    return violations <= slack


def _dedupe_plateau(idx: np.ndarray, values: np.ndarray,
                    want_max: bool) -> np.ndarray:
    """Collapse runs of adjacent extrema indices (plateaus) to a single point.

    argrelextrema with `greater_equal`/`less_equal` flags every member of a
    flat top/bottom; argrelextrema with strict `greater`/`less` misses flat
    extrema entirely.  We use the non-strict comparator (so flats are caught)
    and collapse each consecutive run to its most extreme member here.
    """
    if len(idx) == 0:
        return idx
    keep: List[int] = []
    run = [int(idx[0])]
    for k in range(1, len(idx)):
        if int(idx[k]) == run[-1] + 1:        # still inside the same plateau
            run.append(int(idx[k]))
        else:
            vals = values[run]
            pick = run[int(np.argmax(vals))] if want_max else run[int(np.argmin(vals))]
            keep.append(pick)
            run = [int(idx[k])]
    vals = values[run]
    pick = run[int(np.argmax(vals))] if want_max else run[int(np.argmin(vals))]
    keep.append(pick)
    return np.array(keep, dtype=int)


# ─────────────────────────────────────────────────────────────────────────────
#  Weekly resampling
# ─────────────────────────────────────────────────────────────────────────────

def _resample_ohlcv_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Resample a daily OHLCV DataFrame to weekly (Friday close)."""
    try:
        odf = df.copy()

        # Normalise index to DatetimeIndex
        if not isinstance(odf.index, pd.DatetimeIndex):
            odf.index = pd.to_datetime(odf.index, errors='coerce')
            odf = odf[~odf.index.isna()]

        # Strip timezone to avoid resample errors
        if odf.index.tz is not None:
            odf.index = odf.index.tz_localize(None)

        if odf.empty or 'Close' not in odf.columns:
            return pd.DataFrame()

        agg: Dict[str, str] = {}
        for col, func in [('Open', 'first'), ('High', 'max'),
                          ('Low', 'min'), ('Close', 'last'), ('Volume', 'sum')]:
            if col in odf.columns:
                agg[col] = func

        w = odf.resample('W-FRI').agg(agg).dropna(subset=['Close'])
        w.index.name = 'Date'
        return w

    except Exception as exc:
        logger.warning("Weekly resample failed: %s", exc)
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
#  Confidence scoring
# ─────────────────────────────────────────────────────────────────────────────

_CONF_BASE = {"HIGH": 72.0, "MEDIUM": 52.0, "LOW": 35.0}


def _conf_score(conf: str, trend_ok: bool, rr: float,
                vol_confirmed: Optional[bool]) -> float:
    """Map the qualitative inputs to a 0-100 numeric confidence.

    The downstream quality gate (market_engine._pattern_quality) consumes this
    numeric value.  Components:
      • base        from the detector's HIGH/MEDIUM/LOW label
      • +10         prior-trend context confirmed
      • up to +12   reward:risk (scaled, capped at 3R)
      • ±8          breakout volume confirmation (True/False); 0 if unknown
    """
    s = _CONF_BASE.get(str(conf).upper(), 50.0)
    if trend_ok:
        s += 10.0
    s += min(max(rr, 0.0), 3.0) / 3.0 * 12.0
    if vol_confirmed is True:
        s += 8.0
    elif vol_confirmed is False:
        s -= 8.0
    return round(min(100.0, max(0.0, s)), 1)


# ─────────────────────────────────────────────────────────────────────────────
#  Core detection function
# ─────────────────────────────────────────────────────────────────────────────

def detect_patterns(df: pd.DataFrame, sym: str,
                    timeframe: str = 'D') -> List[Pattern]:
    """
    Detect chart patterns on a single symbol's OHLCV DataFrame.

    Parameters
    ----------
    df        : OHLCV DataFrame with DatetimeIndex (or named date index/column).
    sym       : Ticker symbol string.
    timeframe : 'D' for daily, 'W' for weekly.

    Returns
    -------
    List of Pattern objects (deduplicated within timeframe).
    """
    look_back = 180 if timeframe == 'D' else 130
    df = df.tail(look_back).copy()

    # ── Normalise to RangeIndex, extract date column ─────────────────────────
    if isinstance(df.index, pd.DatetimeIndex):
        df.index.name = 'Date'
        df = df.reset_index()           # → 'Date' column + RangeIndex
    elif not isinstance(df.index, pd.RangeIndex):
        idx_name = df.index.name or 'Date'
        df.index.name = idx_name
        df = df.reset_index()

    if len(df) < 40:
        return []

    # ── Locate date column (robust, checks dtype + known names) ─────────────
    _date_col: Optional[str] = None
    _skip = {'Open', 'High', 'Low', 'Close', 'Volume',
             'open', 'high', 'low', 'close', 'volume'}
    for _c in df.columns:
        if _c in _skip:
            continue
        if str(_c).lower() in ('date', 'datetime', 'timestamp'):
            _date_col = _c
            break
        if pd.api.types.is_datetime64_any_dtype(df[_c]):
            _date_col = _c
            break
    if _date_col is None:
        for _c in df.columns:
            if _c not in _skip and not pd.api.types.is_numeric_dtype(df[_c]):
                _date_col = _c
                break

    def _date(i: int) -> str:
        """Return YYYY-MM-DD string for row i, clamped to valid range."""
        i = min(max(i, 0), len(df) - 1)
        try:
            val = df.iloc[i][_date_col] if _date_col else df.index[i]
            return str(val)[:10]
        except Exception:
            return ""

    # ── Extract numpy arrays ─────────────────────────────────────────────────
    close  = df["Close"].values.astype(float)
    high   = df["High"].values.astype(float)  if "High"   in df.columns else close.copy()
    low    = df["Low"].values.astype(float)   if "Low"    in df.columns else close.copy()
    volume = df["Volume"].values.astype(float) if "Volume" in df.columns else np.zeros(len(close))
    n      = len(close)
    has_vol = bool(np.any(volume > 0))

    # ── Local extrema (plateau-collapsed) ────────────────────────────────────
    order = 4 if timeframe == 'W' else 5
    hi = argrelextrema(high, np.greater_equal, order=order)[0]
    lo = argrelextrema(low,  np.less_equal,    order=order)[0]
    hi = _dedupe_plateau(hi, high, want_max=True)
    lo = _dedupe_plateau(lo, low,  want_max=False)

    sigs: List[Pattern] = []

    # ── ATR-adaptive tolerance ───────────────────────────────────────────────
    _last_atr = _atr14(high, low, close, n - 1, period=20)
    _last_px  = close[-1] if close[-1] > 0 else 1.0
    _atr_pct  = _last_atr / _last_px
    _sim_tol  = float(np.clip(_atr_pct * 1.5, 0.02, 0.06))   # similarity tolerance
    _tight_tol = float(np.clip(_atr_pct * 1.0, 0.015, 0.04))  # tighter check

    # ── Breakout / volume confirmation helpers ───────────────────────────────
    def _breakout(level: float, bull: bool, start: int,
                  horizon: int = 45, buf: float = 0.003) -> Optional[int]:
        """First bar after `start` whose CLOSE breaks `level` (with buffer).
        Returns the breakout bar index, or None if no breakout within horizon.
        """
        end_j = min(n - 1, start + horizon)
        for j in range(start + 1, end_j + 1):
            if bull and close[j] > level * (1 + buf):
                return j
            if (not bull) and close[j] < level * (1 - buf):
                return j
        return None

    def _vol_confirm(j: int, lookback: int = 20) -> Optional[bool]:
        """True if volume at bar j expanded vs the prior `lookback` average.
        Returns None when volume data is unavailable (so it stays neutral).
        """
        if not has_vol:
            return None
        a = max(0, j - lookback)
        if j <= a:
            return None
        base = float(volume[a:j].mean())
        if base <= 0:
            return None
        return bool(volume[j] > base * 1.2)

    def _resolve_entry(level: float, bull: bool, pivot: int
                       ) -> Optional[Tuple[int, str, Optional[bool]]]:
        """Decide the actionable entry bar for a level-breakout pattern.

        Returns (entry_idx, confidence, vol_confirmed) or None to skip.
          • Confirmed breakout (close crossed level)  → entry = breakout bar,
            confidence HIGH, volume checked at that bar.
          • Still forming, price within tolerance of the level → entry = last
            bar, confidence MEDIUM, volume unknown.
          • Pattern never broke out and price has drifted away → skip (stale).
        """
        b = _breakout(level, bull, pivot)
        if b is not None:
            return b, "HIGH", _vol_confirm(b)
        if abs(close[-1] - level) / max(abs(level), 1e-9) <= _sim_tol:
            return n - 1, "MEDIUM", None
        return None

    def _add(pat: str, dir_: str, ei: int,
             e: float, sl: float, tgt: float,
             conf: str, notes: str = "", trend_ok: bool = False,
             min_rr: float = 1.5, risk_cap: bool = False,
             vol_confirmed: Optional[bool] = None) -> None:
        """Append a Pattern if its reward:risk clears `min_rr`.

        risk_cap=True (used for reversal patterns whose textbook
        measured-move target only yields ~1R against a stop beyond the
        pattern extreme): instead of rejecting, tighten the stop toward
        entry so the setup meets `min_rr` exactly.  The tightened stop is
        never moved past the entry, and the adjustment is noted.
        """
        e = float(e); sl = float(sl); tgt = float(tgt)
        reward = abs(tgt - e)
        risk   = abs(e - sl)
        if reward <= 0:
            return
        if risk < 1e-9:
            return
        rr = reward / risk
        if rr < min_rr:
            if risk_cap:
                new_risk = reward / min_rr
                sl = e - new_risk if dir_ == "BULLISH" else e + new_risk
                risk = new_risk
                rr = min_rr
                notes = (notes + " | risk-capped stop").strip(" |")
            else:
                return
        atr = _atr14(high, low, close, ei)
        cscore = _conf_score(conf, trend_ok, rr, vol_confirmed)
        sigs.append(Pattern(
            sym, pat, dir_, _date(ei),
            round(e, 4), round(sl, 4), round(tgt, 4), round(rr, 2),
            conf, notes, timeframe, round(atr, 4), trend_ok, cscore
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # 1. DOUBLE BOTTOM (Bullish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(lo) - 1):
        l1, l2 = lo[i], lo[i + 1]
        if not (8 <= l2 - l1 <= 120):
            continue
        p1, p2 = low[l1], low[l2]
        if not _near(p1, p2, _sim_tol + 0.01):
            continue
        neck = float(high[l1:l2 + 1].max())
        pattern_height = neck - min(p1, p2)
        if pattern_height / max(neck, 1e-9) < 0.05:
            continue
        res = _resolve_entry(neck, True, l2)
        if res is None:
            continue
        ei, conf, vol = res
        trend_ok = _is_downtrend(close, l1, lookback=80)
        _add("Double Bottom", "BULLISH", ei,
             neck * 1.005, min(p1, p2) * 0.99,
             neck + pattern_height,
             conf, f"Neck≈{neck:.2f} Depth={pattern_height/neck:.1%}",
             trend_ok, min_rr=1.5, risk_cap=True, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. DOUBLE TOP (Bearish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(hi) - 1):
        h1, h2 = hi[i], hi[i + 1]
        if not (8 <= h2 - h1 <= 120):
            continue
        p1, p2 = high[h1], high[h2]
        if not _near(p1, p2, _sim_tol + 0.01):
            continue
        neck = float(low[h1:h2 + 1].min())
        pattern_height = max(p1, p2) - neck
        if pattern_height / max(max(p1, p2), 1e-9) < 0.05:
            continue
        res = _resolve_entry(neck, False, h2)
        if res is None:
            continue
        ei, conf, vol = res
        trend_ok = _is_uptrend(close, h1, lookback=80)
        _add("Double Top", "BEARISH", ei,
             neck * 0.995, max(p1, p2) * 1.01,
             neck - pattern_height,
             conf, f"Neck≈{neck:.2f} Depth={pattern_height/max(p1,p2):.1%}",
             trend_ok, min_rr=1.5, risk_cap=True, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. HEAD & SHOULDERS TOP (Bearish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(hi) - 2):
        ls, lh, lr = hi[i], hi[i + 1], hi[i + 2]
        if not (8 <= lh - ls <= 80 and 8 <= lr - lh <= 80):
            continue
        if not (10 <= lr - ls <= 160):
            continue
        slp, head, srp = high[ls], high[lh], high[lr]
        if not (head > slp and head > srp):
            continue
        if not _near(slp, srp, 0.09):
            continue
        head_prominence = head - max(slp, srp)
        if head_prominence / max(head, 1e-9) < 0.03:
            continue
        neck_l = float(low[ls:lh + 1].min())
        neck_r = float(low[lh:lr + 1].min())
        # Neckline must be roughly horizontal (steeply tilted necklines distort
        # the measured target — keep the tilt under ~8%).
        if not _near(neck_l, neck_r, 0.08):
            continue
        neck = (neck_l + neck_r) / 2
        if neck <= 0:
            continue
        if (head - neck) / max(head, 1e-9) < 0.05:
            continue
        res = _resolve_entry(neck, False, lr)
        if res is None:
            continue
        ei, conf, vol = res
        trend_ok = _is_uptrend(close, ls, lookback=80)
        _add("H&S Top", "BEARISH", ei,
             neck * 0.995, head * 1.01,
             neck - (head - neck),
             conf, f"Head={head:.2f} Prom={head_prominence/head:.1%}",
             trend_ok, min_rr=1.5, risk_cap=True, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. INVERSE HEAD & SHOULDERS (Bullish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(lo) - 2):
        ls, lh, lr = lo[i], lo[i + 1], lo[i + 2]
        if not (8 <= lh - ls <= 80 and 8 <= lr - lh <= 80):
            continue
        if not (10 <= lr - ls <= 160):
            continue
        slp, head, srp = low[ls], low[lh], low[lr]
        if not (head < slp and head < srp):
            continue
        if not _near(slp, srp, 0.09):
            continue
        head_depth = min(slp, srp) - head
        if head_depth / max(min(slp, srp), 1e-9) < 0.03:
            continue
        neck_l = float(high[ls:lh + 1].max())
        neck_r = float(high[lh:lr + 1].max())
        if not _near(neck_l, neck_r, 0.08):
            continue
        neck = (neck_l + neck_r) / 2
        if (neck - head) / max(neck, 1e-9) < 0.05:
            continue
        res = _resolve_entry(neck, True, lr)
        if res is None:
            continue
        ei, conf, vol = res
        trend_ok = _is_downtrend(close, ls, lookback=80)
        _add("Inv H&S", "BULLISH", ei,
             neck * 1.005, head * 0.99,
             neck + (neck - head),
             conf, f"Head={head:.2f} Depth={head_depth/min(slp,srp):.1%}",
             trend_ok, min_rr=1.5, risk_cap=True, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. VCP — Volatility Contraction Pattern (Bullish)
    #    Iterate newest→oldest and stop at the first qualifying setup so we
    #    report the most recent contraction (and avoid O(n) duplicate work).
    # ─────────────────────────────────────────────────────────────────────────
    win = 60 if timeframe == 'D' else 30
    q   = max(1, win // 4)

    for end in range(n - 1, win - 1, -1):
        seg_h = high[end - win: end + 1]
        seg_l = low[end - win:  end + 1]
        seg_v = volume[end - win: end + 1]

        sw: List[float] = []
        vq: List[float] = []
        for qi in range(4):
            slc_h = seg_h[qi * q: (qi + 1) * q]
            slc_l = seg_l[qi * q: (qi + 1) * q]
            slc_v = seg_v[qi * q: (qi + 1) * q]
            if len(slc_h) == 0:
                continue
            sw.append(float(slc_h.max()) - float(slc_l.min()))
            vq.append(float(slc_v.mean()) if len(slc_v) > 0 else 0.0)

        if len(sw) < 4:
            continue
        if not all(sw[j] > sw[j + 1] for j in range(len(sw) - 1)):
            continue

        # Volume should also dry up across the base (Minervini: lowest volume
        # in the final contraction).  Allow 20% slack.
        vol_contracting = (not has_vol) or len(vq) < 2 or vq[-1] < vq[0] * 1.2

        res_lvl = float(seg_h.max())
        bl      = float(seg_l.min())
        sl_b    = float(seg_l[-q:].min())

        trend_ok = _is_uptrend(close, end - win, lookback=60, min_gain=0.10)
        vol = _vol_confirm(end) if vol_contracting else False

        notes = "Vol dry-up" + ("" if vol_contracting else " [vol not contracting]")
        conf  = "HIGH" if (trend_ok and vol_contracting) else "MEDIUM"
        before = len(sigs)
        _add("VCP", "BULLISH", end,
             res_lvl * 1.005, sl_b * 0.99,
             res_lvl * 1.005 + (res_lvl - bl) * 0.75,
             conf, notes, trend_ok, vol_confirmed=vol)
        if len(sigs) > before:
            break

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CUP & HANDLE (Bullish)
    # ─────────────────────────────────────────────────────────────────────────
    min_cup = 20 if timeframe == 'D' else 10
    max_cup = 120 if timeframe == 'D' else 60

    for i in range(len(hi) - 1):
        l, r = hi[i], hi[i + 1]
        if not (min_cup <= r - l <= max_cup):
            continue
        tl = float(high[l])
        tr = float(high[r])
        if not _near(tl, tr, 0.07):     # rims must be similar height
            continue
        bot   = float(low[l: r + 1].min())
        depth = (tl - bot) / max(tl, 1e-9)
        if not (0.10 <= depth <= 0.50):  # cup 10–50 % deep
            continue

        # Rounded-bottom check: the deepest point should sit in the middle
        # third of the cup, not at an edge (which would make it a V or a
        # descending wedge rather than a cup).  Soft — downgrades confidence.
        bot_idx = l + int(np.argmin(low[l: r + 1]))
        span = max(r - l, 1)
        rounded = (l + span / 3) <= bot_idx <= (r - span / 3)

        if r + 3 >= n:
            continue
        handle_end = min(r + 15, n - 1)
        handle_low = float(low[r: handle_end + 1].min())
        handle_retrace = (tr - handle_low) / max(tr, 1e-9)

        if handle_retrace > 0.15:        # handle retraces more than 15 % — too deep
            continue
        handle_slope = _slope(close[r: handle_end + 1])
        if handle_slope > 0.003:         # a real handle is flat or drifts down
            continue

        res = _resolve_entry(tr, True, handle_end)
        if res is None:
            continue
        ei, conf, vol = res
        if not rounded and conf == "HIGH":
            conf = "MEDIUM"
        trend_ok = _is_uptrend(close, l, lookback=80)
        _add("Cup & Handle", "BULLISH", ei,
             tr * 1.005, handle_low * 0.99,
             tr * 1.005 + (tr - bot),
             conf, f"Depth={depth:.1%} HandleRetrace={handle_retrace:.1%}"
                   + ("" if rounded else " [shallow round]"),
             trend_ok, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. ASCENDING TRIANGLE (Bullish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(hi) - 1):
        h1, h2 = hi[i], hi[i + 1]
        if not (12 <= h2 - h1 <= 80):
            continue
        p1h, p2h = high[h1], high[h2]
        if not _near(p1h, p2h, _tight_tol):   # flat resistance
            continue
        lo_in = lo[(lo >= h1) & (lo <= h2)]
        if len(lo_in) < 2:
            continue
        lo_vals = low[lo_in]
        if not _monotone_rise(lo_vals, slack=1):
            continue
        if (lo_vals[-1] - lo_vals[0]) / max(lo_vals[0], 1e-9) < 0.015:
            continue
        resistance = (p1h + p2h) / 2
        res = _resolve_entry(resistance, True, h2)
        if res is None:
            continue
        ei, conf, vol = res
        conf = "HIGH" if (conf == "HIGH") else "MEDIUM"
        trend_ok = _is_uptrend(close, h1, lookback=60, min_gain=0.05)
        _add("Asc Triangle", "BULLISH", ei,
             resistance * 1.005, lo_vals[-1] * 0.99,
             resistance + (resistance - lo_vals[0]),
             conf, f"Res≈{resistance:.2f}", trend_ok, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. DESCENDING TRIANGLE (Bearish)
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(lo) - 1):
        l1, l2 = lo[i], lo[i + 1]
        if not (12 <= l2 - l1 <= 80):
            continue
        p1l, p2l = low[l1], low[l2]
        if not _near(p1l, p2l, _tight_tol):
            continue
        hi_in = hi[(hi >= l1) & (hi <= l2)]
        if len(hi_in) < 2:
            continue
        hi_vals = high[hi_in]
        if not _monotone_fall(hi_vals, slack=1):
            continue
        if (hi_vals[0] - hi_vals[-1]) / max(hi_vals[0], 1e-9) < 0.015:
            continue
        support = (p1l + p2l) / 2
        res = _resolve_entry(support, False, l2)
        if res is None:
            continue
        ei, conf, vol = res
        conf = "HIGH" if (conf == "HIGH") else "MEDIUM"
        trend_ok = _is_downtrend(close, l1, lookback=60, min_loss=0.05)
        _add("Desc Triangle", "BEARISH", ei,
             support * 0.995, hi_vals[0] * 1.01,
             support - (hi_vals[0] - support),
             conf, f"Sup≈{support:.2f}", trend_ok, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 9. SYMMETRICAL TRIANGLE (direction follows the prior trend)
    #    Triangles are continuation patterns: ~75% resolve in the direction of
    #    the prevailing trend.  We bias direction by prior trend and require a
    #    confirming breakout through the relevant boundary.
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(hi) - 1):
        h1, h2 = hi[i], hi[i + 1]
        if not (15 <= h2 - h1 <= 80):
            continue
        lo_in = lo[(lo >= h1) & (lo <= h2)]
        if len(lo_in) < 2:
            continue
        l1_i, l2_i = lo_in[0], lo_in[-1]
        p1h, p2h = high[h1], high[h2]
        p1l, p2l = low[l1_i], low[l2_i]
        if p2h >= p1h:    # highs must fall
            continue
        if p2l <= p1l:    # lows must rise
            continue
        fall = (p1h - p2h) / max(p1h, 1e-9)
        rise = (p2l - p1l) / max(p1l, 1e-9)
        if fall < 0.02 or rise < 0.02:   # both sides must converge meaningfully
            continue
        # Need at least one interior low between the two highs (a degenerate
        # 4-point box is not a triangle).  lo_in already has ≥2 members.
        height = p1h - p1l

        up = _is_uptrend(close, h1, lookback=60, min_gain=0.05)
        dn = _is_downtrend(close, h1, lookback=60, min_loss=0.05)
        if dn and not up:
            # Bearish continuation — break of the lower (rising) boundary.
            res = _resolve_entry(p2l, False, h2)
            if res is None:
                continue
            ei, conf, vol = res
            _add("Sym Triangle", "BEARISH", ei,
                 p2l * 0.995, p2h * 1.01,
                 p2l - height * 0.6,
                 conf, f"Converging Fall={fall:.1%} Rise={rise:.1%}",
                 dn, vol_confirmed=vol)
        else:
            # Bullish continuation (default) — break of the upper boundary.
            res = _resolve_entry(p2h, True, h2)
            if res is None:
                continue
            ei, conf, vol = res
            _add("Sym Triangle", "BULLISH", ei,
                 p2h * 1.005, p2l * 0.99,
                 p2h + height * 0.6,
                 conf, f"Converging Fall={fall:.1%} Rise={rise:.1%}",
                 up, vol_confirmed=vol)

    # ─────────────────────────────────────────────────────────────────────────
    # 10. BULL FLAG (Bullish) — newest→oldest, stop at first valid setup.
    # ─────────────────────────────────────────────────────────────────────────
    min_pole_pct = 7  if timeframe == 'D' else 10
    pole_lens    = [7, 10, 15] if timeframe == 'D' else [4, 6, 8]

    found_flag = False
    for pole_end in range(n - 5, 9, -1):
        if found_flag:
            break
        for pole_len in pole_lens:
            pole_start = pole_end - pole_len
            if pole_start < 0:
                continue
            pole_move = (close[pole_end] - close[pole_start]) / max(close[pole_start], 1e-9) * 100
            if pole_move < min_pole_pct:
                continue
            up_bars = sum(1 for k in range(pole_start, pole_end) if close[k + 1] > close[k])
            if up_bars < pole_len * 0.6:
                continue

            consol_len = min(15, n - pole_end - 1)
            if consol_len < 3:
                continue

            c_cl = close[pole_end: pole_end + consol_len + 1]
            c_hi = high[pole_end:  pole_end + consol_len + 1]
            c_lo = low[pole_end:   pole_end + consol_len + 1]
            c_vl = volume[pole_end: pole_end + consol_len + 1]
            p_vl = volume[pole_start: pole_end + 1]

            if (c_cl.max() - c_cl.min()) / max(c_cl[0], 1e-9) * 100 > pole_move * 0.45:
                continue
            if (close[pole_end] - c_lo.min()) > (close[pole_end] - close[pole_start]) * 0.5:
                continue

            slope_norm = float(np.polyfit(range(len(c_cl)), c_cl, 1)[0]) / max(c_cl[0], 1e-9)
            if not (-0.015 <= slope_norm <= 0.003):
                continue

            avg_flag_vol = float(c_vl.mean()) if len(c_vl) > 0 else 0.0
            avg_pole_vol = float(p_vl.mean()) if len(p_vl) > 0 else 0.0
            vol_ok = (not has_vol) or avg_pole_vol == 0 or (avg_flag_vol < avg_pole_vol * 1.1)

            before = len(sigs)
            _add("Bull Flag", "BULLISH", pole_end + consol_len,
                 c_hi.max() * 1.005, c_lo.min() * 0.99,
                 c_hi.max() * 1.005 + (close[pole_end] - close[pole_start]),
                 "HIGH" if vol_ok else "MEDIUM",
                 f"Pole:{pole_move:.1f}%", vol_confirmed=(None if not has_vol else vol_ok))
            if len(sigs) > before:
                found_flag = True
                break

    # ─────────────────────────────────────────────────────────────────────────
    # 11. PENNANT (Bullish) — newest→oldest, stop at first valid setup.
    # ─────────────────────────────────────────────────────────────────────────
    found_pennant = False
    for pole_end in range(n - 5, 9, -1):
        if found_pennant:
            break
        for pole_len in pole_lens:
            pole_start = pole_end - pole_len
            if pole_start < 0:
                continue
            pole_move = (close[pole_end] - close[pole_start]) / max(close[pole_start], 1e-9) * 100
            if pole_move < min_pole_pct:
                continue
            up_bars = sum(1 for k in range(pole_start, pole_end) if close[k + 1] > close[k])
            if up_bars < pole_len * 0.6:
                continue

            consol_len = min(12, n - pole_end - 1)
            if consol_len < 3:
                continue

            c_hi = high[pole_end:  pole_end + consol_len + 1]
            c_lo = low[pole_end:   pole_end + consol_len + 1]
            h_slope = float(np.polyfit(range(len(c_hi)), c_hi, 1)[0])
            l_slope = float(np.polyfit(range(len(c_lo)), c_lo, 1)[0])

            if h_slope >= 0 or l_slope <= 0:   # must converge
                continue
            if (c_hi.max() - c_lo.min()) / max(close[pole_end], 1e-9) * 100 > pole_move * 0.30:
                continue
            # Convergence must be meaningful relative to the pennant's own
            # height, not near-parallel.
            pennant_h = max(c_hi.max() - c_lo.min(), 1e-9)
            if abs(h_slope) + abs(l_slope) < pennant_h / max(len(c_hi), 1) * 0.15:
                continue

            before = len(sigs)
            _add("Pennant", "BULLISH", pole_end + consol_len,
                 c_hi[-1] * 1.005, c_lo[-1] * 0.99,
                 c_hi[-1] * 1.005 + (close[pole_end] - close[pole_start]) * 0.8,
                 "HIGH", f"Pole:{pole_move:.1f}%")
            if len(sigs) > before:
                found_pennant = True
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Deduplicate: keep most recent per (pattern, direction, timeframe)
    # ─────────────────────────────────────────────────────────────────────────
    seen: Dict[Tuple[str, str, str], Pattern] = {}
    for s in sigs:
        key = (s.pattern, s.direction, s.timeframe)
        if key not in seen or s.date > seen[key].date:
            seen[key] = s
    return list(seen.values())


# ─────────────────────────────────────────────────────────────────────────────
#  Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_pattern_detection(
    ohlcv_dict: Dict[str, pd.DataFrame]
) -> Tuple[Dict[str, List[Pattern]], List[Pattern]]:
    """
    Run chart pattern detection on DAILY + WEEKLY timeframes for all symbols.

    Parameters
    ----------
    ohlcv_dict : {symbol: OHLCV DataFrame with DatetimeIndex}

    Returns
    -------
    by_sym   : {symbol: [Pattern, ...]}
    all_pats : flat list of all Pattern objects
    """
    by_sym: Dict[str, List[Pattern]] = {}
    all_pats: List[Pattern] = []
    n = len(ohlcv_dict)
    errors: List[str] = []

    # ── Daily ────────────────────────────────────────────────────────────────
    logger.info("Detecting daily patterns (%d stocks)…", n)
    for i, (sym, df) in enumerate(ohlcv_dict.items()):
        if len(df) < 60:
            continue
        try:
            pats = detect_patterns(df, sym, timeframe='D')
            if pats:
                by_sym[sym] = pats
                all_pats.extend(pats)
        except Exception as exc:
            logger.warning("Daily pattern detection failed for %s: %s", sym, exc)
            errors.append(f"{sym}(D): {exc}")
        if (i + 1) % 100 == 0:
            logger.info("  …%d/%d (daily)", i + 1, n)

    # ── Weekly ───────────────────────────────────────────────────────────────
    logger.info("Detecting weekly patterns (%d stocks)…", n)
    for i, (sym, df) in enumerate(ohlcv_dict.items()):
        if len(df) < 60:
            continue
        try:
            w_df = _resample_ohlcv_weekly(df)
            if len(w_df) < 20:
                continue
            pats_w = detect_patterns(w_df, sym, timeframe='W')
            if pats_w:
                by_sym.setdefault(sym, []).extend(pats_w)
                all_pats.extend(pats_w)
        except Exception as exc:
            logger.warning("Weekly pattern detection failed for %s: %s", sym, exc)
            errors.append(f"{sym}(W): {exc}")
        if (i + 1) % 100 == 0:
            logger.info("  …%d/%d (weekly)", i + 1, n)

    bull  = sum(1 for p in all_pats if p.direction == "BULLISH")
    d_cnt = sum(1 for p in all_pats if p.timeframe == 'D')
    w_cnt = sum(1 for p in all_pats if p.timeframe == 'W')

    logger.info(
        "✅ Patterns:%d | %d Bullish | %d Bearish | Daily:%d | Weekly:%d | %d stocks",
        len(all_pats), bull, len(all_pats) - bull, d_cnt, w_cnt, len(by_sym)
    )
    if errors:
        logger.warning("%d symbols had errors during detection", len(errors))
        for e in errors[:20]:
            logger.debug("  Error: %s", e)

    return by_sym, all_pats


# ─────────────────────────────────────────────────────────────────────────────
#  CHANGELOG — v6.0 → v6.1
# ─────────────────────────────────────────────────────────────────────────────
"""
CRITICAL BUG FIXES
──────────────────
1. [CRITICAL] Reversal patterns (Double Bottom/Top, H&S, Inv H&S) could NEVER
   pass the R:R ≥ 1.5 gate.  Their textbook target is a 1× measured move
   (= pattern height) while the stop sits beyond the pattern extreme
   (≈ pattern height + entry/stop buffers), so R:R is mathematically < 1 in
   every case — these patterns were silently dropped 100% of the time.
   Fix: `_add(risk_cap=True)` for reversal patterns — instead of rejecting,
   the stop is tightened toward entry to meet the R:R floor (a legitimate,
   documented "price fell back into the pattern → invalidated" stop).  The
   stop is never moved past entry; the adjustment is noted in `notes`.

2. [CRITICAL] `confidence` was emitted only as a string ("HIGH"/"MEDIUM"),
   but the downstream gate (market_engine._pattern_quality) did
   `float(p.confidence)`, which always raised → confidence was ignored in
   scoring (treated as neutral 50).
   Fix: added numeric `Pattern.conf_score` (0-100) derived from the label,
   prior-trend context, R:R, and volume confirmation.  (market_engine should
   read `conf_score` instead of `float(confidence)` — see integration note.)

3. [MAJOR] No breakout confirmation — patterns were emitted dated at the
   pivot with an *assumed* entry that may never have occurred, so "fresh"
   signals could be stale formations price had long left behind.
   Fix: `_resolve_entry()` requires either a confirmed close-through-level
   breakout (→ entry dated at the breakout bar, HIGH confidence, volume
   checked) or price still within tolerance of the level (→ "forming",
   MEDIUM confidence).  Patterns that never broke out and drifted away are
   now skipped.  Applied to Double Bottom/Top, H&S, Inv H&S, Cup & Handle,
   Asc/Desc/Sym Triangle.

CORRECTNESS FIXES
─────────────────
4. [MAJOR] Symmetrical Triangle was hard-coded BULLISH.  Triangles are
   continuation patterns (~75% resolve with the prior trend).
   Fix: direction now follows the prior trend (uptrend→bullish break of the
   upper line, downtrend→bearish break of the lower line) with a confirming
   breakout, and a proper bearish entry/stop/target.

5. [MEDIUM] Extrema detection used `greater_equal`/`less_equal`, which tags
   every bar of a flat top/bottom as a separate pivot (plateau spam).
   Fix: `_dedupe_plateau()` collapses each flat run to its single most
   extreme bar (keeps flats, removes duplicates).

6. [MEDIUM] H&S / Inv H&S did not check neckline tilt — a steeply sloped
   neckline distorts the measured target.
   Fix: require the two neckline troughs/peaks to be within ~8%.

7. [LOW] Dead/no-op checks removed or made real:
   - Cup & Handle "jagged bottom" check was a `pass` (did nothing) → replaced
     with a real rounded-bottom test (deepest bar in the middle third);
     failing it downgrades confidence rather than rejecting.
   - Sym Triangle `n_pivots < 4` was always false (unreachable) → removed.
   - Pennant near-parallel guard divided by price (effectively never fired)
     → rewritten relative to the pennant's own height.

QUALITY / PERFORMANCE
─────────────────────
8. VCP / Bull Flag / Pennant now iterate newest→oldest and stop at the first
   qualifying setup, so they report the most recent formation and skip the
   redundant O(n) rescans that the final dedup discarded anyway.

9. Volume confirmation (`_vol_confirm`) folded into `conf_score` for all
   breakout patterns; gracefully neutral when volume data is absent.

10. Trend gain/loss and slope helpers hardened against negative/zero prices
    (abs() in denominators).

INTEGRATION NOTE (market_engine.py)
───────────────────────────────────
`_pattern_quality()` line ~1378 should change:
    conf = float(p.confidence)              # always throws on "HIGH"
to:
    conf = float(getattr(p, "conf_score", 0)) or _LABEL.get(str(p.confidence).upper(), 50)
so the numeric confidence is actually used.  Until then conf_score is still
emitted and harmless (the gate falls back to neutral as before).

UNCERTAIN / APPROXIMATE (unchanged from v6.0)
─────────────────────────────────────────────
- H&S neckline is the average of the two troughs, not a fitted line
  (acceptable for screening; tilt is now bounded to ≤8%).
- The 5–10% prior-trend thresholds are heuristics; callers may tune them.
- VCP quarter-swing method follows Minervini's heuristic, not a rigorous
  mathematical criterion; false positives in sideways markets are expected.
"""
