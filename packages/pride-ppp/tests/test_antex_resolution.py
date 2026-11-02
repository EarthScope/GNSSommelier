import gzip
import io
from pathlib import Path

import pytest
from gnss_product_management.specifications.dependencies.dependencies import (
    DependencyResolution,
    ResolvedDependency,
)
from pride_ppp.factories import antex_resolution as module


def bundle(tmp_path, orbit="IGS20_2425", clock="IGS20_2425", bias="IGS20_2425"):
    result = DependencyResolution("test")
    for spec, text in [
        ("CLOCK", f"{'C  GPSEST V5.5':20}{clock:14} SYS / PCVS APPLIED\nEND OF HEADER\n"),
        ("ORBIT", f"/* PCV:{orbit}\n* epoch\n"),
        ("BIA", f" APC_MODEL {bias}\n+BIAS/SOLUTION\n"),
    ]:
        path = tmp_path / spec
        path.write_text(text)
        result.resolved.append(
            ResolvedDependency(spec=spec, required=True, status="local", local_path=str(path))
        )
    result.resolved.append(ResolvedDependency(spec="ATTATX", required=True, status="missing"))
    return result


def test_exact_download_and_cache(tmp_path, monkeypatch):
    calls = []

    def download(url, timeout):
        calls.append(url)
        return io.BytesIO(gzip.compress(b"     1.4            ANTEX VERSION / SYST\n"))

    monkeypatch.setattr(module, "urlopen", download)
    result = bundle(tmp_path)
    module.resolve_product_antex(result, tmp_path / "table")
    entry = result.resolved[-1]
    assert Path(entry.local_path).name == "igs20_2425.atx"
    assert entry.status == "downloaded"
    assert entry.remote_url.endswith("/igs20_2425.atx.gz")
    assert "sha256=" in result.diagnostics[-1]
    module.resolve_product_antex(result, tmp_path / "table")
    assert entry.status == "local"
    assert len(calls) == 1


def test_conflict(tmp_path):
    with pytest.raises(ValueError, match="Conflicting"):
        module.required_antex(bundle(tmp_path, orbit="IGS20_2300"))


def test_missing_reference(tmp_path):
    result = bundle(tmp_path)
    for entry in result.fulfilled:
        Path(entry.local_path).write_text("no reference\n")
    with pytest.raises(ValueError, match="do not identify"):
        module.required_antex(result)


def test_bad_download_is_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: io.BytesIO(gzip.compress(b"not antex")))
    result = bundle(tmp_path)
    with pytest.raises(ValueError, match="Invalid ANTEX"):
        module.resolve_product_antex(result, tmp_path / "table")
    assert result.resolved[-1].status == "missing"
    assert list((tmp_path / "table").iterdir()) == []


def test_non_ascii_product_comment(tmp_path):
    result = bundle(tmp_path)
    path = Path(result.resolved[2].local_path)
    path.write_bytes(b" comment \xe4\n" + path.read_bytes())
    assert module.required_antex(result) == "igs20_2425"


def test_unversioned_reference_defers_to_versioned(tmp_path):
    assert module.required_antex(bundle(tmp_path, bias="IGS20")) == "igs20_2425"


def test_unversioned_only_keeps_generic_antex(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: pytest.fail("no download expected"))
    result = bundle(tmp_path, orbit="IGS20", clock="IGS20", bias="IGS20")
    generic = tmp_path / "igs20.atx"
    generic.write_text("     1.4            ANTEX VERSION / SYST\n")
    entry = result.resolved[-1]
    entry.local_path, entry.status = str(generic), "local"
    module.resolve_product_antex(result, tmp_path / "table")
    assert entry.local_path == str(generic)
    assert "unversioned" in result.diagnostics[-1]


def test_unversioned_only_without_generic_antex(tmp_path):
    result = bundle(tmp_path, orbit="IGS20", clock="IGS20", bias="IGS20")
    with pytest.raises(ValueError, match="unversioned ANTEX igs20"):
        module.resolve_product_antex(result, tmp_path / "table")
