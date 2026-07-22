"""ProductQuery — fluent builder for GNSS product search and download."""

from __future__ import annotations

import copy
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

from gnss_product_management.factories.models import (
    FoundResource,
    found_resources_from_targets,
)
from gnss_product_management.factories.ranking import (
    sort_by_preferences,
    sort_by_protocol,
)
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.factories.search_planner import SearchPlanner
from gnss_product_management.specifications.dependencies.dependencies import (
    SearchPreference,
)
from gnss_product_management.specifications.remote.resource import SearchTarget

logger = logging.getLogger(__name__)


class ProductQuery:
    """Fluent builder for constructing and executing a GNSS product search.

    Constructed via :meth:`GNSSClient.query` — do not instantiate directly.

    Chain method calls to build the query, then call :meth:`search` or
    :meth:`download` to execute::

        results = (
            client.query("ORBIT")
            .on(date)
            .where(TTT="FIN")
            .sources("COD", "ESA")
            .prefer(TTT=["FIN", "RAP", "ULT"])
            .search()
        )

        paths = (
            client.query("CLOCK")
            .on(date)
            .where(TTT="FIN")
            .sources("local", "COD")
            .download(sink_id="local")
        )

    Args:
        fetcher: :class:`WormHole` used for directory listing and
            file download.
        query_factory: :class:`SearchPlanner` used to build
            :class:`SearchTarget` objects from product specs.
        product: Product name (e.g. ``"ORBIT"``) or dict with ``name``,
            and optionally ``version`` / ``variant``.
    """

    def __init__(
        self,
        wormhole: WormHole,
        search_planner: SearchPlanner,
    ) -> None:
        self._wormhole = wormhole
        self._search_planner = search_planner
        self._product: dict | None = None
        self._date: datetime.datetime | None = None
        self._date_range: tuple[datetime.datetime, datetime.datetime, datetime.timedelta] | None = (
            None
        )
        self._parameters: dict = {}
        self._source_ids: tuple | None = None  # None = all sources
        self._preferences: list[SearchPreference] = []

    def for_product(self, product: str | dict) -> ProductQuery:
        """Set the target product for the query.

        Args:
            product: Product name (e.g. ``"ORBIT"``) or dict with ``name``,
                and optionally ``version`` / ``variant``.

        Returns:
            ``self`` for chaining.
        """
        clone = copy.copy(self)
        clone._product = {"name": product} if isinstance(product, str) else product
        return clone

    def on(self, date: datetime.datetime) -> ProductQuery:
        """Set the target date for the query.

        Args:
            date: Timezone-aware datetime.

        Returns:
            ``self`` for chaining.
        """
        clone = copy.copy(self)
        clone._date = date
        return clone

    def on_range(
        self,
        start: datetime.datetime,
        end: datetime.datetime,
        *,
        step: datetime.timedelta = datetime.timedelta(days=1),
    ) -> ProductQuery:
        """Set a date range for the query.

        Searches are run for every date from *start* to *end* (inclusive)
        with the given *step* (default: 1 day).  Results from all dates are
        merged into a single flat list from :meth:`search`.

        Args:
            start: First date to query (inclusive).
            end: Last date to query (inclusive).
            step: Interval between consecutive dates (default: 1 day).

        Returns:
            ``self`` for chaining.

        Raises:
            ValueError: If *start* is after *end*.
        """
        if start > end:
            raise ValueError(f"start ({start.date()}) must not be after end ({end.date()})")
        clone = copy.copy(self)
        clone._date = None
        clone._date_range = (start, end, step)
        return clone

    def where(self, **parameters) -> ProductQuery:
        """Constrain product parameters (hard filter).

        Keyword arguments use IGS long filename field codes as keys.
        Common constraints:

        - ``TTT="FIN"`` — final solutions only (≥13 days latency)
        - ``TTT="RAP"`` — rapid solutions only (≤17 hours latency)
        - ``TTT="ULT"`` — ultra-rapid solutions only (≤3 hours latency)
        - ``AAA="WUM"`` — Wuhan University products only
        - ``AAA=["WUM", "COD"]`` — WUM or COD only

        Use :meth:`prefer` instead of :meth:`where` when you want to rank
        results without excluding alternatives.

        Args:
            **parameters: IGS field name → required value or list of values.

        Returns:
            ``self`` for chaining.
        """
        clone = copy.copy(self)
        clone._parameters = dict(clone._parameters)
        clone._parameters.update(parameters)
        return clone

    def sources(self, *ids: str) -> ProductQuery:
        """Restrict the search to specific local or remote sources.

        Pass any mix of registered local aliases and remote center IDs.
        Each ID is resolved at :meth:`search` time — local aliases are
        routed to local disk, everything else is treated as a remote
        center ID.

        Calling :meth:`sources` with no arguments is an error; omit the
        call entirely — or pass ``"all"`` explicitly — to search all
        available sources.

        Args:
            *ids: One or more source identifiers, or ``"all"``.

        Returns:
            ``self`` for chaining.

        Raises:
            ValueError: If no IDs are provided.
        """
        if not ids:
            raise ValueError(
                "sources() requires at least one resource ID. "
                "Omit the call entirely to search all sources."
            )
        clone = copy.copy(self)
        clone._source_ids = ids
        return clone

    def prefer(self, **kwargs) -> ProductQuery:
        """Rank results by a preference cascade without hard-filtering.

        Unlike :meth:`where`, ``prefer`` keeps all matching products in the
        result list but sorts them so the most-preferred appear first.  The
        standard IGS timeliness cascade is::

            .prefer(TTT=["FIN", "RAP", "ULT"])

        Center preference can be layered on top::

            .prefer(TTT=["FIN", "RAP", "ULT"], AAA=["WUM", "COD", "GFZ"])

        Multiple :meth:`prefer` calls accumulate in call order; later calls
        do not override earlier ones.

        Args:
            **kwargs: IGS field name → ordered list of preferred values,
                most preferred first.

        Returns:
            ``self`` for chaining.
        """
        clone = copy.copy(self)
        clone._preferences = list(clone._preferences)
        for param, sorting in kwargs.items():
            if isinstance(sorting, str):
                sorting = [sorting]
            clone._preferences.append(SearchPreference(parameter=param, sorting=list(sorting)))
        return clone

    def _ranked_targets(self) -> list[SearchTarget]:
        """Return sorted :class:`SearchTarget` candidates before deduplication.

        Builds queries via :class:`SearchPlanner`, expands them through
        :class:`WormHole`, then applies preference and protocol sorting.
        The result is the pre-deduplication list used both by :meth:`search`
        and by :class:`ResolvePipeline`.

        Returns:
            Sorted list of :class:`SearchTarget` objects, local/file first,
            then ordered by *preferences* within each protocol tier.

        Raises:
            ValueError: If :meth:`for_product` or :meth:`on` have not been called.
        """
        if self._product is None:
            raise ValueError("Call .for_product(product) before searching")
        if self._date is None:
            raise ValueError("Call .on(date) before searching")

        local_ids, remote_ids = self._resolve_sources()
        queries = self._search_planner.get(
            date=self._date,
            product=self._product,
            parameters=self._parameters or None,
            local_resources=local_ids,
            remote_resources=remote_ids,
        )
        expanded = self._wormhole.search(queries)
        if not expanded:
            logger.debug(
                "No search targets found for product %s on date %s",
                self._product,
                self._date,
            )
        logger.debug(
            "Expanded %d queries into %d targets for %s on %s",
            len(queries),
            len(expanded),
            self._product,
            self._date,
        )
        if self._preferences:
            expanded = sort_by_preferences(expanded, self._preferences)
        return sort_by_protocol(expanded)

    def _search_range(self) -> list[FoundResource]:
        """Execute a search for every date in the configured range.

        Runs one :meth:`search` call per date in parallel using a
        :class:`~concurrent.futures.ThreadPoolExecutor` (max 8 workers) and
        merges all results into a single flat list.

        Returns:
            Combined list of :class:`FoundResource` objects from all dates.
        """
        assert self._date_range is not None
        start, end, step = self._date_range

        dates: list[datetime.datetime] = []
        current = start
        while current <= end:
            dates.append(current)
            current += step

        logger.debug(
            "on_range(): %d dates from %s to %s",
            len(dates),
            start.date(),
            end.date(),
        )

        all_results: list[FoundResource] = []
        with ThreadPoolExecutor(max_workers=min(len(dates), 8)) as executor:
            future_to_date = {executor.submit(self.on(date).search): date for date in dates}
            for future in as_completed(future_to_date):
                date = future_to_date[future]
                try:
                    all_results.extend(future.result())
                except Exception as exc:
                    logger.warning("Search failed for date %s: %s", date.date(), exc)

        return all_results

    def search(self) -> list[FoundResource]:
        """Execute the query and return ranked results.

        Returns:
            Ranked list of :class:`FoundResource` objects, best first.
            Local/file results precede remote ones; within each protocol
            tier results are ordered by *preferences*.
            When :meth:`on_range` was used, results from all dates are
            returned as a flat combined list.

        Raises:
            ValueError: If neither :meth:`on` nor :meth:`on_range` has been called.
        """
        if self._product is None:
            raise ValueError("Call .for_product(product) before .search()")

        if self._date_range is not None:
            return self._search_range()

        if self._date is None:
            raise ValueError("Call .on(date) or .on_range(start, end) before .search()")

        logger.debug(
            "search() product=%s date=%s parameters=%s sources=%s",
            self._product,
            self._date,
            self._parameters,
            self._source_ids,
        )

        return found_resources_from_targets(self._ranked_targets(), self._date)

    def download(
        self,
        sink_id: str,
        *,
        limit: int | None = None,
    ) -> list[Path]:
        """Search and download results in one call.

        Args:
            sink_id: Local resource alias to download into (e.g. ``"local"``).
            limit: Maximum number of files to download.  ``None`` downloads
                all results.

        Returns:
            Paths to successfully downloaded files.

        Raises:
            ValueError: If :meth:`for_product` or :meth:`on` have not been called.
        """
        # search() validates that _date is set via _ranked_targets()
        results = self.search()
        if limit is not None:
            results = results[:limit]

        assert self._date is not None  # guaranteed by search() above
        paths: list[Path] = []
        for r in results:
            if r._query is None:
                logger.warning("FoundResource has no internal query; skipping.")
                continue
            path = self._wormhole.download_one(
                query=cast(SearchTarget, r._query),
                local_resource_id=sink_id,
                local_factory=self._search_planner._workspace,
                date=self._date,
            )
            if path is not None:
                r.local_path = path
                if isinstance(path, Path):
                    paths.append(path)
        return paths

    # -- Internal --------------------------------------------------

    def _resolve_sources(self) -> tuple[list[str] | None, list[str] | None]:
        """Split source IDs into (local_ids, remote_ids) for SearchPlanner.

        Returns:
            A ``(local_ids, remote_ids)`` tuple, each ``None`` when empty
            (meaning "all of that type").
        """
        if self._source_ids is None or "all" in self._source_ids:
            return None, None

        local_ids: list[str] = []
        remote_ids: list[str] = []

        for sid in self._source_ids:
            try:
                self._search_planner._workspace._get_registered_spec(sid)
                local_ids.append(sid)
            except KeyError:
                remote_ids.append(sid)

        return local_ids or None, remote_ids or None
