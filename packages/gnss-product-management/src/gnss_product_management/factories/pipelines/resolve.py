"""ResolvePipeline — Find + Download + LockfileWriter in one call.

High-level composition that resolves a :class:`DependencySpec` for a
given date: finds resources, optionally downloads them, writes per-file
sidecar lockfiles, and persists an aggregate lockfile.

Fast path: if an aggregate lockfile already exists for
``(package, task, date, version)`` and every required entry still
validates (file present, sidecar hash matching), the pipeline returns
immediately without searching or downloading.  Otherwise it falls
through to a full re-resolution.
"""

from __future__ import annotations

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from gnss_product_management.environments import ProductRegistry, WorkSpace
from gnss_product_management.factories.models import FoundResource
from gnss_product_management.factories.pipelines.download import DownloadPipeline
from gnss_product_management.factories.pipelines.lockfile_writer import LockfileWriter
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.factories.search_planner import SearchPlanner
from gnss_product_management.lockfile.manager import LockfileManager
from gnss_product_management.lockfile.operations import (
    HashMismatchMode,
    get_lock_product,
    get_package_version,
    validate_lock_product,
)
from gnss_product_management.specifications.dependencies.dependencies import (
    Dependency,
    DependencyResolution,
    DependencySpec,
    ResolvedDependency,
    SearchPreference,
)
from gnss_product_management.utilities.paths import AnyPath

logger = logging.getLogger(__name__)


class ResolvePipeline:
    """Find → Download → Lockfile for every dependency in a spec.

    Uses :class:`ProductQuery`, :class:`DownloadPipeline`, and
    :class:`LockfileWriter` internally.  All dependencies are resolved
    in parallel via a :class:`~concurrent.futures.ThreadPoolExecutor`.

    Fast path: if an aggregate lockfile already exists for the
    ``(package, task, date, version)`` identity and every required
    entry still validates, returns immediately without searching or
    downloading; otherwise re-resolves.

    Args:
        env: The product registry with built catalogs.
        workspace: Workspace with registered local resources.
        max_connections: Maximum concurrent connections per host.
        transport: Optional shared :class:`WormHole` instance.  If
            provided, the pipeline reuses it instead of creating a new
            one — useful when :class:`GNSSClient` already holds a pool.
    """

    def __init__(
        self,
        env: ProductRegistry,
        workspace: WorkSpace,
        *,
        max_connections: int = 4,
        transport: WormHole | None = None,
    ) -> None:
        from gnss_product_management.client.product_query import ProductQuery

        self._env = env
        self._workspace = workspace
        transport = transport or WormHole(max_connections=max_connections, product_registry=env)
        planner = SearchPlanner(product_registry=env, workspace=workspace)
        self._query = ProductQuery(wormhole=transport, search_planner=planner)
        self._downloader = DownloadPipeline(
            env,
            workspace,
            transport=transport,
            max_connections=max_connections,
        )

    def run(
        self,
        spec: DependencySpec,
        date: datetime.datetime,
        *,
        sink_id: str = "local_config",
        centers: list[str] | None = None,
        download: bool = True,
    ) -> tuple[DependencyResolution, AnyPath | None]:
        """Resolve all dependencies in *spec* for *date*.

        Args:
            spec: The dependency specification.
            date: Target date (timezone-aware datetime).
            sink_id: Local resource alias for download destination and
                lockfile storage.
            centers: Restrict remote search to these center IDs.
            download: If ``True`` (default), download remote resources.

        Returns:
            A tuple of (:class:`DependencyResolution`, lockfile path or
            ``None`` if nothing was resolved).
        """
        version = get_package_version()
        lockfile_dir = self._workspace.lockfile_dir(sink_id)
        manager = LockfileManager(lockfile_dir)

        # --- Fast path: return immediately if aggregate lockfile exists -----
        lf_path = manager.lockfile_path(
            package=spec.package,
            task=spec.task,
            date=date,
            version=version,
        )
        existing = manager.load(
            package=spec.package,
            task=spec.task,
            date=date,
            version=version,
        )
        if existing is not None:
            resolution = self._resolution_from_lockfile(existing, spec)
            if resolution.all_required_fulfilled:
                logger.info(
                    "Lockfile already exists for %s on %s — skipping resolution: %s",
                    spec.name,
                    date.date(),
                    lf_path,
                )
                logger.info(resolution.summary())
                return resolution, lf_path
            logger.warning(
                "Lockfile for %s on %s has missing or invalid entries — re-resolving",
                spec.name,
                date.date(),
            )

        # --- Full resolution -------------------------------------------------
        resolve_one = partial(
            self._resolve_one,
            date=date,
            sink_id=sink_id,
            preferences=spec.preferences,
            centers=centers,
            download=download,
        )
        with ThreadPoolExecutor(max_workers=15) as executor:
            resolved = list(executor.map(resolve_one, spec.dependencies))

        resolution = DependencyResolution(spec_name=spec.name, resolved=resolved)

        lf_path: AnyPath | None = None
        if resolution.fulfilled:
            writer = LockfileWriter(lockfile_dir, package=spec.package)
            lf_path = writer.write(resolution, date)

        logger.info(resolution.summary())
        return resolution, lf_path

    # -- Internal ------------------------------------------------------------

    def _resolve_one(
        self,
        dep: Dependency,
        *,
        date: datetime.datetime,
        sink_id: str,
        preferences: list[SearchPreference],
        centers: list[str] | None,
        download: bool,
    ) -> ResolvedDependency:
        """Resolve a single dependency.

        Args:
            dep: The dependency to resolve.
            date: Target date.
            sink_id: Local resource alias.
            preferences: Spec-level preference cascade.
            centers: Remote center IDs to restrict to.
            download: Whether to download remote resources.

        Returns:
            A :class:`ResolvedDependency` with the resolution result.
        """
        logger.debug("Attempting to resolve dependency %s on %s", dep.spec, date.date())
        try:
            q = self._query.for_product(dep.spec).on(date)
            if dep.constraints:
                q = q.where(**dep.constraints)
            if preferences:
                for pref in preferences:
                    q = q.prefer(**{pref.parameter: pref.sorting})
            if centers:
                q = q.sources(*centers)
            candidates = q.search()
            found: FoundResource | None = candidates[0] if candidates else None
        except Exception as exc:
            logger.debug("No candidates for %s: %s", dep.spec, exc)
            return ResolvedDependency(spec=dep.spec, required=dep.required, status="missing")

        if found is None:
            logger.warning("No search results for dependency %s", dep.spec)
            return ResolvedDependency(spec=dep.spec, required=dep.required, status="missing")

        if found.is_local:
            return ResolvedDependency(
                spec=dep.spec,
                required=dep.required,
                status="local",
                local_path=str(found.path),
                remote_url="",
            )

        if not download:
            return ResolvedDependency(
                spec=dep.spec,
                required=dep.required,
                status="remote",
                remote_url=found.uri,
            )

        path = self._downloader.run(found, date, sink_id=sink_id)
        if path is None:
            logger.warning("Download failed for dependency %s", dep.spec)
            return ResolvedDependency(spec=dep.spec, required=dep.required, status="missing")

        logger.info("Downloaded %s → %s", dep.spec, path)
        return ResolvedDependency(
            spec=dep.spec,
            required=dep.required,
            status="downloaded",
            local_path=str(path),
            remote_url=found.uri,
        )

    @staticmethod
    def _lockfile_entry_is_valid(lp) -> bool:
        """Check a lockfile entry's sink file: existence, then sidecar hash.

        Aggregate lockfile entries carry no hash of their own, so after
        the existence check the per-file sidecar ``_lock.json`` (written
        at download time) provides the hash to validate against.  A sink
        with no sidecar is only checked for existence.

        Args:
            lp: The :class:`LockProduct` entry from the aggregate lockfile.

        Returns:
            ``True`` if the sink file exists and matches its recorded hash.
        """
        # Also resolves .gz sinks to their decompressed file, mutating lp.sink.
        if not validate_lock_product(lp, mode=HashMismatchMode.STRICT):
            return False
        sidecar = get_lock_product(lp.sink)
        if sidecar is None:
            return True
        return validate_lock_product(sidecar, mode=HashMismatchMode.STRICT)

    def _resolution_from_lockfile(
        self,
        existing,
        spec: DependencySpec,
    ) -> DependencyResolution:
        """Reconstruct a :class:`DependencyResolution` from an existing lockfile.

        Iterates over every dependency in the spec (not just those in
        the lockfile), marking any absent, file-missing, or
        hash-mismatched entries as ``'missing'``.

        Args:
            existing: The loaded :class:`DependencyLockFile`.
            spec: The dependency specification.

        Returns:
            A :class:`DependencyResolution` with one entry per dependency.
        """
        locked = {lp.name: lp for lp in existing.products}
        resolved: list[ResolvedDependency] = []
        for dep in spec.dependencies:
            lp = locked.get(dep.spec)
            if lp is None:
                resolved.append(
                    ResolvedDependency(spec=dep.spec, required=dep.required, status="missing")
                )
                continue
            if not lp.sink or not self._lockfile_entry_is_valid(lp):
                logger.warning(
                    "Lockfile entry for %s points to a missing or corrupt file %s",
                    dep.spec,
                    lp.sink,
                )
                resolved.append(
                    ResolvedDependency(spec=dep.spec, required=dep.required, status="missing")
                )
                continue
            resolved.append(
                ResolvedDependency(
                    spec=dep.spec,
                    required=dep.required,
                    status="local",
                    remote_url=lp.url,
                    local_path=lp.sink,
                )
            )
        return DependencyResolution(spec_name=spec.name, resolved=resolved)
