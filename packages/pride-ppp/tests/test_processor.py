"""Regression tests for pride_ppp.factories.processor functions.

Tests cover handling of `ResolvedDependency.local_path` as strings
(rather than Path objects), ensuring normalization via `as_path()` works
correctly before accessing `.name` and `.parent` path attributes.
"""

from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

try:
    from gnss_product_management.specifications.dependencies.dependencies import (
        DependencyResolution,
        ResolvedDependency,
    )
except ImportError as e:
    pytest.skip(f"gnss-product-management not installed: {e}", allow_module_level=True)

from pride_ppp.factories import processor as processor_module
from pride_ppp.factories.processor import (
    MissingProductsError,
    PrideProcessor,
    _resolution_to_satellite_products,
    _resolution_to_table_dir,
)


@pytest.fixture
def temp_product_files() -> dict[str, str]:
    """Create temporary product files and return their paths as strings."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create sample product files with uppercase extensions for validation
        orbit_file = tmpdir_path / "orbit_product.SP3"
        clock_file = tmpdir_path / "clock_product.CLK"
        bias_file = tmpdir_path / "bias_product.BIA"
        antex_file = tmpdir_path / "antenna.atx"

        orbit_file.write_text("orbit data")
        clock_file.write_text("clock data")
        bias_file.write_text("bias data")
        antex_file.write_text("antex data")

        # Return paths as strings (mimics how local_path is stored)
        yield {
            "orbit": str(orbit_file),
            "clock": str(clock_file),
            "bias": str(bias_file),
            "antex": str(antex_file),
        }


def test_resolution_to_satellite_products_with_string_local_path(
    temp_product_files: dict[str, str],
) -> None:
    """Test that _resolution_to_satellite_products handles string local_path.

    Regression test for: AttributeError: 'str' object has no attribute 'name'
    """
    # Create ResolvedDependency objects with string local_path values
    resolved_deps = [
        ResolvedDependency(
            spec="ORBIT",
            required=True,
            status="local",
            local_path=temp_product_files["orbit"],
        ),
        ResolvedDependency(
            spec="CLOCK",
            required=True,
            status="local",
            local_path=temp_product_files["clock"],
        ),
        ResolvedDependency(
            spec="BIA",
            required=True,
            status="local",
            local_path=temp_product_files["bias"],
        ),
    ]

    resolution = DependencyResolution(spec_name="test", resolved=resolved_deps)

    # Should not raise AttributeError
    satellite_products, product_dir = _resolution_to_satellite_products(resolution)

    # Verify the function extracted the filenames correctly
    assert satellite_products.satellite_orbit == Path(temp_product_files["orbit"]).name
    assert satellite_products.satellite_clock == Path(temp_product_files["clock"]).name
    assert satellite_products.code_phase_bias == Path(temp_product_files["bias"]).name
    assert product_dir is not None
    assert product_dir == Path(temp_product_files["orbit"]).parent


def test_resolution_to_satellite_products_with_none_local_path() -> None:
    """Test that _resolution_to_satellite_products skips deps with None local_path."""
    resolved_deps = [
        ResolvedDependency(
            spec="ORBIT",
            required=True,
            status="missing",
            local_path=None,
        ),
    ]

    resolution = DependencyResolution(spec_name="test", resolved=resolved_deps)

    # Should not raise; returns empty products
    satellite_products, product_dir = _resolution_to_satellite_products(resolution)

    assert satellite_products.satellite_orbit is None
    assert product_dir is None


def test_resolution_to_table_dir_with_string_local_path(
    temp_product_files: dict[str, str],
) -> None:
    """Test that _resolution_to_table_dir handles string local_path.

    Regression test for: AttributeError: 'str' object has no attribute 'parent'
    """
    # Create a ResolvedDependency with string local_path for ATTATX
    resolved_deps = [
        ResolvedDependency(
            spec="ATTATX",
            required=True,
            status="local",
            local_path=temp_product_files["antex"],
        ),
    ]

    resolution = DependencyResolution(spec_name="test", resolved=resolved_deps)

    # Should not raise AttributeError
    table_dir = _resolution_to_table_dir(resolution)

    # Verify the parent directory was extracted
    assert table_dir is not None
    assert table_dir == Path(temp_product_files["antex"]).parent


def test_resolution_to_table_dir_with_no_attatx() -> None:
    """Test that _resolution_to_table_dir returns None when ATTATX is missing."""
    resolved_deps = [
        ResolvedDependency(
            spec="ORBIT",
            required=True,
            status="local",
            local_path="/some/path/orbit.SP3",
        ),
    ]

    resolution = DependencyResolution(spec_name="test", resolved=resolved_deps)

    table_dir = _resolution_to_table_dir(resolution)
    assert table_dir is None


def test_resolution_to_table_dir_with_none_local_path() -> None:
    """Test that _resolution_to_table_dir skips ATTATX deps with None local_path."""
    resolved_deps = [
        ResolvedDependency(
            spec="ATTATX",
            required=True,
            status="missing",
            local_path=None,
        ),
    ]

    resolution = DependencyResolution(spec_name="test", resolved=resolved_deps)

    table_dir = _resolution_to_table_dir(resolution)
    assert table_dir is None


@pytest.fixture
def processor() -> PrideProcessor:
    """A PrideProcessor without running __init__ — _validate_kinfile is self-free."""
    return object.__new__(PrideProcessor)


class TestValidateKinfile:
    """Regression tests for PrideProcessor._validate_kinfile.

    The original implementation used `if kin_df and not kin_df.empty`, which
    raises `ValueError: The truth value of a DataFrame is ambiguous` for any
    kin file that parses into a DataFrame.
    """

    def test_valid_kinfile_returns_true(self, processor: PrideProcessor, kin_file: Path) -> None:
        # Raised ValueError before the truthiness fix
        assert processor._validate_kinfile(kin_file) is True

    def test_missing_path_returns_false(self, processor: PrideProcessor, tmp_path: Path) -> None:
        assert processor._validate_kinfile(tmp_path / "kin_missing.kin") is False

    def test_override_skips_cache_check(self, processor: PrideProcessor, kin_file: Path) -> None:
        assert processor._validate_kinfile(kin_file, override=True) is False

    def test_unparseable_kinfile_returns_false(
        self, processor: PrideProcessor, tmp_path: Path
    ) -> None:
        garbage = tmp_path / "kin_2021220_bako.kin"
        garbage.write_text("not a kin file\nno header here\n")
        assert processor._validate_kinfile(garbage) is False


class TestRunPdp3:
    """Subprocess handling in _run_pdp3, exercised via a fake pdp3 on PATH."""

    @pytest.fixture
    def fake_pdp3(self, tmp_path, monkeypatch):
        """Return a factory that installs a fake pdp3 shell script on PATH."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        def install(script_body: str) -> None:
            pdp3 = bin_dir / "pdp3"
            pdp3.write_text(f"#!/bin/sh\n{script_body}\n")
            pdp3.chmod(0o755)
            monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

        return install

    def test_outputs_moved_with_extensions(self, fake_pdp3, tmp_path: Path) -> None:
        fake_pdp3("touch kin_2025254_ncc1 res_2025254_ncc1")
        out = tmp_path / "out"

        kin, res, rc, _ = PrideProcessor._run_pdp3(command=["pdp3"], site="NCC1", output_dir=out)

        assert rc == 0
        assert kin == out / "kin_2025254_ncc1.kin" and kin.exists()
        assert res == out / "res_2025254_ncc1.res" and res.exists()

    def test_nonzero_exit_and_missing_output_are_logged(
        self, fake_pdp3, tmp_path: Path, caplog
    ) -> None:
        fake_pdp3("echo boom >&2; exit 2")
        out = tmp_path / "out"

        with caplog.at_level(logging.ERROR, logger="pride_ppp.factories.processor"):
            kin, res, rc, stderr = PrideProcessor._run_pdp3(
                command=["pdp3"], site="NCC1", output_dir=out
            )

        assert rc == 2
        assert kin is None and res is None
        assert "boom" in stderr
        assert any("pdp3 exited with code 2" in m for m in caplog.messages)
        assert any("produced no kin output" in m for m in caplog.messages)


def _unfulfilled_resolution() -> DependencyResolution:
    return DependencyResolution(
        spec_name="test",
        resolved=[
            ResolvedDependency(spec="ORBIT", required=True, status="missing", local_path=None)
        ],
    )


class TestMissingRequiredProducts:
    """Processing must not launch pdp3 when required products are missing."""

    def test_process_raises_missing_products_error(self, tmp_path: Path, monkeypatch) -> None:
        proc = object.__new__(PrideProcessor)
        proc._output_dir = tmp_path / "out"
        monkeypatch.setattr(proc, "_resolve", lambda dt: _unfulfilled_resolution())

        rinex = tmp_path / "test.rnx"
        rinex.write_text("")

        with pytest.raises(MissingProductsError, match="ORBIT"):
            proc.process(rinex, site="ncc1", date=datetime.date(2025, 9, 11))

    def test_process_batch_yields_failed_result_without_running_pdp3(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        proc = object.__new__(PrideProcessor)
        proc._output_dir = tmp_path / "out"
        proc._pride_dir = tmp_path / "pride"
        monkeypatch.setattr(proc, "_resolve", lambda dt: _unfulfilled_resolution())
        # Keep the orchestration test hermetic: no real RINEX headers, no
        # installed PRIDE config template, and pdp3 must never be invoked.
        start = datetime.datetime(2025, 9, 11, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(processor_module, "rinex_get_time_range", lambda p: (start, start))
        monkeypatch.setattr(processor_module, "_write_config", lambda sp, td, dest: dest)

        def _fail(*args, **kwargs):
            raise AssertionError("pdp3 must not run for unfulfilled dates")

        monkeypatch.setattr(proc, "_run_pdp3", _fail)

        rinex = tmp_path / "test.rnx"
        rinex.write_text("")

        results = list(proc.process_batch([rinex], sites=["ncc1"]))

        assert len(results) == 1
        result = results[0]
        assert result.returncode == -1
        assert result.success is False
        assert "Missing required products" in result.stderr
        assert "ORBIT" in result.stderr
