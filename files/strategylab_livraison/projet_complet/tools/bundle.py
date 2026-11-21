"""
Assemble l'application Streamlit ET tout son code Python en UN SEUL fichier (app.py).

    python -m tools.bundle --out deliver

Écrit deliver/app.py, deliver/requirements.txt et deliver/.streamlit/config.toml : c'est tout ce qu'il faut
mettre sur GitHub. Les modules du projet sont embarqués tels quels (aucune réécriture) et enregistrés au
démarrage ; le build vérifie que le code embarqué est identique, caractère pour caractère, aux sources.
"""
import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "ui/streamlit_app.py"
INTERNAL = {"config", "data", "indicators", "strategy", "risk", "portfolio", "backtest", "metrics", "analysis", "ui"}


def _module_file(name: str):
    path = ROOT.joinpath(*name.split("."))
    if path.with_suffix(".py").exists():
        return path.with_suffix(".py")
    if (path / "__init__.py").exists():
        return path / "__init__.py"
    return None


def _deps(name: str, source: str) -> list:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            targets = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        for t in targets:
            if t.split(".")[0] in INTERNAL and _module_file(t) and t != name and t not in found:
                found.append(t)
    return found


def collect() -> tuple:
    """Retourne (paquets, modules dans l'ordre de chargement, source de l'application)."""
    app_src = (ROOT / ENTRY).read_text(encoding="utf-8")
    order, seen, packages = [], set(), set()

    def visit(name: str, stack=()):
        if name in seen:
            return
        if name in stack:
            raise RuntimeError("Dépendance circulaire : " + " -> ".join(stack + (name,)))
        file = _module_file(name)
        src = file.read_text(encoding="utf-8")
        for dep in _deps(name, src):
            visit(dep, stack + (name,))
        seen.add(name)
        packages.add(name.rpartition(".")[0])
        if file.name != "__init__.py":
            order.append((name, src))

    for dep in _deps("__app__", app_src):
        visit(dep)
    return sorted(p for p in packages if p), order, app_src


def _literal(src: str) -> str:
    assert src.endswith("\n"), "chaque module doit se terminer par un retour à la ligne"
    return '"""' + src.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + '"""'


_HEAD = '''"""
StrategyLab — application web 100 % Python (Streamlit), en UN SEUL fichier.
Fichier généré par tools/bundle.py à partir du projet complet : ne pas modifier à la main.
Python fait tout (données, indicateurs, backtest, projection, interface) ; le graphique est TradingView Lightweight Charts.
Simulateur : aucun ordre réel. Un backtest ne garantit jamais la performance future.
"""
import sys
import types

_PACKAGES = __PACKAGES__

# Modules du projet, embarqués tels quels, dans leur ordre de chargement.
_SOURCES = {
__SOURCES__
}


def _install():
    for pkg in _PACKAGES:
        if pkg not in sys.modules:
            module = types.ModuleType(pkg)
            module.__path__ = []
            sys.modules[pkg] = module
    for name, source in _SOURCES.items():
        if name in sys.modules:          # Streamlit relance le script à chaque interaction : on ne recharge pas
            continue
        module = types.ModuleType(name)
        module.__file__ = "<strategylab:" + name + ">"
        module.__package__ = name.rpartition(".")[0]
        sys.modules[name] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        setattr(sys.modules[module.__package__], name.rpartition(".")[2], module)


_install()

# ===================================================================== APPLICATION
'''


def build() -> tuple:
    packages, order, app_src = collect()
    for line in ("from pathlib import Path\n",
                 "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # lancement local depuis le projet complet\n"):
        assert app_src.count(line) == 1, line
        app_src = app_src.replace(line, "")
    body = "\n".join(f"    {name!r}: {_literal(src)}," for name, src in order)
    text = _HEAD.replace("__PACKAGES__", repr(packages)).replace("__SOURCES__", body) + app_src.split('"""', 2)[2].lstrip("\n")
    # Contrôle d'intégrité : le code embarqué doit être identique aux sources, et le fichier doit compiler.
    compile(text, "app.py", "exec")
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_SOURCES":
            embedded = ast.literal_eval(node.value)
            assert embedded == dict(order), "le code embarqué diffère des sources"
    return text, [n for n, _ in order]


REQUIREMENTS = "streamlit>=1.37,<2\npandas>=2.2,<4\nnumpy>=2.0,<3\n"
CONFIG = ('[theme]\nbase = "dark"\nprimaryColor = "#2962ff"\nbackgroundColor = "#131722"\n'
          'secondaryBackgroundColor = "#1e222d"\ntextColor = "#d1d4dc"\nfont = "sans serif"\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="deliver")
    out = Path(parser.parse_args().out)
    text, modules = build()
    (out / ".streamlit").mkdir(parents=True, exist_ok=True)
    (out / "app.py").write_text(text, encoding="utf-8")
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (out / ".streamlit" / "config.toml").write_text(CONFIG, encoding="utf-8")
    print(f"{out / 'app.py'} : {len(text) / 1024:.0f} Ko, {len(modules)} modules embarqués")


if __name__ == "__main__":
    main()
