"""V8.4.2-R5 Forex hardening layer over the audited MT5 V8.4.0 engine."""
import json, importlib.util
from pathlib import Path
import numpy as np, pandas as pd
import tkinter as tk

BASE=Path(__file__).with_name("UniversalForexBot_V8_4_0_MT5_FOREX_EVIDENCE_HARDENED.py")
sp=importlib.util.spec_from_file_location("fx_base",str(BASE)); fx=importlib.util.module_from_spec(sp); sp.loader.exec_module(fx)

APP_VERSION="V8.4.2-FOREX-EVIDENCE-HARDENED-R5"
APP_TITLE="Universal Forex Trading Bot V8.4.2 - MT5 Forex Evidence Hardened R5"
AUDIT_BUILD="V8.4.2-ENGINE-AUDIT-2026-09-21-FOREX-R5"
CONFIG_SCHEMA_VERSION=9
RUNTIME_SCHEMA_VERSION=getattr(fx,"RUNTIME_SCHEMA_VERSION",7)
SUPPORTED_SIGNAL_MODES=fx.SUPPORTED_SIGNAL_MODES
CONFIG_FILE=fx.CONFIG_FILE
DEFAULT_MAX_OPEN_TRADES=1
DEFAULT_ATR_SL_MULTIPLIER=1.5
DEFAULT_ATR_TP1_MULTIPLIER=1.2
DEFAULT_ATR_TP2_MULTIPLIER=2.2

def _f(self,name,default):
    try:return float(getattr(self,name).get())
    except:return float(default)

def get_completed_atr(self,symbol,limit=120):
    rows=self.exchange.fetch_ohlcv(symbol,self.v_tf.get(),limit)
    d=pd.DataFrame(rows,columns=["time","open","high","low","close","vol"])
    if len(d)<20: raise RuntimeError("Not enough candles for completed-candle ATR.")
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift(1)).abs(),(d.low-d.close.shift(1)).abs()],axis=1).max(axis=1)
    atr=float(fx.calculate_rma(tr,14).iloc[-2])
    if not np.isfinite(atr) or atr<=0: raise RuntimeError("Completed-candle ATR is invalid.")
    return atr

GUI=fx.UniversalFuturesBotGUI
_orig_init=GUI.__init__; _orig_save=GUI.save_settings; _orig_load=GUI.load_settings
_orig_pre=GUI._validate_strategy_preflight; _orig_prot=fx.fx_v2_calculate_protection_prices; _orig_start=GUI.start_bot

def _add_controls(self):
    if hasattr(self,"e_max_open_trades"): return
    f=tk.LabelFrame(self.scroll_frame,text=" V8.4.2-R5 Protection / Execution ")
    f.pack(fill="x",padx=10,pady=5)
    tk.Label(f,text="Max Open Trades (per bot/symbol):").grid(row=0,column=0,sticky="w")
    self.e_max_open_trades=tk.Entry(f,width=7); self.e_max_open_trades.insert(0,"1"); self.e_max_open_trades.grid(row=0,column=1,padx=5)
    tk.Label(f,text="Current engine limit: 1 net position").grid(row=0,column=2,columnspan=4,sticky="w")
    tk.Label(f,text="ATR SL ×:").grid(row=1,column=0,sticky="w")
    self.e_atr_sl_r5=tk.Entry(f,width=7); self.e_atr_sl_r5.insert(0,"1.5"); self.e_atr_sl_r5.grid(row=1,column=1)
    tk.Label(f,text="TP1 × SL:").grid(row=1,column=2,sticky="e")
    self.e_atr_tp1_mult=tk.Entry(f,width=7); self.e_atr_tp1_mult.insert(0,"1.2"); self.e_atr_tp1_mult.grid(row=1,column=3)
    tk.Label(f,text="TP2 × SL:").grid(row=1,column=4,sticky="e")
    self.e_atr_tp2_mult=tk.Entry(f,width=7); self.e_atr_tp2_mult.insert(0,"2.2"); self.e_atr_tp2_mult.grid(row=1,column=5)
    tk.Label(f,text="Completed-candle ATR • actual filled entry/quantity • Price % + ROI %",fg="#444").grid(row=2,column=0,columnspan=6,sticky="w")


def _new_profile_defaults(self):
    vals={"e_st_mult":"3.0","e_ema_len":"50","e_ema_slow":"21","e_macd_fast":"12","e_macd_slow":"26","e_macd_signal":"9","e_rsi_ob":"70","e_rsi_os":"30","e_adx_thresh":"20","e_evidence_min_families":"2","e_evidence_family_min_score":"0.35"}
    for name,value in vals.items():
        if hasattr(self,name):
            w=getattr(self,name); w.delete(0,tk.END); w.insert(0,value)
    for name,value in {"v_use_ema_cross":True,"v_use_macd":True,"v_use_rsi":True,"v_use_stoch":True,"v_use_vwap":True,"v_use_vwap_delta":True,"v_vwap_delta_smooth":True,"v_use_vol":True,"v_use_vol_sr":True,"v_use_mtf":True,"v_use_liq_swing":True,"v_use_trendline":True,"v_use_divergence":True,"v_evidence_require_trend":True,"v_evidence_require_independent":True,"v_hold_until_all_reverse":False,"v_use_atr_sl":True}.items():
        if hasattr(self,name): getattr(self,name).set(value)
    if hasattr(self,"v_signal_mode"): self.v_signal_mode.set("ADAPTIVE_EVIDENCE")
    if hasattr(self,"v_st_entry_mode"): self.v_st_entry_mode.set("CURRENT_TREND")
    if hasattr(self,"v_ema_cross_entry_mode"): self.v_ema_cross_entry_mode.set("CURRENT_TREND")
    if hasattr(self,"v_rsi_logic"): self.v_rsi_logic.set("CROSS_MA")
    if hasattr(self,"e_lev"):
        self.e_lev.delete(0,tk.END); self.e_lev.insert(0,"5")

def r5_init(self,root):
    fresh=not Path(CONFIG_FILE).exists()
    _orig_init(self,root); _add_controls(self)
    if fresh: _new_profile_defaults(self)
    try:self.e_cooldown_min.grid_configure(row=4,column=1)
    except:pass
    try:
        with open(CONFIG_FILE,encoding="utf-8") as f:c=json.load(f)
        self.e_max_open_trades.delete(0,tk.END); self.e_max_open_trades.insert(0,c.get("max_open_trades",1))
        self.e_atr_sl_r5.delete(0,tk.END); self.e_atr_sl_r5.insert(0,c.get("atr_sl_mult",1.5))
        self.e_atr_tp1_mult.delete(0,tk.END); self.e_atr_tp1_mult.insert(0,c.get("atr_tp1_mult",1.2))
        self.e_atr_tp2_mult.delete(0,tk.END); self.e_atr_tp2_mult.insert(0,c.get("atr_tp2_mult",2.2))
    except:pass

def r5_save(self):
    _orig_save(self)
    try:
        with open(CONFIG_FILE,encoding="utf-8") as f:c=json.load(f)
        c.update(config_schema_version=9,max_open_trades=self.e_max_open_trades.get(),
                 atr_sl_mult=self.e_atr_sl_r5.get(),atr_tp1_mult=self.e_atr_tp1_mult.get(),
                 atr_tp2_mult=self.e_atr_tp2_mult.get(),use_atr_sl=bool(self.v_use_atr_sl.get()))
        with open(CONFIG_FILE,"w",encoding="utf-8") as f:json.dump(c,f,indent=4)
    except Exception as e:self.log(f"R5 config extension warning: {e}")

def r5_load(self):
    _orig_load(self); _add_controls(self)
    try:
        with open(CONFIG_FILE,encoding="utf-8") as f:c=json.load(f)
        self.e_max_open_trades.delete(0,tk.END); self.e_max_open_trades.insert(0,c.get("max_open_trades",1))
        self.e_atr_sl_r5.delete(0,tk.END); self.e_atr_sl_r5.insert(0,c.get("atr_sl_mult",1.5))
        self.e_atr_tp1_mult.delete(0,tk.END); self.e_atr_tp1_mult.insert(0,c.get("atr_tp1_mult",1.2))
        self.e_atr_tp2_mult.delete(0,tk.END); self.e_atr_tp2_mult.insert(0,c.get("atr_tp2_mult",2.2))
    except:pass

def r5_pre(self):
    r=_orig_pre(self); n=int(self.e_max_open_trades.get())
    if n<1:raise ValueError("Max Open Trades must be >= 1.")
    if n>1:
        self.log(f"Max Open Trades={n} requested, but this single-symbol bot manages one net position per bot profile. Normalizing to 1.")
        n=1; self.e_max_open_trades.delete(0,tk.END); self.e_max_open_trades.insert(0,"1")
    for a,lim in (("e_atr_sl_r5",10),("e_atr_tp1_mult",20),("e_atr_tp2_mult",50)):
        v=_f(self,a,0)
        if v<=0 or v>lim:raise ValueError(f"{a} must be > 0 and <= {lim}.")
    r["max_open_trades"]=n; return r

def r5_prot(self,symbol,side,entry,qty,margin,slp,tp1p,tp2p,slmode,tpmode,lev,**kw):
    dynamic=bool(self.v_use_atr_sl.get()) and not bool(self.v_hold_until_all_reverse.get())
    if not dynamic:return _orig_prot(self,symbol,side,entry,qty,margin,slp,tp1p,tp2p,slmode,tpmode,lev)
    atr=get_completed_atr(self,symbol); sm=_f(self,"e_atr_sl_r5",1.5); m1=_f(self,"e_atr_tp1_mult",1.2); m2=_f(self,"e_atr_tp2_mult",2.2)
    sd=atr*sm; d1=sd*m1; d2=sd*m2
    if side=="LONG":sl,tp1,tp2=entry-sd,entry+d1,entry+d2
    else:sl,tp1,tp2=entry+sd,entry-d1,entry-d2
    sl,tp1,tp2=[fx.fx_safe_price(self,symbol,x) for x in (sl,tp1,tp2)]
    if side=="LONG" and not(sl<entry<tp1<tp2):raise RuntimeError("Invalid LONG ATR Dynamic protection.")
    if side=="SHORT" and not(sl>entry>tp1>tp2):raise RuntimeError("Invalid SHORT ATR Dynamic protection.")
    def roi(target):
        try:
            if float(margin)>0:
                pnl=abs(float(self.exchange.calc_profit(side,symbol,qty,entry,float(target))))
                return pnl/float(margin)*100.0
        except Exception:
            pass
        return abs(float(target)-entry)/entry*max(float(lev),1.0)*100.0
    sr,tr1r,tr2r=roi(sl),roi(tp1),roi(tp2)
    self.log(f"SL/TP ENGINE — ATR DYNAMIC | Entry={entry:.12g} | ATR={atr:.12g} | SL={sm:.2f} ATR")
    self.log(f"SL={sl:.12g} | Price -{sd/entry*100:.4f}% | ROI -{sr:.2f}%")
    self.log(f"TP1={tp1:.12g} | Price +{d1/entry*100:.4f}% | ROI +{tr1r:.2f}% | {m1:.2f}R")
    self.log(f"TP2={tp2:.12g} | Price +{d2/entry*100:.4f}% | ROI +{tr2r:.2f}% | {m2:.2f}R")
    return sl,tp1,tp2,sd/entry,d1/entry,d2/entry

def r5_start(self):
    _orig_start(self)
    if self.is_running:
        self.log(f"MAX OPEN TRADES: {self.e_max_open_trades.get()} net position per bot/symbol.")
        self.log(f"ATR DYNAMIC SL/TP: {'ON' if self.v_use_atr_sl.get() else 'OFF'} | SL={self.e_atr_sl_r5.get()} ATR | TP1={self.e_atr_tp1_mult.get()}x SL | TP2={self.e_atr_tp2_mult.get()}x SL")

GUI.__init__=r5_init; GUI.save_settings=r5_save; GUI.load_settings=r5_load
GUI._validate_strategy_preflight=r5_pre; GUI.calculate_protection_prices=r5_prot; GUI.start_bot=r5_start
UniversalFuturesBotGUI=GUI
