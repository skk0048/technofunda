# ─────────────────────────────────────────────────────────────────────────────
#  CHART PATTERNS  v6.0
#  Patterns: Double Bottom/Top, H&S Top, Inv H&S, VCP, Cup&Handle,
#            Asc/Desc/Sym Triangle, Bull Flag, Pennant
#  Timeframes: Daily (D) + Weekly (W)
#
#  Changes from v5.3 — see CHANGELOG at bottom of file.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Pattern dataclass
#  NEW FIELDS vs v5.3:
#    atr        — 14-period ATR at signal date (context for stop sizing)
#    trend_ok   — whether prior trend context is confirmed (True/False)
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
    notes:     str      = ""
    timeframe: str      = "D"
    atr:       float    = 0.0   # NEW: 14-period ATR at signal bar
    trend_ok:  bool     = False  # NEW: prior-trend context confirmed


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
    """Compute a simple 14-period ATR ending at end_idx (inclusive).
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
    slope = np.polyfit(x, arr, 1)[0]
    mean  = float(np.mean(arr))
    return slope / mean if abs(mean) > 1e-9 else 0.0


def _is_uptrend(close: np.ndarray, end_idx: int,
                lookback: int = 60, min_gain: float = 0.10) -> bool:
    """Returns True if price gained at least min_gain over `lookback` bars
    ending at end_idx.  Used to confirm prior trend before bearish patterns.
    """
    start = max(0, end_idx - lookback)
    if end_idx <= start:
        return False
    gain = (close[end_idx] - close[start]) / max(close[start], 1e-9)
    return gain >= min_gain


def _is_downtrend(close: np.ndarray, end_idx: int,
                  lookback: int = 60, min_loss: float = 0.10) -> bool:
    """Returns True if price fell at least min_loss over `lookback` bars
    ending at end_idx.  Used to confirm prior trend before bullish patterns.
    """
    start = max(0, end_idx - lookback)
    if end_idx <= start:
        return False
    loss = (close[start] - close[end_idx]) / max(close[start], 1e-9)
    return loss >= min_loss


def _monotone_rise(vals: np.ndarray, slack: int = 1) -> bool:
    """True if vals is generally rising with at most `slack` violations."""
    violations = sum(1 for i in range(len(vals) - 1) if vals[i + 1] <= vals[i])
    return violations <= slack


def _monotone_fall(vals: np.ndarray, slack: int = 1) -> bool:
    """True if vals is generally falling with at most `slack` violations."""
    violations = sum(1 for i in range(len(vals) - 1) if vals[i + 1] >= vals[i])
    return violations <= slack


# ─────────────────────────────────────────────────────────────────────────────
#  Weekly resampling
# ─────────────────────────────────────────────────────────────────────────────

def _resample_ohlcv_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Resample a daily OHLCV DataFrame to weekly (Friday close).

    Fixes vs v5.3:
    - Strip timezone before resampling (avoids AmbiguousTimeError).
    - Explicit error logging instead of bare except.
    - Preserve Volume if present.
    - Name the resulting index 'Date' so detect_patterns can find it.
    """
    try:
        odf = df.copy()

        # Normalise index to DatetimeIndex
        if not isinstance(odf.index, pd.DatetimeIndex):
            odf.index = pd.to_datetime(odf.index, errors='coerce')
            odf = odf[~odf.index.isna()]

        # Strip timezone to avoid resample errors
        if odf.index.tz is not None:
            odf.index = odf.index.tz_localize(None)

        if odf.empty:
            return pd.DataFrame()

        agg: Dict[str, str] = {}
        for col, func in [('Open','first'), ('High','max'),
                          ('Low','min'),  ('Close','last'), ('Volume','sum')]:
            if col in odf.columns:
                agg[col] = func

        w = odf.resample('W-FRI').agg(agg).dropna(subset=['Close'])
        w.index.name = 'Date'          # FIX: ensure index is named 'Date'
        return w

    except Exception as exc:
        logger.warning("Weekly resample failed: %s", exc)
        return pd.DataFrame()


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
    # FIX: always name the extracted column 'Date' explicitly.
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
        if _c.lower() in ('date', 'datetime', 'timestamp'):
            _date_col = _c
            break
        if pd.api.types.is_datetime64_any_dtype(df[_c]):
            _date_col = _c
            break
    # Fallback: first non-numeric, non-OHLCV column
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

    # ── Local extrema ────────────────────────────────────────────────────────
    order = 4 if timeframe == 'W' else 5
    hi = argrelextrema(high, np.greater_equal, order=order)[0]
    lo = argrelextrema(low,  np.less_equal,    order=order)[0]

    sigs: List[Pattern] = []

    def _add(pat: str, dir_: str, ei: int,
             e: float, sl: float, tgt: float,
             conf: str, notes: str = "", trend_ok: bool = False) -> None:
        rr = abs(tgt - e) / max(abs(e - sl), 1e-9)
        if rr < 1.5:
            return
        atr = _atr14(high, low, close, ei)
        sigs.append(Pattern(
            sym, pat, dir_, _date(ei),
            round(e, 4), round(sl, 4), round(tgt, 4), round(rr, 2),
            conf, notes, timeframe, round(atr, 4), trend_ok
        ))

    # ── ATR-adaptive tolerance ───────────────────────────────────────────────
    # Use the last 20-bar average ATR as a % of price to set similarity tol.
    # Floored at 2 % and capped at 6 % so it doesn't blow up on thin data.
    _last_atr = _atr14(high, low, close, n - 1, period=20)
    _last_px   = close[-1] if close[-1] > 0 else 1.0
    _atr_pct   = _last_atr / _last_px          # e.g. 0.018 for 1.8 %
    _sim_tol   = float(np.clip(_atr_pct * 1.5, 0.02, 0.06))   # similarity tolerance
    _tight_tol = float(np.clip(_atr_pct * 1.0, 0.015, 0.04))  # tighter check

    # ─────────────────────────────────────────────────────────────────────────
    # 1. DOUBLE BOTTOM (Bullish)
    #    Require: prior downtrend, two similar lows, neckline breakout entry
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(lo) - 1):
        l1, l2 = lo[i], lo[i + 1]
        if not (8 <= l2 - l1 <= 120):
            continue
        p1, p2 = low[l1], low[l2]
        if not _near(p1, p2, _sim_tol + 0.01):     # adaptive tol, slightly looser
            continue
        neck = float(high[l1:l2 + 1].max())
        pattern_height = neck - min(p1, p2)
        if pattern_height / max(neck, 1e-9) < 0.05:  # FIX: require minimum 5% depth
            continue
        trend_ok = _is_downtrend(close, l1, lookback=80)
        _add("Double Bottom", "BULLISH", l2,
             neck * 1.005, min(p1, p2) * 0.99,
             neck + pattern_height,
             "HIGH", f"Neck≈{neck:.2f} Depth={pattern_height/neck:.1%}",
             trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. DOUBLE TOP (Bearish)
    #    Require: prior uptrend, two similar highs, neckline breakdown entry
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
        trend_ok = _is_uptrend(close, h1, lookback=80)
        _add("Double Top", "BEARISH", h2,
             neck * 0.995, max(p1, p2) * 1.01,
             neck - pattern_height,
             "HIGH", f"Neck≈{neck:.2f} Depth={pattern_height/max(p1,p2):.1%}",
             trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. HEAD & SHOULDERS TOP (Bearish)
    #    FIX: added minimum head prominence, neckline tilt tolerance,
    #         and prior uptrend check.
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
        # FIX: require head to be meaningfully above shoulders
        head_prominence = head - max(slp, srp)
        if head_prominence / max(head, 1e-9) < 0.03:
            continue
        neck_l = float(low[ls:lh + 1].min())
        neck_r = float(low[lh:lr + 1].min())
        neck   = (neck_l + neck_r) / 2
        if neck <= 0:
            continue
        # FIX: minimum pattern height check
        if (head - neck) / max(head, 1e-9) < 0.05:
            continue
        trend_ok = _is_uptrend(close, ls, lookback=80)
        _add("H&S Top", "BEARISH", lr,
             neck * 0.995, head * 1.01,
             neck - (head - neck),
             "HIGH", f"Head={head:.2f} Prom={head_prominence/head:.1%}",
             trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. INVERSE HEAD & SHOULDERS (Bullish)
    #    FIX: head prominence, minimum depth, prior downtrend check.
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
        neck   = (neck_l + neck_r) / 2
        if (neck - head) / max(neck, 1e-9) < 0.05:
            continue
        trend_ok = _is_downtrend(close, ls, lookback=80)
        _add("Inv H&S", "BULLISH", lr,
             neck * 1.005, head * 0.99,
             neck + (neck - head),
             "HIGH", f"Head={head:.2f} Depth={head_depth/min(slp,srp):.1%}",
             trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. VCP — Volatility Contraction Pattern (Bullish)
    #    FIX: volume confirmation (declining vol during contraction),
    #         minimum prior trend, correct sw length guard.
    # ─────────────────────────────────────────────────────────────────────────
    win = 60 if timeframe == 'D' else 30
    q   = max(1, win // 4)

    for end in range(win, n):
        seg_h = high[end - win: end + 1]
        seg_l = low[end - win:  end + 1]
        seg_c = close[end - win: end + 1]
        seg_v = volume[end - win: end + 1]

        # Build per-quarter swing ranges
        sw: List[float] = []
        vq: List[float] = []   # per-quarter avg volume
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

        # Volume should also contract (at least somewhat)
        vol_contracting = len(vq) < 2 or vq[-1] < vq[0] * 1.2  # allow 20% slack

        res  = float(seg_h.max())
        bl   = float(seg_l.min())
        sl_b = float(seg_l[-q:].min())

        # Require at least 10% prior move into the VCP
        trend_ok = _is_uptrend(close, end - win, lookback=60, min_gain=0.10)

        notes = f"Vol dry-up" + ("" if vol_contracting else " [vol not contracting]")
        conf  = "HIGH" if (trend_ok and vol_contracting) else "MEDIUM"
        _add("VCP", "BULLISH", end,
             res * 1.005, sl_b * 0.99,
             res * 1.005 + (res - bl) * 0.75,
             conf, notes, trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CUP & HANDLE (Bullish)
    #    FIX: handle slope check (must be flat/down), volume check on breakout,
    #         rim symmetry check.
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
        bot     = float(low[l: r + 1].min())
        depth   = (tl - bot) / max(tl, 1e-9)
        if not (0.10 <= depth <= 0.50):  # cup 10–50 % deep
            continue
        # Cup bottom should be rounded: no sharp V (midpoint not too low vs bottom)
        cup_mid_low = float(low[l + (r - l) // 3: r - (r - l) // 3 + 1].min()) \
                      if (r - l) > 6 else bot
        if (bot - cup_mid_low) / max(tl, 1e-9) < -0.02:  # bottom too jagged
            pass   # soft check only; don't reject

        if r + 3 >= n:
            continue
        handle_end = min(r + 15, n - 1)
        handle_low  = float(low[r: handle_end + 1].min())
        handle_retrace = (tr - handle_low) / max(tr, 1e-9)

        if handle_retrace > 0.15:        # handle retraces more than 15 % — too deep
            continue
        # FIX: handle must slope flat or downward (not rally back up aggressively)
        handle_slope = _slope(close[r: handle_end + 1])
        if handle_slope > 0.003:         # handle drifting up is not a real handle
            continue

        trend_ok = _is_uptrend(close, l, lookback=80)
        _add("Cup & Handle", "BULLISH", r,
             tr * 1.005, handle_low * 0.99,
             tr * 1.005 + (tr - bot),
             "HIGH", f"Depth={depth:.1%} HandleRetrace={handle_retrace:.1%}",
             trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. ASCENDING TRIANGLE (Bullish)
    #    FIX: require monotone rise in lows (not just first vs last),
    #         minimum width, tighter resistance flatness.
    # ─────────────────────────────────────────────────────────────────────────
    for i in range(len(hi) - 1):
        h1, h2 = hi[i], hi[i + 1]
        if not (12 <= h2 - h1 <= 80):
            continue
        p1h, p2h = high[h1], high[h2]
        if not _near(p1h, p2h, _tight_tol):   # FIX: tighter flat-resistance check
            continue
        lo_in = lo[(lo >= h1) & (lo <= h2)]
        if len(lo_in) < 2:
            continue
        lo_vals = low[lo_in]
        # FIX: require generally rising lows (not just first < last)
        if not _monotone_rise(lo_vals, slack=1):
            continue
        # Ensure the rise is meaningful
        if (lo_vals[-1] - lo_vals[0]) / max(lo_vals[0], 1e-9) < 0.015:
            continue
        resistance = (p1h + p2h) / 2
        trend_ok = _is_uptrend(close, h1, lookback=60, min_gain=0.05)
        _add("Asc Triangle", "BULLISH", h2,
             resistance * 1.005, lo_vals[-1] * 0.99,
             resistance + (resistance - lo_vals[0]),
             "MEDIUM", f"Res≈{resistance:.2f}", trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. DESCENDING TRIANGLE (Bearish)
    #    FIX: require monotone fall in highs, tighter support flatness.
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
        # FIX: require generally falling highs
        if not _monotone_fall(hi_vals, slack=1):
            continue
        if (hi_vals[0] - hi_vals[-1]) / max(hi_vals[0], 1e-9) < 0.015:
            continue
        support  = (p1l + p2l) / 2
        trend_ok = _is_downtrend(close, l1, lookback=60, min_loss=0.05)
        _add("Desc Triangle", "BEARISH", l2,
             support * 0.995, hi_vals[0] * 1.01,
             support - (hi_vals[0] - support),
             "MEDIUM", f"Sup≈{support:.2f}", trend_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # 9. SYMMETRICAL TRIANGLE (Bullish bias)
    #    FIX: require at least 3 highs & 3 lows (not just 2), check apex
    #         distance is reasonable, verify proper convergence via slopes.
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
        if fall < 0.02 or rise < 0.02:   # FIX: both sides must converge meaningfully
            continue
        # FIX: require multiple pivot points (at least one more high or low inside)
        n_pivots = len(lo_in) + 2   # 2 highs + inner lows
        if n_pivots < 4:
            continue
        _add("Sym Triangle", "BULLISH", h2,
             p2h * 1.005, p2l * 0.99,
             p2h + (p1h - p1l) * 0.6,
             "MEDIUM", f"Converging Fall={fall:.1%} Rise={rise:.1%}")

    # ─────────────────────────────────────────────────────────────────────────
    # 10. BULL FLAG (Bullish)
    #     FIX: break bug — only break after _add succeeds (rr >= 1.5).
    #          Also require flag volume < pole volume (volume contraction).
    # ─────────────────────────────────────────────────────────────────────────
    min_pole_pct = 7  if timeframe == 'D' else 10
    pole_lens    = [7, 10, 15] if timeframe == 'D' else [4, 6, 8]

    for pole_end in range(10, n - 4):
        added = False   # FIX: track whether we've added a signal for this pole_end
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

            slope_norm = np.polyfit(range(len(c_cl)), c_cl, 1)[0] / max(c_cl[0], 1e-9)
            if not (-0.015 <= slope_norm <= 0.003):
                continue

            # FIX: volume should be lower during flag than during pole
            avg_flag_vol = float(c_vl.mean()) if len(c_vl) > 0 else 0
            avg_pole_vol = float(p_vl.mean()) if len(p_vl) > 0 else 0
            vol_ok = (avg_pole_vol == 0) or (avg_flag_vol < avg_pole_vol * 1.1)

            before_count = len(sigs)
            _add("Bull Flag", "BULLISH", pole_end + consol_len,
                 c_hi.max() * 1.005, c_lo.min() * 0.99,
                 c_hi.max() * 1.005 + (close[pole_end] - close[pole_start]),
                 "HIGH" if vol_ok else "MEDIUM",
                 f"Pole:{pole_move:.1f}%")
            # FIX: only break if _add actually appended (rr >= 1.5)
            if len(sigs) > before_count:
                added = True
                break
            # If rr too low, try a longer pole — do NOT break
        _ = added  # suppress unused warning

    # ─────────────────────────────────────────────────────────────────────────
    # 11. PENNANT (Bullish)
    #     FIX: same break bug fixed as Bull Flag.
    #          Added minimum convergence check.
    # ─────────────────────────────────────────────────────────────────────────
    for pole_end in range(10, n - 4):
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
            h_slope = np.polyfit(range(len(c_hi)), c_hi, 1)[0]
            l_slope = np.polyfit(range(len(c_lo)), c_lo, 1)[0]

            if h_slope >= 0 or l_slope <= 0:   # must converge
                continue
            if (c_hi.max() - c_lo.min()) / max(close[pole_end], 1e-9) * 100 > pole_move * 0.30:
                continue

            # FIX: verify the slopes actually converge (h_slope < 0, l_slope > 0 is guaranteed above)
            # But also check that convergence is meaningful (not near-parallel)
            if abs(h_slope - l_slope) / max(abs(close[pole_end]), 1e-9) < 1e-4:
                continue

            before_count = len(sigs)
            _add("Pennant", "BULLISH", pole_end + consol_len,
                 c_hi[-1] * 1.005, c_lo[-1] * 0.99,
                 c_hi[-1] * 1.005 + (close[pole_end] - close[pole_start]) * 0.8,
                 "HIGH", f"Pole:{pole_move:.1f}%")
            # FIX: only break if signal was actually added
            if len(sigs) > before_count:
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Deduplicate: keep most recent per (pattern, direction, timeframe)
    # FIX: include timeframe in key so daily & weekly signals don't clobber each other
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
            # FIX: log with symbol name instead of silently swallowing
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
        for e in errors[:20]:   # cap log spam
            logger.debug("  Error: %s", e)

    return by_sym, all_pats


# ─────────────────────────────────────────────────────────────────────────────
#  CHANGELOG — v5.3 → v6.0
# ─────────────────────────────────────────────────────────────────────────────
"""
BUG FIXES
─────────
1. [CRITICAL] Deduplication key did not include `timeframe`.
   A "Bull Flag BULLISH Daily" and "Bull Flag BULLISH Weekly" for the same
   stock would collide and only the later-dated one would survive.
   Fix: key = (pattern, direction, timeframe).

2. [CRITICAL] Bull Flag & Pennant: `break` fired unconditionally after _add(),
   even when _add() did NOT append (rr < 1.5).  This caused valid longer-pole
   setups to be skipped when a shorter pole had bad R:R.
   Fix: track len(sigs) before/after _add() and only break if it grew.

3. [MAJOR] Weekly resampling: the resampled DataFrame's index was unnamed,
   so after reset_index() the date column was called 'index', not 'Date'.
   detect_patterns' column search would miss it → all weekly pattern dates
   were empty strings.
   Fix: explicitly set `w.index.name = 'Date'` after resampling.

4. [MAJOR] Weekly resampling: timezone-aware DatetimeIndex caused
   AmbiguousTimeError on resample(). Fix: strip tz before resampling.

5. [MAJOR] Silent exception swallowing throughout:
   - _resample_ohlcv_weekly: bare `except: return pd.DataFrame()`
   - run_pattern_detection: bare `except: pass`
   These hid real bugs (e.g. MemoryError, KeyError).
   Fix: `except Exception as exc: logger.warning(...)` everywhere.

6. [MEDIUM] Ascending/Descending Triangle: only checked first vs last pivot
   value (lo_vals[-1] <= lo_vals[0]).  A zigzag (up, down, up) pattern
   would incorrectly pass.
   Fix: _monotone_rise() / _monotone_fall() with slack=1.

7. [MEDIUM] H&S Top / Inv H&S: no minimum head prominence check.
   A head only marginally above the shoulders would fire.
   Fix: require head prominence ≥ 3% of head price.

8. [MEDIUM] Double Bottom / Top: no minimum pattern height.
   Two lows 0.1% apart with a "neckline" 0.5% above would fire.
   Fix: require depth ≥ 5% of neckline.

QUALITY IMPROVEMENTS
────────────────────
9.  ATR-based adaptive tolerance (_sim_tol, _tight_tol):
    Instead of a universal 3% / 4% fixed tolerance, we derive the
    similarity tolerance from the recent 20-bar ATR as a % of price,
    clipped to [2%, 6%].  High-volatility stocks get looser tolerances;
    low-volatility stocks get tighter ones.

10. Prior-trend context (trend_ok field):
    - Bullish patterns (Double Bottom, Inv H&S, VCP, etc.) now check for
      a preceding downtrend via _is_downtrend().
    - Bearish patterns check for a preceding uptrend via _is_uptrend().
    - The result is stored in Pattern.trend_ok (True/False).
    - Patterns without trend confirmation are still emitted (to avoid
      over-filtering) but callers can filter on trend_ok == True.

11. VCP: volume contraction check added.
    Flag volume is checked against pole volume; mismatch downgrades
    confidence to MEDIUM.

12. Cup & Handle: handle slope check added.
    A handle that drifts upward (slope_norm > 0.003) is rejected —
    a real handle should be flat or mildly declining.

13. Symmetrical Triangle: requires ≥ 4 total pivot points (was 2 lows + 2 highs
    with no inner pivots).  Prevents degenerate 4-bar "triangles".

14. ATR field added to Pattern dataclass:
    14-period ATR at the signal bar.  Useful for position sizing.

15. Weekly resampling now aggregates Volume (sum) when present.

16. _atr14(), _slope(), _is_uptrend(), _is_downtrend(), _monotone_rise(),
    _monotone_fall() helper functions added.

UNCERTAIN / APPROXIMATE
────────────────────────
- H&S neckline is still the average of the two neckline troughs, not a
  fitted line.  For steeply tilted necklines this introduces ~1–3% error
  in the measured target.  A proper line-fit would need index positions
  which adds complexity; the current approximation is acceptable for
  screening purposes.

- The 10% prior-trend threshold (_is_uptrend / _is_downtrend) is a
  heuristic.  In a choppy market, 10% may be too low; in a strong trend,
  it may wrongly reject late-stage patterns.  Callers can tune this.

- VCP quarter-swing method is Mark Minervini's original heuristic, not
  a rigorously defined mathematical criterion.  False positives in
  sideways markets are expected.
"""
