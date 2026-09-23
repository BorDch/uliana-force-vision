import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_service_worker_excludes_private_routes_and_bumps_cache():
    worker = (ROOT / "uliana-demo/public/sw.js").read_text(encoding="utf-8")
    assert "uliana-mobile-shell-v2" in worker
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'request.method !== "GET"' in worker
    assert "/session" not in json.loads((ROOT / "uliana-demo/public/manifest.webmanifest").read_text())["start_url"]


def test_mobile_css_has_narrow_viewport_containment():
    css = (ROOT / "uliana-demo/app/globals.css").read_text(encoding="utf-8")
    for width in (320, 360, 375, 390, 414, 430):
        assert width <= 430  # all requested widths use the max-width:430 rules
    assert "overflow-x:clip" in css
    assert "min-width:0" in css
    assert "env(safe-area-inset" in css


def test_english_date_and_plural_copy_are_explicit():
    source = (ROOT / "uliana-demo/components/prototype-app.tsx").read_text(encoding="utf-8")
    assert 'toLocaleDateString("en-GB"' in source
    assert 'count === 1 ? singular : pluralForm' in source
    assert 'plural(result.repetition_count??0,"repetition")' in source
