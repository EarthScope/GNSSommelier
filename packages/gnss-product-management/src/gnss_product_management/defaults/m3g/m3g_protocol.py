"""Generic M3G-backed network protocol.

Queries the M3G (Metadata Management and Distribution System for Multiple
GNSS Networks) REST API hosted at gnss-metadata.eu for station metadata.
A single class serves any of the ~96 networks catalogued by M3G — each
instance is parameterised by network ID.

API docs: https://gnss-metadata.eu/site/api-docs
Data licensed under CC BY 4.0: https://doi.org/10.24414/ROB-GNSS-M3G
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

import numpy as np
import requests
from shapely import Point, STRtree

from gnss_product_management.environments.gnss_station_network import (
    GNSSStation,
    NetworkProtocol,
)

logger = logging.getLogger(__name__)

_M3G_BASE = "https://gnss-metadata.eu/v1"
_GEOJSON_URL = f"{_M3G_BASE}/sitelog/geojson"
_NETWORK_URL = f"{_M3G_BASE}/network/view"

_CACHE_FILE = Path(__file__).parent / "m3g_cache.json"


class M3GStation:
    """Lightweight station record parsed from M3G GeoJSON."""

    __slots__ = ("nine_char_id", "site_code", "lat", "lon", "country_code")

    def __init__(
        self,
        nine_char_id: str,
        lat: float,
        lon: float,
        country_code: str = "",
    ) -> None:
        self.nine_char_id = nine_char_id
        self.site_code = nine_char_id[:4].lower()
        self.lat = lat
        self.lon = lon
        self.country_code = country_code


class M3GStationIndex:
    """Spatial index of stations for a single M3G network."""

    def __init__(self, stations: list[M3GStation]) -> None:
        self.stations = stations
        self._rtree = STRtree([Point(s.lon, s.lat) for s in stations])

    def within(self, lat: float, lon: float, radius_km: float) -> list[M3GStation]:
        center = Point(lon, lat)
        km_to_deg = 111 * np.cos(np.radians(lat))
        buffer = center.buffer(radius_km / km_to_deg)
        idxs: np.ndarray = self._rtree.query(buffer)
        return [self.stations[i] for i in idxs.tolist()]

    @classmethod
    def from_geojson(cls, features: list[dict]) -> M3GStationIndex:
        stations: list[M3GStation] = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates")
            if coords is None or len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            nine_char = props.get("id", "")
            location = props.get("location", {})
            country = location.get("countryCode", "") if isinstance(location, dict) else ""
            stations.append(M3GStation(nine_char, lat, lon, country))
        return cls(stations)


def _fetch_network_geojson(network_id: str) -> list[dict]:
    """Fetch all GeoJSON features for *network_id* from M3G API.

    The M3G API caps responses at 50 items per page, so we paginate
    until an empty or partial page is returned.
    """
    all_features: list[dict] = []
    page = 1
    per_page = 50
    while True:
        resp = requests.get(
            _GEOJSON_URL,
            params={"network": network_id, "page": page, "per-page": per_page},
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_features.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return all_features


# Parsed once and shared across all ~95 M3GNetworkProtocol instances — the
# consolidated cache file is several MB and re-reading it per network made
# broad queries pay the JSON-parse cost ~95 times.
_cache_data: dict[str, list[dict]] | None = None


def _load_cache() -> dict[str, list[dict]]:
    global _cache_data
    if _cache_data is None:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE) as f:
                _cache_data = json.load(f)
        else:
            _cache_data = {}
    return _cache_data


def _save_cache(data: dict[str, list[dict]]) -> None:
    global _cache_data
    _cache_data = data
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump(data, f, separators=(",", ":"))


class M3GNetworkProtocol(NetworkProtocol):
    """NetworkProtocol backed by the M3G REST API.

    Parameters
    ----------
    network_id:
        The M3G network identifier (e.g. ``"EPN"``, ``"RING"``,
        ``"RENAG"``).  Must match exactly what the M3G API returns.
    use_cache:
        If ``True`` (default), station metadata is loaded from the
        consolidated ``m3g_cache.json`` when available, falling back
        to the live API.  Set ``False`` to always query live.
    """

    def __init__(self, network_id: str, *, use_cache: bool = True) -> None:
        self._network_id = network_id
        self._use_cache = use_cache
        self._index: M3GStationIndex | None = None

    @property
    def id(self) -> str:  # type: ignore[override]
        return self._network_id

    def _ensure_index(self) -> M3GStationIndex:
        if self._index is not None:
            return self._index

        if self._use_cache:
            cached = _load_cache()
            if self._network_id in cached:
                logger.debug("Loading cached M3G index for %s", self._network_id)
                self._index = M3GStationIndex.from_geojson(cached[self._network_id])
                return self._index

        logger.info("Fetching M3G station metadata for network %s", self._network_id)
        try:
            features = _fetch_network_geojson(self._network_id)
        except requests.RequestException:
            logger.warning("Failed to fetch M3G data for %s", self._network_id, exc_info=True)
            self._index = M3GStationIndex([])
            return self._index

        self._index = M3GStationIndex.from_geojson(features)

        # Persist to consolidated cache
        try:
            cache_data = _load_cache()
            cache_data[self._network_id] = features
            _save_cache(cache_data)
            logger.debug("Cached %d stations for %s", len(self._index.stations), self._network_id)
        except OSError:
            logger.debug("Could not write cache for %s", self._network_id, exc_info=True)

        return self._index

    def radius_spatial_query(
        self,
        date: datetime.datetime,  # noqa: ARG002
        lat: float,
        lon: float,
        radius_km: float,
    ) -> list[GNSSStation] | None:
        index = self._ensure_index()
        matches = index.within(lat, lon, radius_km)
        return [
            GNSSStation(
                site_code=s.site_code,
                lat=s.lat,
                lon=s.lon,
                network_id=self._network_id,
            )
            for s in matches
        ]

    def station_catalog(self) -> list[GNSSStation] | None:
        """Enumerate stations from the bundled cache only — never hits the API."""
        features = _load_cache().get(self._network_id)
        if features is None:
            return None
        stations: list[GNSSStation] = []
        for feat in features:
            coords = feat.get("geometry", {}).get("coordinates")
            nine_char = feat.get("properties", {}).get("id", "")
            if not nine_char or not coords or len(coords) < 2:
                continue
            stations.append(
                GNSSStation(
                    site_code=nine_char[:4].lower(),
                    lat=coords[1],
                    lon=coords[0],
                    network_id=self._network_id,
                )
            )
        return stations

    def parse_spatial_query_response(self, response: object) -> list[GNSSStation] | None:
        return None

    def login(self) -> str | None:
        return None

    def filesystem(self) -> object | None:
        return None
