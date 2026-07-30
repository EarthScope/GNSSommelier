"""
Tests: Lockfile subsystem — models, operations, and LockfileManager.

All tests are local-only (no network access).  Uses tmp_path fixtures
for filesystem operations.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from gnss_product_management.lockfile import (
    DependencyLockFile,
    HashMismatchMode,
    LockfileManager,
    LockProduct,
    build_lock_product,
    get_dependency_lockfile,
    get_dependency_lockfile_name,
    get_lock_product,
    get_package_version,
    validate_lock_product,
    write_dependency_lockfile,
    write_lock_product,
)

# ── Constants ─────────────────────────────────────────────────────

TEST_DATE = datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc)
PKG = "PRIDE"
TASK = "PPP"


# ── Helpers ───────────────────────────────────────────────────────


def _make_product_file(tmp_path: Path, name: str = "test.SP3") -> Path:
    """Create a small fixture file and return its path."""
    p = tmp_path / name
    p.write_text("dummy product content")
    return p


def _make_lock_product(tmp_path: Path, name: str = "ORBIT") -> LockProduct:
    """Build a LockProduct from a fixture file."""
    sink = _make_product_file(tmp_path, f"{name}.SP3")
    return build_lock_product(
        sink=sink,
        url=f"ftp://example.com/{name}.SP3",
        name=name,
        description=f"Test {name}",
    )


def _make_lockfile(
    tmp_path: Path, n_products: int = 3, version: str | None = None
) -> DependencyLockFile:
    """Build a DependencyLockFile with n fixture products."""
    products = []
    for i in range(n_products):
        products.append(_make_lock_product(tmp_path, name=f"PROD_{i}"))
    return DependencyLockFile(
        date=TEST_DATE.strftime("%Y-%m-%d"),
        package=PKG,
        task=TASK,
        version=version or get_package_version(),
        products=products,
    )


# ===================================================================
# Models
# ===================================================================


class TestDependencyLockFileModel:
    def test_no_station_field(self) -> None:
        """Station should not be part of the lockfile model."""
        lf = DependencyLockFile(
            date="2025-01-15",
            package=PKG,
            task=TASK,
            version="0.1.0",
        )
        assert not hasattr(lf, "station") or "station" not in lf.model_fields

    def test_version_required(self) -> None:
        """Version is a required field (no default)."""
        with pytest.raises(Exception):
            DependencyLockFile(date="2025-01-15", package=PKG, task=TASK)

    def test_round_trip_json(self) -> None:
        lf = DependencyLockFile(
            date="2025-01-15",
            package=PKG,
            task=TASK,
            version="0.1.0",
            products=[LockProduct(name="ORBIT", url="ftp://x/o.SP3", hash="abc123")],
        )
        json_str = lf.model_dump_json()
        lf2 = DependencyLockFile.model_validate_json(json_str)
        assert lf2.package == PKG
        assert len(lf2.products) == 1
        assert lf2.products[0].hash == "abc123"


# ===================================================================
# Operations: naming
# ===================================================================


class TestLockfileNaming:
    def test_filename_no_station(self) -> None:
        """Filename should NOT contain a station prefix."""
        name = get_dependency_lockfile_name(package=PKG, task=TASK, date=TEST_DATE, version="0.1.0")
        assert name == "PRIDE_PPP_2025_015_0.1.0_lock.json"

    def test_filename_default_version(self) -> None:
        """When version is None, uses installed package version."""
        name = get_dependency_lockfile_name(package=PKG, task=TASK, date=TEST_DATE)
        assert get_package_version() in name

    def test_filename_string_date(self) -> None:
        name = get_dependency_lockfile_name(
            package=PKG, task=TASK, date="2025-01-15", version="1.0.0"
        )
        assert name == "PRIDE_PPP_2025_015_1.0.0_lock.json"

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError):
            get_dependency_lockfile_name(package=PKG, task=TASK, date="not-a-date", version="0.1.0")


# ===================================================================
# Operations: per-file sidecars
# ===================================================================


class TestSidecarOperations:
    def test_build_lock_product(self, tmp_path: Path) -> None:
        sink = _make_product_file(tmp_path)
        lp = build_lock_product(sink=sink, url="ftp://x/test.SP3", name="TEST")
        assert lp.name == "TEST"
        assert lp.hash != ""
        assert lp.size > 0
        assert lp.sink == str(sink)

    def test_build_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_lock_product(sink=tmp_path / "no_such_file", url="ftp://x/missing")

    def test_write_and_read_sidecar(self, tmp_path: Path) -> None:
        lp = _make_lock_product(tmp_path)
        written = write_lock_product(lp)
        assert written.exists()
        read_back = get_lock_product(Path(lp.sink))
        assert read_back is not None
        assert read_back.name == lp.name
        assert read_back.hash == lp.hash

    def test_get_lock_product_missing(self, tmp_path: Path) -> None:
        """No sidecar → returns None."""
        sink = _make_product_file(tmp_path, "no_sidecar.SP3")
        assert get_lock_product(sink) is None


# ===================================================================
# Operations: validate_lock_product
# ===================================================================


class TestValidation:
    def test_valid_product(self, tmp_path: Path) -> None:
        lp = _make_lock_product(tmp_path)
        assert validate_lock_product(lp) is True

    def test_missing_sink_returns_false(self, tmp_path: Path) -> None:
        lp = LockProduct(
            name="GONE",
            url="ftp://x/gone.SP3",
            sink=str(tmp_path / "nonexistent"),
            hash="abc",
        )
        assert validate_lock_product(lp) is False

    def test_hash_mismatch_warn_returns_true(self, tmp_path: Path) -> None:
        lp = _make_lock_product(tmp_path)
        lp.hash = "wrong_hash_value"
        assert validate_lock_product(lp, mode=HashMismatchMode.WARN) is True

    def test_hash_mismatch_strict_returns_false(self, tmp_path: Path) -> None:
        lp = _make_lock_product(tmp_path)
        lp.hash = "wrong_hash_value"
        assert validate_lock_product(lp, mode=HashMismatchMode.STRICT) is False


# ===================================================================
# Operations: aggregate lockfile read/write
# ===================================================================


class TestAggregateReadWrite:
    def test_write_and_read(self, tmp_path: Path) -> None:
        lf = _make_lockfile(tmp_path)
        path = write_dependency_lockfile(lf, tmp_path)
        assert path.exists()
        loaded, loaded_path = get_dependency_lockfile(
            directory=tmp_path,
            package=PKG,
            task=TASK,
            date=TEST_DATE,
            version=lf.version,
        )
        assert loaded is not None
        assert loaded_path == path
        assert len(loaded.products) == 3

    def test_write_duplicate_raises(self, tmp_path: Path) -> None:
        lf = _make_lockfile(tmp_path)
        write_dependency_lockfile(lf, tmp_path)
        with pytest.raises(FileExistsError):
            write_dependency_lockfile(lf, tmp_path, update=False)

    def test_write_update_overwrites(self, tmp_path: Path) -> None:
        lf = _make_lockfile(tmp_path, n_products=1)
        write_dependency_lockfile(lf, tmp_path)
        lf.products.append(LockProduct(name="EXTRA", url="ftp://x/extra"))
        write_dependency_lockfile(lf, tmp_path, update=True)
        loaded, _ = get_dependency_lockfile(
            directory=tmp_path,
            package=PKG,
            task=TASK,
            date=TEST_DATE,
            version=lf.version,
        )
        assert len(loaded.products) == 2

    def test_read_nonexistent_returns_none(self, tmp_path: Path) -> None:
        lf, path = get_dependency_lockfile(
            directory=tmp_path,
            package=PKG,
            task=TASK,
            date=TEST_DATE,
            version="0.1.0",
        )
        assert lf is None
        assert path is not None  # expected path returned


# ===================================================================
# LockfileManager
# ===================================================================


class TestLockfileManager:
    def test_exists_false_when_empty(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        assert mgr.exists(PKG, TASK, TEST_DATE, "0.1.0") is False

    def test_save_and_load(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        lf = _make_lockfile(tmp_path)
        mgr.save(lf)
        assert mgr.exists(PKG, TASK, TEST_DATE, lf.version)
        loaded = mgr.load(PKG, TASK, TEST_DATE, lf.version)
        assert loaded is not None
        assert len(loaded.products) == len(lf.products)

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        assert mgr.load(PKG, TASK, TEST_DATE, "0.1.0") is None

    def test_build_aggregate(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        products = [_make_lock_product(tmp_path, f"P{i}") for i in range(5)]
        agg = mgr.build_aggregate(
            products=products,
            package=PKG,
            task=TASK,
            date=TEST_DATE,
            version="0.1.0",
        )
        assert len(agg.products) == 5
        assert agg.package == PKG
        assert agg.version == "0.1.0"

    def test_round_trip(self, tmp_path: Path) -> None:
        """Save → load round-trip preserves all data."""
        mgr = LockfileManager(tmp_path)
        lf = _make_lockfile(tmp_path)
        mgr.save(lf)
        loaded = mgr.load(PKG, TASK, TEST_DATE, lf.version)
        assert loaded is not None
        assert loaded.date == lf.date
        assert loaded.package == lf.package
        assert loaded.task == lf.task
        assert loaded.version == lf.version
        for orig, back in zip(lf.products, loaded.products):
            assert orig.name == back.name
            assert orig.hash == back.hash
            assert orig.url == back.url

    def test_export_lockfile(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        lf = _make_lockfile(tmp_path)
        mgr.save(lf)
        exported = mgr.export_lockfile(PKG, TASK, TEST_DATE, lf.version)
        assert exported.exists()

    def test_export_nonexistent_raises(self, tmp_path: Path) -> None:
        mgr = LockfileManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            mgr.export_lockfile(PKG, TASK, TEST_DATE, "0.1.0")

    def test_import_lockfile_warn_mode(self, tmp_path: Path) -> None:
        """Import with warn mode keeps products even if hash mismatches."""
        mgr = LockfileManager(tmp_path)
        lf = _make_lockfile(tmp_path, n_products=2)
        lf.products[0].hash = "deliberately_wrong"
        path = mgr.save(lf)
        imported = mgr.import_lockfile(path, strict=False)
        # In warn mode, all products kept (product 0 has wrong hash
        # but file still exists → warn mode returns True)
        assert len(imported.products) == 2

    def test_import_lockfile_strict_mode(self, tmp_path: Path) -> None:
        """Import with strict mode drops products with hash mismatches."""
        mgr = LockfileManager(tmp_path)
        lf = _make_lockfile(tmp_path, n_products=2)
        lf.products[0].hash = "deliberately_wrong"
        path = mgr.save(lf)
        imported = mgr.import_lockfile(path, strict=True)
        # strict mode should drop the bad-hash product
        assert len(imported.products) == 1
        assert imported.products[0].name == lf.products[1].name

    def test_lockfile_creates_directory(self, tmp_path: Path) -> None:
        """Saving to a non-existent directory should create it."""
        subdir = tmp_path / "deep" / "nested" / "lockfiles"
        mgr = LockfileManager(subdir)
        lf = _make_lockfile(tmp_path)
        mgr.save(lf)
        assert mgr.exists(PKG, TASK, TEST_DATE, lf.version)


# ===================================================================
# Package version
# ===================================================================


class TestPackageVersion:
    def test_returns_string(self) -> None:
        v = get_package_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_installed_version(self) -> None:
        """Installed version should be the one from pyproject.toml."""
        v = get_package_version()
        # At minimum it should be a semver-ish string
        assert "." in v


# ── ResolvePipeline lockfile-entry validation ─────────────────────


class TestLockfileEntryValidation:
    """_lockfile_entry_is_valid guards the ResolvePipeline fast path:
    aggregate entries carry no hash, so the per-file sidecar written at
    download time provides the hash to validate against."""

    def test_entry_with_matching_sidecar_is_valid(self, tmp_path: Path) -> None:
        from gnss_product_management.factories.pipelines.resolve import ResolvePipeline

        sink = _make_product_file(tmp_path)
        write_lock_product(build_lock_product(sink=sink, url="", name="ORBIT"))
        entry = LockProduct(name="ORBIT", url="", sink=str(sink))
        assert ResolvePipeline._lockfile_entry_is_valid(entry)

    def test_entry_without_sidecar_only_needs_existence(self, tmp_path: Path) -> None:
        from gnss_product_management.factories.pipelines.resolve import ResolvePipeline

        sink = _make_product_file(tmp_path)
        entry = LockProduct(name="ORBIT", url="", sink=str(sink))
        assert ResolvePipeline._lockfile_entry_is_valid(entry)

    def test_entry_with_missing_file_is_invalid(self, tmp_path: Path) -> None:
        from gnss_product_management.factories.pipelines.resolve import ResolvePipeline

        entry = LockProduct(name="ORBIT", url="", sink=str(tmp_path / "gone.SP3"))
        assert not ResolvePipeline._lockfile_entry_is_valid(entry)

    def test_entry_corrupted_after_sidecar_is_invalid(self, tmp_path: Path) -> None:
        from gnss_product_management.factories.pipelines.resolve import ResolvePipeline

        sink = _make_product_file(tmp_path)
        write_lock_product(build_lock_product(sink=sink, url="", name="ORBIT"))
        sink.write_text("corrupted after the sidecar was written")
        entry = LockProduct(name="ORBIT", url="", sink=str(sink))
        assert not ResolvePipeline._lockfile_entry_is_valid(entry)
