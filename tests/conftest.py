"""Test setup.

The Home Assistant test tools only run on Linux/macOS (they import a Unix-only module), so on Windows only the pure rules
tests (test_logic.py) run locally, with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. The full set runs in CI on every push.
"""
import pytest

collect_ignore = []

try:
    import pytest_homeassistant_custom_component.plugins  # noqa: F401  (needs a Unix-only module)
except ImportError:
    collect_ignore.append("test_integration.py")
else:

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Let Home Assistant load the integration from custom_components/ in these tests."""
        yield
