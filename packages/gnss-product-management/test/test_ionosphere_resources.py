"""
Tests: Ionosphere (GIM) products via SearchPlanner.

Products: IONEX
Centers : CODE (FTP), Wuhan (FTP), CDDIS (FTPS)
"""

from __future__ import annotations

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
# Unit: CODE GIM query expansion
# ---------------------------------------------------------------------------


class TestCODGIMExpansion:
    def test_ionex_queries_returned(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "IONEX")
        assert len(queries) > 0

    def test_ionex_server_protocol(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "IONEX")
        for q in queries:
            assert q.server.protocol.lower() == "https"

    def test_ionex_directory_not_empty(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "IONEX")
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert len(d) > 0

    def test_ionex_filename_pattern(self, cod_qf, test_date) -> None:
        queries = _get_remote_queries(cod_qf, test_date, "IONEX")
        patterns = [q.product.filename.pattern for q in queries]
        assert any("INX" in p.upper() or "GIM" in p.upper() for p in patterns)


# ---------------------------------------------------------------------------
# Unit: Wuhan GIM query expansion
# ---------------------------------------------------------------------------


class TestWuhanGIMExpansion:
    def test_ionex_queries_returned(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "IONEX")
        assert len(queries) > 0

    def test_ionex_server_protocol(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "IONEX")
        for q in queries:
            assert q.server.protocol.lower() == "ftp"

    def test_ionex_directory_not_empty(self, wuhan_qf, test_date) -> None:
        queries = _get_remote_queries(wuhan_qf, test_date, "IONEX")
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert len(d) > 0


# ---------------------------------------------------------------------------
# Unit: CDDIS GIM query expansion
# ---------------------------------------------------------------------------


class TestCDDISGIMExpansion:
    def test_ionex_queries_returned(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "IONEX", {"AAA": "COD"})
        assert len(queries) > 0

    def test_ionex_protocol_is_ftps(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "IONEX", {"AAA": "COD"})
        for q in queries:
            assert q.server.protocol.lower() == "ftps"

    def test_ionex_directory_not_empty(self, cddis_qf, test_date) -> None:
        queries = _get_remote_queries(cddis_qf, test_date, "IONEX", {"AAA": "COD"})
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert len(d) > 0


# ---------------------------------------------------------------------------
# Integration: CODE GIM probe
# ---------------------------------------------------------------------------


class TestCODGIMProbe:
    def test_ionex_found(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "IONEX")
        _assert_found(results, "IONEX")

    def test_ionex_filenames_contain_gim_or_inx(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "IONEX")
        found = _assert_found(results, "IONEX")
        for r in found:
            assert any("GIM" in f.upper() or "INX" in f.upper() for f in [r.product.filename.value])

    def test_ionex_filenames_contain_cod(self, cod_qf, fetcher, test_date) -> None:
        results = _search_remote(cod_qf, fetcher, test_date, "IONEX")
        found = _assert_found(results, "IONEX")
        for r in found:
            assert any("COD" in f for f in [r.product.filename.value])


# ---------------------------------------------------------------------------
# Integration: Wuhan GIM probe
# ---------------------------------------------------------------------------


class TestWuhanGIMProbe:
    def test_ionex_found(self, wuhan_qf, fetcher, test_date) -> None:
        results = _search_remote(wuhan_qf, fetcher, test_date, "IONEX")
        _assert_found(results, "IONEX")


# ---------------------------------------------------------------------------
# Integration: CDDIS GIM probe
# ---------------------------------------------------------------------------


class TestCDDISGIMProbe:
    def test_ionex_found(self, cddis_qf, fetcher, test_date) -> None:
        results = _search_remote(cddis_qf, fetcher, test_date, "IONEX", {"AAA": "COD"})
        _assert_found(results, "IONEX")
