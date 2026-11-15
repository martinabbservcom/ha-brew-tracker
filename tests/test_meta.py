"""Small consistency checks that need no Home Assistant."""
import json
import pathlib

from custom_components.brew_tracker.const import VERSION

BASE = pathlib.Path(__file__).parent.parent / "custom_components" / "brew_tracker"


def test_versions_match():
    assert json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))["version"] == VERSION


def test_every_service_has_a_translation():
    import re
    services = set(re.findall(r"^([a-z_]+):", (BASE / "services.yaml").read_text(encoding="utf-8"), re.M))
    assert services == set(json.loads((BASE / "strings.json").read_text(encoding="utf-8"))["services"])
    assert json.loads((BASE / "strings.json").read_text(encoding="utf-8")) == json.loads((BASE / "translations" / "en.json").read_text(encoding="utf-8"))
