from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MARKET_DATA = ROOT / "apps" / "api" / "app" / "market_data"


def test_binance_adapters_remain_on_public_spot_market_data_hosts() -> None:
    rest = (MARKET_DATA / "binance_rest.py").read_text(encoding="utf-8")
    historical = (MARKET_DATA / "binance_historical_rest.py").read_text(
        encoding="utf-8"
    )
    stream = (MARKET_DATA / "binance_stream.py").read_text(encoding="utf-8")

    assert (
        'BINANCE_SPOT_REST_BASE_URL = "https://data-api.binance.vision"' in rest
    )
    assert (
        'BINANCE_SPOT_REST_BASE_URL = "https://data-api.binance.vision"' in historical
    )
    assert 'BINANCE_SPOT_WS_BASE_URL = "wss://data-stream.binance.vision"' in stream
    assert '"/api/v3/trades"' in rest
    assert '"/api/v3/klines"' in historical
    assert '@trade' in stream

    forbidden_markers = (
        "api.binance.com",
        "fapi.binance.com",
        "dapi.binance.com",
        "sapi/",
        "/api/v3/account",
        "/api/v3/order",
        "X-MBX-APIKEY",
        "recvWindow",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
    )
    for source in (rest, historical, stream):
        for marker in forbidden_markers:
            assert marker not in source


def test_environment_templates_do_not_declare_binance_credentials() -> None:
    templates = (
        ROOT / ".env.example",
        ROOT / "apps" / "web" / ".env.example",
    )
    forbidden = re.compile(r"^BINANCE_(?:API_KEY|API_SECRET)=", re.MULTILINE)

    for template in templates:
        content = template.read_text(encoding="utf-8")
        assert forbidden.search(content) is None


def test_render_manifest_does_not_configure_binance_credentials_or_extra_services(
) -> None:
    manifest = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert manifest.count("  - type:") == 1
    assert "name: baymax-api" in manifest
    assert "BINANCE_API_KEY" not in manifest
    assert "BINANCE_API_SECRET" not in manifest
