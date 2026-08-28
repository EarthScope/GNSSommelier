"""Regression tests for CODE's S3-backed HTTPS product archive."""

from unittest.mock import MagicMock

from gnss_product_management.client.product_query import _remote_uri
from gnss_product_management.factories.connection_pool import ConnectionPoolFactory


def test_code_https_listing_extracts_download_filenames(monkeypatch) -> None:
    html = b"""
    <a href="https://www.aiub.unibe.ch/download/CODE/COD0OPSRAP_20262390000_01D_05M_ORB.SP3">
      COD0OPSRAP_20262390000_01D_05M_ORB.SP3
    </a>
    """
    factory = ConnectionPoolFactory(max_connections=1)
    hostname = "https://www.aiub.unibe.ch/download"
    factory.add_connection(hostname)
    pool = factory._pools[hostname]
    connection = MagicMock()
    connection.cat_file.return_value = html
    monkeypatch.setattr(pool, "_connect", lambda: connection)

    assert factory.list_directory(hostname, "CODE/") == [
        "COD0OPSRAP_20262390000_01D_05M_ORB.SP3"
    ]


def test_remote_uri_keeps_existing_https_scheme() -> None:
    assert _remote_uri(
        "https",
        "https://www.aiub.unibe.ch/download",
        "CODE/",
        "COD0OPSRAP_20262390000_01D_05M_ORB.SP3",
    ) == (
        "https://www.aiub.unibe.ch/download/CODE/"
        "COD0OPSRAP_20262390000_01D_05M_ORB.SP3"
    )
