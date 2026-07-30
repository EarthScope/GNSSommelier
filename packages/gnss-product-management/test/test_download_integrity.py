"""
Tests: WormHole.download_one integrity validation.

All tests are local-only (no network access) — the "remote" server is a
directory on disk served through the ``file`` protocol, exercising the
real ConnectionPoolFactory download path.

Covers issue #26 symptom (c): truncated/corrupt downloads must never be
cached and reused as satisfied dependencies.
"""

from __future__ import annotations

import datetime
import gzip
from pathlib import Path

import pytest
from gnss_product_management.factories.connection_pool import ConnectionPoolFactory
from gnss_product_management.factories.remote_transport import WormHole
from gnss_product_management.lockfile.operations import (
    build_lock_product,
    get_lock_product_path,
    write_lock_product,
)
from gnss_product_management.specifications.products.product import PathTemplate, Product
from gnss_product_management.specifications.remote.resource import SearchTarget, Server

# ── Constants ─────────────────────────────────────────────────────

TEST_DATE = datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc)
REMOTE_CONTENT = b"full remote product content, definitely not truncated"


# ── Helpers ───────────────────────────────────────────────────────


class _StubWorkspace:
    """Minimal stand-in for WorkSpace.sink_product."""

    def __init__(self, sink_root: Path):
        self._sink_root = sink_root

    def sink_product(self, product: Product, resource_id: str, date) -> SearchTarget:
        return SearchTarget(
            product=product,
            server=Server(id="local_sink", hostname=str(self._sink_root)),
            directory=PathTemplate(pattern="sink", value="sink"),
        )


def _make_query(remote_root: Path, filename: str) -> SearchTarget:
    product = Product(
        name="ORBIT",
        parameters=[],
        filename=PathTemplate(pattern=filename, value=filename),
    )
    return SearchTarget(
        product=product,
        server=Server(id="remote", hostname=str(remote_root)),
        directory=PathTemplate(pattern="products", value="products"),
    )


@pytest.fixture
def env(tmp_path: Path):
    """A local 'remote' server dir, a sink dir, a WormHole, and a query."""
    remote_root = tmp_path / "remote"
    remote_dir = remote_root / "products"
    remote_dir.mkdir(parents=True)
    (remote_dir / "TEST.SP3").write_bytes(REMOTE_CONTENT)

    sink_root = tmp_path / "workspace"
    wh = WormHole()
    wh._connection_pool_factory.add_connection(str(remote_root))

    return {
        "remote_root": remote_root,
        "remote_dir": remote_dir,
        "workspace": _StubWorkspace(sink_root),
        "sink_dir": sink_root / "sink",
        "wormhole": wh,
    }


def _download(env, filename: str = "TEST.SP3") -> Path | None:
    query = _make_query(env["remote_root"], filename)
    return env["wormhole"].download_one(
        query=query,
        local_resource_id="local_config",
        local_factory=env["workspace"],
        date=TEST_DATE,
    )


def _write_sidecar(path: Path) -> None:
    write_lock_product(build_lock_product(sink=path, url="file://test", name="ORBIT"))


# ── Fresh downloads ───────────────────────────────────────────────


class TestFreshDownload:
    def test_download_succeeds(self, env) -> None:
        result = _download(env)
        assert result is not None
        assert result.read_bytes() == REMOTE_CONTENT

    def test_zero_byte_remote_is_skipped(self, env) -> None:
        (env["remote_dir"] / "TEST.SP3").write_bytes(b"")
        assert _download(env) is None


# ── Truncated transfers ───────────────────────────────────────────


class TestTruncatedDownload:
    def test_truncated_download_is_deleted_not_cached(self, env, monkeypatch) -> None:
        """A transfer that keeps coming back short must fail — and leave
        nothing on disk for a later run to treat as satisfied."""

        def _truncated(self, hostname, remote_path, target_dir):
            local = Path(target_dir) / Path(remote_path).name
            local.write_bytes(REMOTE_CONTENT[: len(REMOTE_CONTENT) // 2])
            return local

        monkeypatch.setattr(ConnectionPoolFactory, "download_file", _truncated)
        assert _download(env) is None
        assert not (env["sink_dir"] / "TEST.SP3").exists()

    def test_truncated_download_retries_and_succeeds(self, env, monkeypatch) -> None:
        calls: list[int] = []

        def _flaky(self, hostname, remote_path, target_dir):
            calls.append(1)
            local = Path(target_dir) / Path(remote_path).name
            content = REMOTE_CONTENT if len(calls) > 1 else REMOTE_CONTENT[:10]
            local.write_bytes(content)
            return local

        monkeypatch.setattr(ConnectionPoolFactory, "download_file", _flaky)
        result = _download(env)
        assert result is not None
        assert result.read_bytes() == REMOTE_CONTENT
        assert len(calls) == 2


# ── Cached files ──────────────────────────────────────────────────


class TestCachedFile:
    def test_valid_cache_is_reused_without_download(self, env, monkeypatch) -> None:
        cached = env["sink_dir"] / "TEST.SP3"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(REMOTE_CONTENT)
        _write_sidecar(cached)

        calls: list[int] = []
        monkeypatch.setattr(
            ConnectionPoolFactory,
            "download_file",
            lambda self, **kw: calls.append(1),
        )
        assert _download(env) == cached
        assert calls == []

    def test_cache_without_sidecar_is_trusted(self, env, monkeypatch) -> None:
        cached = env["sink_dir"] / "TEST.SP3"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b"pre-existing content, no sidecar")

        calls: list[int] = []
        monkeypatch.setattr(
            ConnectionPoolFactory,
            "download_file",
            lambda self, **kw: calls.append(1),
        )
        assert _download(env) == cached
        assert calls == []

    def test_corrupt_cache_is_evicted_and_redownloaded(self, env) -> None:
        """A cached file whose hash no longer matches its sidecar must be
        evicted (with its stale sidecar) and fetched fresh."""
        cached = env["sink_dir"] / "TEST.SP3"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(REMOTE_CONTENT)
        _write_sidecar(cached)
        cached.write_bytes(b"corrupted after the sidecar was written")

        result = _download(env)
        assert result == cached
        assert result.read_bytes() == REMOTE_CONTENT
        assert not get_lock_product_path(cached).exists()


# ── Gzip cache path ───────────────────────────────────────────────


class TestGzipCache:
    @pytest.fixture
    def gz_env(self, env):
        (env["remote_dir"] / "ATT.OBX.gz").write_bytes(gzip.compress(REMOTE_CONTENT))
        return env

    def test_gz_download_decompresses(self, gz_env) -> None:
        result = _download(gz_env, filename="ATT.OBX.gz")
        assert result is not None
        assert result.name == "ATT.OBX"
        assert result.read_bytes() == REMOTE_CONTENT

    def test_corrupt_decompressed_cache_is_evicted_and_redownloaded(self, gz_env) -> None:
        cached = gz_env["sink_dir"] / "ATT.OBX"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(REMOTE_CONTENT)
        _write_sidecar(cached)
        cached.write_bytes(b"truncated OBX poisoning the cache")

        result = _download(gz_env, filename="ATT.OBX.gz")
        assert result == cached
        assert result.read_bytes() == REMOTE_CONTENT

    def test_valid_decompressed_cache_is_reused(self, gz_env, monkeypatch) -> None:
        cached = gz_env["sink_dir"] / "ATT.OBX"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(REMOTE_CONTENT)
        _write_sidecar(cached)

        calls: list[int] = []
        monkeypatch.setattr(
            ConnectionPoolFactory,
            "download_file",
            lambda self, **kw: calls.append(1),
        )
        assert _download(gz_env, filename="ATT.OBX.gz") == cached
        assert calls == []
