"""Construit web/index.html (page autonome) à partir du modèle.

    python -m web.build                       # même domaine que la page (API servie au même endroit)
    python -m web.build --api-url https://strategylab-api-xxxx.run.app --out dist/index.html
"""
import argparse
import json
import re
from pathlib import Path

from ui import tv_chart

HERE = Path(__file__).resolve().parent


def build(api_url: str = "") -> str:
    if api_url and not re.match(r"^https://[^\s\"'<>\\]+$|^http://localhost(:\d+)?$", api_url):
        raise ValueError("L'adresse de l'API doit commencer par https:// et ne contenir ni espace ni guillemet.")
    html = (HERE / "index.template.html").read_text(encoding="utf-8")
    return (html.replace("__LWC_URL__", tv_chart.LWC_URL)
            .replace("__RENDER_JS__", tv_chart.RENDER_JS)
            .replace("__THEME__", json.dumps(tv_chart.THEME))
            .replace("__API_URL__", api_url.rstrip("/")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="")
    parser.add_argument("--out", default=str(HERE / "index.html"))
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(args.api_url), encoding="utf-8")
    print(f"{out} écrit ({out.stat().st_size / 1024:.0f} Ko)")


if __name__ == "__main__":
    main()
