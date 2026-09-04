"""
Tests: Product filepath generation.

Verifies that the catalog chain (ParameterCatalog → FormatCatalog →
ProductCatalog) and the SearchPlanner produce correct file-path patterns
for all product types at each stage of resolution.

These tests are purely offline (no network access).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from conftest import (
    TEST_DATE,
    format_spec_catalog,
    parameter_catalog,
    product_spec_catalog,
)
from gnss_product_management.specifications.format.format_spec import (
    FormatCatalog,
)
from gnss_product_management.specifications.parameters.parameter import (
    Parameter,
)
from gnss_product_management.specifications.products.catalog import (
    ProductCatalog,
)
from gnss_product_management.specifications.products.product import PathTemplate
from gnss_product_management.utilities.metadata_funcs import register_computed_fields

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_catalogs():
    """Build the full catalog chain from specification-layer catalogs."""
    pc = parameter_catalog
    register_computed_fields(pc)
    fc = FormatCatalog.build(
        format_spec_catalog=format_spec_catalog,
        parameter_catalog=pc,
    )
    prod_cat = ProductCatalog.build(
        product_spec_catalog=product_spec_catalog,
        format_catalog=fc,
    )
    return pc, fc, prod_cat


PARAM_CAT, FORMAT_CAT, PRODUCT_CAT = _build_catalogs()


# ---------------------------------------------------------------------------
# Unit: PathTemplate.derive
# ---------------------------------------------------------------------------


class TestPathTemplateDerive:
    """Verify PathTemplate template substitution."""

    def test_simple_substitution(self) -> None:
        pp = PathTemplate(pattern="{AAA}0{PPP}{TTT}_{YYYY}{DDD}{HH}{MM}_{LEN}_{SMP}_{CNT}.{FMT}.*")
        params = [
            Parameter(name="AAA", value="WUM"),
            Parameter(name="PPP", value="MGX"),
            Parameter(name="TTT", value="FIN"),
            Parameter(name="YYYY", value="2025"),
            Parameter(name="DDD", value="015"),
            Parameter(name="HH", value="00"),
            Parameter(name="MM", value="00"),
            Parameter(name="LEN", value="01D"),
            Parameter(name="SMP", value="05M"),
            Parameter(name="CNT", value="ORB"),
            Parameter(name="FMT", value="SP3"),
        ]
        pp.derive(params)
        assert pp.pattern == "WUM0MGXFIN_20250150000_01D_05M_ORB.SP3.*"

    def test_partial_substitution(self) -> None:
        """Unresolved placeholders (value=None) stay as {NAME}."""
        pp = PathTemplate(pattern="{AAA}0{PPP}{TTT}_{YYYY}")
        params = [
            Parameter(name="AAA", value="WUM"),
            Parameter(name="PPP", value=None),
            Parameter(name="TTT", value="FIN"),
            Parameter(name="YYYY", value="2025"),
        ]
        pp.derive(params)
        assert "{PPP}" in pp.pattern
        assert pp.pattern == "WUM0{PPP}FIN_2025"

    def test_no_double_derive(self) -> None:
        """Once .value is set, derive() is a no-op."""
        pp = PathTemplate(pattern="{AAA}", value="FROZEN")
        pp.derive([Parameter(name="AAA", value="WUM")])
        assert pp.value == "FROZEN"

    def test_directory_template(self) -> None:
        pp = PathTemplate(pattern="pub/whu/phasebias/{YYYY}/orbit/")
        params = [Parameter(name="YYYY", value="2025")]
        pp.derive(params)
        assert pp.pattern == "pub/whu/phasebias/2025/orbit/"


# ---------------------------------------------------------------------------
# Unit: ParameterCatalog — computed fields
# ---------------------------------------------------------------------------


class TestParameterCatalogComputed:
    """Verify date-computed parameter resolution."""

    def test_yyyy(self) -> None:
        assert PARAM_CAT["YYYY"].compute(TEST_DATE) == "2025"

    def test_ddd(self) -> None:
        assert PARAM_CAT["DDD"].compute(TEST_DATE) == "015"

    def test_yy(self) -> None:
        assert PARAM_CAT["YY"].compute(TEST_DATE) == "25"

    def test_month(self) -> None:
        assert PARAM_CAT["MONTH"].compute(TEST_DATE) == "01"

    def test_day(self) -> None:
        assert PARAM_CAT["DAY"].compute(TEST_DATE) == "15"

    def test_hh(self) -> None:
        assert PARAM_CAT["HH"].compute(TEST_DATE) == "00"

    def test_mm(self) -> None:
        assert PARAM_CAT["MM"].compute(TEST_DATE) == "00"

    def test_gpsweek(self) -> None:
        # 2025-01-15 → GPS week 2347
        expected = (TEST_DATE.date() - datetime.date(1980, 1, 6)).days // 7
        assert PARAM_CAT["GPSWEEK"].compute(TEST_DATE) == str(expected)

    def test_refframe(self) -> None:
        # 2025 → igs20
        assert PARAM_CAT["REFFRAME"].compute(TEST_DATE) == "igs20"

    def test_interpolate_template(self) -> None:
        template = "gnss/products/{GPSWEEK}/"
        resolved = PARAM_CAT.interpolate(template, TEST_DATE, computed_only=True)
        gpsweek = PARAM_CAT["GPSWEEK"].compute(TEST_DATE)
        assert resolved == f"gnss/products/{gpsweek}/"


# ---------------------------------------------------------------------------
# Unit: ProductCatalog — product resolution
# ---------------------------------------------------------------------------


class TestProductCatalogResolution:
    """Verify product catalog resolves specs into Products with correct filenames."""

    def test_orbit_in_catalog(self) -> None:
        assert "ORBIT" in PRODUCT_CAT.products

    def test_clock_in_catalog(self) -> None:
        assert "CLOCK" in PRODUCT_CAT.products

    def test_erp_in_catalog(self) -> None:
        assert "ERP" in PRODUCT_CAT.products

    def test_bia_in_catalog(self) -> None:
        assert "BIA" in PRODUCT_CAT.products

    def test_ionex_in_catalog(self) -> None:
        assert "IONEX" in PRODUCT_CAT.products

    def test_brdc_in_catalog(self) -> None:
        assert "RNX3_BRDC" in PRODUCT_CAT.products

    def test_leap_sec_in_catalog(self) -> None:
        assert "LEAP_SEC" in PRODUCT_CAT.products

    def test_vmf_in_catalog(self) -> None:
        assert "VMF" in PRODUCT_CAT.products

    def test_attatx_in_catalog(self) -> None:
        assert "ATTATX" in PRODUCT_CAT.products

    def test_orbit_filename_pattern(self) -> None:
        """ORBIT should have an SP3 filename pattern with parameter placeholders."""
        orbit = PRODUCT_CAT.products["ORBIT"].versions["1"].variants["default"]
        assert orbit.filename is not None
        # After catalog resolution, fixed params are substituted
        assert "ORB" in orbit.filename.pattern
        assert "SP3" in orbit.filename.pattern

    def test_clock_filename_pattern(self) -> None:
        clock = PRODUCT_CAT.products["CLOCK"].versions["1"].variants["default"]
        assert clock.filename is not None
        assert "CLK" in clock.filename.pattern

    def test_ionex_filename_pattern(self) -> None:
        ionex = PRODUCT_CAT.products["IONEX"].versions["1"].variants["default"]
        assert ionex.filename is not None
        assert "GIM" in ionex.filename.pattern
        assert "INX" in ionex.filename.pattern

    def test_leap_sec_fixed_filename(self) -> None:
        """LEAP_SEC has a product-level filename override: 'leap.sec'."""
        leap = PRODUCT_CAT.products["LEAP_SEC"].versions["1"].variants["default"]
        assert leap.filename is not None
        assert leap.filename.pattern == "leap.sec"

    def test_sat_params_fixed_filename(self) -> None:
        sat = PRODUCT_CAT.products["SAT_PARAMS"].versions["1"].variants["default"]
        assert sat.filename is not None
        assert sat.filename.pattern == "sat_parameters"

    def test_brdc_filename_contains_brdc(self) -> None:
        brdc = PRODUCT_CAT.products["RNX3_BRDC"].versions["3"].variants["navigation"]
        assert brdc.filename is not None
        assert "BRDC" in brdc.filename.pattern

    def test_attatx_filename_contains_atx(self) -> None:
        atx = PRODUCT_CAT.products["ATTATX"].versions["1"].variants["default"]
        assert atx.filename is not None
        assert ".atx" in atx.filename.pattern

    def test_vmf_filename_pattern(self) -> None:
        vmf = PRODUCT_CAT.products["VMF"].versions["1"].variants["default"]
        assert vmf.filename is not None
        # VMF pattern has {PRODUCT}_{YYYY}{MONTH}{DAY}.{VMFHH}
        assert "{PRODUCT}" in vmf.filename.pattern or "PRODUCT" in vmf.filename.pattern


# ---------------------------------------------------------------------------
# Unit: SearchPlanner — filepath generation for each product type
# ---------------------------------------------------------------------------


class TestSearchPlannerFilepaths:
    """Verify SearchPlanner.get() produces correct resolved directory and filename patterns."""

    def test_orbit_directory_resolved(self, wuhan_qf, test_date) -> None:
        gpsweek = str((test_date.date() - datetime.date(1980, 1, 6)).days // 7)
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            # Directory should have 2025 or GPS week resolved (computed)
            d = q.directory.pattern if hasattr(q.directory, "pattern") else str(q.directory)
            assert "2025" in d or gpsweek in d  # Either year or GPS week

    def test_orbit_filename_has_sp3(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        for q in remote:
            fn = q.product.filename.pattern
            assert "SP3" in fn.upper() or "sp3" in fn.lower()

    def test_orbit_narrowed_by_center(self, wuhan_qf, test_date) -> None:
        """Querying with AAA=WUM should only produce WUM orbit files."""
        queries = wuhan_qf.get(
            date=test_date,
            product={"name": "ORBIT"},
            parameters={"AAA": "WUM"},
        )
        remote = [q for q in queries if q.server.protocol != "file"]
        for q in remote:
            fn = q.product.filename.pattern
            assert "WUM" in fn

    def test_clock_filename_has_clk(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "CLOCK"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert "CLK" in fn.upper()

    def test_erp_filename_has_erp(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ERP"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert "ERP" in fn.upper()

    def test_bia_filename_has_bia(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "BIA"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert "BIA" in fn.upper() or "OSB" in fn.upper()

    def test_ionex_filename_has_gim_inx(self, cod_qf, test_date) -> None:
        queries = cod_qf.get(date=test_date, product={"name": "IONEX"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert "GIM" in fn and "INX" in fn

    def test_ionex_directory_uses_code_root(self, cod_qf, test_date) -> None:
        queries = cod_qf.get(date=test_date, product={"name": "IONEX"})
        remote = [q for q in queries if q.server.protocol != "file"]
        for q in remote:
            d = q.directory.pattern
            assert d == "CODE/"

    def test_brdc_filename_contains_brdc(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "RNX3_BRDC"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert "BRDC" in fn

    def test_leap_sec_fixed_filename(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "LEAP_SEC"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert fn == "leap.sec"

    def test_sat_params_fixed_filename(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "SAT_PARAMS"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            fn = q.product.filename.pattern
            assert fn == "sat_parameters"

    def test_date_substitution_in_directory(self, wuhan_qf, test_date) -> None:
        """YYYY in directory template should be replaced with '2025'."""
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        for q in remote:
            d = q.directory.pattern
            assert "{YYYY}" not in d, f"Unresolved placeholder in directory: {d}"

    def test_date_substitution_in_filename(self, wuhan_qf, test_date) -> None:
        """YYYY and DDD in filename should be resolved to concrete values."""
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        for q in remote:
            fn = q.product.filename.pattern
            assert "{YYYY}" not in fn, f"Unresolved YYYY in filename: {fn}"
            assert "{DDD}" not in fn, f"Unresolved DDD in filename: {fn}"
            assert "2025" in fn
            assert "015" in fn

    def test_gpsweek_substitution(self, cddis_qf, test_date) -> None:
        """CDDIS directories use {GPSWEEK} which should be resolved."""
        gpsweek = str((test_date.date() - datetime.date(1980, 1, 6)).days // 7)
        queries = cddis_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        dirs = [q.directory.pattern for q in remote]
        # CDDIS uses gnss/products/{GPSWEEK}/ — should have the GPS week resolved
        assert any(gpsweek in d for d in dirs), f"No directory with GPS week {gpsweek}: {dirs}"

    def test_filename_is_valid_regex(self, wuhan_qf, test_date) -> None:
        """Generated filename patterns should be valid regex (for WormHole matching)."""
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        for q in queries:
            if q.product.filename:
                fn = q.product.filename.pattern
                try:
                    re.compile(fn, re.IGNORECASE)
                except re.error:
                    pytest.fail(f"Invalid regex in filename pattern: {fn}")


# ---------------------------------------------------------------------------
# Unit: Local directory resolution
# ---------------------------------------------------------------------------


class TestLocalDirectoryResolution:
    """Verify local factory produces correct local directories."""

    @staticmethod
    def _local_dir(qf, product_name: str, date) -> str:
        """Helper: resolve the local sink directory for a product name."""
        queries = qf.get(date=date, product={"name": product_name})
        local = [q for q in queries if q.server.protocol == "file"]
        assert local, f"No local queries for {product_name}"
        q = local[0]
        d = q.directory.value or q.directory.pattern
        return str(Path(q.server.hostname) / d)

    def test_orbit_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "ORBIT", test_date)
        assert "2025" in d
        assert "015" in d
        assert "products" in d

    def test_clock_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "CLOCK", test_date)
        assert "products" in d

    def test_ionex_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "IONEX", test_date)
        assert "common" in d

    def test_brdc_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "RNX3_BRDC", test_date)
        assert "rinex" in d

    def test_leap_sec_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "LEAP_SEC", test_date)
        assert "table" in d

    def test_attatx_local_directory(self, wuhan_qf, test_date) -> None:
        d = self._local_dir(wuhan_qf, "ATTATX", test_date)
        assert "table" in d

    def test_local_query_has_file_protocol(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        local = [q for q in queries if q.server.protocol == "file"]
        assert len(local) > 0


# ---------------------------------------------------------------------------
# Unit: Query counts and structure
# ---------------------------------------------------------------------------


class TestQueryStructure:
    """Verify query factory generates expected numbers and shapes of queries."""

    def test_orbit_generates_multiple_queries(self, wuhan_qf, test_date) -> None:
        """Wuhan ORBIT has multiple AAA values → multiple queries."""
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        # At least 2 (WUM, WMC)
        assert len(remote) >= 2

    def test_each_query_has_server(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        for q in queries:
            assert q.server is not None
            assert q.server.hostname is not None

    def test_each_query_has_directory(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        for q in queries:
            assert q.directory is not None

    def test_each_query_has_filename(self, wuhan_qf, test_date) -> None:
        queries = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        for q in queries:
            assert q.product.filename is not None

    def test_narrowing_reduces_queries(self, wuhan_qf, test_date) -> None:
        """Constraining AAA=WUM should produce fewer queries than unconstrained."""
        all_q = wuhan_qf.get(date=test_date, product={"name": "ORBIT"})
        narrow_q = wuhan_qf.get(
            date=test_date,
            product={"name": "ORBIT"},
            parameters={"AAA": "WUM"},
        )
        remote_all = [q for q in all_q if q.server.protocol != "file"]
        remote_narrow = [q for q in narrow_q if q.server.protocol != "file"]
        assert len(remote_narrow) < len(remote_all)

    def test_invalid_product_raises(self, wuhan_qf, test_date) -> None:
        with pytest.raises(ValueError, match="not found"):
            wuhan_qf.get(date=test_date, product={"name": "NONEXISTENT"})

    def test_cod_orbit_directory_is_code_yyyy(self, cod_qf, test_date) -> None:
        queries = cod_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            d = q.directory.pattern
            assert d.startswith("CODE/")

    def test_cddis_orbit_directory_is_gpsweek(self, cddis_qf, test_date) -> None:
        gpsweek = str((test_date.date() - datetime.date(1980, 1, 6)).days // 7)
        queries = cddis_qf.get(date=test_date, product={"name": "ORBIT"})
        remote = [q for q in queries if q.server.protocol != "file"]
        assert len(remote) > 0
        for q in remote:
            d = q.directory.pattern
            assert gpsweek in d
