"""GNSSClient — high-level entry point for searching and downloading GNSS products."""

from __future__ import annotations

import datetime
import logging
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from gpm_specs.configs import LOCAL_SPEC_DIR

from gnss_product_management.client.product_query import ProductQuery
from gnss_product_management.defaults import DefaultProductEnvironment
from gnss_product_management.environments import WorkSpace
from gnss_product_management.factories.models import FoundResource
from gnss_product_management.factories.pipelines.download import DownloadPipeline
from gnss_product_management.factories.pipelines.resolve import ResolvePipeline
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.factories.search_planner import SearchPlanner
from gnss_product_management.specifications.dependencies.dependencies import (
    DependencyResolution,
    DependencySpec,
    SearchPreference,
)
from gnss_product_management.utilities.paths import AnyPath

if TYPE_CHECKING:
    from gnss_product_management.environments import ProductRegistry

logger = logging.getLogger(__name__)


class GNSSClient:
    """Single entry point for IGS product search, download, and dependency resolution.

    Wraps :class:`ProductQuery`, :class:`DownloadPipeline`, and
    :class:`ResolvePipeline`. All user-facing operations go through this class.

    Use :meth:`from_defaults` to build from the bundled IGS center and product
    specs. Pass a ``base_dir`` to enable downloads and local-first resolution::

        # Search only (no local sink)
        client = GNSSClient.from_defaults()
        results = client.search(date, product="ORBIT", parameters={"TTT": "FIN"})

        # Search and download to a local directory
        client = GNSSClient.from_defaults(base_dir="/data/gnss")
        paths = client.download(results[:1], sink_id="local")

        # Search and download to S3
        client = GNSSClient.from_defaults(base_dir="s3://my-bucket/gnss")
        paths = client.download(results[:1], sink_id="local")

        # Full dependency resolution (orbit + clock + bias + ERP + ...)
        resolution, lockfile = client.resolve_dependencies("spec.yaml", date, sink_id="local")

    ``max_connections`` sets the per-host FTP/HTTPS connection pool size.
    CDDIS (NASA FTPS) enforces strict anonymous connection limits; keep it at
    2–4 for CDDIS-heavy queries. FTP centers (COD, WUM, GFZ) generally
    tolerate 6–8.

    Args:
        product_registry: Built :class:`ProductRegistry` with loaded product
            and center specs.
        workspace: :class:`WorkSpace` with registered local directories.
        max_connections: Maximum concurrent connections per host (default 4).
    """

    def __init__(
        self,
        product_registry: ProductRegistry,
        workspace: WorkSpace,
        *,
        max_connections: int = 4,
    ) -> None:

        self._product_registry = product_registry
        self._workspace = workspace
        self._transport = WormHole(
            max_connections=max_connections, product_registry=product_registry
        )
        self._planner = SearchPlanner(product_registry=product_registry, workspace=workspace)
        self._query = ProductQuery(wormhole=self._transport, search_planner=self._planner)
        self._downloader = DownloadPipeline(
            product_registry,
            workspace,
            transport=self._transport,
        )

    @classmethod
    def from_defaults(
        cls,
        base_dir: Path | str | None = None,
        *,
        local_alias: str = "local",
        max_connections: int = 4,
    ) -> GNSSClient:
        """Construct a client from the bundled default specs.

        Loads the pre-built :data:`DefaultProductEnvironment` and creates a
        fresh :class:`WorkSpace` from the bundled local layout specs.  If
        *base_dir* is provided, all local specs are registered against that
        directory, enabling downloads and local-first resolution.

        *base_dir* may be a local path **or** a cloud storage URI supported
        by `cloudpathlib <https://cloudpathlib.drivendata.org/>`_::

            # Local
            client = GNSSClient.from_defaults(base_dir="/data/gnss")
            # Amazon S3
            client = GNSSClient.from_defaults(base_dir="s3://my-bucket/gnss")
            # Google Cloud Storage
            client = GNSSClient.from_defaults(base_dir="gs://my-bucket/gnss")

        Args:
            base_dir: Root directory for local product storage.  If ``None``,
                the client operates in search-only mode (no local sink).
            local_alias: Alias for the registered local resource (default
                ``"local"``).  Used as the ``sink_id`` in
                :meth:`download` and :meth:`resolve_dependencies`.
            max_connections: Maximum concurrent connections per host.
                Keep at 2–4 for CDDIS; 6–8 for COD, WUM, GFZ.

        Returns:
            A configured :class:`GNSSClient` instance.
        """
        workspace = WorkSpace()
        for path in Path(LOCAL_SPEC_DIR).glob("*.yaml"):
            workspace.add_resource_spec(path)

        if base_dir is not None:
            spec_ids = list(workspace._resource_specs.keys())
            workspace.register_spec(
                base_dir=Path(base_dir),
                spec_ids=spec_ids,
                alias=local_alias,
            )

        return cls(
            product_registry=DefaultProductEnvironment,
            workspace=workspace,
            max_connections=max_connections,
        )

    def display(self) -> None:
        """Display the client's loaded product registry and workspace specs."""
        self._product_registry.display()
        self._workspace.display()

    def query(self) -> ProductQuery:
        """Return a fluent :class:`ProductQuery` builder.

        This is the preferred entry point for building searches.  Chain
        calls to narrow the query, then call :meth:`ProductQuery.search`
        or :meth:`ProductQuery.download` to execute::

            results = (
                client.query()
                .for_product("ORBIT")
                .on(date)
                .where(TTT="FIN")
                .sources("COD", "ESA")
                .search()
            )

        Returns:
            A :class:`ProductQuery` bound to this client.
        """
        return ProductQuery(
            wormhole=self._transport,
            search_planner=self._planner,
        )

    def search(
        self,
        date: datetime.datetime,
        product: str | dict,
        *,
        parameters: dict | None = None,
        preferences: list[SearchPreference] | None = None,
        local_resources: list[str] | None = None,
        remote_resources: list[str] | None = None,
    ) -> list[FoundResource]:
        """Search for IGS products matching the given criteria.

        Builds :class:`SearchTarget` objects from the product catalog, lists
        remote directories via the connection pool, matches filenames by regex,
        and ranks results by preference and protocol.

        Key ``parameters`` keys follow the IGS long filename convention:

        - ``TTT`` — solution timeliness: ``"FIN"`` (final, ≥13 d),
          ``"RAP"`` (rapid, ≤17 h), ``"ULT"`` (ultra-rapid, ≤3 h)
        - ``AAA`` — analysis center: ``"COD"``, ``"ESA"``, ``"GFZ"``,
          ``"WUM"``, ``"IGS"``, …

        For the full fluent interface (including date-range searches) use
        :meth:`query` instead.

        Args:
            date: Target date (timezone-aware datetime).
            product: Product name (e.g. ``"ORBIT"``, ``"CLOCK"``, ``"BIA"``)
                or a dict with ``name``, and optionally ``version`` /
                ``variant``.
            parameters: Parameter constraints, e.g.
                ``{"TTT": "FIN", "AAA": "WUM"}``.
            preferences: Preference cascade for ranking.  Each
                :class:`SearchPreference` names a parameter and an ordered
                list of preferred values, e.g.
                ``SearchPreference(parameter="TTT", sorting=["FIN","RAP"])``.
            local_resources: Restrict to these local resource aliases.
            remote_resources: Restrict to these remote center IDs.

        Returns:
            Ranked list of :class:`FoundResource` objects.  Local (file://)
            results precede remote ones; within each protocol tier results
            are ordered by *preferences*.
        """
        product_name: str = product.get("name", "") if isinstance(product, dict) else product
        q = self._query.for_product(product_name).on(date)
        if parameters:
            q = q.where(**parameters)
        if preferences:
            for pref in preferences:
                q = q.prefer(**{pref.parameter: pref.sorting})
        if local_resources or remote_resources:
            sources = list(local_resources or []) + list(remote_resources or [])
            q = q.sources(*sources)
        return q.search()

    def download(
        self,
        results: list[FoundResource],
        *,
        sink_id: str,
    ) -> list[Path]:
        """Download product candidates to the local sink.

        Pass a pre-sliced list to limit how many files are fetched, e.g.
        ``client.download(results[:1], sink_id="local")``.

        Args:
            results: Ranked :class:`FoundResource` list from :meth:`search`
                or :meth:`ProductQuery.search`.  Each result must carry a
                ``date`` (set automatically by the query builders).
            sink_id: Local resource identifier (alias registered in the
                workspace, e.g. ``"local"``).

        Returns:
            Paths to successfully downloaded (and decompressed) files.
        """
        # by_date: Dict[datetime.datetime, List[FoundResource]] = {}
        # for r in results:
        #     if r.date is None:
        #         logger.warning("FoundResource has no date; skipping.")
        #         continue
        #     by_date.setdefault(r.date, []).append(r)
        by_date = {
            k: list(v)
            for k, v in groupby(
                results,
                key=lambda r: r.date if r.date is not None else datetime.datetime.min,
            )
        }

        paths: list[Path] = []
        for date, date_results in by_date.items():
            downloaded = self._downloader.run(date_results, date, sink_id=sink_id)

            for r, path in zip(date_results, downloaded):
                if path is not None:
                    r.local_path = path
                    if isinstance(path, Path):
                        paths.append(path)
        return paths

    def resolve_dependencies(
        self,
        dep_spec: DependencySpec | Path | str,
        date: datetime.datetime,
        *,
        sink_id: str,
        force_download: bool = False,
        centers: list[str] | None = None,
        bundle_centers: list[str] | None = None,
    ) -> tuple[DependencyResolution, AnyPath | None]:
        """Resolve all dependencies in a spec for the given date.

        Accepts a :class:`DependencySpec` object or a path to a YAML file.
        Checks local disk first, then downloads any missing files.  If a
        ``DependencyLockFile`` already exists for ``(package, task, date,
        version)``, resolution returns immediately without any network calls.

        Args:
            dep_spec: Dependency specification — a :class:`DependencySpec`
                instance, or a path (``str`` or :class:`Path`) to a YAML file.
                The spec encodes which products are required, the center/
                timeliness preference cascade, and per-product constraints.
            date: Target date (timezone-aware datetime, midnight UTC).
            sink_id: Local resource alias for storing resolved files
                (e.g. ``"local"``).
            centers: Optional remote resource IDs to search.  When omitted,
                all configured centers are eligible.

        Returns:
            A ``(DependencyResolution, lockfile_path)`` tuple.
            ``DependencyResolution`` exposes ``.summary()``, ``.table()``,
            ``.product_paths()``, ``.missing``, and
            ``.all_required_fulfilled``.
        """
        if isinstance(dep_spec, (str, Path)):
            dep_spec = DependencySpec.from_yaml(dep_spec)

        pipeline = ResolvePipeline(
            env=self._product_registry,
            workspace=self._workspace,
            transport=self._transport,
        )
        return pipeline.run(
            dep_spec,
            date,
            sink_id=sink_id,
            force_download=force_download,
            centers=centers,
            bundle_centers=bundle_centers,
        )
