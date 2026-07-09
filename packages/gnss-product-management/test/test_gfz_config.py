"""GFZ center config regression tests.

These tests lock in the 2026 GFZ ISDC archive migration:
- anonymous SFTP endpoint at isdc-data.gfz.de
- separate final/rapid archives
- OPS-only products on this endpoint
"""

from __future__ import annotations


def _remote_queries(qf, date, product_name: str):
    queries = qf.get(date=date, product={"name": product_name})
    return [q for q in queries if (q.server.protocol or "").upper() not in ("FILE", "LOCAL", "")]


def _param_values(query, name: str) -> list[str]:
    return [p.value for p in query.product.parameters if p.name == name and p.value is not None]


class TestGFZConfig:
    def test_gfz_uses_isdc_sftp_endpoint(self, gfz_qf, test_date) -> None:
        queries = _remote_queries(gfz_qf, test_date, "ORBIT")
        assert queries
        for q in queries:
            assert q.server.protocol.lower() == "sftp"
            assert "isdc-data.gfz.de" in q.server.hostname

    def test_gfz_orbit_queries_split_final_and_rapid_archives(self, gfz_qf, test_date) -> None:
        queries = _remote_queries(gfz_qf, test_date, "ORBIT")
        assert queries

        final_dirs = []
        rapid_dirs = []
        for q in queries:
            directory = q.directory.value or q.directory.pattern
            ttt_values = _param_values(q, "TTT")
            if "FIN" in ttt_values:
                final_dirs.append(directory)
            if "RAP" in ttt_values:
                rapid_dirs.append(directory)

        assert final_dirs
        assert rapid_dirs
        assert all("/gnss/products/final/w" in d for d in final_dirs)
        assert all("/gnss/products/rapid/w" in d for d in rapid_dirs)

    def test_gfz_queries_are_ops_only(self, gfz_qf, test_date) -> None:
        for product_name in ("ORBIT", "CLOCK", "ERP", "SINEX", "TROP"):
            queries = _remote_queries(gfz_qf, test_date, product_name)
            assert queries
            for q in queries:
                assert _param_values(q, "AAA") == ["GFZ"]
                assert _param_values(q, "PPP") == ["OPS"]
