import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np, pandas as pd
from api.server import create_server
from data.live_providers import LiveDataProvider
logging.disable(logging.CRITICAL)
rng = np.random.default_rng(5); n = 2300
dates = pd.bdate_range("2017-01-02", periods=n)
close = 60 * np.exp(np.cumsum(rng.normal(0, 0.017, n)))
csv = ("\n".join(["observation_date,DCOILWTICO"] + [f"{d.date()},{c:.2f}" for d, c in zip(dates, close)])).encode()
create_server(("127.0.0.1", int(sys.argv[1])), LiveDataProvider(http_get=lambda url: csv)).serve_forever()
