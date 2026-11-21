import json
import pandas as pd
import pytest

from data.live_providers import (DataUnavailable, LiveDataProvider, parse_firestore_bars, parse_fred_api, parse_fred_wti, parse_twelvedata)

FRED = ("observation_date,DCOILWTICO\n2024-01-02,70.0\n2024-01-03,.\n2024-01-04,72.0\n"
        "2024-01-05,-5.0\n2024-01-08,71.0\n")


def _gold_json(n=3):
    return json.dumps({"values": [
        {"datetime": f"2024-01-{i + 1:02d}", "open": "2000", "high": "2010", "low": "1990",
         "close": "2005", "volume": "0"} for i in range(n)]}).encode()


def test_fred_skips_missing_and_non_positive_days():
    df = parse_fred_wti(FRED)
    assert list(df["close"]) == [70.0, 72.0, 71.0]


def test_fred_rebuilds_bars_from_closes():
    df = parse_fred_wti(FRED)
    assert df["open"].iloc[1] == 70.0          # open = clôture précédente
    assert df["high"].iloc[1] == 72.0 and df["low"].iloc[1] == 70.0
    assert (df["volume"] == 0).all()


def test_fred_empty_rejected():
    with pytest.raises(DataUnavailable):
        parse_fred_wti("observation_date,DCOILWTICO\n2024-01-02,.\n")


def test_twelvedata_error_payload_rejected():
    with pytest.raises(DataUnavailable, match="invalid"):
        parse_twelvedata({"status": "error", "message": "invalid key"})


def test_twelvedata_parses_values():
    df = parse_twelvedata(json.loads(_gold_json(2)))
    assert len(df) == 2 and df["close"].iloc[0] == 2005.0


def test_gold_without_key_raises_clear_error():
    p = LiveDataProvider(twelvedata_api_key=None, http_get=lambda url: b"")
    with pytest.raises(DataUnavailable, match="TWELVEDATA_API_KEY"):
        p.get_ohlcv("GOLD")


def test_provider_caches_within_ttl():
    calls = {"n": 0}

    def fake(url):
        calls["n"] += 1
        return FRED.encode()

    p = LiveDataProvider(http_get=fake, ttl_seconds=3600)
    p.get_ohlcv("OIL"); p.get_ohlcv("OIL")
    assert calls["n"] == 1
    assert p.info("OIL")["ohlc_approx"] is True and p.info("OIL")["has_volume"] is False


def test_provider_serves_stale_copy_and_flags_it_when_source_fails():
    state = {"fail": False}

    def fake(url):
        if state["fail"]:
            raise OSError("réseau coupé")
        return FRED.encode()

    p = LiveDataProvider(http_get=fake, ttl_seconds=1)
    first = p.get_ohlcv("OIL")
    state["fail"] = True
    p._cache["OIL"] = (0.0, p._cache["OIL"][1])    # force l'expiration du cache
    again = p.get_ohlcv("OIL")
    assert len(again) == len(first)
    assert "réseau coupé" in p.info("OIL")["stale_error"]


def test_provider_fails_loudly_without_any_copy():
    def fake(url):
        raise OSError("réseau coupé")
    p = LiveDataProvider(http_get=fake)
    with pytest.raises(DataUnavailable):
        p.get_ohlcv("OIL")


def test_api_key_never_appears_in_error_message():
    def fake(url):
        raise OSError("échec pour " + url)         # une erreur qui "fuit" l'URL, donc la clé
    p = LiveDataProvider(twelvedata_api_key="SECRET123", http_get=fake)
    with pytest.raises(DataUnavailable) as exc:
        p.get_ohlcv("GOLD")
    assert "SECRET123" not in str(exc.value)


def test_unknown_symbol_rejected():
    with pytest.raises(ValueError, match="inconnu"):
        LiveDataProvider().get_ohlcv("SILVER")


# ---------- solution de secours : API officielle FRED (clé gratuite facultative) ----------

def _fred_api_json(n=3):
    return json.dumps({"observations": [
        {"date": f"2024-01-{i + 2:02d}", "value": ("." if i == 1 else str(70 + i))} for i in range(n)]}).encode()


def test_fred_api_parser_skips_missing_days_and_rejects_error_payloads():
    df = parse_fred_api(json.loads(_fred_api_json(3)))
    assert list(df["close"]) == [70.0, 72.0]
    with pytest.raises(DataUnavailable, match="clé invalide"):
        parse_fred_api({"error_code": 400, "error_message": "clé invalide"})


def test_oil_falls_back_to_official_fred_api_when_csv_fails():
    def fake(url):
        if "fredgraph" in url:
            raise OSError("403 Forbidden")
        return _fred_api_json(5)

    p = LiveDataProvider(http_get=fake, fred_api_key="KEYFRED")
    assert len(p.get_ohlcv("OIL")) == 4
    assert "API" in p.info("OIL")["source"]


def test_without_fred_key_the_error_names_the_cause_and_the_fix():
    def fake(url):
        raise OSError("403 Forbidden")

    with pytest.raises(DataUnavailable) as exc:
        LiveDataProvider(http_get=fake).get_ohlcv("OIL")
    assert "403 Forbidden" in str(exc.value) and "FRED_API_KEY" in str(exc.value)


def test_fred_key_never_appears_in_error_messages():
    def fake(url):
        raise OSError("échec pour " + url)

    with pytest.raises(DataUnavailable) as exc:
        LiveDataProvider(http_get=fake, fred_api_key="SECRETFRED").get_ohlcv("OIL")
    assert "SECRETFRED" not in str(exc.value)


# ---------- Firebase : lecture de la base alimentée par la fonction planifiée ----------

def _fs_bar(d, volume=0):
    f = {"d": {"stringValue": d}, "o": {"doubleValue": 70.0}, "h": {"doubleValue": 71.0}, "l": {"doubleValue": 69.0},
         "c": {"doubleValue": 70.5}, "v": {"integerValue": str(volume)}}      # les entiers arrivent en texte
    return {"mapValue": {"fields": f}}


def _fs_year(year, dates, volume=0):
    return {"name": f"projects/p/databases/(default)/documents/markets/X/years/{year}",
            "fields": {"year": {"integerValue": str(year)}, "bars": {"arrayValue": {"values": [_fs_bar(d, volume) for d in dates]}}}}


def _recent_dates(n=40):
    return [str(d.date()) for d in pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=n)]


def _meta(source="EIA via FRED", approx=True, has_volume=False):
    return {"fields": {"source": {"stringValue": source}, "ohlcApprox": {"booleanValue": approx},
                       "hasVolume": {"booleanValue": has_volume}}}


def _firebase_world(docs_by_page, meta=None, live=None, calls=None):
    """Faux réseau : Firestore répond avec `docs_by_page` ; toute autre adresse est traitée par `live`."""
    def fake(url):
        if calls is not None:
            calls.append(url)
        if "firestore.googleapis.com" in url:
            if "/years" in url:
                page = 1 if "pageToken=T" in url else 0
                body = {"documents": docs_by_page[page]}
                if page == 0 and len(docs_by_page) > 1:
                    body["nextPageToken"] = "T"
                return json.dumps(body).encode()
            return json.dumps(meta or _meta()).encode()
        if live is None:
            raise AssertionError("la lecture directe ne devait pas être appelée : " + url)
        return live(url)
    return fake


def _provider(fake, **kw):
    return LiveDataProvider(http_get=fake, firebase_project="p", firebase_api_key="KEYFB", **kw)


def test_firestore_parser_reads_typed_values_and_rejects_an_empty_base():
    df = parse_firestore_bars([_fs_year(2025, ["2025-01-02", "2025-01-03"])])
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"] and df["volume"].iloc[0] == 0.0
    with pytest.raises(DataUnavailable, match="aucune barre"):
        parse_firestore_bars([])


def test_firebase_is_read_first_and_the_live_sources_are_not_called():
    p = _provider(_firebase_world([[_fs_year(2026, _recent_dates())]]))
    assert len(p.get_ohlcv("OIL")) == 40
    info = p.info("OIL")
    assert info["source"].startswith("Firebase") and info["ohlc_approx"] is True and info["stale_error"] is None


def test_firebase_pagination_reads_every_page():
    calls = []
    dates = _recent_dates(40)
    p = _provider(_firebase_world([[_fs_year(2025, dates[:20])], [_fs_year(2026, dates[20:])]], calls=calls))
    assert len(p.get_ohlcv("OIL")) == 40
    assert len([c for c in calls if "/years" in c]) == 2 and any("pageToken=T" in c for c in calls)


def test_stale_firebase_data_makes_the_app_use_the_live_sources():
    old = [str(d.date()) for d in pd.bdate_range("2020-01-01", periods=40)]
    p = _provider(_firebase_world([[_fs_year(2020, old)]], live=lambda url: FRED.encode()))
    p.get_ohlcv("OIL")
    assert p.info("OIL")["source"] == "EIA via FRED (DCOILWTICO)"


def test_empty_firebase_falls_back_to_live_without_failing():
    def fake(url):
        if "firestore.googleapis.com" in url:
            raise OSError("HTTP Error 404: Not Found")
        return FRED.encode()

    p = _provider(fake)
    assert len(p.get_ohlcv("OIL")) == 3 and p.info("OIL")["stale_error"] is None


def test_when_everything_is_down_every_reason_is_reported():
    def fake(url):
        raise OSError("HTTP Error 404: Not Found" if "firestore" in url else "réseau coupé")

    with pytest.raises(DataUnavailable) as exc:
        _provider(fake).get_ohlcv("OIL")
    text = str(exc.value)
    assert "Firebase" in text and "Firestore est vide" in text and "FRED CSV" in text and "réseau coupé" in text


def test_stale_firebase_copy_is_served_with_a_warning_when_live_also_fails():
    old = [str(d.date()) for d in pd.bdate_range("2020-01-01", periods=40)]

    def live(url):
        raise OSError("réseau coupé")

    p = _provider(_firebase_world([[_fs_year(2020, old)]], live=live))
    assert len(p.get_ohlcv("OIL")) == 40
    assert "trop anciennes" in p.info("OIL")["stale_error"]


def test_gold_comes_from_firebase_without_any_twelvedata_key():
    p = _provider(_firebase_world([[_fs_year(2026, _recent_dates(), volume=1000)]],
                                  meta=_meta("Twelve Data (XAU/USD)", approx=False, has_volume=True)))
    assert len(p.get_ohlcv("GOLD")) == 40
    assert p.info("GOLD")["has_volume"] is True and p.info("GOLD")["ohlc_approx"] is False


def test_firebase_key_never_appears_in_error_messages():
    def fake(url):
        raise OSError("échec pour " + url)

    with pytest.raises(DataUnavailable) as exc:
        _provider(fake).get_ohlcv("OIL")
    assert "KEYFB" not in str(exc.value)
