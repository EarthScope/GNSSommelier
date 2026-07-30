"""Tests for pride_ppp.specifications.config — pdp3 config_file generation.

Guards against ctrl-file key drift (issue #28): pdp3's set of required
keys grows over time (`ISB model`, then `AI Ambiguity validation`), and a
generated config_file missing a required key makes every PPP run silently
produce 0 KIN files via a sed crash inside pdp3.sh.

``data/upstream_config_template_b7451a8`` is PRIDE-PPPAR's shipped
``table/config_template`` at the commit the table source is pinned to
(see pride_table_config.yaml).  Refresh it when re-pinning.
"""

from __future__ import annotations

from pathlib import Path

from pride_ppp.specifications.config import (
    ObservationConfig,
    PRIDEPPPFileConfig,
    SatelliteProducts,
)

DATA_DIR = Path(__file__).parent / "data"
UPSTREAM_TEMPLATE = DATA_DIR / "upstream_config_template_b7451a8"
SHIPPED_TEMPLATE = (
    Path(__file__).parents[1] / "src" / "pride_ppp" / "specifications" / "config_template"
)


def _config_keys(text: str) -> list[str]:
    """Extract ``key`` names from ``key = value`` ctrl-file lines."""
    keys = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith(("#", "!", "+", "-", "*")) or "=" not in line:
            continue
        key = line.split("=")[0].strip()
        if key:
            keys.append(key)
    return keys


def _default_config() -> PRIDEPPPFileConfig:
    return PRIDEPPPFileConfig(
        observation=ObservationConfig(table_directory="Default"),
        satellite_products=SatelliteProducts(),
    )


def _write_to_text(config: PRIDEPPPFileConfig, tmp_path: Path) -> str:
    dest = tmp_path / "config_file"
    config.write_config_file(dest)
    return dest.read_text()


class TestAiAmbiguityValidation:
    def test_written_config_contains_key(self, tmp_path: Path) -> None:
        text = _write_to_text(_default_config(), tmp_path)
        assert "AI Ambiguity validation = YES" in text

    def test_key_round_trips(self, tmp_path: Path) -> None:
        """A template that sets the key to NO must keep NO through
        read → write."""
        config = _default_config()
        config.ambiguity.ai_ambiguity_validation = "NO"
        dest = tmp_path / "config_file"
        config.write_config_file(dest)

        reread = PRIDEPPPFileConfig.read_config_file(str(dest))
        assert reread.ambiguity.ai_ambiguity_validation == "NO"

    def test_key_injected_when_template_lacks_it(self, tmp_path: Path) -> None:
        """Reading an old installed template without the key (pre-3.2.10
        PRIDE) must still produce a config_file that includes it."""
        old_template = tmp_path / "old_template"
        old_template.write_text(
            SHIPPED_TEMPLATE.read_text().replace(
                "AI Ambiguity validation = YES                    ! Ambiguity fixing validation is SVM or not\n",
                "",
            )
        )
        config = PRIDEPPPFileConfig.read_config_file(str(old_template))
        assert config.ambiguity.ai_ambiguity_validation == "YES"
        assert "AI Ambiguity validation = YES" in _write_to_text(config, tmp_path)


class TestUpstreamKeyDrift:
    """Fail when pdp3's ctrl-file keys drift ahead of this wrapper."""

    def test_shipped_template_covers_upstream_keys(self) -> None:
        upstream = set(_config_keys(UPSTREAM_TEMPLATE.read_text()))
        shipped = set(_config_keys(SHIPPED_TEMPLATE.read_text()))
        missing = upstream - shipped
        assert not missing, (
            f"config_template is missing keys that PRIDE-PPPAR's shipped "
            f"template declares: {sorted(missing)}. pdp3 may crash on the "
            f"absent keys (see issue #28)."
        )

    def test_written_config_covers_upstream_keys(self, tmp_path: Path) -> None:
        """The writer itself must emit every upstream key — a model field
        without a corresponding write line would silently drop it."""
        upstream = set(_config_keys(UPSTREAM_TEMPLATE.read_text()))
        written = set(_config_keys(_write_to_text(_default_config(), tmp_path)))
        missing = upstream - written
        assert not missing, (
            f"write_config_file omits keys that PRIDE-PPPAR's shipped "
            f"template declares: {sorted(missing)} (see issue #28)."
        )

    def test_upstream_keys_survive_read_write_round_trip(self, tmp_path: Path) -> None:
        """Reading the upstream template and writing it back must not strip
        any of its keys — this is exactly how issue #28 manifested: the
        installed template had the key, but read → write dropped it."""
        upstream_text = UPSTREAM_TEMPLATE.read_text()
        config = PRIDEPPPFileConfig.read_config_file(str(UPSTREAM_TEMPLATE))
        written = set(_config_keys(_write_to_text(config, tmp_path)))
        missing = set(_config_keys(upstream_text)) - written
        assert not missing, f"read_config_file → write_config_file strips keys: {sorted(missing)}"
