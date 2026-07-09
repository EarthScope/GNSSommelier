"""Connection pool — thread-safe fsspec filesystem instances per host."""

import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import fsspec
import fsspec.utils

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe pool of fsspec filesystem instances for a single host.

    Attributes:
        hostname: Server address (URL or local path).
        protocol: Inferred protocol (``'ftp'``, ``'http'``, ``'file'``, etc.).
        max_connections: Maximum number of concurrent connections.
    """

    def __init__(self, hostname: str, max_connections: int = 4):
        """Initialise a connection pool for *hostname*.

        Args:
            hostname: Server address or local path.
            max_connections: Maximum number of concurrent connections.
        """
        self.hostname = hostname
        self.protocol = fsspec.utils.get_protocol(hostname) or "file"
        self.max_connections = max_connections
        self._pool: list[fsspec.AbstractFileSystem] = []
        self._semaphore: threading.Semaphore | None = None
        self._pool_lock = threading.Lock()
        self._initialized = False
        self._failed = False

    def _connect(self) -> fsspec.AbstractFileSystem | None:
        """Create a single fsspec filesystem connection.

        Returns:
            A filesystem instance, or ``None`` on failure.
        """
        if self.protocol == "file":
            try:
                return fsspec.filesystem("file")
            except Exception as e:
                logger.warning("Error creating local filesystem: %s", e)
                return None

        if self.protocol == "ftp":
            parsed = urlparse(self.hostname)
            host = parsed.hostname or self.hostname
            # Try plain FTP first, then FTPS (TLS) fallback
            for tls in (False, True):
                try:
                    return fsspec.filesystem(
                        "ftp",
                        host=host,
                        tls=tls,
                        timeout=30,
                        skip_instance_cache=True,
                    )
                except Exception:
                    continue
            logger.warning("FTP/FTPS connection failed for %s", self.hostname)
            return None

        # HTTP, HTTPS, and other protocols
        try:
            fs, _ = fsspec.core.url_to_fs(self.hostname, skip_instance_cache=True)
            return fs
        except Exception as e:
            logger.warning("Error creating filesystem for %s: %s", self.hostname, e)
            return None

    def _initialize_pool(self):
        """Lazily initialise the connection pool (double-checked locking)."""
        if self._initialized or self._failed:
            return
        with self._pool_lock:
            if self._initialized or self._failed:
                return
            first = self._connect()
            if first is None:
                self._failed = True
                return
            self._pool.append(first)
            for _ in range(self.max_connections - 1):
                conn = self._connect()
                if conn is None:
                    break
                self._pool.append(conn)
            self._semaphore = threading.Semaphore(len(self._pool))
            self._initialized = True
            logger.debug("Pool for %s: %d connections", self.hostname, len(self._pool))

    @contextmanager
    def get_connection(self):
        """Acquire a connection from the pool.

        Yields:
            An :class:`fsspec.AbstractFileSystem` instance.

        Raises:
            ConnectionError: If the pool failed to initialise.
        """
        self._initialize_pool()
        if not self._initialized:
            raise ConnectionError(f"No connections available for {self.hostname}")
        self._semaphore.acquire()
        with self._pool_lock:
            connection = self._pool.pop(0)
        try:
            yield connection
        finally:
            with self._pool_lock:
                self._pool.append(connection)
            self._semaphore.release()

    def replace_connection(
        self, dead: "fsspec.AbstractFileSystem"
    ) -> Optional["fsspec.AbstractFileSystem"]:
        """Swap a dead connection for a fresh one in the pool.

        The caller must already hold a semaphore slot (i.e. be inside
        ``get_connection``).

        Args:
            dead: The stale filesystem instance to remove and replace.

        Returns:
            A fresh :class:`fsspec.AbstractFileSystem`, or ``None`` if
            reconnection fails (the pool will be one slot smaller).
        """
        with self._pool_lock:
            try:
                self._pool.remove(dead)
            except ValueError:
                pass
        fresh = self._connect()
        if fresh is not None:
            with self._pool_lock:
                self._pool.append(fresh)
        else:
            # Give back the semaphore slot since we can't replace it
            logger.warning("Reconnect failed for %s; pool shrunk by 1", self.hostname)
            return None
        return fresh

    def full_path(self, directory: str) -> str:
        """Combine hostname base with a relative directory.

        Behaviour differs by protocol: ``file`` uses :func:`os.path.join`,
        ``http``/``https`` concatenates with forward slashes, and other
        remote protocols (FTP / FTPS / SFTP / etc.) treat the directory as
        an already-resolved server path.

        Args:
            directory: Relative directory path (or absolute for FTP).

        Returns:
            Full path string suitable for passing to fsspec operations.
        """
        if self.protocol == "file":
            return os.path.join(self.hostname, directory)
        if self.protocol in ("http", "https"):
            return f"{self.hostname.rstrip('/')}/{directory.lstrip('/')}"
        # Remote protocol path is already resolved relative to the server root
        return directory


class ConnectionPoolFactory:
    """Manage per-host connection pools with a shared directory listing cache.

    Attributes:
        max_connections: Default maximum connections per host.
    """

    def __init__(self, max_connections: int = 4):
        """Initialise the factory.

        Args:
            max_connections: Default maximum connections per host pool.
        """
        self.max_connections = max_connections
        self._pools: dict[str, ConnectionPool] = {}
        self._factory_lock = threading.Lock()
        self._listing_cache: dict[str, list[str]] = {}
        self._listing_cache_lock = threading.Lock()

    def add_connection(self, hostname: str):
        """Ensure a connection pool exists for *hostname*.

        Args:
            hostname: Server address to pool.
        """
        with self._factory_lock:
            if hostname not in self._pools:
                self._pools[hostname] = ConnectionPool(hostname, self.max_connections)

    @contextmanager
    def get_connection(self, hostname: str):
        """Acquire a connection for *hostname*.

        Args:
            hostname: Server address.

        Yields:
            An :class:`fsspec.AbstractFileSystem` instance.

        Raises:
            ValueError: If no pool exists for *hostname*.
        """
        if hostname not in self._pools:
            raise ValueError(f"No connection pool for: {hostname}")
        with self._pools[hostname].get_connection() as connection:
            yield connection

    def list_directory(self, hostname: str, directory: str) -> list[str]:
        """List a remote or local directory with caching.

        Results (including empty lists for failed lookups) are cached
        to avoid redundant network calls.

        Args:
            hostname: Server address.
            directory: Directory path.

        Returns:
            A list of filenames.

        Raises:
            ValueError: If no pool exists for *hostname*.
        """
        pool = self._pools.get(hostname)
        if pool is None:
            raise ValueError(f"No connection pool for: {hostname}")

        cache_key = f"{hostname}:{directory}"
        with self._listing_cache_lock:
            if cache_key in self._listing_cache:
                return self._listing_cache[cache_key]

        full_path = pool.full_path(directory)

        def _ls(conn: "fsspec.AbstractFileSystem") -> list[str]:
            raw = conn.ls(full_path, detail=False)
            return [Path(p).name for p in raw]

        def _cache(listing: list[str]) -> list[str]:
            # Only cache non-empty results — a transient failure (empty list)
            # should not poison the cache for the lifetime of the session.
            if listing:
                with self._listing_cache_lock:
                    self._listing_cache[cache_key] = listing
            return listing

        try:
            with pool.get_connection() as conn:
                try:
                    return _cache(_ls(conn))
                except (BrokenPipeError, ConnectionError, EOFError, OSError) as e:
                    if pool.protocol == "file":
                        # Local dir doesn't exist — not a transient failure, no retry.
                        return []
                    logger.debug("Stale connection for %s, reconnecting: %s", hostname, e)
                    fresh = pool.replace_connection(conn)
                    if fresh is None:
                        return []
                    try:
                        return _cache(_ls(fresh))
                    except Exception as e2:
                        logger.warning("Retry failed listing %s on %s: %s", directory, hostname, e2)
                        return []
                except Exception as e:
                    logger.warning("Error listing %s on %s: %s", directory, hostname, e)
                    return []
        except ConnectionError:
            # Pool failed to initialise (e.g. FTP host unreachable).
            return []

    def get_file_size(self, hostname: str, remote_path: str) -> int | None:
        """Return the size of a remote file in bytes, or ``None`` if unavailable.

        Uses ``fsspec.info()`` which is a metadata-only call — no data is
        transferred.  Returns ``None`` on any error so callers can treat an
        unknown size as "proceed with download".

        Args:
            hostname: Server address.
            remote_path: Relative path on the remote host.

        Returns:
            File size in bytes, or ``None`` if the size cannot be determined.
        """
        pool = self._pools.get(hostname)
        if pool is None:
            return None

        full_path = pool.full_path(remote_path)
        try:
            with pool.get_connection() as conn:
                info = conn.info(full_path)
                return info.get("size")
        except Exception as e:
            logger.debug("Could not get file size for %s/%s: %s", hostname, remote_path, e)
            return None

    def download_file(self, hostname: str, remote_path: str, target_dir: str) -> Path | None:
        """Download a file from a remote or local host.

        Retries once with a fresh connection on broken-pipe errors.

        Args:
            hostname: Server address.
            remote_path: Relative path on the remote host.
            target_dir: Local directory to write the file into.

        Returns:
            Path to the downloaded file, or ``None`` on failure.

        Raises:
            ValueError: If no pool exists for *hostname*.
        """
        pool = self._pools.get(hostname)
        if pool is None:
            raise ValueError(f"No connection pool for: {hostname}")

        full_path = pool.full_path(remote_path)
        filename = Path(remote_path).name
        local_path = Path(target_dir) / filename

        def _get(conn: "fsspec.AbstractFileSystem") -> Path | None:
            conn.get(full_path, str(local_path))
            if local_path.exists() and local_path.stat().st_size > 0:
                return local_path
            logger.error("Downloaded file is missing or empty: %s", local_path)
            local_path.unlink(missing_ok=True)
            return None

        with pool.get_connection() as conn:
            try:
                return _get(conn)
            except (BrokenPipeError, ConnectionError, EOFError, OSError) as e:
                logger.debug("Stale connection for %s, reconnecting: %s", hostname, e)
                fresh = pool.replace_connection(conn)
                if fresh is None:
                    return None
                try:
                    return _get(fresh)
                except Exception as e2:
                    logger.warning(
                        "Retry failed downloading %s from %s: %s",
                        remote_path,
                        hostname,
                        e2,
                    )
                    return None
            except Exception as e:
                logger.warning("Download failed %s from %s: %s", remote_path, hostname, e)
                return None
