"""Tests for StationQuery fluent builder — immutable-clone pattern.

Pure unit tests: no network calls, no filesystem access.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from gnss_product_management.client.station_query import StationQuery
from gnss_product_management.environments.gnss_station_network import (
    BoundingBox,
    GNSSNetworkRegistry,
    PointRadius,
)

# ── Fixtures ───────────────────────────────────────────────────────────

DATE = datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc)


def _query() -> StationQuery:
    """Return a fresh StationQuery with mock dependencies."""
    reg = GNSSNetworkRegistry()
    return StationQuery(
        wormhole=MagicMock(),
        search_planner=MagicMock(),
        network_env=reg,
    )


# ── .within() ─────────────────────────────────────────────────────────


class TestWithin:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.within(60.0, -150.0, 100.0) is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.within(60.0, -150.0, 100.0)
        assert q._spatial_filter is None

    def test_sets_point_radius(self) -> None:
        q = _query().within(60.0, -150.0, 100.0)
        assert isinstance(q._spatial_filter, PointRadius)
        assert q._spatial_filter.lat == 60.0
        assert q._spatial_filter.radius_km == 100.0

    def test_last_wins_over_in_bbox(self) -> None:
        q = _query().in_bbox(59.0, -151.0, 61.0, -149.0).within(60.0, -150.0, 50.0)
        assert isinstance(q._spatial_filter, PointRadius)


# ── .in_bbox() ────────────────────────────────────────────────────────


class TestInBbox:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.in_bbox(59.0, -151.0, 61.0, -149.0) is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.in_bbox(59.0, -151.0, 61.0, -149.0)
        assert q._spatial_filter is None

    def test_sets_bbox(self) -> None:
        q = _query().in_bbox(59.0, -151.0, 61.0, -149.0)
        assert isinstance(q._spatial_filter, BoundingBox)
        assert q._spatial_filter.min_lat == 59.0

    def test_last_wins_over_within(self) -> None:
        q = _query().within(60.0, -150.0, 50.0).in_bbox(59.0, -151.0, 61.0, -149.0)
        assert isinstance(q._spatial_filter, BoundingBox)


# ── .from_stations() ──────────────────────────────────────────────────


class TestFromStations:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.from_stations("FAIR") is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.from_stations("FAIR")
        assert q._station_codes is None

    def test_codes_stored(self) -> None:
        q = _query().from_stations("FAIR", "WHIT")
        assert "FAIR" in q._station_codes
        assert "WHIT" in q._station_codes


# ── .centers() ────────────────────────────────────────────────────────


class TestCenters:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.networks("ERT") is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.networks("ERT")
        assert q._network_ids is None

    def test_ids_stored(self) -> None:
        q = _query().networks("ERT", "CORS")
        assert "ERT" in q._network_ids
        assert "CORS" in q._network_ids

    def test_last_call_wins(self) -> None:
        q = _query().networks("ERT").networks("CORS")
        assert q._network_ids == ("CORS",)


# ── .on() ─────────────────────────────────────────────────────────────


class TestOn:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.on(DATE) is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.on(DATE)
        assert q._date is None

    def test_date_set(self) -> None:
        q = _query().on(DATE)
        assert q._date == DATE

    def test_last_call_wins(self) -> None:
        date2 = datetime.datetime(2025, 2, 1, tzinfo=datetime.timezone.utc)
        q = _query().on(DATE).on(date2)
        assert q._date == date2


# ── .rinex_version() ──────────────────────────────────────────────────


class TestRinexVersion:
    def test_default_is_3(self) -> None:
        assert _query()._rinex_version == "3"

    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.rinex_version("2") is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.rinex_version("2")
        assert q._rinex_version == "3"

    def test_version_set(self) -> None:
        q = _query().rinex_version("2")
        assert q._rinex_version == "2"


# ── .refresh_index() ──────────────────────────────────────────────────


class TestRefreshIndex:
    def test_returns_new_instance(self) -> None:
        q = _query()
        assert q.refresh_index() is not q

    def test_original_unchanged(self) -> None:
        q = _query()
        q.refresh_index()
        assert q._refresh_index is False


# ── Validation ────────────────────────────────────────────────────────


class TestValidation:
    def test_metadata_without_filter_raises(self) -> None:
        q = _query().networks("ERT").on(DATE)
        with pytest.raises(ValueError, match="within"):
            q.metadata()

    def test_metadata_with_from_stations_no_centers_raises(self) -> None:
        q = _query().from_stations("FAIR").on(DATE)
        with pytest.raises(ValueError, match="networks"):
            q.metadata()

    def test_metadata_with_spatial_filter_and_no_centers_is_valid(self) -> None:
        # Should not raise (centers is optional for spatial queries)
        q = _query().within(60.0, -150.0, 100.0).on(DATE)
        # Will return empty list since no networks registered
        result = q.metadata()
        assert result == []

    def test_metadata_with_from_stations_and_centers_is_valid(self) -> None:
        # Should not raise
        q = _query().from_stations("FAIR").networks("ERT").on(DATE)
        result = q.metadata()
        assert isinstance(result, list)
