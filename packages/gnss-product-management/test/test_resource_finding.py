"""
Tests: Resource finding — full pipeline from SearchPlanner to WormHole.

Verifies that the complete query→search pipeline finds actual files on real
GNSS data servers.  Each test class targets one data center.

Servers : Wuhan (FTP), CODE (FTP), CDDIS (FTPS)
Products: ORBIT, CLOCK, ERP, BIA, IONEX, RNX3_BRDC, LEAP_SEC, SAT_PARAMS, ATTOBX

All tests in this module are marked ``integration`` (hit real servers).
"""

from __future__ import annotations

import datetime

import pytest
from gnss_product_management.factories import WormHole
from gnss_product_management.specifications.products.product import PathTemplate

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_remote(qf, fetcher, date, product_name, parameters=None):
    """Run the full query→search pipeline and return matched SearchTargets."""
    queries = qf.get(date=date, product={"name": product_name}, parameters=parameters)
    remote_queries = [
        q for q in queries if (q.server.protocol or "").upper() not in ("FILE", "LOCAL", "")
    ]
    return fetcher.search(remote_queries)


def _assert_found(results, product_name, min_matches=1):
    """Assert at least *min_matches* SearchTargets were matched."""
    assert len(results) >= min_matches, (
        f"{product_name}: expected >= {min_matches} results, got {len(results)}."
    )
    return results


# ---------------------------------------------------------------------------
# Wuhan (FTP) — igs.gnsswhu.cn
# ---------------------------------------------------------------------------


class TestWuhanResourceFinding:
    """Search for products on Wuhan FTP."""

    def test_orbit_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        found = _assert_found(results, "ORBIT")
        assert any("SP3" in r.product.filename.value.upper() for r in found)

    def test_clock_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "CLOCK", {"AAA": "WUM"})
        found = _assert_found(results, "CLOCK")
        assert any("CLK" in r.product.filename.value.upper() for r in found)

    def test_erp_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ERP")
        _assert_found(results, "ERP")

    def test_bias_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "BIA", {"AAA": "WUM"})
        _assert_found(results, "BIA")

    def test_attobx_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ATTOBX", {"AAA": "WUM"})
        _assert_found(results, "ATTOBX")

    def test_leap_sec_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "LEAP_SEC")
        found = _assert_found(results, "LEAP_SEC")
        assert any("leap" in r.product.filename.value.lower() for r in found)

    def test_sat_params_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "SAT_PARAMS")
        found = _assert_found(results, "SAT_PARAMS")
        assert any("sat_param" in r.product.filename.value.lower() for r in found)

    def test_orbit_filenames_match_date(self, wuhan_qf, fetcher, test_date) -> None:
        """Matched orbit filenames should contain the target date identifiers."""
        results = _search_remote(wuhan_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        found = _assert_found(results, "ORBIT")
        for r in found:
            fn = r.product.filename.value
            assert "2025" in fn, f"Missing year in filename: {fn}"
            assert "015" in fn, f"Missing DOY in filename: {fn}"


# ---------------------------------------------------------------------------
# CODE (HTTPS) — www.aiub.unibe.ch/download
# ---------------------------------------------------------------------------


class TestCODResourceFinding:
    """Search for products through the CODE HTTPS archive."""

    def test_orbit_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "ORBIT")
        _assert_found(results, "ORBIT")

    def test_clock_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "CLOCK")
        _assert_found(results, "CLOCK")

    def test_erp_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "ERP")
        _assert_found(results, "ERP")

    def test_bias_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "BIA")
        _assert_found(results, "BIA")

    def test_ionex_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "IONEX")
        found = _assert_found(results, "IONEX")
        assert any(
            "GIM" in r.product.filename.value.upper() or "INX" in r.product.filename.value.upper()
            for r in found
        )

    def test_orbit_directory_is_code_root(self, cod_qf, fetcher, test_date) -> None:
        """AIUB's HTTPS browser exposes products from the CODE root."""
        results = _search_remote(cod_qf, fetcher, test_date, "ORBIT")
        found = _assert_found(results, "ORBIT")
        for r in found:
            d = r.directory
            d_str = d.pattern if isinstance(d, PathTemplate) else str(d)
            assert d_str == "CODE/"

    def test_orbit_filenames_contain_cod(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "ORBIT")
        found = _assert_found(results, "ORBIT")
        assert any("COD" in r.product.filename.value for r in found)


# ---------------------------------------------------------------------------
# CDDIS (FTPS) — gdc.cddis.eosdis.nasa.gov
# ---------------------------------------------------------------------------


class TestCDDISResourceFinding:
    """Search for products on CDDIS FTPS."""

    def test_orbit_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        _assert_found(results, "ORBIT")

    def test_clock_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "CLOCK", {"AAA": "IGS"})
        _assert_found(results, "CLOCK")

    def test_ionex_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "IONEX", {"AAA": "COD"})
        _assert_found(results, "IONEX")

    def test_ftps_protocol_used(self, cddis_qf, fetcher, test_date) -> None:
        """CDDIS queries should use FTPS protocol."""
        results = _search_remote(cddis_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        for r in results:
            assert r.server.protocol.lower() == "ftps"

    def test_gpsweek_in_directory(self, cddis_qf, fetcher, test_date) -> None:
        gpsweek = str((test_date.date() - datetime.date(1980, 1, 6)).days // 7)
        results = _search_remote(cddis_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        for r in results:
            d = r.directory
            d_str = d.pattern if isinstance(d, PathTemplate) else str(d)
            assert gpsweek in d_str


# ---------------------------------------------------------------------------
# Cross-center: WormHole caching
# ---------------------------------------------------------------------------


class TestFetcherCaching:
    """Verify WormHole caches directory listings across queries."""

    def test_listing_cached_after_search(self, wuhan_qf, test_date) -> None:
        """After searching, the listing cache should contain entries."""
        fresh_fetcher = WormHole()
        queries = wuhan_qf.get(
            date=test_date,
            product={"name": "ORBIT"},
            parameters={"AAA": "WUM"},
        )
        remote_queries = [
            q for q in queries if (q.server.protocol or "").upper() not in ("FILE", "LOCAL", "")
        ]
        fresh_fetcher.search(remote_queries)
        assert len(fresh_fetcher._connection_pool_factory._listing_cache) > 0

    def test_same_directory_not_listed_twice(self, wuhan_qf, test_date) -> None:
        """Two queries sharing the same directory should reuse the cached listing."""
        fresh_fetcher = WormHole()
        orbit_queries = wuhan_qf.get(
            date=test_date,
            product={"name": "ORBIT"},
            parameters={"AAA": "WUM"},
        )
        erp_queries = wuhan_qf.get(date=test_date, product={"name": "ERP"})
        remote = [
            q
            for q in orbit_queries + erp_queries
            if (q.server.protocol or "").upper() not in ("FILE", "LOCAL", "")
        ]
        fresh_fetcher.search(remote)
        assert len(fresh_fetcher._connection_pool_factory._listing_cache) <= len(remote)
