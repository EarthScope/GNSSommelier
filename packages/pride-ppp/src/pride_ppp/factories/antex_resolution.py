"""Resolve the ANTEX calibration explicitly required by selected products."""

import gzip
import hashlib
import logging
import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

from gnss_product_management.utilities.paths import as_path

logger = logging.getLogger(__name__)
_ARCHIVE = "https://files.igs.org/pub/station/general/pcv_archive/"


def required_antex(resolution):
    """Read calibration references from clock, SP3 and Bias-SINEX headers."""
    references = set()
    for item in resolution.fulfilled:
        if item.spec not in {"CLOCK", "ORBIT", "BIA"} or not item.local_path:
            continue
        with as_path(item.local_path).open(encoding="ascii", errors="replace") as stream:
            for line in stream:
                if item.spec == "CLOCK" and "END OF HEADER" in line:
                    break
                if item.spec == "ORBIT" and line.startswith("* "):
                    break
                if item.spec == "BIA" and line.startswith("+BIAS/SOLUTION"):
                    break
                value = None
                if item.spec == "CLOCK" and "SYS / PCVS APPLIED" in line:
                    value = line[20:34].strip()
                elif item.spec == "ORBIT":
                    match = re.search(r"\bPCV:\s*(\S+)", line)
                    if match:
                        value = match.group(1)
                elif item.spec == "BIA":
                    match = re.search(r"\bAPC_MODEL\s+(\S+)", line)
                    if match:
                        value = match.group(1)
                if value:
                    references.add(value.lower().removesuffix(".atx"))
    if not references:
        raise ValueError("Selected products do not identify an ANTEX calibration")
    unsupported = [r for r in references if not re.fullmatch(r"igs[0-9]{2}(_[0-9]{4})?", r)]
    if unsupported:
        raise ValueError(f"Unsupported ANTEX reference: {sorted(unsupported)}")
    # A bare frame name (e.g. "igs20") is compatible with any revision of that frame.
    versioned = {r for r in references if "_" in r}
    references -= {
        r for r in references if "_" not in r and any(v.startswith(f"{r}_") for v in versioned)
    }
    if len(references) != 1:
        raise ValueError(f"Conflicting ANTEX references: {sorted(references)}")
    return references.pop()


def resolve_product_antex(resolution, table_dir):
    """Replace the generic ATTATX result with the exact product calibration."""
    if not all(
        any(r.spec == spec for r in resolution.fulfilled) for spec in ("CLOCK", "ORBIT", "BIA")
    ):
        return resolution
    revision = required_antex(resolution)
    entry = next((r for r in resolution.resolved if r.spec == "ATTATX"), None)
    if entry is None:
        raise ValueError("ANTEX dependency is absent from processing specification")
    if "_" not in revision:
        # Unversioned reference: products only name the frame, so keep the generic ATTATX.
        current = Path(as_path(entry.local_path)) if entry.local_path else None
        if current is None or not current.exists() or current.stem.lower() != revision:
            raise ValueError(f"Products require unversioned ANTEX {revision}, resolved {current}")
        _validate(current)
        digest = hashlib.sha256(current.read_bytes()).hexdigest()
        resolution.diagnostics.append(
            f"ANTEX {revision} (unversioned in products): sha256={digest}; source={current}"
        )
        return resolution
    table_dir = Path(table_dir)
    table_dir.mkdir(parents=True, exist_ok=True)
    target = table_dir / f"{revision}.atx"
    url = f"{_ARCHIVE}{revision}.atx.gz"
    downloaded = False
    if not target.exists():
        logger.info("Resolving product-required ANTEX %s from %s", revision, url)
        partial = None
        try:
            with tempfile.NamedTemporaryFile(dir=table_dir, delete=False) as out:
                partial = Path(out.name)
                with urlopen(url, timeout=60) as response, gzip.GzipFile(fileobj=response) as data:
                    shutil.copyfileobj(data, out)
            _validate(partial)
            partial.replace(target)
            downloaded = True
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
    _validate(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    entry.local_path = str(target)
    entry.remote_url = url
    entry.status = "downloaded" if downloaded else "local"
    resolution.diagnostics.append(f"ANTEX {revision}: sha256={digest}; source={url}")
    return resolution


def _validate(path):
    with path.open("rb") as stream:
        if b"ANTEX VERSION / SYST" not in stream.readline():
            raise ValueError(f"Invalid ANTEX file: {path}")
