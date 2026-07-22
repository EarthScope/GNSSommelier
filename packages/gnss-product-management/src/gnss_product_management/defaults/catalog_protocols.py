"""Network protocols backed by bundled YAML station catalogs.

Each protocol loads its station coordinates from a catalog shipped in
``gpm_specs`` under ``configs/networks/`` and answers point-radius
queries with a Shapely STRtree.  Catalog schema::

    stations:
    - site_code: abmf
      lat: 16.2623
      lon: -61.527537
      server_id: IGN

Networks that need live API access or authentication (EarthScope, M3G)
have dedicated modules instead.
"""

import datetime
from pathlib import Path

import numpy as np
import yaml
from shapely import Point, STRtree

from gnss_product_management.environments.gnss_station_network import (
    GNSSStation,
    NetworkProtocol,
)


class YAMLCatalogProtocol(NetworkProtocol):
    """Point-radius spatial queries over a bundled YAML station catalog.

    Subclasses set :attr:`id` and :attr:`catalog_name`.  When
    :attr:`pin_data_center` is true (the default), each station's catalog
    ``server_id`` is carried as :attr:`GNSSStation.data_center`, routing
    downloads to the archive that hosts the station.  Disable it for
    networks whose servers all mirror every station.
    """

    id: str
    catalog_name: str
    pin_data_center: bool = True

    def __init__(self, catalog_path: Path | None = None) -> None:
        if catalog_path is None:
            from gpm_specs.configs import NETWORKS_RESOURCE_DIR

            catalog_path = Path(NETWORKS_RESOURCE_DIR) / self.catalog_name

        with open(catalog_path) as f:
            data = yaml.safe_load(f)

        self._stations: list[dict] = data["stations"]
        self._rtree = STRtree([Point(s["lon"], s["lat"]) for s in self._stations])

    def _within(self, lat: float, lon: float, radius_km: float) -> list[dict]:
        center = Point(lon, lat)
        km_to_deg = 111 * np.cos(np.radians(lat))
        buffer = center.buffer(radius_km / km_to_deg)
        matches: np.ndarray = self._rtree.query(buffer)
        return [self._stations[i] for i in matches.tolist()]

    def radius_spatial_query(
        self,
        date: datetime.datetime,
        lat: float,
        lon: float,
        radius_km: float,
    ) -> list[GNSSStation] | None:
        return [
            GNSSStation(
                site_code=s["site_code"],
                lat=s["lat"],
                lon=s["lon"],
                network_id=self.id,
                data_center=s.get("server_id") if self.pin_data_center else None,
            )
            for s in self._within(lat, lon, radius_km)
        ]


class IGSProtocol(YAMLCatalogProtocol):
    """IGS global network — stations pinned to their archive (CDDIS, IGN, BKG)."""

    id = "IGS"
    catalog_name = "igs_stations.yaml"


class GAProtocol(YAMLCatalogProtocol):
    """Geoscience Australia CORS network (public, data.gnss.ga.gov.au)."""

    id = "GA"
    catalog_name = "ga_stations.yaml"


class RBMCProtocol(YAMLCatalogProtocol):
    """Brazilian RBMC network (public, geoftp.ibge.gov.br)."""

    id = "RBMC"
    catalog_name = "rbmc_stations.yaml"


class NOAACORSProtocol(YAMLCatalogProtocol):
    """NOAA CORS network — NGS and S3 servers both mirror every station."""

    id = "CORS"
    catalog_name = "cors_stations.yaml"
    pin_data_center = False
