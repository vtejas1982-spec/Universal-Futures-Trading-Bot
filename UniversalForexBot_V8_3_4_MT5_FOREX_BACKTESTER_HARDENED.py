import csv, math, tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd

BOT_PATH = Path(__file__).with_name("UniversalForexBot_V8_3_4_MT5_FOREX_HARDENED.py")
spec=importlib.util.spec_from_file_location("fx_live", str(BOT_PATH))
fx=importlib.util.module_from_spec(spec); spec.loader.exec_module(fx)

APP_VERSION="V8.3.4-FOREX-HARDENED-BT"
APP_TITLE="Universal Forex Bot V8.3.4 — MT5 Forex Hardened Strategy Backtester"

DEFAULTS={
    "capital":10000.0,"risk_pct":1.0,"contract_size":100000.0,"commission_per_lot":0.0,
    "spread_pips":1.2,"slippage_pips":0.2,"max_trades":0,"cooldown_bars":0,
    "signal_mode":"ADAPTIVE_SCORE","min_score":1,"adaptive_edge":0.18,"adaptive_min_weight":3.5,
    "use_st":True,"st_len":10,"st_mult":2.0,"st_source":"CLOSE","st_change_atr":True,"st_entry":"FRESH_FLIP",
    "use_ema":True,"ema_len":200,"use_ema_cross":False,"ema_fast":9,"ema_slow":20,"ema_cross_entry":"FRESH_CROSS",
    "use_macd":False,"macd_fast":12,"macd_slow":26,"macd_signal":9,
    "use_rsi":False,"rsi_len":14,"rsi_ob":80,"rsi_os":20,"rsi_logic":"REVERSAL_ZONE","rsi_ma_type":"EMA","rsi_ma_len":9,
    "use_bb":False,"bb_len":20,"bb_std":2.0,"use_stoch":False,"stoch_k":14,"stoch_smooth":3,"stoch_d":3,
    "use_vwap":False,"vwap_len":50,"use_vwap_delta":False,"vwap_delta_smooth":False,"vwap_delta_smooth_len":21,"vwap_delta_baseline":50,"vwap_delta_logic":"CURRENT_TREND",
    "use_vidya":False,"vidya_len":10,"vidya_momentum":20,"vidya_band":2.0,"vidya_entry":"CURRENT_TREND",
    "use_nwe":False,"nwe_bandwidth":8.0,"nwe_mult":3.0,"nwe_entry":"FRESH_CROSS","nwe_repaint":False,
    "use_atr":False,"atr_min_pct":0.30,"use_vol":True,"vol_len":20,"use_adx":True,"adx_thresh":20,"use_mtf":True,
    "use_liq_swing":True,"liq_len":14,"liq_area":"Wick Extremity","liq_filter":"Count","liq_filter_value":0.0,
    "use_trendline":True,"trend_len":14,"trend_min_dist":5,"trend_buffer":0.0,"trend_retest":3,"trend_entry":"FRESH_BREAK",
    "use_divergence":True,"div_pivot":5,"div_max_pivots":10,"div_max_bars":100,"div_type":"Regular/Hidden","div_source":"Close",
    "div_cci_len":10,"div_mom_len":10,"div_vwmacd_fast":12,"div_vwmacd_slow":26,"div_cmf_len":21,"div_mfi_len":14,
    "use_vol_sr":True,"sr_volume_ma":6,"sr_vote_mode":"MAJORITY","sr_entry_mode":"CURRENT_ZONE","sr_tf1":"Chart","sr_tf2":"4h","sr_tf3":"D","sr_tf4":"W",
    "sl_mode":"PIPS","sl_pips":25.0,"sl_pct":0.25,"tp1_pips":25.0,"tp2_pips":50.0,"tp1_close":50.0,"tp2_close":50.0,"atr_sl_mult":1.5,
    "use_atr_sl":False,"use_trailing":False,"trail_activation_pips":30.0,"trail_distance_pips":20.0,
    "use_session":False,"session_start":"07:00","session_end":"20:00","friday_protect":True,"friday_cutoff":"18:00",
    "daily_loss_pct":3.0,"daily_profit_pct":0.0,"max_dd_pct":5.0,"emergency_capital_pct":30.0,"max_loss_streak":3,"no_same_candle":True,"hold_until_all_reverse":True,
}

def load_csv(path):
    d=pd.read_csv(path)
    cols={c.lower().strip():c for c in d.columns}
    aliases={'time':'time','timestamp':'time','datetime':'datetime','date':'datetime','open':'open','high':'high','low':'low','close':'close','volume':'vol','vol':'vol','tick_volume':'vol'}
    rename={cols[k]:v for k,v in aliases.items() if k in cols}
    d=d.rename(columns=rename)
    for c in ('open','high','low','close'):
        if c not in d: raise ValueError(f"CSV missing {c}")
        d[c]=pd.to_numeric(d[c],errors='coerce')
    if 'vol' not in d: d['vol']=1.0
    d['vol']=pd.to_numeric(d['vol'],errors='coerce').fillna(1.0)
    if 'datetime' in d:
        d['datetime']=pd.to_datetime(d['datetime'],utc=True,errors='coerce')
    elif 'time' in d:
        x=d['time']
        unit='ms' if pd.to_numeric(x,errors='coerce').median()>1e11 else 's'
        d['datetime']=pd.to_datetime(x,unit=unit,utc=True,errors='coerce')
    else: raise ValueError('CSV needs datetime/date or time/timestamp')
    d=d.dropna(subset=['datetime','open','high','low','close']).sort_values('datetime').drop_duplicates('datetime').reset_index(drop=True)
    d['time']=(d['datetime'].astype('int64')//10**6).astype('int64')
    return d[['time','datetime','open','high','low','close','vol']]

def build_frame(df,c):
    x=df.copy()
    x=fx.calculate_supertrend(x,int(c['st_len']),float(c['st_mult']),c['st_source'],bool(c['st_change_atr']))
    x=fx.calculate_adx(x)
    x['ema']=x.close.ewm(span=int(c['ema_len']),adjust=False).mean()
    x['ema_fast']=x.close.ewm(span=int(c['ema_fast']),adjust=False).mean()
    x['ema_slow']=x.close.ewm(span=int(c['ema_slow']),adjust=False).mean()
    if c['use_macd']: x=fx.calculate_macd(x,int(c['macd_fast']),int(c['macd_slow']),int(c['macd_signal']))
    if c['use_rsi']: x=fx.calculate_rsi(x,int(c['rsi_len'])); x=fx.calculate_rsi_ma(x,c['rsi_ma_type'],int(c['rsi_ma_len']))
    if c['use_bb']: x=fx.calculate_bollinger(x,int(c['bb_len']),float(c['bb_std']))
    if c['use_stoch']: x=fx.calculate_stochastic(x,int(c['stoch_k']),int(c['stoch_smooth']),int(c['stoch_d']))
    if c['use_vwap']: x=fx.calculate_vwap(x,int(c['vwap_len']))
    if c['use_vwap_delta']: x=fx.calculate_vwap_delta(x,bool(c['vwap_delta_smooth']),int(c['vwap_delta_smooth_len']),int(c['vwap_delta_baseline']))
    if c['use_vidya']: x=fx.calculate_vidya(x,int(c['vidya_len']),int(c['vidya_momentum']),float(c['vidya_band']))
    if c['use_nwe']: x=fx.calculate_nadaraya_watson_envelope(x,float(c['nwe_bandwidth']),float(c['nwe_mult']),bool(c['nwe_repaint']))
    x['vol_ma']=x.vol.rolling(int(c['vol_len'])).mean()
    if c['use_liq_swing']: x=fx.calculate_liquidity_swings(x,int(c['liq_len']),c['liq_area'],c['liq_filter'],float(c['liq_filter_value']))
    if c['use_trendline']: x=fx.calculate_trendline_breakout(x,int(c['trend_len']),int(c['trend_min_dist']),float(c['trend_buffer']),int(c['trend_retest']))
    divcfg=dict(c)
    if c['use_divergence']: x=fx.calculate_divergence_module(x,divcfg)
    if c['use_vol_sr']: x=fx._volume_sr_base_series(x,divcfg)
    # 4H MTF; only completed 4H candles are merged into the base series.
    if c['use_mtf']:
        z=x.set_index('datetime').resample('4h',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','vol':'sum'}).dropna()
        z['ema200']=z.close.ewm(span=200,adjust=False).mean(); z['available_at']=z.index+pd.Timedelta(hours=4)
        z=z.reset_index(drop=False).rename(columns={'datetime':'mtf_time'})
        x=pd.merge_asof(x.sort_values('datetime'),z[['available_at','close','ema200']].rename(columns={'close':'mtf_close'}).sort_values('available_at'),left_on='datetime',right_on='available_at',direction='backward')
    else:
        x['mtf_close']=np.nan;x['ema200']=np.nan
    return x

def modules_at(x,i,c):
    if i<3:return [],True,True,True,True,True
    q=x.iloc[i]; p=x.iloc[i-1]; pp=x.iloc[i-2]; close=float(q.close)
    atr_pct=float(q.atr)/close*100 if close else 0
    atr_pass=(not c['use_atr']) or atr_pct>=float(c['atr_min_pct'])
    vol_pass=(not c['use_vol']) or float(q.vol)>float(q.vol_ma)
    adx_pass=(not c['use_adx']) or float(q.adx)>=float(c['adx_thresh'])
    mtf_bull=(not c['use_mtf']) or (np.isfinite(q.get('mtf_close',np.nan)) and q.mtf_close>q.ema200)
    mtf_bear=(not c['use_mtf']) or (np.isfinite(q.get('mtf_close',np.nan)) and q.mtf_close<q.ema200)
    mods=[]
    candle_bull=float(q.close)>float(q.open); candle_bear=float(q.close)<float(q.open)
    st_trend=bool(q.trend); st_flip_bull=(not bool(pp.trend)) and bool(q.trend); st_flip_bear=bool(pp.trend) and not bool(q.trend)
    if c['use_st']: mods.append(('ST',(st_trend if c['st_entry']=='CURRENT_TREND' else st_flip_bull),(not st_trend if c['st_entry']=='CURRENT_TREND' else st_flip_bear)))
    if c['use_ema']: mods.append(('EMA',close>float(q.ema),close<float(q.ema)))
    if c['use_ema_cross']:
        up=float(pp.ema_fast)<=float(pp.ema_slow) and float(q.ema_fast)>float(q.ema_slow); dn=float(pp.ema_fast)>=float(pp.ema_slow) and float(q.ema_fast)<float(q.ema_slow)
        mods.append(('EMA_CROSS',(float(q.ema_fast)>float(q.ema_slow)) if c['ema_cross_entry']=='CURRENT_TREND' else up,(float(q.ema_fast)<float(q.ema_slow)) if c['ema_cross_entry']=='CURRENT_TREND' else dn))
    if c['use_macd']: mods.append(('MACD',float(pp.macd)<=float(pp.macd_signal) and float(q.macd)>float(q.macd_signal),float(pp.macd)>=float(pp.macd_signal) and float(q.macd)<float(q.macd_signal)))
    if c['use_rsi']:
        rb=float(q.rsi)<=float(c['rsi_os']); rs=float(q.rsi)>=float(c['rsi_ob']); cb=float(pp.rsi)<=float(pp.rsi_ma) and float(q.rsi)>float(q.rsi_ma); cs=float(pp.rsi)>=float(pp.rsi_ma) and float(q.rsi)<float(q.rsi_ma)
        mods.append(('RSI',(rb if c['rsi_logic']!='CROSS_MA' else cb) or (c['rsi_logic']=='EITHER' and cb),(rs if c['rsi_logic']!='CROSS_MA' else cs) or (c['rsi_logic']=='EITHER' and cs)))
    if c['use_bb']: mods.append(('BB',close>float(q.bb_mid),close<float(q.bb_mid)))
    if c['use_stoch']: mods.append(('STOCH',float(pp.stoch_k)<=float(pp.stoch_d) and float(q.stoch_k)>float(q.stoch_d),float(pp.stoch_k)>=float(pp.stoch_d) and float(q.stoch_k)<float(q.stoch_d)))
    if c['use_vwap']: mods.append(('VWAP',close>float(q.vwap),close<float(q.vwap)))
    if c['use_vwap_delta']:
        b=float(q.vwap_delta)>float(q.vwap_delta_baseline); s=float(q.vwap_delta)<float(q.vwap_delta_baseline); mods.append(('VWAP_DELTA',b,s))
    if c['use_vidya']: mods.append(('VIDYA',bool(q.vidya_cross_up) if c['vidya_entry']=='FRESH_FLIP' else bool(q.vidya_trend_up),bool(q.vidya_cross_down) if c['vidya_entry']=='FRESH_FLIP' else not bool(q.vidya_trend_up)))
    if c['use_nwe']:
        b=(close<float(q.nwe_lower) and float(p.close)>=float(p.nwe_lower)) if c['nwe_entry']=='FRESH_CROSS' else float(q.nwe_out)>float(p.nwe_out)
        s=(close>float(q.nwe_upper) and float(p.close)<=float(p.nwe_upper)) if c['nwe_entry']=='FRESH_CROSS' else float(q.nwe_out)<float(p.nwe_out)
        mods.append(('NWE',b,s))
    if c['use_liq_swing']: mods.append(('LIQ_SWING',float(q.liq_swing_trend)>0,float(q.liq_swing_trend)<0))
    if c['use_trendline']:
        if c['trend_entry']=='FRESH_BREAK': b=bool(q.trendline_break_up);s=bool(q.trendline_break_down)
        elif c['trend_entry']=='BREAK_RETEST': b=bool(q.trendline_retest_up);s=bool(q.trendline_retest_down)
        else:b=float(q.trendline_state)>0;s=float(q.trendline_state)<0
        mods.append(('TRENDLINE',b,s))
    if c['use_mtf']: mods.append(('MTF',mtf_bull,mtf_bear))
    if c['use_divergence']: mods.append(('DIVERGENCE',bool(q.div_bull_signal),bool(q.div_bear_signal)))
    if c['use_vol_sr']: mods.append(('VOL_SR',bool(q.sr_bull),bool(q.sr_bear)))
    if c['use_vol'] and vol_pass: mods.append(('VOL',candle_bull,candle_bear))
    if c['use_adx'] and adx_pass: mods.append(('ADX',float(q.plus_di)>float(q.minus_di),float(q.minus_di)>float(q.plus_di)))
    if c['use_atr'] and atr_pass: mods.append(('ATR',candle_bull,candle_bear))
    return mods,atr_pass,vol_pass,adx_pass,mtf_bull,mtf_bear

def signal_at(x,i,c):
    mods,ap,vp,dp,mb,ms=modules_at(x,i,c)
    b,s,bs,ss=fx.StrategyEngine.decide_signal(mods,c['signal_mode'],int(c['min_score']),ap,vp,dp,mb,ms,float(c['adaptive_edge']),float(c['adaptive_min_weight']))
    return ('BUY' if b else 'SELL' if s else 'NONE'),bs,ss,mods

def in_window(ts,c):
    if not c['use_session']: return True
    hm=ts.hour*60+ts.minute; a=int(c['session_start'][:2])*60+int(c['session_start'][3:]); b=int(c['session_end'][:2])*60+int(c['session_end'][3:])
    return a<=hm<=b if a<=b else (hm>=a or hm<=b)

def backtest(df,c,progress=None):
    x=build_frame(df,c); equity=float(c['capital']); start=equity; peak=equity; daily_start=equity; daily_day=None; trades=[]; pos=None; cooldown=0; last_entry=-999; max_dd=0.0; loss_streak=0; halted_reason=None
    spread=float(c['spread_pips'])*0.0001; slip=float(c['slippage_pips'])*0.0001
    for i in range(250,len(x)-1):
        ts=x.datetime.iloc[i]
        if daily_day!=ts.date(): daily_day=ts.date(); daily_start=equity; loss_streak=0
        peak=max(peak,equity)
        current_dd=(peak-equity)/peak if peak else 0.0
        max_dd=max(max_dd,current_dd)
        if float(c.get('emergency_capital_pct',0))>0 and equity <= start*(1-float(c['emergency_capital_pct'])/100):
            halted_reason='EMERGENCY_CAPITAL_STOP'
            if pos:
                px=float(x.close.iloc[i]); pnl=((px-pos['entry']) if pos['side']=='BUY' else (pos['entry']-px))*pos['qty']*c['contract_size']; equity+=pnl; trades.append({**pos,'exit':px,'reason':halted_reason,'pnl':pnl}); pos=None
            break
        if float(c.get('max_dd_pct',0))>0 and current_dd >= float(c['max_dd_pct'])/100:
            halted_reason='MAX_DRAWDOWN_STOP'
            if pos:
                px=float(x.close.iloc[i]); pnl=((px-pos['entry']) if pos['side']=='BUY' else (pos['entry']-px))*pos['qty']*c['contract_size']; equity+=pnl; trades.append({**pos,'exit':px,'reason':halted_reason,'pnl':pnl}); pos=None
            break
        if loss_streak >= int(c.get('max_loss_streak',0)) > 0:
            halted_reason='LOSS_STREAK_STOP'
            if pos:
                px=float(x.close.iloc[i]); pnl=((px-pos['entry']) if pos['side']=='BUY' else (pos['entry']-px))*pos['qty']*c['contract_size']; equity+=pnl; trades.append({**pos,'exit':px,'reason':halted_reason,'pnl':pnl}); pos=None
            break
        if cooldown>0: cooldown-=1
        if pos:
            # Manage current position on completed bar i.
            hi,lo=float(x.high.iloc[i]),float(x.low.iloc[i]); exit_px=None; reason=None
            if pos['side']=='BUY':
                if lo<=pos['sl']: exit_px=pos['sl']; reason='SL'
                elif hi>=pos['tp2']: exit_px=pos['tp2']; reason='TP2'
                elif hi>=pos['tp1'] and not pos['tp1_done']:
                    part=pos['qty']*float(c['tp1_close'])/100.0; pnl=(pos['tp1']-pos['entry'])*part*c['contract_size']; equity+=pnl; pos['qty']-=part; pos['tp1_done']=True; pos['sl']=pos['entry']
            else:
                if hi>=pos['sl']: exit_px=pos['sl']; reason='SL'
                elif lo<=pos['tp2']: exit_px=pos['tp2']; reason='TP2'
                elif lo<=pos['tp1'] and not pos['tp1_done']:
                    part=pos['qty']*float(c['tp1_close'])/100.0; pnl=(pos['entry']-pos['tp1'])*part*c['contract_size']; equity+=pnl; pos['qty']-=part; pos['tp1_done']=True; pos['sl']=pos['entry']
            if exit_px is not None:
                pnl=((exit_px-pos['entry']) if pos['side']=='BUY' else (pos['entry']-exit_px))*pos['qty']*c['contract_size']
                equity+=pnl; equity-=float(c['commission_per_lot'])*pos['orig_qty']; trades.append({**pos,'exit':exit_px,'reason':reason,'pnl':pnl}); pos=None; cooldown=int(c['cooldown_bars']); loss_streak = loss_streak + 1 if pnl < 0 else 0
        if pos is None and cooldown==0 and in_window(ts,c) and (not c['friday_protect'] or not (ts.weekday()==4 and ts.hour*60+ts.minute>=int(c['friday_cutoff'][:2])*60+int(c['friday_cutoff'][3:]))):
            if c['daily_loss_pct']>0 and equity<=daily_start*(1-c['daily_loss_pct']/100): continue
            if c['daily_profit_pct']>0 and equity>=daily_start*(1+c['daily_profit_pct']/100): continue
            sig,bs,ss,mods=signal_at(x,i,c)
            if sig=='NONE' or (c['no_same_candle'] and i==last_entry): continue
            entry=float(x.open.iloc[i+1]) + (spread/2+slip if sig=='BUY' else -spread/2-slip)
            pip=0.0001
            if c['sl_mode']=='PIPS': sl_dist=float(c['sl_pips'])*pip; tp1_dist=float(c['tp1_pips'])*pip; tp2_dist=float(c['tp2_pips'])*pip
            elif c['sl_mode']=='ATR': sl_dist=float(x.atr.iloc[i])*float(c['atr_sl_mult']); tp1_dist=float(c['tp1_pips'])*pip; tp2_dist=float(c['tp2_pips'])*pip
            else: sl_dist=entry*float(c['sl_pct'])/100; tp1_dist=entry*float(c['tp1_pips'])/100; tp2_dist=entry*float(c['tp2_pips'])/100
            risk_money=equity*float(c['risk_pct'])/100; qty=risk_money/(max(sl_dist,1e-9)*float(c['contract_size']))
            qty=max(0.01,round(qty,2)); sl=entry-sl_dist if sig=='BUY' else entry+sl_dist; tp1=entry+tp1_dist if sig=='BUY' else entry-tp1_dist; tp2=entry+tp2_dist if sig=='BUY' else entry-tp2_dist
            pos={'side':sig,'entry':entry,'qty':qty,'orig_qty':qty,'sl':sl,'tp1':tp1,'tp2':tp2,'tp1_done':False,'signal_bar':i}
            last_entry=i
        peak=max(peak,equity); max_dd=max(max_dd,(peak-equity)/peak if peak else 0)
        if progress and i%100==0: progress(i,len(x))
    if pos:
        px=float(x.close.iloc[-1]); pnl=((px-pos['entry']) if pos['side']=='BUY' else (pos['entry']-px))*pos['qty']*c['contract_size']; equity+=pnl; trades.append({**pos,'exit':px,'reason':'EOD','pnl':pnl})
    wins=sum(t['pnl']>0 for t in trades); losses=sum(t['pnl']<0 for t in trades); net=equity-start
    return {'starting_equity':start,'ending_equity':equity,'net_pnl':net,'return_pct':net/start*100,'trades':len(trades),'wins':wins,'losses':losses,'win_rate':wins/len(trades)*100 if trades else 0,'max_drawdown_pct':max_dd*100,'halted_reason':halted_reason,'trades_detail':trades}

class App:
    def __init__(self,root):
        self.root=root; root.title(APP_TITLE); root.geometry('1200x820'); self.path=tk.StringVar(); self.status=tk.StringVar(value='Load an MT5/Forex OHLCV CSV.'); self.vars={}
        top=ttk.Frame(root); top.pack(fill='x',padx=8,pady=8); ttk.Entry(top,textvariable=self.path).pack(side='left',fill='x',expand=True); ttk.Button(top,text='Load CSV',command=self.load).pack(side='left',padx=5); ttk.Button(top,text='RUN BACKTEST',command=self.run).pack(side='left')
        f=ttk.LabelFrame(root,text='V8.3.3 Forex Backtest Controls'); f.pack(fill='x',padx=8,pady=5)
        fields=[('Capital','capital'),('Risk %','risk_pct'),('Spread pips','spread_pips'),('Slippage pips','slippage_pips'),('SL pips','sl_pips'),('TP1 pips','tp1_pips'),('TP2 pips','tp2_pips'),('Adaptive Edge','adaptive_edge'),('Adaptive Min Weight','adaptive_min_weight'),('Min Score','min_score')]
        for j,(label,key) in enumerate(fields):
            r=j//5; col=(j%5)*2; ttk.Label(f,text=label).grid(row=r,column=col,sticky='e',padx=3,pady=3); v=tk.StringVar(value=str(DEFAULTS[key])); self.vars[key]=v; ttk.Entry(f,textvariable=v,width=10).grid(row=r,column=col+1)
        self.mode=tk.StringVar(value=DEFAULTS['signal_mode']); ttk.Label(f,text='Signal Mode').grid(row=2,column=0,sticky='e'); ttk.Combobox(f,textvariable=self.mode,values=list(fx.SUPPORTED_SIGNAL_MODES),state='readonly',width=18).grid(row=2,column=1)
        self.result=tk.Text(root,height=30); self.result.pack(fill='both',expand=True,padx=8,pady=8); ttk.Label(root,textvariable=self.status).pack(fill='x',padx=8)
    def load(self):
        p=filedialog.askopenfilename(filetypes=[('CSV','*.csv'),('All','*.*')]);
        if p:self.path.set(p); self.status.set('Loaded: '+p)
    def run(self):
        try:
            if not self.path.get(): raise ValueError('Select CSV first.')
            d=load_csv(self.path.get()); c=dict(DEFAULTS); c.update({k:float(v.get()) for k,v in self.vars.items() if k!='min_score'}); c['min_score']=int(float(self.vars['min_score'].get())); c['signal_mode']=self.mode.get()
            self.status.set(f'Building {len(d):,} candles and running V8.3.3...'); self.root.update_idletasks(); m=backtest(d,c); self.result.delete('1.0','end'); self.result.insert('end',pd.Series({k:v for k,v in m.items() if k!='trades_detail'}).to_string()); self.result.insert('end','\n\nLast trades:\n'); self.result.insert('end',pd.DataFrame(m['trades_detail']).tail(20).to_string(index=False)); self.status.set('BACKTEST COMPLETE')
        except Exception as e: messagebox.showerror('Backtest error',str(e)); self.status.set('ERROR: '+str(e))

if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
