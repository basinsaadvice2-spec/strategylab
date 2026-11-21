import re

import pytest

from web import build as wb


def test_default_build_has_no_leftover_placeholders_and_pins_the_charting_library():
    html = wb.build()
    assert re.findall(r"__[A-Z_]+__", html) == []
    assert "lightweight-charts@4.2.0" in html and "https://www.tradingview.com/" in html
    assert 'var BAKED_API = "";' in html


def test_api_url_is_baked_without_trailing_slash():
    assert 'var BAKED_API = "https://strategylab-api-x.run.app";' in wb.build("https://strategylab-api-x.run.app/")


def test_unsafe_api_urls_are_rejected():
    for bad in ['https://a.example/"; alert(1); "', "http://evil.example", "ftp://x.example",
                "https://has space.example", "javascript:alert(1)", "https://a.example/<script>"]:
        with pytest.raises(ValueError):
            wb.build(bad)


def test_localhost_http_is_allowed_for_local_tests():
    assert 'var BAKED_API = "http://localhost:8080";' in wb.build("http://localhost:8080")


def test_page_builds_ui_with_text_nodes_not_html_strings():
    # Garde-fou : les données venant de l'API ne doivent jamais passer par innerHTML.
    assert "innerHTML" not in wb.build()


def test_address_box_is_never_shown_when_the_address_is_baked_in():
    # La saisie d'adresse est réservée à la page générique (administrateur) : jamais montrée à un utilisateur final.
    assert "!CFG && !BAKED_API" in wb.build("https://strategylab-api-x.run.app")
    assert "adresse" not in wb.build("https://x.run.app").split("function api(")[1].split("function showAlert")[0].split("BAKED_API ?")[0].lower()
