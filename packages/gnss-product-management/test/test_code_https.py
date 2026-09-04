"""Regression tests for CODE's S3-backed HTTPS product archive."""

from unittest.mock import MagicMock

import pytest
from gnss_product_management.client.product_query import _remote_uri
from gnss_product_management.factories.connection_pool import ConnectionPoolFactory


def test_configured_https_listing_extracts_download_filenames(monkeypatch) -> None:
    html = b"""
    <a href="https://archive.example/download/CODE/COD0OPSRAP_20262390000_01D_05M_ORB.SP3">
      COD0OPSRAP_20262390000_01D_05M_ORB.SP3
    </a>
    """
    factory = ConnectionPoolFactory(max_connections=1)
    hostname = "https://archive.example/download"
    factory.add_connection(
        hostname,
        listing_url="https://listing.example/browse?path={directory}",
    )
    pool = factory._pools[hostname]
    connection = MagicMock()
    connection.cat_file.return_value = html
    monkeypatch.setattr(pool, "_connect", lambda: connection)

    assert factory.list_directory(hostname, "CODE/") == [
        "COD0OPSRAP_20262390000_01D_05M_ORB.SP3"
    ]
    connection.cat_file.assert_called_once_with(
        "https://listing.example/browse?path=CODE"
    )


def test_code_spec_configures_aiub_listing_url(cod_qf, test_date) -> None:
    targets = cod_qf.get(date=test_date, product={"name": "ORBIT"})
    remote = [target for target in targets if target.server.protocol == "https"]

    assert remote
    assert all(
        target.server.listing_url
        == (
            "https://code.aiub.unibe.ch/s3_script/"
            "aiub_s3_bucket_listing.php?path={directory}"
        )
        for target in remote
    )


@pytest.mark.parametrize("product", ["ORBIT", "CLOCK", "ERP", "BIA"])
@pytest.mark.parametrize(
    ("timeliness", "expected_directory"),
    [("FIN", "CODE/2025/"), ("RAP", "CODE/")],
)
def test_code_precise_product_directory_matches_family(
    cod_qf, test_date, product, timeliness, expected_directory
) -> None:
    targets = cod_qf.get(
        date=test_date,
        product={"name": product},
        parameters={"TTT": timeliness},
    )
    remote = [target for target in targets if target.server.protocol == "https"]

    assert remote
    assert {
        target.directory.value or target.directory.pattern for target in remote
    } == {expected_directory}


@pytest.mark.parametrize(
    ("timeliness", "expected_directory"),
    [("FIN", "CODE/2025/"), ("RAP", "CODE/"), ("PRD", "CODE/")],
)
def test_code_ionosphere_directory_matches_family(
    cod_qf, test_date, timeliness, expected_directory
) -> None:
    targets = cod_qf.get(
        date=test_date,
        product={"name": "IONEX"},
        parameters={"TTT": timeliness},
    )
    remote = [target for target in targets if target.server.protocol == "https"]

    assert remote
    assert {
        target.directory.value or target.directory.pattern for target in remote
    } == {expected_directory}


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
