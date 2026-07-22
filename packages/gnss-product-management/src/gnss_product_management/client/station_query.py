"""StationQuery — fluent builder for GNSS station metadata and RINEX search."""

from __future__ import annotations

import copy
import datetime
import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

import tqdm

from gnss_product_management.environments.gnss_station_network import (
    GNSSNetworkRegistry,
    GNSSStation,
    PointRadius,
)
from gnss_product_management.factories.models import (
    FoundResource,
    found_resources_from_targets,
)
from gnss_product_management.factories.ranking import sort_by_protocol
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.factories.search_planner import SearchPlanner
from gnss_product_management.specifications.remote.resource import SearchTarget

logger = logging.getLogger(__name__)


class StationQuery:
    """Fluent builder for GNSS station metadata queries and RINEX file retrieval.

    Constructed via :meth:`GNSSClient.station_query` — do not instantiate
    directly.

    Chain method calls to build the query, then call :meth:`metadata`,
    :meth:`search`, or :meth:`download` to execute::

        stations = (
            client.station_query()
            .within(64.9, -147.5, 150.0)
            .networks("ERT")
            .on(date)
            .metadata()
        )

        results = (
            client.station_query()
            .within(64.9, -147.5, 150.0)
            .networks("ERT")
            .on(date)
            .rinex_version("3")
            .search()
        )
    """

    def __init__(
        self,
        wormhole: WormHole,
        search_planner: SearchPlanner,
        network_env: GNSSNetworkRegistry,
    ) -> None:
        self._wormhole = wormhole
        self._search_planner = search_planner
        self._network_env = network_env

        self._spatial_filter: PointRadius | None = None
        self._station_codes: tuple[str, ...] | None = None
        self._network_ids: tuple[str, ...] | None = None
        self._local_resource_ids: tuple[str, ...] | None = None
        self._country_codes: tuple[str, ...] | None = None
        self._date: datetime.datetime | None = None
        self._rinex_version: Literal["2", "3", "4"] = "3"
        self._rinex_variant: Literal["OBS", "NAV", "MET"] = "OBS"
        self._refresh_index: bool = False
        self._version_fallback: bool = False

    # ── Builder methods ───────────────────────────────────────────────

    def within(self, lat: float, lon: float, radius_km: float) -> StationQuery:
        """Set a point-radius spatial filter.

        Args:
            lat: Centre latitude in decimal degrees.
            lon: Centre longitude in decimal degrees.
            radius_km: Search radius in kilometres (must be > 0).

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._spatial_filter = PointRadius(lat=lat, lon=lon, radius_km=radius_km)
        return clone

    def from_stations(self, *codes: str) -> StationQuery:
        """Restrict the query to explicit 4-char station codes.

        Requires :meth:`centers` to also be set — station codes can
        overlap across networks.  Enforced at :meth:`metadata` /
        :meth:`search` / :meth:`download` time.

        Args:
            *codes: One or more 4-char SSSS station codes.

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._station_codes = codes
        return clone

    def networks(self, *ids: str) -> StationQuery:
        """Restrict the query to these network/center IDs.

        Optional for spatial queries; required when :meth:`from_stations`
        is set.  Mirrors ``ProductQuery.sources()``.

        Args:
            *ids: One or more registered network IDs (e.g. ``"ERT"``).

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._network_ids = ids
        return clone

    def local_resources(self, *ids: str) -> StationQuery:
        """Restrict the local search to these workspace resource IDs.

        When called, only the named local resources are searched for
        existing RINEX files.  When not called (the default) all
        registered local resources are searched.

        Args:
            *ids: One or more workspace resource IDs (e.g. ``"local"``).

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._local_resource_ids = ids
        return clone

    def on(self, date: datetime.datetime) -> StationQuery:
        """Set the target date.

        Serves as both the station availability filter and the RINEX
        file retrieval date.  ``.on_range()`` is not supported.

        Args:
            date: Timezone-aware datetime.

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._date = date
        return clone

    def rinex_version(self, version: Literal["2", "3", "4"]) -> StationQuery:
        """Pin the RINEX version for all execution methods.

        Defaults to ``"3"``.  Filters stations and files at
        :meth:`metadata`, :meth:`search`, and :meth:`download`.

        Args:
            version: ``"2"``, ``"3"``, or ``"4"``.

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._rinex_version = version
        return clone

    def rinex_variant(self, variant: Literal["OBS", "NAV", "MET"]) -> StationQuery:
        """Pin the RINEX file type for all execution methods.

        Defaults to ``"OBS"`` (observation files).

        Args:
            variant: ``"OBS"`` (observation), ``"NAV"`` (navigation), or
                ``"MET"`` (meteorological).

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._rinex_variant = variant
        return clone

    def with_version_fallback(self, enable: bool = True) -> StationQuery:
        """Enable automatic RINEX version fallback for stations with no results.

        When enabled, any station that returns zero file candidates for the
        requested RINEX version is automatically retried with the next lower
        version (``"3"`` → ``"2"``; ``"4"`` → ``"3"``).  This is useful when
        a network archives most stations at v3 but keeps some legacy stations
        at v2 only (e.g. EarthScope GAGE has ~100 stations with v2 data only).

        The fallback candidates are included alongside v3 hits in both
        :meth:`search` and :meth:`download`, ranked below any v3 results for
        the same station.

        Args:
            enable: ``True`` to enable fallback (default), ``False`` to disable.

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._version_fallback = enable
        return clone

    def country_codes(self, *codes: str) -> StationQuery:
        """Pin the 3-char data-centre / country code (``CCC`` parameter).

        Narrows the search to files produced by the named data centres,
        e.g. ``"USA"``, ``"DEU"``.  When not called all country codes
        are accepted.

        Args:
            *codes: One or more 3-char ISO country / data-centre codes.

        Returns:
            New :class:`StationQuery` instance.
        """
        clone = copy.copy(self)
        clone._country_codes = codes
        return clone

    # ── Validation ────────────────────────────────────────────────────

    def _validate_for_execution(self) -> None:
        """Raise ``ValueError`` if the query is not ready to execute."""
        if self._station_codes is None and self._spatial_filter is None:
            raise ValueError("Call .within() or .from_stations() before executing.")
        if self._station_codes is not None and not self._network_ids:
            raise ValueError(
                ".from_stations() requires .networks() to be set — "
                "station codes can overlap across networks."
            )

    def _effective_network_ids(self) -> list[str]:
        """Return network IDs to query: explicit list or all registered."""
        if self._network_ids:
            return list(self._network_ids)
        return list(self._network_env.network_ids)

    # ── Execution methods ─────────────────────────────────────────────

    def metadata(self) -> list[GNSSStation]:
        """Query station metadata across the configured networks.

        Returns partial results if a network is unreachable (warning logged).

        Returns:
            List of :class:`GNSSStation` objects matching the spatial and
            temporal filters.

        Raises:
            ValueError: If neither a spatial filter nor
                :meth:`from_stations` has been set, or if
                :meth:`from_stations` is set without :meth:`networks`.
        """
        self._validate_for_execution()

        all_stations: list[GNSSStation] = []

        for network_id in self._effective_network_ids():
            try:
                config = self._network_env.config_for(network_id)
            except KeyError:
                logger.warning("Network %r not found in NetworkRegistry; skipping.", network_id)
                continue

            # Attempt login for auth-required servers before querying.
            for server in config.servers:
                if server.auth_required:
                    login_fn: Callable | None = self._network_env.get_login_protocol(network_id)
                    if login_fn is not None:
                        try:
                            login_fn()
                        except Exception as exc:
                            logger.warning(
                                "Login for network %r failed: %s; skipping.",
                                network_id,
                                exc,
                            )
                    break  # only handle the first server's auth

            try:
                if self._station_codes is not None:
                    stations = self._query_by_codes(network_id)
                else:
                    stations = self._query_spatial(network_id)
            except Exception as exc:
                logger.warning("Station metadata query failed for network %r: %s", network_id, exc)
                continue

            if self._date is not None:
                stations = self._apply_temporal_filter(stations, self._date)

            all_stations.extend(stations)
        all_stations.sort(key=lambda s: s.site_code)  # sort by station code ascending
        return all_stations

    def _query_spatial(self, network_id: str) -> list[GNSSStation]:
        """Execute a spatial query for *network_id*.

        Tries a registered :class:`NetworkProtocol` first, then falls back to
        a registered station-query callable.
        """
        assert self._spatial_filter is not None

        protocol = self._network_env.get_protocol(network_id)
        if protocol is not None and isinstance(self._spatial_filter, PointRadius):
            date = self._date or datetime.datetime.now(tz=datetime.timezone.utc)
            result = protocol.radius_spatial_query(
                date,
                self._spatial_filter.lat,
                self._spatial_filter.lon,
                self._spatial_filter.radius_km,
            )
            return result or []

        fn = self._network_env.get_station_query(network_id)
        if fn is not None:
            return fn(self._spatial_filter) or []

        logger.debug("No spatial query handler registered for network %r; skipping.", network_id)
        return []

    def _query_by_codes(self, network_id: str) -> list[GNSSStation]:
        """Return stub :class:`GNSSStation` objects for explicit station codes."""
        assert self._station_codes is not None
        return [
            GNSSStation(site_code=code, lat=0.0, lon=0.0, network_id=network_id)
            for code in self._station_codes
        ]

    @staticmethod
    def _apply_temporal_filter(
        stations: list[GNSSStation],
        date: datetime.datetime,
    ) -> list[GNSSStation]:
        """Keep stations active on *date*.

        A station with ``start_date=None`` is included (unknown start).
        A station with ``end_date=None`` is included (currently active).
        """
        target = date.date()
        result = []
        for s in stations:
            if s.start_date is not None and target < s.start_date:
                continue
            if s.end_date is not None and target > s.end_date:
                continue
            result.append(s)
        return result

    def _register_filesystems(self, network_ids: list[str]) -> None:
        """Ensure a connection-pool entry exists for each network's archive servers.

        If the network has a registered :class:`NetworkProtocol` that returns an
        authenticated filesystem, that filesystem is injected into the pool so all
        subsequent directory listings and downloads use the correct credentials.
        """
        for network_id in network_ids:
            try:
                config = self._network_env.config_for(network_id)
            except KeyError:
                continue
            protocol = self._network_env.get_protocol(network_id)
            fs = protocol.filesystem() if protocol is not None else None
            for server in config.servers:
                self._wormhole._connection_pool_factory.add_connection(
                    server.hostname, filesystem=fs
                )

    def _ranked_targets(self) -> list[SearchTarget]:
        """Return sorted :class:`SearchTarget` candidates before deduplication.

        Resolves station metadata, registers network filesystems, builds
        per-station queries via :class:`SearchPlanner`, expands them through
        :class:`WormHole`, then applies :func:`sort_by_protocol` so local
        results precede remote ones.

        Returns:
            Sorted list of :class:`SearchTarget` objects, local/file first,
            then by network protocol.

        Raises:
            ValueError: If spatial/station filter or date have not been set.
        """
        self._validate_for_execution()
        if self._date is None:
            raise ValueError(".on(date) is required before searching")

        network_ids = self._effective_network_ids()
        local_resource_ids = list(self._local_resource_ids) if self._local_resource_ids else None

        stations = self.metadata()
        if not stations:
            return []

        self._register_filesystems(network_ids)

        targets = self._search_planner.get_stations(
            stations=stations,
            date=self._date,
            version=self._rinex_version,
            variant=self._rinex_variant,
            network_ids=network_ids,
            local_resource_ids=local_resource_ids,
            country_codes=list(self._country_codes) if self._country_codes else None,
        )
        if not targets:
            return []

        expanded = self._wormhole.search(targets)
        logger.debug(
            "Expanded %d station targets into %d matches on %s",
            len(targets),
            len(expanded),
            self._date.date(),
        )

        # Version fallback: retry stations with zero candidates at a lower version.
        if self._version_fallback and self._rinex_version in ("3", "4"):
            fallback_version: Literal["2", "3"] = "2" if self._rinex_version == "3" else "3"
            hit_codes = {
                next((p.value for p in rq.product.parameters if p.name == "SSSS"), None)
                for rq in expanded
            }
            missing_codes = {s.site_code for s in stations} - {c for c in hit_codes if c}
            if missing_codes:
                fallback_stations = [s for s in stations if s.site_code in missing_codes]
                logger.info(
                    "v%s fallback: %d station(s) have no v%s candidates, retrying with v%s",
                    fallback_version,
                    len(fallback_stations),
                    self._rinex_version,
                    fallback_version,
                )
                fallback_targets = self._search_planner.get_stations(
                    stations=fallback_stations,
                    date=self._date,
                    version=fallback_version,
                    variant=self._rinex_variant,
                    network_ids=network_ids,
                    local_resource_ids=local_resource_ids,
                    country_codes=list(self._country_codes) if self._country_codes else None,
                )
                if fallback_targets:
                    fallback_expanded = self._wormhole.search(fallback_targets)
                    if fallback_expanded:
                        recovered = {
                            next(
                                (p.value for p in rq.product.parameters if p.name == "SSSS"),
                                None,
                            )
                            for rq in fallback_expanded
                        } - {None}
                        logger.info(
                            "v%s fallback: recovered %d file(s) across %d station(s)",
                            fallback_version,
                            len(fallback_expanded),
                            len(recovered),
                        )
                    expanded.extend(fallback_expanded)

        return sort_by_protocol(expanded)

    def search(self) -> list[FoundResource]:
        """Discover RINEX observation files for matching stations.

        Calls :meth:`_ranked_targets` to obtain protocol-sorted
        :class:`SearchTarget` objects, deduplicates by ``(hostname, filename)``,
        then returns :class:`FoundResource` objects sorted station-code ascending
        with local results before remote ones for each station.

        Returns:
            Ranked list of :class:`FoundResource` objects with
            ``product="RINEX_<variant>"`` and ``parameters["SSSS"]`` set.
            Within each station: local before remote, then RINEX version
            descending.

        Raises:
            ValueError: If spatial/station filter or date have not been set.
        """
        ranked = self._ranked_targets()
        if not ranked:
            return []

        results = found_resources_from_targets(ranked, self._date)

        # Sort: station code ascending (alphabetical, case-insensitive);
        # within each station local before remote, then RINEX version descending.
        # The download() fallback tries candidates in this order, so local files
        # are always preferred over network fetches.
        def _sort_key(r: FoundResource) -> tuple:
            ssss = r.parameters.get("SSSS", "").upper()
            is_remote = 0 if r.source == "local" else 1
            try:
                v_int = int(r.parameters.get("V", "0"))
            except (ValueError, TypeError):
                v_int = 0
            return (ssss, is_remote, -v_int)

        results.sort(key=_sort_key)
        return results

    def _download_station(
        self,
        ssss: str,
        station_candidates: list[FoundResource],
        sink_id: str,
        workspace: object,
    ) -> FoundResource | None:
        """Try candidates for a single station; return the first success."""
        for fr in station_candidates:
            query = fr._query
            if query is None:
                logger.debug("FoundResource for %r has no internal query; skipping.", ssss)
                continue

            try:
                local_path = self._wormhole.download_one(
                    query=query,
                    local_resource_id=sink_id,
                    local_factory=workspace,
                    date=self._date,
                )
            except Exception as exc:
                logger.warning(
                    "Download attempt failed for station %r from %r: %s",
                    ssss,
                    fr.uri,
                    exc,
                )
                local_path = None

            if local_path is not None:
                fr.local_path = local_path
                return fr

        logger.warning(
            "All download attempts failed for station %r; no RINEX file retrieved.",
            ssss,
        )
        return None

    def download(self, sink_id: str, *, max_workers: int = 8) -> list[FoundResource]:
        """Search and download RINEX files in one call with per-station fallback.

        Calls :meth:`search` to obtain a ranked :class:`FoundResource` list,
        then groups results by station code and downloads stations
        concurrently.  For each station the candidates are tried in order;
        the first successful download wins and remaining candidates are
        skipped.  Stations where every candidate fails are absent from the
        return list (no error is raised).

        Args:
            sink_id: Local resource alias registered in the workspace
                (e.g. ``"local"``).  RINEX_OBS files are written under the
                directory defined for ``RINEX_OBS`` in the workspace spec.
            max_workers: Maximum number of parallel download threads.
                Defaults to ``8``.

        Returns:
            List of :class:`FoundResource` objects with ``local_path``
            populated — one per successfully downloaded station.

        Raises:
            ValueError: If validation fails (see :meth:`_validate_for_execution`)
                or if :meth:`on` has not been called.
        """
        candidates = self.search()
        if not candidates:
            return []

        # Group by station code preserving the sorted order.
        by_station: dict[str, list[FoundResource]] = defaultdict(list)
        for fr in candidates:
            ssss = fr.parameters.get("SSSS", "")
            by_station[ssss].append(fr)

        workspace = self._search_planner._workspace
        results: list[FoundResource] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._download_station, ssss, scands, sink_id, workspace): ssss
                for ssss, scands in by_station.items()
            }
            for future in tqdm.tqdm(as_completed(futures), total=len(futures)):
                ssss = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.warning("Unexpected error downloading station %r: %s", ssss, exc)
                else:
                    if result is not None:
                        results.append(result)

        return results
