"""
Tests: Orography grid products via SearchPlanner.

Products: OROGRAPHY (plain VMF1), OROGRAPHY_1X1, OROGRAPHY_5X5
Centers : VMF / TU Wien (HTTPS)
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
# Unit: Orography query expansion
# ---------------------------------------------------------------------------


class TestOrographyExpansion:
    @pytest.mark.parametrize("product_name", ["OROGRAPHY_1X1", "OROGRAPHY_5X5"])
    def test_orography_queries_returned(self, vmf_qf, test_date, product_name) -> None:
        queries = _get_remote_queries(vmf_qf, test_date, product_name)
        assert len(queries) > 0

    @pytest.mark.parametrize("product_name", ["OROGRAPHY_1X1", "OROGRAPHY_5X5"])
    def test_orography_server_protocol_is_https(self, vmf_qf, test_date, product_name) -> None:
        queries = _get_remote_queries(vmf_qf, test_date, product_name)
        for q in queries:
            assert q.server.protocol.lower() == "https"

    def test_orography_1x1_filename_pattern(self, vmf_qf, test_date) -> None:
        queries = _get_remote_queries(vmf_qf, test_date, "OROGRAPHY_1X1")
        patterns = [q.product.filename.pattern for q in queries]
        assert any("1x1" in p for p in patterns)

    def test_orography_5x5_filename_pattern(self, vmf_qf, test_date) -> None:
        queries = _get_remote_queries(vmf_qf, test_date, "OROGRAPHY_5X5")
        patterns = [q.product.filename.pattern for q in queries]
        assert any("5x5" in p for p in patterns)

    @pytest.mark.parametrize("product_name", ["OROGRAPHY_1X1", "OROGRAPHY_5X5"])
    def test_orography_at_least_one_query(self, vmf_qf, test_date, product_name) -> None:
        queries = _get_remote_queries(vmf_qf, test_date, product_name)
        assert len(queries) >= 1

    def test_orography_1x1_and_5x5_are_distinct_products(self, vmf_qf, test_date) -> None:
        """Regression: OROGRAPHY_1X1 and OROGRAPHY_5X5 used to share the
        product name OROGRAPHY, so a query for one could resolve to the
        other's file. They must now be independent products."""
        queries_1x1 = _get_remote_queries(vmf_qf, test_date, "OROGRAPHY_1X1")
        queries_5x5 = _get_remote_queries(vmf_qf, test_date, "OROGRAPHY_5X5")
        filenames_1x1 = {q.product.filename.pattern for q in queries_1x1}
        filenames_5x5 = {q.product.filename.pattern for q in queries_5x5}
        assert filenames_1x1.isdisjoint(filenames_5x5)

    def test_plain_orography_does_not_resolve_to_a_resolution_variant(
        self, vmf_qf, test_date
    ) -> None:
        """Regression: plain OROGRAPHY (VMF1) must not resolve against the
        VMF/TU Wien resolution-specific resources — it's a static table file
        bundled with PRIDE-PPPAR, not something fetched from TU Wien."""
        queries = _get_remote_queries(vmf_qf, test_date, "OROGRAPHY")
        assert queries == []


# ---------------------------------------------------------------------------
# Integration: Orography HTTPS probe
# ---------------------------------------------------------------------------


class TestOrographyProbe:
    @pytest.mark.parametrize("product_name", ["OROGRAPHY_1X1", "OROGRAPHY_5X5"])
    def test_orography_found(self, vmf_qf, fetcher, test_date, product_name) -> None:
        results = _search_remote(vmf_qf, fetcher, test_date, product_name)
        _assert_found(results, product_name)
