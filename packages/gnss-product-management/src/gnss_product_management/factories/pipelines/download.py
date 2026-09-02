"""DownloadPipeline — found resource → local path.

Fetches remote :class:`FoundResource` objects to the local workspace
using :class:`WormHole` and :class:`SearchPlanner` for sink path
resolution.  Writes a per-file sidecar lockfile after every successful
fetch (local or remote) so that callers can verify integrity later.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from gnss_product_management.environments import ProductRegistry, WorkSpace
from gnss_product_management.factories.models import FoundResource
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.factories.search_planner import SearchPlanner
from gnss_product_management.lockfile.operations import (
    build_lock_product,
    get_lock_product,
    write_lock_product,
)

logger = logging.getLogger(__name__)


class DownloadPipeline:
    """Download :class:`FoundResource` objects to the local workspace.

    Already-local resources return immediately with their existing path.
    Remote resources are downloaded via :class:`WormHole`.

    A per-file sidecar ``<filename>_lock.json`` is written alongside
    every successfully resolved file if one does not already exist.

    Args:
        env: The product registry with built catalogs.
        workspace: Workspace with registered local resources.
        max_connections: Maximum concurrent connections per host.
        transport: Optional shared :class:`WormHole` instance.
    """

    def __init__(
        self,
        env: ProductRegistry,
        workspace: WorkSpace,
        *,
        transport: WormHole | None = None,
        max_connections: int = 4,
    ) -> None:
        self._env = env
        self._planner = SearchPlanner(product_registry=env, workspace=workspace)
        self._transport = transport or WormHole(
            max_connections=max_connections, product_registry=env
        )

    def run(
        self,
        resources: FoundResource | list[FoundResource],
        date: datetime.datetime,
        *,
        sink_id: str = "local_config",
        force: bool = False,
    ) -> Path | None | list[Path | None]:
        """Download found resources to the workspace.

        Args:
            resources: A single :class:`FoundResource` or a list of them.
            date: Target date for computing sink directory.
            sink_id: Local resource alias to download into.

        Returns:
            A :class:`Path` (or ``None`` on failure) for a single resource,
            or a list of paths for multiple resources.
        """
        single = isinstance(resources, FoundResource)
        if single:
            resources = [resources]

        paths: list[Path | None] = []
        for r in resources:
            path = self._download_one(r, date, sink_id, force=force)
            paths.append(path)

        if single:
            return paths[0]
        return paths

    def _download_one(
        self,
        resource: FoundResource,
        date: datetime.datetime,
        sink_id: str,
        *,
        force: bool = False,
    ) -> Path | None:
        """Download a single resource and write its sidecar lockfile.

        Args:
            resource: The resource to download.
            date: Target date.
            sink_id: Local resource alias.

        Returns:
            Path to the resolved file, or ``None`` on failure.
        """
        if resource.is_local and not force:
            local_path = resource.path
            if local_path and local_path.exists():
                logger.debug("Already local: %s", local_path)
                if get_lock_product(local_path) is None:
                    lock = build_lock_product(sink=local_path, url="", name=resource.product)
                    write_lock_product(lock)
                return local_path

        query = resource._query
        if query is None:
            logger.debug("FoundResource has no internal query; skipping download.")
            return None

        path = self._transport.download_one(
            query=query,
            local_resource_id=sink_id,
            local_factory=self._planner._workspace,
            date=date,
            force=force,
        )
        if path is not None:
            if force or get_lock_product(path) is None:
                lock = build_lock_product(sink=path, url=resource.uri, name=resource.product)
                write_lock_product(lock)
            logger.info("Downloaded %s → %s", resource.product, path)
        return path
