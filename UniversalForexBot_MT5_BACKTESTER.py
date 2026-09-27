"""V8.4.2-FOREX-AI-AGENT-R6.5 MT5/Forex strategy + risk + SL/TP backtester.

This backtester is intentionally paired with UniversalForexBot_MT5.py R6.5.
The trading decision contract is the same as the live engine:
- same five Evidence Families (REGIME is gate-only)
- same AI-Agent council thresholds and bounded management
- same completed-candle discipline
- same indicator parameters and entry semantics from the R6.5 preset
- same ATR-based AI SL and R-multiple TP1/TP2 management

MT5 execution itself is NOT simulated as an exchange API. Backtest fills are
modeled at the next completed bar open, with optional spread/slippage costs.
Forex P/L uses price-distance * lots * contract_size; USD-quoted pairs such as
EURUSD map directly to account-USD P/L. Cross-currency pairs require an
appropriate quote-currency conversion outside this simple backtest model.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LIVE = Path(__file__).with_name("UniversalForexBot_MT5.py")
spec = importlib.util.spec_from_file_location("fx_r65", str(LIVE))
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load Forex engine: {LIVE}")
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)

APP_VERSION = "V8.4.2-FOREX-AI-AGENT-BACKTESTER-R6.5"
AUDIT_BUILD = "V8.4.2-FOREX-AI-AGENT-BACKTEST-AUDIT-2026-09-28"

AI_DEFAULTS = dict(fx.AI_AGENT_PRESET)
DEFAULTS: dict[str, Any] = {
    **AI_DEFAULTS,
    "capital": 10000.0,
    "symbol": "EURUSD",
    "contract_size": 100000.0,
    "min_lot": 0.01,
    "lot_step": 0.01,
    "max_lot": 100.0,
    "spread_pips": 0.0,
    "slippage_pips": 0.0,
    "use_session_filter": False,
    "session_start_utc": "07:00",
    "session_end_utc": "20:00",
    "friday_protect": False,
    "friday_cutoff_utc": "20:00",
    "use_daily_loss": True,
    "daily_loss_pct": 2.0,
    "use_daily_profit": False,
    "daily_profit_pct": 0.0,
    "use_loss_streak": True,
    "max_loss_streak": 3,
}


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def load_ohlcv(data: str | Path | pd.DataFrame) -> pd.DataFrame:
    """Load normalized OHLCV data from CSV/Parquet/DataFrame.

    Required: open, high, low, close
    Time column: datetime, time, timestamp or date. Volume is optional.
    """
    if isinstance(data, pd.DataFrame):
        x = data.copy()
    else:
        path = Path(data)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() in {".parquet", ".pq"}:
            x = pd.read_parquet(path)
        else:
            x = pd.read_csv(path)

    x.columns = [str(c).strip().lower() for c in x.columns]
    rename = {
        "timestamp": "time",
        "date": "datetime",
        "datetime_utc": "datetime",
        "tick_volume": "vol",
        "volume": "vol",
    }
    for old, new in rename.items():
        if old in x.columns and new not in x.columns:
            x[new] = x[old]

    if "datetime" not in x.columns:
        if "time" not in x.columns:
            raise ValueError("Input needs datetime/date or time/timestamp.")
        raw = pd.to_numeric(x["time"], errors="coerce")
        unit = "ms" if raw.dropna().median() > 1e11 else "s"
        x["datetime"] = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")
    else:
        x["datetime"] = pd.to_datetime(x["datetime"], utc=True, errors="coerce")

    for col in ["open", "high", "low", "close"]:
        if col not in x.columns:
            raise ValueError(f"Missing required column: {col}")
        x[col] = pd.to_numeric(x[col], errors="coerce")

    if "vol" not in x.columns:
        x["vol"] = 1.0
    x["vol"] = pd.to_numeric(x["vol"], errors="coerce").fillna(0.0)
    x = x.dropna(subset=["datetime", "open", "high", "low", "close"])
    x = x.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    x["time"] = (x["datetime"].astype("int64") // 10**6).astype("int64")
    return x


def _cfg(c: dict[str, Any]) -> dict[str, Any]:
    x = dict(DEFAULTS)
    x.update(c or {})
    # Normalize the Forex GUI's historical singular spellings to the shared
    # Crypto R6.5 preset spellings used by the strategy engine.
    if "use_liq_swing" in x and "use_liq_swings" not in c:
        x["use_liq_swings"] = x["use_liq_swing"]
    if "trend_len" in x and "trendline_length" not in c:
        x["trendline_length"] = x["trend_len"]
    if "trend_min_dist" in x and "trendline_min_distance" not in c:
        x["trendline_min_distance"] = x["trend_min_dist"]
    if "trend_entry" in x and "trendline_entry_mode" not in c:
        x["trendline_entry_mode"] = x["trend_entry"]
    if "trend_buffer" in x and "trendline_buffer" not in c:
        x["trendline_buffer"] = x["trend_buffer"]
    if "trend_retest" in x and "trendline_retest_candles" not in c:
        x["trendline_retest_candles"] = x["trend_retest"]
    # Backwards-compatible local aliases used by the Forex loop implementation.
    x.setdefault("liq_len", x.get("liq_length", 14))
    x.setdefault("use_liq_swing", x.get("use_liq_swings", True))
    x.setdefault("trend_len", x.get("trendline_length", 14))
    x.setdefault("trend_min_dist", x.get("trendline_min_distance", 5))
    x.setdefault("trend_entry", x.get("trendline_entry_mode", "FRESH_BREAK"))
    x.setdefault("trend_buffer", x.get("trendline_buffer", 0))
    x.setdefault("trend_retest", x.get("trendline_retest_candles", 3))
    x.setdefault("st_change_atr", True)
    # Keep R6.5 AI-Agent live contract explicit in every test even if caller
    # changes a non-AI field.
    x["signal_mode"] = str(x.get("signal_mode", "AI_AGENT")).strip().upper()
    x["max_open_trades"] = 1
    return x


def build_frame(df: pd.DataFrame, c: dict[str, Any]) -> pd.DataFrame:
    """Build the same causal indicator families used by the live Forex engine."""
    x = load_ohlcv(df)
    x = fx.calculate_supertrend(
        x,
        int(c.get("st_len", 10)),
        float(c.get("st_mult", 2.0)),
        str(c.get("st_source", "CLOSE")),
        _bool(c.get("st_change_atr", True)),
    )
    x = fx.calculate_adx(x, int(c.get("adx_len", 14)))
    x["ema"] = x.close.ewm(span=int(c["ema_len"]), adjust=False).mean()
    x["ema_fast"] = x.close.ewm(span=int(c["ema_fast"]), adjust=False).mean()
    x["ema_slow"] = x.close.ewm(span=int(c["ema_slow"]), adjust=False).mean()

    if _bool(c["use_macd"]):
        x = fx.calculate_macd(x, int(c["macd_fast"]), int(c["macd_slow"]), int(c["macd_signal"]))
    if _bool(c["use_rsi"]):
        x = fx.calculate_rsi(x, int(c["rsi_len"]))
        x = fx.calculate_rsi_ma(x, str(c["rsi_ma_type"]), int(c["rsi_ma_len"]))
    if _bool(c["use_bb"]):
        x = fx.calculate_bollinger(x, int(c["bb_len"]), float(c["bb_std"]))
    if _bool(c["use_stoch"]):
        x = fx.calculate_stochastic(x, int(c["stoch_k"]), int(c["stoch_smooth"]), int(c["stoch_d"]))
    if _bool(c["use_vwap"]):
        x = fx.calculate_vwap(x, int(c["vwap_len"]))
    if _bool(c["use_vwap_delta"]):
        x = fx.calculate_vwap_delta(
            x,
            _bool(c["vwap_delta_smooth"]),
            int(c["vwap_delta_smooth_len"]),
            int(c["vwap_delta_baseline"]),
        )
    if _bool(c["use_vidya"]):
        x = fx.calculate_vidya(
            x,
            int(c["vidya_len"]),
            int(c["vidya_momentum"]),
            float(c["vidya_band"]),
        )
    if _bool(c["use_nwe"]):
        x = fx.calculate_nadaraya_watson_envelope(
            x,
            float(c["nwe_bandwidth"]),
            float(c["nwe_mult"]),
        )

    x["vol_ma"] = x.vol.rolling(int(c["vol_len"])).mean()

    if _bool(c.get("use_liq_swings", c.get("use_liq_swing", True))):
        x = fx.calculate_liquidity_swings(
            x,
            length=int(c.get("liq_length", c.get("liq_len", 14))),
            area=str(c["liq_area"]),
            filter_options=str(c["liq_filter"]),
            filter_value=float(c["liq_filter_value"]),
        )
    if _bool(c["use_trendline"]):
        x = fx.calculate_trendline_breakout(
            x,
            length=int(c.get("trendline_length", c.get("trend_len", 14))),
            min_pivot_distance=int(c.get("trendline_min_distance", c.get("trend_min_dist", 5))),
            breakout_buffer_pct=float(c.get("trendline_buffer", c.get("trend_buffer", 0))),
            retest_candles=int(c.get("trendline_retest_candles", c.get("trend_retest", 3))),
        )
    if _bool(c["use_divergence"]):
        div_cfg = dict(c)
        div_cfg.setdefault("div_max_pivots", c.get("div_max_pivots", 10))
        div_cfg.setdefault("div_max_bars", c.get("div_max_bars", 100))
        x = fx.calculate_divergence_module(x, div_cfg)
    if _bool(c["use_vol_sr"]):
        x = fx._volume_sr_base_series(x, dict(c))

    if _bool(c["use_mtf"]):
        z = (
            x.set_index("datetime")
            .resample("4h", label="left", closed="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"})
            .dropna()
        )
        z["ema200"] = z.close.ewm(span=200, adjust=False).mean()
        z["available_at"] = z.index + pd.Timedelta(hours=4)
        z = z.reset_index()
        x = pd.merge_asof(
            x.sort_values("datetime"),
            z[["available_at", "close", "ema200"]]
            .rename(columns={"close": "mtf_close"})
            .sort_values("available_at"),
            left_on="datetime",
            right_on="available_at",
            direction="backward",
        )
    else:
        x["mtf_close"] = np.nan
        x["ema200"] = np.nan

    return x.reset_index(drop=True)


def module_votes(x: pd.DataFrame, i: int, c: dict[str, Any]):
    """Return live-equivalent directional modules and gate state for bar i."""
    q, p, pp = x.iloc[i], x.iloc[i - 1], x.iloc[i - 2]
    close = float(q.close)
    candle_bull = float(q.close) > float(q.open)
    candle_bear = float(q.close) < float(q.open)

    use_st = _bool(c["use_st"])
    use_ema = _bool(c["use_ema"])
    use_ema_cross = _bool(c["use_ema_cross"])
    use_macd = _bool(c["use_macd"])
    use_rsi = _bool(c["use_rsi"])
    use_bb = _bool(c["use_bb"])
    use_stoch = _bool(c["use_stoch"])
    use_vwap = _bool(c["use_vwap"])
    use_vwap_delta = _bool(c["use_vwap_delta"])
    use_vidya = _bool(c["use_vidya"])
    use_nwe = _bool(c["use_nwe"])
    use_liq_swing = _bool(c.get("use_liq_swings", c.get("use_liq_swing", True)))
    use_trendline = _bool(c.get("use_trendline", True))
    use_mtf = _bool(c["use_mtf"])
    use_divergence = _bool(c["use_divergence"])
    use_vol_sr = _bool(c["use_vol_sr"])
    use_vol = _bool(c["use_vol"])
    use_adx = _bool(c["use_adx"])
    use_atr = _bool(c["use_atr"])

    st_trend_bull = bool(q.trend)
    st_trend_bear = not st_trend_bull
    st_flip_bull = bool(q.trend) and not bool(p.trend)
    st_flip_bear = bool(p.trend) and not bool(q.trend)

    st_entry = str(c["st_entry_mode"]).strip().upper()
    ema_bull = close > float(q.ema)
    ema_bear = close < float(q.ema)

    ema_cross_up = float(p.ema_fast) <= float(p.ema_slow) and float(q.ema_fast) > float(q.ema_slow)
    ema_cross_down = float(p.ema_fast) >= float(p.ema_slow) and float(q.ema_fast) < float(q.ema_slow)
    ema_cross_trend_bull = float(q.ema_fast) > float(q.ema_slow)
    ema_cross_trend_bear = float(q.ema_fast) < float(q.ema_slow)
    if str(c["ema_cross_entry_mode"]).strip().upper() == "CURRENT_TREND":
        ema_cross_bull, ema_cross_bear = ema_cross_trend_bull, ema_cross_trend_bear
    else:
        ema_cross_bull, ema_cross_bear = ema_cross_up, ema_cross_down

    macd_bull = (
        float(p.macd) <= float(p.macd_signal)
        and float(q.macd) > float(q.macd_signal)
    ) if use_macd else True
    macd_bear = (
        float(p.macd) >= float(p.macd_signal)
        and float(q.macd) < float(q.macd_signal)
    ) if use_macd else True

    if use_rsi:
        rsi_reversal_bull = float(q.rsi) <= float(c["rsi_os"])
        rsi_reversal_bear = float(q.rsi) >= float(c["rsi_ob"])
        rsi_cross_bull = float(p.rsi) <= float(p.rsi_ma) and float(q.rsi) > float(q.rsi_ma)
        rsi_cross_bear = float(p.rsi) >= float(p.rsi_ma) and float(q.rsi) < float(q.rsi_ma)
        logic = str(c["rsi_logic"]).strip().upper()
        if logic == "CROSS_MA":
            rsi_bull, rsi_bear = rsi_cross_bull, rsi_cross_bear
        elif logic == "EITHER":
            rsi_bull, rsi_bear = rsi_reversal_bull or rsi_cross_bull, rsi_reversal_bear or rsi_cross_bear
        else:
            rsi_bull, rsi_bear = rsi_reversal_bull, rsi_reversal_bear
    else:
        rsi_bull = rsi_bear = True

    if use_bb:
        bb_bull = close > float(q.bb_upper); bb_bear = close < float(q.bb_lower)
    else:
        bb_bull = bb_bear = True

    if use_stoch:
        stoch_bull = float(p.stoch_k) <= float(p.stoch_d) and float(q.stoch_k) > float(q.stoch_d)
        stoch_bear = float(p.stoch_k) >= float(p.stoch_d) and float(q.stoch_k) < float(q.stoch_d)
    else:
        stoch_bull = stoch_bear = True

    if use_vwap:
        vwap_bull = close > float(q.vwap); vwap_bear = close < float(q.vwap)
    else:
        vwap_bull = vwap_bear = True

    if use_vwap_delta:
        vd_now = float(q.vwap_delta); vd_base_now = float(q.vwap_delta_baseline)
        vd_prev = float(p.vwap_delta); vd_base_prev = float(p.vwap_delta_baseline)
        if str(c["vwap_delta_logic"]).strip().upper() == "CROSS_BASELINE":
            vwap_delta_bull = vd_prev <= vd_base_prev and vd_now > vd_base_now
            vwap_delta_bear = vd_prev >= vd_base_prev and vd_now < vd_base_now
        else:
            vwap_delta_bull = vd_now > vd_base_now; vwap_delta_bear = vd_now < vd_base_now
    else:
        vwap_delta_bull = vwap_delta_bear = True

    if use_vidya:
        if str(c["vidya_entry_mode"]).strip().upper() == "FRESH_FLIP":
            vidya_bull = bool(q.vidya_cross_up); vidya_bear = bool(q.vidya_cross_down)
        else:
            vidya_bull = bool(q.vidya_trend_up); vidya_bear = not bool(q.vidya_trend_up)
    else:
        vidya_bull = vidya_bear = True

    if use_nwe:
        vals = [q.nwe_out, p.nwe_out, q.nwe_upper, q.nwe_lower, q.close, p.close, p.nwe_upper, p.nwe_lower]
        if not all(np.isfinite(float(v)) for v in vals):
            nwe_bull = nwe_bear = False
        elif str(c["nwe_entry_mode"]).strip().upper() == "FRESH_CROSS":
            nwe_bull = float(q.close) < float(q.nwe_lower) and float(p.close) >= float(p.nwe_lower)
            nwe_bear = float(q.close) > float(q.nwe_upper) and float(p.close) <= float(p.nwe_upper)
        else:
            nwe_bull = float(q.nwe_out) > float(p.nwe_out); nwe_bear = float(q.nwe_out) < float(p.nwe_out)
    else:
        nwe_bull = nwe_bear = True

    atr = float(q.atr); atr_pct = atr / close * 100.0 if close > 0 else 0.0
    atr_pass = (not use_atr) or atr_pct >= _float(c["atr_min_pct"])
    vol_pass = (not use_vol) or float(q.vol) > float(q.vol_ma)
    adx_pass = (not use_adx) or float(q.adx) >= _float(c["adx_thresh"])

    if use_mtf:
        mtf_close = float(q.mtf_close) if pd.notna(q.mtf_close) else math.nan
        mtf_ema = float(q.ema200) if pd.notna(q.ema200) else math.nan
        mtf_pass_bull = np.isfinite(mtf_close) and np.isfinite(mtf_ema) and mtf_close > mtf_ema
        mtf_pass_bear = np.isfinite(mtf_close) and np.isfinite(mtf_ema) and mtf_close < mtf_ema
    else:
        mtf_pass_bull = mtf_pass_bear = True

    mods=[]
    if use_st: mods.append(("ST", st_trend_bull if st_entry=="CURRENT_TREND" else st_flip_bull, st_trend_bear if st_entry=="CURRENT_TREND" else st_flip_bear))
    if use_ema: mods.append(("EMA", ema_bull, ema_bear))
    if use_ema_cross: mods.append(("EMA_CROSS", ema_cross_bull, ema_cross_bear))
    if use_macd: mods.append(("MACD", macd_bull, macd_bear))
    if use_rsi: mods.append(("RSI", rsi_bull, rsi_bear))
    if use_bb: mods.append(("BB", bb_bull, bb_bear))
    if use_stoch: mods.append(("STOCH", stoch_bull, stoch_bear))
    if use_vwap: mods.append(("VWAP", vwap_bull, vwap_bear))
    if use_vwap_delta: mods.append(("VWAP_DELTA", vwap_delta_bull, vwap_delta_bear))
    if use_vidya: mods.append(("VIDYA", vidya_bull, vidya_bear))
    if use_nwe: mods.append(("NWE", nwe_bull, nwe_bear))
    if use_liq_swing:
        mods.append(("LIQ_SWING", float(q.liq_swing_trend)>0, float(q.liq_swing_trend)<0))
    if use_trendline:
        mode=str(c["trend_entry"]).strip().upper()
        up = bool(q.trendline_break_up) if mode=="FRESH_BREAK" else bool(q.trendline_retest_up) if mode=="BREAK_RETEST" else bool(q.trendline_state>0)
        dn = bool(q.trendline_break_down) if mode=="FRESH_BREAK" else bool(q.trendline_retest_down) if mode=="BREAK_RETEST" else bool(q.trendline_state<0)
        mods.append(("TRENDLINE",up,dn))
    if use_mtf: mods.append(("MTF", mtf_pass_bull, mtf_pass_bear))
    if use_divergence: mods.append(("DIVERGENCE", bool(q.div_bull_signal), bool(q.div_bear_signal)))
    if use_vol_sr: mods.append(("VOL_SR", bool(q.sr_bull), bool(q.sr_bear)))
    if use_vol and vol_pass: mods.append(("VOL", candle_bull, candle_bear))
    if use_adx and adx_pass: mods.append(("ADX", float(q.plus_di)>float(q.minus_di), float(q.minus_di)>float(q.plus_di)))
    if use_atr and atr_pass: mods.append(("ATR", candle_bull, candle_bear))

    return mods, {"atr_pass":atr_pass,"vol_pass":vol_pass,"adx_pass":adx_pass,"mtf_bull":mtf_pass_bull,"mtf_bear":mtf_pass_bear,"atr_value":atr,"atr_pct":atr_pct}


def signal_at(x: pd.DataFrame, i: int, c: dict[str, Any]):
    mods, gates = module_votes(x, i, c)
    mode = str(c["signal_mode"]).upper()
    result = fx.StrategyEngine.ai_agent_decision(
        mods,
        atr_pass=gates["atr_pass"], vol_pass=gates["vol_pass"], adx_pass=gates["adx_pass"],
        mtf_pass_bull=gates["mtf_bull"], mtf_pass_bear=gates["mtf_bear"],
        min_families=_int(c["ai_min_families"], 3),
        min_edge=_float(c["ai_min_edge"], .20),
        min_family_confidence=_float(c["ai_family_confidence"], .55),
        require_trend=_bool(c["ai_require_trend"]),
        require_structure=_bool(c["ai_require_structure"]),
        max_conflicting_families=_int(c["ai_max_conflicts"], 1),
    ) if mode == "AI_AGENT" else None
    if mode == "AI_AGENT":
        side = result["side"]
        reason = fx.StrategyEngine.decision_reason(
            mods, mode, _int(c.get("min_score"),1),
            atr_pass=gates["atr_pass"], vol_pass=gates["vol_pass"], adx_pass=gates["adx_pass"],
            mtf_pass_bull=gates["mtf_bull"], mtf_pass_bear=gates["mtf_bear"],
            ai_min_families=_int(c["ai_min_families"],3), ai_min_edge=_float(c["ai_min_edge"],.20),
            ai_min_family_confidence=_float(c["ai_family_confidence"],.55),
            ai_require_trend=_bool(c["ai_require_trend"]), ai_require_structure=_bool(c["ai_require_structure"]),
            ai_max_conflicting_families=_int(c["ai_max_conflicts"],1),
        )
        return ("BUY" if side == "BUY" else "SELL" if side == "SELL" else "NONE"), mods, gates, result, reason

    buy, sell, *_ = fx.StrategyEngine.decide_signal(
        mods, mode, _int(c.get("min_score"), 1),
        atr_pass=gates["atr_pass"], vol_pass=gates["vol_pass"], adx_pass=gates["adx_pass"],
        mtf_pass_bull=gates["mtf_bull"], mtf_pass_bear=gates["mtf_bear"],
        adaptive_edge=_float(c.get("adaptive_edge"),.18), adaptive_min_weight=_float(c.get("adaptive_min_weight"),3.5),
        evidence_min_families=_int(c.get("evidence_min_families"),2), evidence_family_min_score=_float(c.get("evidence_family_min_score"),.35),
        evidence_require_trend=_bool(c.get("evidence_require_trend")), evidence_require_independent=_bool(c.get("evidence_require_independent")),
    )
    return ("BUY" if buy else "SELL" if sell else "NONE"), mods, gates, None, fx.StrategyEngine.decision_reason(mods,mode,_int(c.get("min_score"),1))


def _parse_hm(value: str):
    try:
        h,m=[int(x) for x in str(value).strip().split(":",1)]
        if 0<=h<=23 and 0<=m<=59: return h,m
    except Exception: pass
    return None,None


def _in_session(ts: pd.Timestamp, start: str, end: str):
    sh,sm=_parse_hm(start); eh,em=_parse_hm(end)
    if sh is None or eh is None: return True
    cur=ts.hour*60+ts.minute; a=sh*60+sm; b=eh*60+em
    return a<=cur<=b if a<=b else (cur>=a or cur<=b)


def _pip_size(symbol: str):
    s=str(symbol).upper().replace("/","")
    return 0.01 if "JPY" in s else 0.0001


def _round_lot(qty: float, c: dict[str,Any]):
    step=max(_float(c.get("lot_step"),.01),1e-12); mn=max(_float(c.get("min_lot"),.01),step); mx=max(_float(c.get("max_lot"),100.0),mn)
    q=math.floor(min(qty,mx)/step+1e-12)*step
    return round(q,8) if q>=mn else 0.0


def run_backtest(data: str | Path | pd.DataFrame, config: dict[str,Any]|None=None, return_dataframes: bool=False):
    c=_cfg(config or {})
    x=build_frame(data,c)
    if len(x)<650:
        raise ValueError(f"Need at least ~650 candles for full R6.5 warm-up; got {len(x)}.")

    equity=float(c.get("capital",10000.0)); starting=equity; peak=equity; max_dd_abs=0.0; max_dd_pct=0.0
    daily_anchor=None; daily_start=equity; loss_streak=0; cooldown_until=None; locked_side=None; last_entry_bar=None
    pos=None; trades=[]; rejects={"ai_blocked":0,"session":0,"daily_loss":0,"daily_profit":0,"loss_streak":0,"cooldown":0,"post_sl_lock":0}

    warmup=max(650, int(c["st_len"])*5, int(c["ema_len"])+10, int(c["vol_len"])+10)
    last_i=len(x)-1
    spread_price=_float(c.get("spread_pips"),0)*_pip_size(c.get("symbol","EURUSD"))
    slip_price=_float(c.get("slippage_pips"),0)*_pip_size(c.get("symbol","EURUSD"))

    def update_dd():
        nonlocal peak,max_dd_abs,max_dd_pct
        peak=max(peak,equity); dd=peak-equity; pct=(dd/peak*100) if peak>0 else 0
        max_dd_abs=max(max_dd_abs,dd); max_dd_pct=max(max_dd_pct,pct)

    def close_trade(exit_price, reason, bar_ts):
        nonlocal equity,pos,locked_side,cooldown_until,loss_streak
        if pos is None: return
        side=pos["side"]; qty=pos["qty"]; entry=pos["entry"]
        gross=(exit_price-entry)*qty*float(c["contract_size"]) if side=="LONG" else (entry-exit_price)*qty*float(c["contract_size"])
        pnl=gross + float(pos.get("realized_pnl",0.0))
        equity+=gross; update_dd()
        total_realized=pnl
        r_multiple=total_realized/max(pos["risk_amount"],1e-12)
        tr={**pos,"exit":float(exit_price),"pnl":float(total_realized),"r":float(r_multiple),"exit_reason":reason,"exit_time":str(bar_ts)}
        trades.append(tr)
        if pnl<0: loss_streak+=1
        elif pnl>0: loss_streak=0
        if reason.startswith("SL"):
            locked_side=side
            cd=int(float(c.get("cooldown_min",15)))
            cooldown_until=bar_ts+pd.Timedelta(minutes=max(0,cd))
        pos=None

    for i in range(warmup,last_i):
        ts=pd.Timestamp(x.datetime.iloc[i])
        # reset daily guard at UTC date.
        day=str(ts.date())
        if day!=daily_anchor:
            daily_anchor=day; daily_start=equity
        daily_loss_hit=_bool(c.get("use_daily_loss",True)) and equity <= daily_start*(1-_float(c.get("daily_loss_pct"),2)/100)
        daily_profit_hit=_bool(c.get("use_daily_profit",False)) and _float(c.get("daily_profit_pct"),0)>0 and equity >= daily_start*(1+_float(c.get("daily_profit_pct"),0)/100)

        # Manage existing position on current completed candle. Same-bar SL has
        # precedence over TP to remain conservative when both extremes are hit.
        if pos is not None:
            hi=float(x.high.iloc[i]); lo=float(x.low.iloc[i]); side=pos["side"]
            if side=="LONG":
                sl_hit=lo<=pos["sl"]; tp2_hit=hi>=pos["tp2"]; tp1_hit=(hi>=pos["tp1"] and not pos["tp1_done"])
            else:
                sl_hit=hi>=pos["sl"]; tp2_hit=lo<=pos["tp2"]; tp1_hit=(lo<=pos["tp1"] and not pos["tp1_done"])
            if sl_hit:
                close_trade(float(pos["sl"]),"SL",ts); last_entry_bar=None
            elif tp2_hit:
                close_trade(float(pos["tp2"]),"TP2",ts); last_entry_bar=None
            elif tp1_hit:
                part=pos["qty"]*float(c.get("tp1_close",50))/100.0
                part=max(0.0,min(part,pos["qty"]))
                if part>0:
                    p1=(float(pos["tp1"])-pos["entry"])*part*float(c["contract_size"]) if side=="LONG" else (pos["entry"]-float(pos["tp1"]))*part*float(c["contract_size"])
                    equity+=p1
                    pos["realized_pnl"]=float(pos.get("realized_pnl",0.0))+float(p1)
                    pos["qty"]-=part; pos["tp1_done"]=True
                    if _bool(c.get("tp1_be",True)): pos["sl"]=pos["entry"]
                    update_dd()

        if pos is not None:
            continue

        if daily_loss_hit:
            rejects["daily_loss"]+=1; continue
        if daily_profit_hit:
            rejects["daily_profit"]+=1; continue
        if _bool(c.get("use_loss_streak",True)) and loss_streak>=_int(c.get("max_loss_streak"),3):
            rejects["loss_streak"]+=1; continue
        if cooldown_until is not None and ts<cooldown_until:
            rejects["cooldown"]+=1; continue
        if _bool(c.get("use_session_filter",False)) and not _in_session(ts,str(c.get("session_start_utc","07:00")),str(c.get("session_end_utc","20:00"))):
            rejects["session"]+=1; continue
        if _bool(c.get("friday_protect",False)) and ts.weekday()==4:
            fh,fm=_parse_hm(str(c.get("friday_cutoff_utc","20:00")))
            if fh is not None and ts.hour*60+ts.minute>=fh*60+fm:
                rejects["session"]+=1; continue

        sig,mods,gates,ai,reason=signal_at(x,i,c)
        if sig=="NONE":
            if str(c["signal_mode"]).upper()=="AI_AGENT": rejects["ai_blocked"]+=1
            continue
        desired="LONG" if sig=="BUY" else "SHORT"
        if locked_side==desired and _bool(c.get("require_opposite_after_sl",True)):
            rejects["post_sl_lock"]+=1; continue
        locked_side=None

        entry=float(x.open.iloc[i+1])
        # Apply half-spread/slippage adverse to the entry.
        if desired=="LONG": entry += spread_price/2 + slip_price
        else: entry -= spread_price/2 + slip_price

        if ai is None:
            # Non-AI modes: use fixed baseline risk/SL/TP; retained for parity testing.
            risk_pct=_float(c.get("risk_pct"),.35)
            sl_mult=_float(c.get("atr_sl_mult"),1.8)
            tp1_r=_float(c.get("atr_tp1_mult"),1.2)
            tp2_r=_float(c.get("atr_tp2_mult"),2.2)
            atr_val=float(gates["atr_value"])
        else:
            # Reuse the exact live R6.5 AI manager implementation.
            dummy=object()
            ai=fx.UniversalFuturesBotGUI._ai_agent_trade_management(
                dummy,mods,desired,gates["atr_value"],entry,_float(c["risk_pct"],.35),_float(c["atr_sl_mult"],1.8),_float(c["atr_tp1_mult"],1.2),_float(c["atr_tp2_mult"],2.2),
                _int(c["ai_min_families"],3),_float(c["ai_min_edge"],.20),_float(c["ai_family_confidence"],.55),_bool(c["ai_require_trend"]),_bool(c["ai_require_structure"]),_int(c["ai_max_conflicts"],1)
            )
            risk_pct=float(ai["risk_pct"]); sl_mult=float(ai["atr_sl_mult"]); tp1_r=float(ai["tp1_r"]); tp2_r=float(ai["tp2_r"]); atr_val=float(gates["atr_value"])

        stop_distance=atr_val*sl_mult
        if not np.isfinite(stop_distance) or stop_distance<=0: continue
        risk_amount=equity*risk_pct/100
        qty=_round_lot(risk_amount/(stop_distance*float(c["contract_size"])),c)
        if qty<=0: continue
        sl=entry-stop_distance if desired=="LONG" else entry+stop_distance
        tp1=entry+stop_distance*tp1_r if desired=="LONG" else entry-stop_distance*tp1_r
        tp2=entry+stop_distance*tp2_r if desired=="LONG" else entry-stop_distance*tp2_r
        if not (sl<entry<tp1<tp2 if desired=="LONG" else sl>entry>tp1>tp2): continue
        pos={"side":desired,"entry":entry,"qty":qty,"initial_qty":qty,"realized_pnl":0.0,"sl":sl,"tp1":tp1,"tp2":tp2,"tp1_done":False,"risk_pct":risk_pct,"risk_amount":risk_amount,"sl_atr":sl_mult,"tp1_r":tp1_r,"tp2_r":tp2_r,"ai_families":(ai or {}).get("families",[]),"ai_edge":(ai or {}).get("edge",0.0),"ai_confidence":(ai or {}).get("confidence",0.0),"signal_reason":reason,"entry_time":str(x.datetime.iloc[i+1])}
        last_entry_bar=i+1

    if pos is not None:
        final_close=float(x.close.iloc[last_i])
        close_trade(final_close,"FORCED_CLOSE_END",pd.Timestamp(x.datetime.iloc[last_i]))

    wins=[t for t in trades if t["pnl"]>0]; losses=[t for t in trades if t["pnl"]<0]
    gp=sum(t["pnl"] for t in wins); gl=sum(t["pnl"] for t in losses)
    metrics={
        "app_version":APP_VERSION,"symbol":str(c.get("symbol","EURUSD")),"starting_equity":starting,"ending_equity":equity,"net_pnl":equity-starting,
        "return_pct":(equity/starting-1)*100 if starting else 0.0,"trades":len(trades),"wins":len(wins),"losses":len(losses),"win_rate_pct":(len(wins)/len(trades)*100) if trades else 0.0,
        "gross_profit":gp,"gross_loss":gl,"profit_factor":(gp/abs(gl)) if gl<0 else (math.inf if gp>0 else 0.0),"avg_trade":((equity-starting)/len(trades)) if trades else 0.0,
        "largest_win":max((t["pnl"] for t in trades),default=0.0),"largest_loss":min((t["pnl"] for t in trades),default=0.0),"avg_R":(sum(t["r"] for t in trades)/len(trades)) if trades else 0.0,
        "max_drawdown_abs":max_dd_abs,"max_drawdown_pct":max_dd_pct,"final_loss_streak":loss_streak,"rejects":rejects,
        "ai_min_families":_int(c["ai_min_families"],3),"ai_min_edge":_float(c["ai_min_edge"],.20),"ai_family_confidence":_float(c["ai_family_confidence"],.55),"ai_max_conflicts":_int(c["ai_max_conflicts"],1),
        "ai_risk_envelope":f"{fx.AI_AGENT_MIN_RISK_PCT:.2f}-{fx.AI_AGENT_MAX_RISK_PCT:.2f}%","ai_sl_envelope":f"{fx.AI_AGENT_MIN_ATR_SL_MULT:.2f}-{fx.AI_AGENT_MAX_ATR_SL_MULT:.2f} ATR","ai_tp1_envelope":f"{fx.AI_AGENT_MIN_TP1_R_MULT:.2f}-{fx.AI_AGENT_MAX_TP1_R_MULT:.2f}R","ai_tp2_envelope":f"{fx.AI_AGENT_MIN_TP2_R_MULT:.2f}-{fx.AI_AGENT_MAX_TP2_R_MULT:.2f}R",
    }
    out={"metrics":metrics,"trades":trades}
    if return_dataframes:
        out["trades_df"]=pd.DataFrame(trades)
        out["frame"]=x
    return out


def main(argv=None):
    ap=argparse.ArgumentParser(description="Forex/MT5 R6.5 AI-Agent backtester")
    ap.add_argument("data",help="CSV/Parquet with OHLCV")
    ap.add_argument("--capital",type=float,default=10000.0)
    ap.add_argument("--symbol",default="EURUSD")
    ap.add_argument("--risk",dest="risk_pct",type=float,default=.35)
    ap.add_argument("--spread-pips",type=float,default=0.0)
    ap.add_argument("--slippage-pips",type=float,default=0.0)
    ap.add_argument("--output",default="forex_ai_r6_5_backtest_report.json")
    args=ap.parse_args(argv)
    result=run_backtest(args.data,{"capital":args.capital,"symbol":args.symbol,"risk_pct":str(args.risk_pct),"spread_pips":args.spread_pips,"slippage_pips":args.slippage_pips})
    Path(args.output).write_text(json.dumps(result["metrics"],indent=2,default=str),encoding="utf-8")
    print(json.dumps(result["metrics"],indent=2,default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())