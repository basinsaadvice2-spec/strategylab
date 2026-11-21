import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests import streamlit_stub as stub
from tools import bundle

ROOT = Path(__file__).resolve().parent.parent


def _workspace(tmp_path, app_source_path=None):
    (tmp_path / "streamlit" / "components").mkdir(parents=True)
    (tmp_path / "streamlit" / "__init__.py").write_text(stub.STUB_INIT, encoding="utf-8")
    (tmp_path / "streamlit" / "components" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "streamlit" / "components" / "v1.py").write_text(stub.STUB_COMPONENTS_V1, encoding="utf-8")
    (tmp_path / "runner.py").write_text(stub.RUNNER, encoding="utf-8")
    if app_source_path:
        shutil.copy(app_source_path, tmp_path / "app.py")


def _run(tmp_path, app_path, mode="online", extra_path=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "TWELVEDATA_API_KEY")}
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path)] + ([extra_path] if extra_path else []))
    proc = subprocess.run([sys.executable, str(tmp_path / "runner.py"), mode, str(app_path)], cwd=str(tmp_path),
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT:")][-1]
    return json.loads(line[len("RESULT:"):])


def _assert_full_page(res):
    assert res["stopped"] is None and res["errors"] == []
    assert [m[0] for m in res["metrics"]] == ["P&L total", "Drawdown maximal", "Nombre de trades", "Trades gagnants", "Profit factor"]
    assert len(res["html"]) == 2 and all(h["has_lib"] and h["has_attr"] for h in res["html"])     # graphique principal + projection
    assert res["tables"] >= 3 and res["areas"] == 1
    assert any("Pétrole (WTI)" in l and "%" in l for l in res["labels"])                          # liste de suivi avec prix et variation
    assert any("Or (XAU/USD)" in c and "TWELVEDATA_API_KEY" in c for c in res["captions"])         # or indiqué indisponible, avec la raison


def test_modular_app_renders_the_whole_page(tmp_path):
    _workspace(tmp_path)
    _assert_full_page(_run(tmp_path, ROOT / "ui" / "streamlit_app.py", extra_path=str(ROOT)))


def test_single_file_bundle_is_self_contained_and_renders_the_whole_page(tmp_path):
    text, modules = bundle.build()
    src = tmp_path / "bundle_src.py"
    src.write_text(text, encoding="utf-8")
    _workspace(tmp_path, src)
    # Aucun accès au projet (pas dans PYTHONPATH, cwd = dossier temporaire) : app.py doit se suffire à lui-même.
    _assert_full_page(_run(tmp_path, tmp_path / "app.py"))
    assert "ui.tv_chart" in modules and "indicators.base" in modules


def test_bundle_embeds_exactly_the_project_sources():
    text, modules = bundle.build()      # build() lève une erreur si le code embarqué diffère des sources
    assert text.count("def _install()") == 1 and "sys.path.insert" not in text
    compile(text, "app.py", "exec")


def test_app_shows_a_clear_message_and_stops_when_no_data_source_answers(tmp_path):
    _workspace(tmp_path)
    res = _run(tmp_path, ROOT / "ui" / "streamlit_app.py", mode="offline", extra_path=str(ROOT))
    assert res["stopped"] == "st.stop" and any("Aucune donnée de marché" in e for e in res["errors"])
    assert res["metrics"] == [] and res["html"] == []
    # la raison exacte est affichée en clair, pour pouvoir diagnostiquer depuis une simple capture d'écran
    assert any("Pétrole" in c and "réseau coupé" in c for c in res["codes"])
