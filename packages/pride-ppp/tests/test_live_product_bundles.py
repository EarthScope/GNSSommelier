"""Opt-in live tests for coherent near-real-time PRIDE product bundles."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from pride_ppp.factories.processor import PrideProcessor

_PRECISE_REQUIRED = ("ORBIT", "CLOCK", "ERP", "BIA")
_FAMILY_RE = re.compile(r"([A-Z]{3})0([A-Z0-9]{3})(FIN|RTS|RAP|ULT)_")


def _diagnostic_rinex(path: Path, day: datetime.date) -> Path:
    """Write a header-only RINEX spanning the target UTC day."""
    first = f"  {day.year:4d}    {day.month:2d}    {day.day:2d}     0     0    0.0000000     GPS"
    last = f"  {day.year:4d}    {day.month:2d}    {day.day:2d}    23    59   30.0000000     GPS"
    path.write_text(
        "G    4 C1C L1C C2W L2W                              SYS / # / OBS TYPES\n"
        "R    4 C1C L1C C2C L2C                              SYS / # / OBS TYPES\n"
        "E    4 C1C L1C C7Q L7Q                              SYS / # / OBS TYPES\n"
        "C    4 C2I L2I C7I L7I                              SYS / # / OBS TYPES\n"
        "J    4 C1C L1C C2L L2L                              SYS / # / OBS TYPES\n"
        f"{first:<60}TIME OF FIRST OBS\n"
        f"{last:<60}TIME OF LAST OBS\n"
        f"{'':60}END OF HEADER\n"
    )
    return path


@pytest.fixture(scope="module")
def live_processor(tmp_path_factory: pytest.TempPathFactory) -> PrideProcessor:
    root = tmp_path_factory.mktemp("live-pride-products")
    product_dir = root / "products"
    output_dir = root / "output"
    product_dir.mkdir()
    output_dir.mkdir()
    return PrideProcessor(
        pride_dir=product_dir,
        output_dir=output_dir,
        override_products_download=True,
    )


@pytest.mark.integration
@pytest.mark.parametrize("days_ago", [0, 1], ids=["current_utc_day", "previous_utc_day"])
def test_live_coherent_product_bundle(
    live_processor: PrideProcessor,
    tmp_path: Path,
    days_ago: int,
) -> None:
    """Download and inspect one coherent precise-product family."""
    day = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=days_ago)
    target = datetime.datetime.combine(day, datetime.time(), tzinfo=datetime.UTC)

    resolution = live_processor._resolve(target)
    rinex = _diagnostic_rinex(tmp_path / f"diagnostic-{day}.rnx", day)
    live_processor._add_product_diagnostics([rinex], resolution)

    by_spec = {result.spec: result for result in resolution.resolved}
    missing = [name for name in _PRECISE_REQUIRED if by_spec[name].status == "missing"]
    if missing and days_ago == 0:
        pytest.skip(f"No complete same-day product family published yet: missing {missing}")
    assert not missing, f"No complete precise-product bundle for {day}: missing {missing}"

    families = set()
    for name in _PRECISE_REQUIRED:
        result = by_spec[name]
        match = _FAMILY_RE.search(Path(result.remote_url or result.local_path or "").name)
        assert match, f"Could not infer family from {name}: {result.remote_url}"
        families.add(match.groups())
    assert len(families) == 1, f"Mixed precise-product families selected: {families}"

    print(f"\n{day}: selected family {next(iter(families))}")
    for name in _PRECISE_REQUIRED:
        result = by_spec[name]
        print(f"  {name:<5} {result.status:<10} {result.remote_url or result.local_path}")
    for message in resolution.diagnostics:
        print(f"  diagnostic: {message}")


@pytest.mark.integration
@pytest.mark.parametrize("days_ago", [0, 1], ids=["current_utc_day", "previous_utc_day"])
def test_live_wum_product_preflight(
    live_processor: PrideProcessor,
    days_ago: int,
) -> None:
    """Search and download using only Wuhan product sources."""
    day = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=days_ago)
    target = datetime.datetime.combine(day, datetime.time(), tzinfo=datetime.UTC)

    resolution = live_processor._resolve(target, centers=["WUM"])
    by_spec = {result.spec: result for result in resolution.resolved}

    print(f"\nWUM-only result for {day}")
    for name in _PRECISE_REQUIRED:
        result = by_spec[name]
        print(f"  {name:<5} {result.status:<10} {result.remote_url or result.local_path or '-'}")

    missing = [name for name in _PRECISE_REQUIRED if by_spec[name].status == "missing"]
    assert not missing, f"No complete WUM product bundle for {day}: missing {missing}"
