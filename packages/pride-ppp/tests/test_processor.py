"""Regression tests for pride_ppp.factories.processor functions.

Tests cover handling of `ResolvedDependency.local_path` as strings
(rather than Path objects), ensuring normalization via `as_path()` works
correctly before accessing `.name` and `.parent` path attributes.
"""

from __future__ import annotations

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

from pride_ppp.factories.processor import (
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
