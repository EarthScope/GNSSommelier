"""WormHole — protocol-agnostic file search and download."""

import datetime
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fsspec
import fsspec.utils

from gnss_product_management.environments import WorkSpace
from gnss_product_management.factories.connection_pool import ConnectionPoolFactory
from gnss_product_management.lockfile.operations import (
    HashMismatchMode,
    get_lock_product,
    validate_lock_product,
)
from gnss_product_management.specifications.products.product import PathTemplate
from gnss_product_management.specifications.remote.resource import SearchTarget
from gnss_product_management.utilities.helpers import decompress_gzip
from gnss_product_management.utilities.paths import AnyPath, as_path

logger = logging.getLogger(__name__)

# Type alias for (hostname, directory) grouping key
_DirKey = tuple[str, str]


class WormHole:
    """Search for files described by :class:`SearchTarget` objects.

    For each target, lists the remote (FTP/HTTP) or local directory, matches
    ``product.filename.pattern`` against the listing, and populates
    ``directory.value`` and ``filename.value`` on the target.

    Attributes:
        _connection_pool_factory: Factory managing per-host connection pools.
        _env: Optional product registry for parameter back-filling.

    Usage::

        targets = sp.get(date=..., product=..., parameters=...)
        transport = WormHole()
        results = transport.search(targets)

        for st in results:
            print(st.server.hostname, st.product.filename.value)
    """

    def __init__(
        self,
        *,
        max_connections: int = 4,
        product_registry=None,
    ) -> None:
        """Initialise the transport.

        Args:
            max_connections: Maximum connections per host pool.
            product_registry: Optional :class:`ProductRegistry` for parameter back-filling
                after a filename match.
        """
        self._connection_pool_factory = ConnectionPoolFactory(max_connections=max_connections)
        self._product_registry = product_registry

    # -- Public API ------------------------------------------------

    def search(self, targets: list[SearchTarget]) -> list[SearchTarget]:
        """Search every target's server/directory for matching files.

        Targets are grouped by ``(hostname, directory)`` so each unique
        remote directory is listed exactly once.  Pattern matching for
        every target in the group runs against the shared listing.
        The ``filename.value`` field is set on each returned target.

        Args:
            targets: SearchTarget objects to search.

        Returns:
            A list of :class:`SearchTarget` objects with ``filename.value``
            already populated — one per matched filename.
        """
        groups, rejected = self._group_targets(targets)

        # Ensure connection pools exist for every hostname we'll contact.
        for hostname, _ in groups:
            self._connection_pool_factory.add_connection(hostname)

        # List each unique directory in parallel.
        dir_keys = list(groups.keys())
        with ThreadPoolExecutor(max_workers=max(min(len(dir_keys), 25), 1)) as pool:
            listings = dict(zip(dir_keys, pool.map(self._list_dir, dir_keys)))

        # Match every target's file pattern against the pre-fetched listing.
        results: list[SearchTarget] = list(rejected)
        for key, group_targets in groups.items():
            listing = listings[key]
            for target, file_pattern in group_targets:
                target.directory.value = key[1]  # type: ignore[union-attr]
                matches = self._match_files(listing, file_pattern)
                for filename in matches:
                    expanded = target.model_copy(deep=True)
                    expanded.product.filename.value = filename  # type: ignore[union-attr]
                    results.append(expanded)

        return results

    # -- Grouping --------------------------------------------------

    def _group_targets(
        self, targets: list[SearchTarget]
    ) -> tuple[dict[_DirKey, list[tuple[SearchTarget, str]]], list[SearchTarget]]:
        """Group targets by ``(hostname, directory)``.

        Args:
            targets: SearchTarget objects to group.

        Returns:
            A tuple of (grouped targets, rejected targets).
            Grouped targets map each unique key to the targets and
            file patterns for that directory. Rejected targets are
            those missing directory or pattern.
        """
        groups: dict[_DirKey, list[tuple[SearchTarget, str]]] = defaultdict(list)
        rejected: list[SearchTarget] = []

        for t in targets:
            directory = self._get_directory(t)
            file_pattern = self._get_file_pattern(t)
            if not directory or not file_pattern:
                logger.debug(
                    "Skipping target with missing directory or file pattern: dir=%r, pat=%r",
                    directory,
                    file_pattern,
                )
                continue
            if fsspec.utils.get_protocol(t.server.hostname) == "file":
                if not (Path(t.server.hostname) / directory).exists():
                    logger.debug("Local directory does not exist: %s", t.server.hostname)
                    continue
            key: _DirKey = (t.server.hostname, directory)
            groups[key].append((t, file_pattern))

        return groups, rejected

    # -- Directory listing -----------------------------------------

    def _list_dir(self, key: _DirKey) -> list[str]:
        """List a single ``(hostname, directory)`` pair.

        Args:
            key: A ``(hostname, directory)`` tuple.

        Returns:
            A list of filenames, or ``[]`` on failure.
        """
        hostname, directory = key
        try:
            return self._connection_pool_factory.list_directory(hostname, directory)
        except Exception as e:
            logger.warning("Listing failed for %s/%s: %s", hostname, directory, e)
            return []

    # -- Pattern matching ------------------------------------------

    @staticmethod
    def _match_files(listing: list[str], file_pattern: str) -> list[str]:
        """Match filenames in a directory listing against a regex pattern.

        Args:
            listing: Filenames from a directory listing.
            file_pattern: Regex pattern to match.

        Returns:
            Matching filenames (excluding ``.lock`` files).
        """
        # remove lockfile sidecars and .lock files from listing before matching
        listing = [f for f in listing if not f.endswith(".lock") and not f.endswith("_lock.json")]
        try:
            rx = re.compile(file_pattern, re.IGNORECASE)
            return [f for f in listing if rx.search(f)]
        except re.error:
            return [f for f in listing if file_pattern in f]

    # -- Helpers ---------------------------------------------------

    @staticmethod
    def _get_directory(target: SearchTarget) -> str | None:
        """Extract the resolved directory string from a target.

        Args:
            target: The target to inspect.

        Returns:
            The directory string, or ``None``.
        """
        d = target.directory
        if isinstance(d, PathTemplate):
            return d.value or d.pattern
        if isinstance(d, str):
            return d
        return None

    @staticmethod
    def _get_file_pattern(target: SearchTarget) -> str | None:
        """Extract the file regex pattern from a target.

        Args:
            target: The target to inspect.

        Returns:
            The file pattern string, or ``None``.
        """
        if target.product.filename is None:
            return None
        fn = target.product.filename
        if isinstance(fn, PathTemplate):
            return fn.pattern
        if isinstance(fn, str):
            return fn
        return None

    def _update_parameters(self, search_target: SearchTarget) -> SearchTarget:
        """Update a SearchTarget's parameters by re-interpolating patterns.

        Uses :func:`infer_from_regex` and ``self._env.classify``
        to fill in parameter values from the matched filename.

        Args:
            search_target: The target to update.

        Returns:
            A deep copy of the target with updated parameters.
        """
        from gnss_product_management.specifications.products.product import (
            infer_from_regex,
        )

        updated = search_target.model_copy(deep=True)
        updated_params = infer_from_regex(
            regex=updated.product.filename.pattern,  # type: ignore
            filename=updated.product.filename.value,  # type: ignore
            parameters=updated.product.parameters,
        )
        updated.product.parameters = updated_params

        if self._product_registry is not None:
            classification_results = self._product_registry.classify(
                filename=updated.product.filename.value,
                parameters=updated.product.parameters,
            )
            if classification_results:
                class_parameters: dict[str, str] = classification_results.get("parameters", {})
                if updated.product.parameters is not None:
                    for p in updated.product.parameters:
                        if p.name in class_parameters and p.value is None:
                            p.value = class_parameters[p.name]

        return updated

    @staticmethod
    def _validate_cached_or_evict(path: AnyPath) -> bool:
        """Validate a cached file against its sidecar lockfile hash.

        Returns ``True`` when the file can be trusted: either its SHA-256
        matches the sidecar ``_lock.json`` written at download time, or no
        sidecar exists to validate against.  On a hash mismatch the file
        and its stale sidecar are deleted so the caller re-downloads.

        Args:
            path: Existing cached file to validate.

        Returns:
            ``True`` if the cached file is usable, ``False`` if it was
            evicted and must be re-downloaded.
        """
        lock = get_lock_product(path)
        if lock is None or validate_lock_product(lock, mode=HashMismatchMode.STRICT):
            return True
        logger.warning("Cached file failed hash validation, evicting: %s", path)
        as_path(str(path) + "_lock.json").unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        return False

    def download_one(
        self,
        query: SearchTarget,
        local_resource_id: str,
        local_factory: WorkSpace,
        date: datetime.datetime,
    ) -> AnyPath | None:
        """Synchronously download matched files for one search target.

        Skips the download if the destination file already exists,
        is non-empty, and matches its sidecar lockfile hash (when one
        exists) — a corrupt cached file is evicted and re-downloaded.
        Downloaded files are verified against the remote size (when the
        server reports one) and retried once on mismatch, so truncated
        transfers are never cached.

        Args:
            query: The resolved search target with filename value.
            local_resource_id: Target local resource identifier.
            local_factory: Planner for resolving local sink paths.
            date: Target date for computing sink directory.

        Returns:
            Path (local or cloud) to the downloaded file, or ``None`` on failure.
        """

        hostname = query.server.hostname

        destination_resource = local_factory.sink_product(query.product, local_resource_id, date)
        destination_dir = (
            as_path(destination_resource.server.hostname) / destination_resource.directory.value
        )  # type: ignore[union-attr]
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / query.product.filename.value  # type: ignore[union-attr]

        # Prefer an already-decompressed version on disk
        if destination_path.suffix == ".gz":
            decompressed_path = destination_path.with_suffix("")
            if (
                decompressed_path.exists()
                and decompressed_path.stat().st_size > 0
                and self._validate_cached_or_evict(decompressed_path)
            ):
                logger.debug(
                    "Skipping download, decompressed file already exists: %s",
                    decompressed_path,
                )
                return decompressed_path

        # Skip download if the file already exists, is non-empty, and
        # passes sidecar hash validation.
        if (
            destination_path.exists()
            and destination_path.stat().st_size > 0
            and self._validate_cached_or_evict(destination_path)
        ):
            logger.debug("Skipping download, file already exists: %s", destination_path)
            return destination_path

        remote_file_path = str(
            Path(query.directory.value) / query.product.filename.value  # type: ignore[union-attr]
        )

        # Skip download if the remote file is zero bytes (stale/incomplete upload).
        remote_size = self._connection_pool_factory.get_file_size(hostname, remote_file_path)
        if remote_size is not None and remote_size == 0:
            logger.warning("Skipping zero-byte remote file: %s/%s", hostname, remote_file_path)
            return None

        result: Path | None = None
        for attempt in range(2):
            try:
                result = self._connection_pool_factory.download_file(
                    hostname=hostname,
                    remote_path=remote_file_path,
                    target_dir=destination_dir,
                )
            except Exception as e:
                logger.warning(
                    "Download failed for %s/%s/%s: %s",
                    hostname,
                    query.directory.value,
                    query.product.filename.value,
                    e,
                )
                return None
            if result is None:
                return None
            if remote_size is None:
                break
            local_size = result.stat().st_size
            if local_size == remote_size:
                break
            # Truncated/corrupt transfer: never leave it on disk where a
            # later run would treat it as a satisfied dependency.
            logger.warning(
                "Size mismatch for %s: %d bytes local vs %d remote — deleting%s",
                result,
                local_size,
                remote_size,
                ", retrying" if attempt == 0 else "",
            )
            result.unlink(missing_ok=True)
            result = None

        if result is None:
            return None

        # Decompress gzip files after download
        if result.suffix == ".gz":
            decompressed = decompress_gzip(result)
            if decompressed is not None:
                return decompressed
            logger.warning("Decompression failed for %s, returning compressed file", result)

        return result
