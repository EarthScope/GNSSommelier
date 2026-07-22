"""NetworkRegistry — loads network configs and manages registered query functions.

Network configs live in YAML files under ``configs/networks/``.  Each config
describes a GNSS station data network (distinct from product-only IGS centers).

Network-specific logic is registered via four decorator methods::

    registry = NetworkRegistry.from_config("configs/networks/")

    @registry.station_query("ERT")
    def query_earthscope(filter, context):
        ...

    @registry.response_adapter("ERT")
    def adapt_earthscope(raw):
        ...

    @registry.credential("earthscope_token")
    def resolve_token(env_var):
        ...

    @registry.filesystem("ERT")
    def build_fs(credentials):
        ...
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    import fsspec

from gnss_product_management.specifications.parameters.parameter import (
    Parameter,
    ParameterCatalog,
)
from gnss_product_management.specifications.products.product import Product
from gnss_product_management.specifications.remote.resource import (
    ResourceSpec,
    SearchTarget,
)

logger = logging.getLogger(__name__)


class GNSSStation(BaseModel):
    """Minimal metadata for a GNSS station.

    Required fields uniquely identify and locate the station.  Optional
    fields describe network membership and operational window.

    ``end_date=None`` means the station is currently active.
    ``start_date=None`` means the operational start is unknown; such
    stations are *included* rather than excluded by temporal filters.
    ``data_center`` carries the short identifier of the archive that hosts
    this station's observation files (e.g. ``"CDDIS"``, ``"IGN"``,
    ``"BKG"``).  When set, the search planner will route downloads to the
    matching server rather than trying all servers in the network config.
    """

    site_code: str
    lat: float
    lon: float
    network_id: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    data_center: str | None = None


class PointRadius(BaseModel):
    """Great-circle spatial filter: all stations within *radius_km* of a point."""

    type: Literal["point_radius"] = "point_radius"
    lat: float
    lon: float
    radius_km: float

    @model_validator(mode="after")
    def _check_radius(self) -> PointRadius:
        if self.radius_km <= 0:
            raise ValueError(f"radius_km must be positive, got {self.radius_km}")
        return self


class BoundingBox(BaseModel):
    """Rectangular spatial filter defined by latitude/longitude bounds."""

    type: Literal["bbox"] = "bbox"
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @model_validator(mode="after")
    def _check_bounds(self) -> BoundingBox:
        if self.min_lat > self.max_lat:
            raise ValueError(f"min_lat ({self.min_lat}) must not exceed max_lat ({self.max_lat})")
        return self


SpatialFilter = Annotated[PointRadius | BoundingBox, Field(discriminator="type")]


class NetworkProtocol(Protocol):
    """Protocol for executing a spatial station query against a network."""

    id: str

    def radius_spatial_query(
        self,
        date: Any,
        lat: float,
        lon: float,
        radius_km: float,
    ) -> list[GNSSStation] | None:
        """Execute a spatial query for stations within *radius_km* of the
        point (*lat*, *lon*).
        """
        return None

    def station_catalog(self) -> list[GNSSStation] | None:
        """Return every station this network hosts, if enumerable offline.

        Backs the registry's station→network index so explicit station-code
        queries can be routed to the right network without touching every
        server.  Return ``None`` when the network can only be queried live
        (e.g. EarthScope).
        """
        return None

    def parse_spatial_query_response(self, response: Any) -> list[GNSSStation] | None:
        """Parse the raw response from a spatial query into a list of stations."""
        return None

    def login(self) -> str | None:
        """Perform any necessary login/authentication and return a token if needed."""
        return None

    def filesystem(self) -> fsspec.AbstractFileSystem | None:
        """Return an authenticated fsspec filesystem for this network's archive server.

        Return ``None`` to let the connection pool create an anonymous connection.
        Implement this when the archive requires credentials (e.g. Bearer tokens).
        """
        return None


class GNSSNetworkRegistry:
    """Maps network IDs to configs and decorator-registered functions.

    Use :meth:`from_config` to load from a directory of YAML files, then
    decorate functions to register network-specific logic.
    """

    def __init__(self) -> None:
        self._network_protocols: dict[str, NetworkProtocol] = {}
        self._configs: dict[str, ResourceSpec] = {}
        self._station_queries: dict[str, Callable] = {}
        self._login_calls: dict[str, Callable] = {}
        self._response_adapters: dict[str, Callable] = {}
        self._parameter_catalog: ParameterCatalog | None = None
        self._station_index: dict[str, list[GNSSStation]] | None = None

    def load_config(self, config_path: Path | str) -> None:
        """Load a single network config from *config_path*."""
        with open(config_path) as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict) or "id" not in raw:
            raise ValueError(f"Invalid network config: {config_path}")
        config = ResourceSpec.model_validate(raw)
        self._configs[config.id] = config
        logger.debug("Loaded network config: %s from %s", config.id, config_path)

    def register_protocol(self, protocol: NetworkProtocol) -> None:
        """Register a NetworkProtocol instance for a network."""
        assert protocol.id in self._configs, (
            f"Protocol ID {protocol.id!r} must match a loaded config"
        )
        self._network_protocols[protocol.id] = protocol
        self._station_index = None  # rebuilt lazily on next lookup
        logger.debug("Registered protocol for network: %s", protocol.id)

    # ── Loading ───────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config_dir: Path | str) -> GNSSNetworkRegistry:
        """Load all ``*.yaml`` files from *config_dir* into a new registry.

        Silently skips files that lack a top-level ``id`` field (they are
        not network configs).  Files whose top-level value is a *list* are
        treated as M3G-style multi-network manifests (each element must
        have at least ``id`` and ``name`` keys).

        Args:
            config_dir: Path to the directory containing network YAML files.

        Returns:
            A :class:`NetworkRegistry` populated with the loaded configs.
        """
        registry = cls()
        config_dir = Path(config_dir)

        for path in sorted(config_dir.rglob("*.yaml")):
            with open(path) as fh:
                raw = yaml.safe_load(fh)

            # ── Multi-network manifest (list of dicts) ────────────
            if isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, dict) or "id" not in entry:
                        continue
                    spec = registry._m3g_entry_to_spec(entry)
                    registry._configs[spec.id] = spec
                    logger.debug("Loaded M3G network: %s from %s", spec.id, path.name)
                continue

            # ── Single-network config (dict with id) ──────────────
            if not isinstance(raw, dict) or "id" not in raw:
                continue
            config = ResourceSpec.model_validate(raw)

            registry._configs[config.id] = config
            logger.debug("Loaded network config: %s from %s", config.id, path.name)

        return registry

    @staticmethod
    def _m3g_entry_to_spec(entry: dict) -> ResourceSpec:
        """Convert a lightweight M3G manifest entry to a ResourceSpec."""
        nid = entry["id"]
        name = entry.get("name", nid)
        parts = [name]
        if entry.get("country"):
            parts.append(f"Country: {entry['country']}.")
        if entry.get("agency"):
            parts.append(f"Operated by {entry['agency']}.")
        parts.append("Station metadata via M3G API (gnss-metadata.eu).")
        if entry.get("doi"):
            parts.append(f"DOI: {entry['doi']}")
        description = " ".join(parts)

        servers = []
        products = []
        if entry.get("euref"):
            safe_id = nid.replace(" ", "_").replace(".", "_").lower()

            # BKG EUREF Regional Data Centre — obs + nav, ~277 obs files/day.
            servers.append(
                {
                    "id": "BKG_EUREF",
                    "hostname": "ftp://igs-ftp.bkg.bund.de",
                    "protocol": "ftp",
                    "auth_required": False,
                    "description": "BKG EUREF Regional Data Centre (anonymous FTP).",
                }
            )
            products.append(
                {
                    "id": f"{safe_id}_bkg_rinex3_obs",
                    "product_name": "RINEX_OBS",
                    "server_id": "BKG_EUREF",
                    "available": True,
                    "description": f"RINEX 3 observation files for {nid} via BKG EUREF.",
                    "parameters": [{"name": "V", "value": "3"}],
                    "directory": {"pattern": "EUREF/obs/{YYYY}/{DDD}/"},
                }
            )

            # EPN Historical Data Centre (ROB) — definitive EPN archive,
            # ~394 obs files/day.
            servers.append(
                {
                    "id": "EPN_HDC",
                    "hostname": "ftp://ftp.epncb.oma.be",
                    "protocol": "ftp",
                    "auth_required": False,
                    "description": "EPN Historical Data Centre at ROB (anonymous FTP).",
                }
            )
            products.append(
                {
                    "id": f"{safe_id}_epn_rinex3_obs",
                    "product_name": "RINEX_OBS",
                    "server_id": "EPN_HDC",
                    "available": True,
                    "description": f"RINEX 3 observation files for {nid} via EPN-HDC.",
                    "parameters": [{"name": "V", "value": "3"}],
                    "directory": {"pattern": "pub/RINEX/{YYYY}/{DDD}/"},
                }
            )

        return ResourceSpec.model_validate(
            {
                "id": nid,
                "name": name,
                "description": description,
                "servers": servers,
                "products": products,
            }
        )

    # ── Lookups ───────────────────────────────────────────────────────

    @property
    def network_ids(self) -> list[str]:
        """Return all registered network IDs."""
        return list(self._configs.keys())

    def config_for(self, network_id: str) -> ResourceSpec:
        """Return the parsed config for *network_id*.

        Raises:
            KeyError: If the network is not registered.
        """
        if network_id not in self._configs:
            raise KeyError(f"Network {network_id!r} not found in registry")
        return self._configs[network_id]

    def get_protocol(self, network_id: str) -> NetworkProtocol | None:
        """Return the registered :class:`NetworkProtocol` for *network_id*, or ``None``."""
        return self._network_protocols.get(network_id)

    @property
    def station_index(self) -> dict[str, list[GNSSStation]]:
        """Lazily-built map of ``site_code`` → catalog entries across all protocols.

        Aggregates :meth:`NetworkProtocol.station_catalog` from every
        registered protocol that can enumerate its stations offline.  A code
        maps to one entry per hosting network.  Live-only networks (no
        catalog) do not appear.
        """
        if self._station_index is None:
            index: dict[str, list[GNSSStation]] = {}
            for protocol in self._network_protocols.values():
                catalog = protocol.station_catalog()
                if not catalog:
                    continue
                for station in catalog:
                    index.setdefault(station.site_code.lower(), []).append(station)
            self._station_index = index
            logger.debug("Built station index: %d unique site codes", len(index))
        return self._station_index

    def lookup_stations(
        self,
        site_code: str,
        network_ids: list[str] | None = None,
    ) -> list[GNSSStation]:
        """Return catalog entries for *site_code*, optionally scoped to *network_ids*.

        Returns an empty list when the code is not in any offline catalog —
        the station may still exist on a live-query network.
        """
        entries = self.station_index.get(site_code.lower(), [])
        if network_ids:
            entries = [s for s in entries if s.network_id in network_ids]
        return entries

    def has_station_query(self, network_id: str) -> bool:
        return network_id in self._station_queries

    def get_station_query(self, network_id: str) -> Callable | None:
        return self._station_queries.get(network_id)

    def get_response_adapter(self, network_id: str) -> Callable | None:
        return self._response_adapters.get(network_id)

    def get_login_protocol(self, name: str) -> Callable | None:
        return self._login_calls.get(name)

    # ── QueryPlanner interface ────────────────────────────────────────

    def bind(self, product_registry: Any) -> None:
        """Borrow the :class:`ParameterCatalog` from a built ProductRegistry.

        Must be called before using :meth:`source_product` so that
        directory templates can be date-interpolated.
        """
        self._parameter_catalog = product_registry._parameter_catalog

    @property
    def resource_ids(self) -> list[str]:
        """Alias for :attr:`network_ids` — satisfies the QueryPlanner protocol."""
        return self.network_ids

    def source_product(self, product: Product, resource_id: str) -> list[SearchTarget]:
        """Resolve *product* into SearchTargets for a network resource.

        Iterates the network's ``ResourceProductSpec`` entries, matching on
        ``product_name`` and pinned parameter values.

        Args:
            product: Product template to resolve.
            resource_id: Network identifier (e.g. ``"ERT"``).

        Returns:
            A list of :class:`SearchTarget` objects.

        Raises:
            KeyError: If *resource_id* is not registered or no matching
                product spec is found.
        """
        config = self.config_for(resource_id)
        server_map = {s.id: s for s in config.servers}

        candidates = [p for p in config.products if p.product_name == product.name and p.available]
        if not candidates:
            raise KeyError(
                f"Product {product.name!r} not found in network {resource_id!r}. "
                f"Known products: {set(p.product_name for p in config.products)}"
            )

        incoming_params = {p.name: p.value for p in product.parameters if p.value is not None}

        results: list[SearchTarget] = []
        for spec in candidates:
            # Check pinned parameters don't conflict with incoming constraints.
            spec_params = {p.name: p.value for p in spec.parameters if p.value is not None}
            conflict = False
            for key in set(spec_params) & set(incoming_params):
                if spec_params[key] != incoming_params[key]:
                    conflict = True
                    break
            if conflict:
                continue

            server = server_map.get(spec.server_id)
            if server is None:
                logger.debug(
                    "Server %r referenced by product %r not found in network %r; skipping.",
                    spec.server_id,
                    spec.id,
                    resource_id,
                )
                continue

            merged = product.model_copy(deep=True)
            # Fill in any spec-pinned values the incoming product didn't set.
            for p in merged.parameters:
                if p.value is None and p.name in spec_params:
                    p.value = spec_params[p.name]
            # Add spec-pinned parameters not present in the incoming product template.
            existing_names = {p.name for p in merged.parameters}
            for param_name, param_value in spec_params.items():
                if param_name not in existing_names:
                    merged.parameters.append(Parameter(name=param_name, value=param_value))

            directory = spec.directory.model_copy(deep=True)
            directory.derive(merged.parameters)

            if merged.filename is not None:
                merged.filename.derive(merged.parameters)

            results.append(SearchTarget(product=merged, server=server, directory=directory))

        return results
