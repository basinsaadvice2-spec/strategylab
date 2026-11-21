"""Faux Streamlit + lanceur, pour exécuter l'application SANS navigateur ni Streamlit installé.
Utilisé par test_streamlit_app.py : l'application est lancée dans un processus Python propre."""

STUB_INIT = '''
import datetime, functools, sys

LOG = {"metrics": [], "html": [], "errors": [], "warnings": [], "infos": [], "tables": 0, "dataframes": 0,
       "areas": 0, "captions": [], "downloads": 0, "labels": [], "codes": []}


class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name): return getattr(sys.modules["streamlit"], name)


class _Secrets:
    def get(self, key, default=None): raise FileNotFoundError("pas de fichier de secrets")


secrets = _Secrets()
sidebar = Ctx()
session_state = {}


def _labels(options, fmt):
    if fmt:
        LOG["labels"].extend(str(fmt(o)) for o in options)       # exerce aussi les fonctions de libellé


def set_page_config(*a, **k): pass
def markdown(*a, **k): pass
def write(*a, **k): pass
def caption(text, *a, **k): LOG["captions"].append(str(text))
def error(text, *a, **k): LOG["errors"].append(str(text))
def warning(text, *a, **k): LOG["warnings"].append(str(text))
def info(text, *a, **k): LOG["infos"].append(str(text))
def code(text, *a, **k): LOG["codes"].append(str(text))
def stop(): raise SystemExit("st.stop")
def cache_resource(f=None, **kw): return functools.lru_cache(maxsize=None)(f) if callable(f) else (lambda g: functools.lru_cache(maxsize=None)(g))
def cache_data(f=None, **kw): return f if callable(f) else (lambda g: g)
def columns(spec, **k): return [Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
def tabs(names): return [Ctx() for _ in names]
def container(**k): return Ctx()
def radio(label, options, index=0, format_func=None, **k): _labels(options, format_func); return options[index or 0]
def selectbox(label, options, index=0, format_func=None, **k): _labels(options, format_func); return options[index or 0]
def number_input(label, min_value=None, max_value=None, value=None, **k): return value if value is not None else min_value
def date_input(label, value=None, **k): return value or datetime.date.today()
def metric(label, value, delta=None, **k): LOG["metrics"].append((label, str(value), delta))
def table(df, *a, **k): LOG["tables"] += 1
def dataframe(df, *a, **k): LOG["dataframes"] += 1
def area_chart(df, *a, **k): LOG["areas"] += 1
def download_button(*a, **k): LOG["downloads"] += 1
'''

STUB_COMPONENTS_V1 = '''
import streamlit
def html(content, height=None, scrolling=None):
    streamlit.LOG["html"].append({"size": len(content), "height": height, "content": content})
'''

RUNNER = '''
import json, sys, runpy, io, urllib.request
import numpy as np, pandas as pd

mode, app_path = sys.argv[1], sys.argv[2]
rng = np.random.default_rng(5); n = 2300
dates = pd.bdate_range("2017-01-02", periods=n)
close = 60 * np.exp(np.cumsum(rng.normal(0, 0.017, n)))
rows = ["observation_date,DCOILWTICO"] + [f"{d.date()},{c:.2f}" for d, c in zip(dates, close)]
rows[5] = f"{dates[4].date()},."
CSV = "\\n".join(rows).encode()

class Resp:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(req, timeout=None):
    if mode == "offline":
        raise OSError("réseau coupé")
    return Resp(CSV)
urllib.request.urlopen = fake_urlopen

import streamlit
result = {"stopped": None}
try:
    runpy.run_path(app_path, run_name="__main__")
except SystemExit as exc:
    result["stopped"] = str(exc)
log = streamlit.LOG
result.update({k: v for k, v in log.items() if k != "html"})
result["html"] = [{"size": h["size"], "height": h["height"], "has_lib": "lightweight-charts@4.2.0" in h["content"],
                   "has_attr": "tradingview.com" in h["content"], "n_markers": h["content"].count('"arrowUp"')} for h in log["html"]]
print("RESULT:" + json.dumps(result))
'''
