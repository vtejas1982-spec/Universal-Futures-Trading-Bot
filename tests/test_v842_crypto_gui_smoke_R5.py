import sys, types, tkinter as tk, importlib.util
stub=types.ModuleType("ccxt"); stub.Exchange=type("Exchange",(),{})
for n in ("bybit","binance","gateio"): setattr(stub,n,type(n,(),{}))
sys.modules["ccxt"]=stub
p="UniversalFuturesBot_V8_4_2_CRYPTO_EVIDENCE_HARDENED_R5.py"
sp=importlib.util.spec_from_file_location("crypto_r5_gui",p); m=importlib.util.module_from_spec(sp); sys.modules["crypto_r5_gui"]=m; sp.loader.exec_module(m)
root=tk.Tk(); root.withdraw(); app=m.UniversalFuturesBotGUI(root)
app.e_max_open_trades.delete(0,tk.END); app.e_max_open_trades.insert(0,"2")
app._validate_strategy_preflight()
assert app.e_max_open_trades.get()=="1"
assert float(app.e_atr_sl_mult.get())==1.5
assert float(app.e_atr_tp1_mult.get())==1.2
assert float(app.e_atr_tp2_mult.get())==2.2
assert app.v_use_atr_sl.get() is True
root.destroy(); print("CRYPTO R5 GUI SMOKE: PASS")
