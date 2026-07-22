"""Tests for StationQuery.metadata() end-to-end with mocked HTTP.

Uses the `responses` library to intercept HTTP calls without live network.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
import responses as responses_lib
from gnss_product_management.client.station_query import StationQuery
from gnss_product_management.defaults import DefaultProductEnvironment
from gnss_product_management.environments.gnss_station_network import GNSSNetworkRegistry
from gpm_specs.configs import NETWORKS_RESOURCE_DIR

try:
    import responses as responses_lib

    HAS_RESPONSES = True
except ImportError:
    HAS_RESPONSES = False

pytestmark = pytest.mark.skipif(not HAS_RESPONSES, reason="responses library not installed")

DATE = datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc)
RADIUS_SEARCH_URL = "https://web-services.unavco.org/events/event_response/radius_search/beta"

# Minimal radius-search JSON fixture (flat array)
API_RESPONSE = [
    {
        "station_code": "FAIR",
        "lat": 64.978,
        "lon": -147.499,
        "latest_data_from_search": "2025-01-15",
    },
    {
        "station_code": "WHIT",
        "lat": 60.751,
        "lon": -135.224,
        "latest_data_from_search": "2025-01-15",
    },
    # Record missing required lat — should be skipped
    {
        "station_code": "BAD",
        "lon": -100.0,
    },
]


@pytest.fixture(scope="module")
def ert_env() -> GNSSNetworkRegistry:
    reg = GNSSNetworkRegistry.from_config(NETWORKS_RESOURCE_DIR)
    reg.bind(DefaultProductEnvironment)
    return reg


@pytest.fixture
def station_query(ert_env) -> StationQuery:
    return StationQuery(
        wormhole=MagicMock(),
        search_planner=MagicMock(),
        network_env=ert_env,
    )


# ── metadata() with mocked HTTP ───────────────────────────────────────
@responses_lib.activate
def test_metadata_returns_stations(station_query) -> None:
    responses_lib.add(
        responses_lib.GET,
        RADIUS_SEARCH_URL,
        json=API_RESPONSE,
        status=200,
    )
    stations = station_query.within(62.0, -140.0, 500.0).networks("ERT").on(DATE).metadata()
    assert len(stations) == 2
    codes = {s.site_code for s in stations}
    assert codes == {"FAIR", "WHIT"}


@responses_lib.activate
def test_metadata_skips_bad_records(station_query) -> None:
    responses_lib.add(
        responses_lib.GET,
        RADIUS_SEARCH_URL,
        json=API_RESPONSE,
        status=200,
    )
    stations = station_query.within(62.0, -140.0, 500.0).networks("ERT").on(DATE).metadata()
    # BAD record (missing lat) should be silently skipped
    assert all(s.site_code != "BAD" for s in stations)


@responses_lib.activate
def test_metadata_partial_failure_returns_partial_results(station_query) -> None:
    """Unreachable center returns partial results, not an error."""
    responses_lib.add(
        responses_lib.GET,
        RADIUS_SEARCH_URL,
        body=Exception("connection refused"),
    )
    # Should return empty list (ERT failed) but NOT raise
    stations = station_query.within(62.0, -140.0, 500.0).networks("ERT").on(DATE).metadata()
    assert stations == []


@responses_lib.activate
def test_metadata_temporal_filter(station_query) -> None:
    """Stations outside the date window should be filtered."""
    response_with_old_station = [
        {
            "station_code": "FAIR",
            "lat": 64.978,
            "lon": -147.499,
            "latest_data_from_search": "2000-12-31",  # ended before our date
        },
        {
            "station_code": "WHIT",
            "lat": 60.751,
            "lon": -135.224,
            # No latest_data_from_search — treated as still active
        },
    ]
    responses_lib.add(
        responses_lib.GET,
        RADIUS_SEARCH_URL,
        json=response_with_old_station,
        status=200,
    )
    stations = (
        station_query.within(62.0, -140.0, 500.0)
        .networks("ERT")
        .on(DATE)  # 2025-01-15
        .metadata()
    )
    codes = {s.site_code for s in stations}
    assert "FAIR" not in codes  # ended in 2000
    assert "WHIT" in codes  # still active


def test_gnss_client_station_query_returns_station_query() -> None:
    """GNSSClient.station_query() returns a StationQuery instance."""
    from gnss_product_management.client.gnss_client import GNSSClient

    client = GNSSClient.from_defaults()
    sq = client.station_query()
    assert isinstance(sq, StationQuery)
