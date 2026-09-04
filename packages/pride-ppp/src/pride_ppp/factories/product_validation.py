"""Advisory checks for PRIDE precise-product compatibility."""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable
from pathlib import Path

from gnss_product_management.specifications.dependencies.dependencies import DependencyResolution

from .rinex import rinex_get_time_range

_OBS = re.compile(r"^[CLDS][1-9][A-Z]$")
_SAT = re.compile(r"^[GRECJ]\d{2,3}$")


def rinex_phase_observables(paths: Iterable[Path]) -> dict[str, set[str]]:
    """Return phase observables advertised by RINEX 3/4 headers."""
    observables: dict[str, set[str]] = {}
    for path in paths:
        current_system = ""
        with Path(path).open(errors="replace") as stream:
            for line in stream:
                if "END OF HEADER" in line:
                    break
                if "SYS / # / OBS TYPES" not in line:
                    continue
                is_first_line = bool(line[:1].strip())
                if is_first_line:
                    current_system = line[0]
                if not current_system:
                    continue
                tokens = line[:60].split()
                for token in tokens[2:] if is_first_line else tokens:
                    if _OBS.match(token) and token.startswith("L"):
                        observables.setdefault(current_system, set()).add(token)
    return observables


def bias_phase_observables(path: Path) -> dict[str, set[str]]:
    """Return satellite phase observables present in a SINEX BIA file."""
    observables: dict[str, set[str]] = {}
    with path.open(errors="replace") as stream:
        for line in stream:
            if not line.lstrip().startswith("OSB"):
                continue
            tokens = line.split()
            satellite = next((token for token in tokens if _SAT.match(token)), None)
            observable = next(
                (token for token in tokens if _OBS.match(token) and token.startswith("L")), None
            )
            if satellite and observable:
                observables.setdefault(satellite[0], set()).add(observable)
    return observables


def rinex_phase_bands(paths: Iterable[Path]) -> dict[str, set[str]]:
    """Return phase-frequency bands advertised by RINEX 3/4 headers."""
    return {
        system: {observable[1] for observable in observables}
        for system, observables in rinex_phase_observables(paths).items()
    }


def bias_phase_bands(path: Path) -> dict[str, set[str]]:
    """Return satellite phase-frequency bands present in a SINEX BIA file."""
    return {
        system: {observable[1] for observable in observables}
        for system, observables in bias_phase_observables(path).items()
    }


def product_epoch_bounds(
    path: Path, product: str
) -> tuple[datetime.datetime, datetime.datetime] | None:
    """Read coarse epoch bounds from SP3 or RINEX-clock content."""
    epochs: list[datetime.datetime] = []
    with path.open(errors="replace") as stream:
        for line in stream:
            fields = line.split()
            try:
                if product == "ORBIT" and line.startswith("*"):
                    values = fields[1:7]
                elif product == "CLOCK" and fields[:1] in (["AS"], ["AR"]):
                    values = fields[2:8]
                else:
                    continue
                epochs.append(
                    datetime.datetime(
                        int(values[0]),
                        int(values[1]),
                        int(values[2]),
                        int(values[3]),
                        int(values[4]),
                        int(float(values[5])),
                    )
                )
            except (ValueError, IndexError):
                continue
    return (min(epochs), max(epochs)) if epochs else None


def validate_pride_products(
    rinex_paths: Iterable[Path],
    resolution: DependencyResolution,
    frequency_combinations: Iterable[str],
) -> list[str]:
    """Describe product coverage for the configured, observed constellations.

    These checks are deliberately advisory.  Product coherence and successful
    downloads determine bundle acceptance; imperfect coverage is reported so
    callers can judge PPP-AR capability without losing a usable float solution.
    """
    rinex_paths = [Path(path) for path in rinex_paths]
    messages: list[str] = []
    observed = rinex_phase_observables(rinex_paths)
    configured = {item[0]: set(item[1:]) for item in frequency_combinations if len(item) >= 2}
    by_spec = {item.spec: Path(item.local_path) for item in resolution.fulfilled if item.local_path}

    bias_path = by_spec.get("BIA")
    if not bias_path or not bias_path.exists():
        messages.append("BIA unavailable; phase-bias capability cannot be evaluated")
        bias = None
    else:
        bias = bias_phase_observables(bias_path)
    for system, required in configured.items():
        present_observables = observed.get(system, set())
        if not present_observables:
            continue
        if bias is None:
            continue
        present = {observable[1] for observable in present_observables}
        relevant = required & present
        supported_observables = bias.get(system, set()) & present_observables
        supported = {observable[1] for observable in supported_observables}
        missing = relevant - supported
        if not relevant:
            messages.append(
                f"{system}: configured bands {sorted(required)} are not present in the RINEX"
            )
        elif missing:
            messages.append(
                f"{system}: BIA phase coverage is partial; missing bands {sorted(missing)} "
                f"for observed signals {sorted(present_observables)} "
                f"(matched {sorted(supported_observables)})"
            )
        else:
            messages.append(f"{system}: BIA phase coverage supports bands {sorted(relevant)}")

    starts_ends = [rinex_get_time_range(path) for path in rinex_paths]
    obs_start = min(item[0] for item in starts_ends)
    obs_end = max(item[1] for item in starts_ends)
    for product in ("ORBIT", "CLOCK"):
        path = by_spec.get(product)
        if not path or not path.exists():
            continue
        bounds = product_epoch_bounds(path, product)
        if bounds is None:
            messages.append(f"{product}: epoch coverage could not be read")
        elif bounds[0] > obs_start or bounds[1] < obs_end:
            messages.append(
                f"{product}: partial epoch coverage {bounds[0].isoformat()} to "
                f"{bounds[1].isoformat()} for observations ending {obs_end.isoformat()}"
            )
        else:
            messages.append(f"{product}: covers the observation interval")
    return messages
