"""
Tests: Orbit/Clock products via SearchPlanner.

Products: ORBIT, CLOCK, ERP, BIA, ATTOBX
Centers : Wuhan (FTP), CODE (FTP), CDDIS (FTPS)
"""

from __future__ import annotations

import datetime

import pytest

pytestmark = pytest.mark.integration


def _get_remote_queries(qf, date, product_name, parameters=None):
    queries = qf.get(date=date, product={"name": product_name}, parameters=parameters)
    return [q for q in queries if (q.server.protocol or "").upper() not in ("FILE", "LOCAL", "")]


def _search_remote(qf, fetcher, date, product_name, parameters=None):
    queries = _get_remote_queries(qf, date, product_name, parameters)
    return fetcher.search(queries)


def _assert_found(results, product_name, min_matches=1):
    found = [r for r in results if r.product.filename and r.product.filename.value]
    assert len(found) >= min_matches, (
        f"{product_name}: expected >= {min_matches} found, got {len(found)} "
        f"out of {len(results)} results."
    )
    return found


# ---------------------------------------------------------------------------
# Unit: Wuhan Orbit/Clock query expansion
# ---------------------------------------------------------------------------


class TestWuhanOrbitExpansion:
    def test_orbit_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ORBIT", {"AAA": "WUM"})
        assert len(queries) > 0

    def test_orbit_server_protocol_is_ftp(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ORBIT", {"AAA": "WUM"})
        for q in queries:
            assert q.server.protocol.lower() == "ftp"

    def test_orbit_directory_contains_date_info(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ORBIT", {"AAA": "WUM"})
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert "2025" in d or "2349" in d  # year or GPS week

    def test_orbit_filename_pattern_has_sp3(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ORBIT", {"AAA": "WUM"})
        patterns = [q.product.filename.pattern for q in queries]
        assert any("SP3" in p for p in patterns), f"No SP3 in {patterns}"

    def test_clock_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "CLOCK", {"AAA": "WUM"})
        assert len(queries) > 0

    def test_clock_filename_pattern_has_clk(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "CLOCK", {"AAA": "WUM"})
        patterns = [q.product.filename.pattern for q in queries]
        assert any("CLK" in p for p in patterns), f"No CLK in {patterns}"

    def test_erp_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ERP")
        assert len(queries) > 0

    def test_bias_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "BIA", {"AAA": "WUM"})
        assert len(queries) > 0

    def test_attobx_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ATTOBX", {"AAA": "WUM"})
        assert len(queries) > 0

    def test_filename_contains_wum(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "ORBIT", {"AAA": "WUM"})
        patterns = [q.product.filename.pattern for q in queries]
        assert any("WUM" in p for p in patterns)


# ---------------------------------------------------------------------------
# Unit: CODE Orbit/Clock query expansion
# ---------------------------------------------------------------------------


class TestCODOrbitExpansion:
    def test_orbit_queries_returned(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "ORBIT")
        assert len(queries) > 0

    def test_orbit_server_protocol_is_https(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "ORBIT")
        for q in queries:
            assert q.server.protocol.lower() == "https"

    def test_orbit_directory_contains_code(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "ORBIT")
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert "CODE" in d

    def test_orbit_filename_contains_cod(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "ORBIT")
        patterns = [q.product.filename.pattern for q in queries]
        assert any("COD" in p for p in patterns)

    def test_clock_queries_returned(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "CLOCK")
        assert len(queries) > 0

    def test_erp_queries_returned(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "ERP")
        assert len(queries) > 0

    def test_bias_queries_returned(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "BIA")
        assert len(queries) > 0


# ---------------------------------------------------------------------------
# Unit: CDDIS Orbit/Clock query expansion
# ---------------------------------------------------------------------------


class TestCDDISOrbitExpansion:
    def test_orbit_queries_returned(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "ORBIT", {"AAA": "WUM"})
        assert len(queries) > 0

    def test_orbit_protocol_is_ftps(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "ORBIT", {"AAA": "WUM"})
        for q in queries:
            assert q.server.protocol.lower() == "ftps"

    def test_orbit_directory_contains_gpsweek(self, cddis_qf, test_date) -> None:
        gpsweek = str((test_date.date() - datetime.date(1980, 1, 6)).days // 7)
        queries = _get_remote_queries(cddis_qf, test_date, "ORBIT", {"AAA": "WUM"})
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert gpsweek in d

    def test_clock_queries_returned(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "CLOCK", {"AAA": "IGS"})
        assert len(queries) > 0


# ---------------------------------------------------------------------------
# Integration: Wuhan FTP orbit probe
# ---------------------------------------------------------------------------


class TestWuhanOrbitProbe:
    def test_orbit_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        _assert_found(results, "ORBIT")

    def test_orbit_filenames_contain_sp3(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        found = _assert_found(results, "ORBIT")
        for r in found:
            assert any("SP3" in f.upper() for f in [r.product.filename.value])

    def test_orbit_filenames_match_date(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        found = _assert_found(results, "ORBIT")
        for r in found:
            for fn in [r.product.filename.value]:
                assert "WUM" in fn or "wum" in fn.lower()

    def test_clock_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "CLOCK", {"AAA": "WUM"})
        _assert_found(results, "CLOCK")

    def test_erp_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ERP")
        _assert_found(results, "ERP")

    def test_bias_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "BIA", {"AAA": "WUM"})
        _assert_found(results, "BIA")

    def test_attobx_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "ATTOBX", {"AAA": "WUM"})
        _assert_found(results, "ATTOBX")


# ---------------------------------------------------------------------------
# Integration: CODE FTP orbit probe
# ---------------------------------------------------------------------------


class TestCODOrbitProbe:
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

    def test_orbit_filenames_contain_cod(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "ORBIT")
        found = _assert_found(results, "ORBIT")
        for r in found:
            assert any("COD" in f for f in [r.product.filename.value])


# ---------------------------------------------------------------------------
# Integration: CDDIS FTPS orbit probe
# ---------------------------------------------------------------------------


class TestCDDISOrbitProbe:
    def test_orbit_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        _assert_found(results, "ORBIT")

    def test_clock_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "CLOCK", {"AAA": "IGS"})
        _assert_found(results, "CLOCK")

    def test_ftps_protocol_used(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "ORBIT", {"AAA": "WUM"})
        for r in results:
            assert r.server.protocol.lower() == "ftps"
