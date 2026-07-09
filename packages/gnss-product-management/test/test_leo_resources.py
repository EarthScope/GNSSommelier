"""
Tests: LEO satellite (GRACE) products via SearchPlanner.

Products: LEO_L1B
Centers : GFZ (SFTP)
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skip(reason="LEO_L1B not yet configured in GFZ center config"),
]


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
# Unit: GFZ LEO query expansion
# ---------------------------------------------------------------------------


class TestGFZLEOExpansion:
    def test_leo_queries_returned(self, gfz_qf, test_date) -> None:
        queries = _get_remote_queries(gfz_qf, test_date, "LEO_L1B")
        assert len(queries) > 0

    def test_leo_server_protocol_is_sftp(self, gfz_qf, test_date) -> None:
        queries = _get_remote_queries(gfz_qf, test_date, "LEO_L1B")
        for q in queries:
            assert q.server.protocol.lower() == "sftp"

    def test_leo_directory_not_empty(self, gfz_qf, test_date) -> None:
        queries = _get_remote_queries(gfz_qf, test_date, "LEO_L1B")
        for q in queries:
            d = q.directory.value or q.directory.pattern
            assert len(d) > 0


# ---------------------------------------------------------------------------
# Integration: GFZ LEO probe
# ---------------------------------------------------------------------------


class TestGFZLEOProbe:
    def test_leo_found(self, gfz_qf, fetcher, test_date) -> None:
        results = _search_remote(gfz_qf, fetcher, test_date, "LEO_L1B")
        _assert_found(results, "LEO_L1B")
