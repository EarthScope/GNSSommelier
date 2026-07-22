"""Public return types and exceptions for the ProductRegistry API."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from gnss_product_management.utilities.paths import AnyPath

if TYPE_CHECKING:
    from gnss_product_management.lockfile import DependencyLockFile
    from gnss_product_management.specifications.remote.resource import SearchTarget


class FoundResource(BaseModel):
    """A discovered IGS product — either a local file or a remote URI.

    Returned by :meth:`GNSSClient.search` and :meth:`ProductQuery.search`.
    The most useful properties for geodetic workflows:

    - ``r.center`` — analysis center code (``AAA`` field, e.g. ``"WUM"``)
    - ``r.quality`` — timeliness code (``TTT`` field: ``"FIN"``, ``"RAP"``, ``"ULT"``)
    - ``r.filename`` — bare IGS long filename
    - ``r.uri`` — full remote URL (``ftp://...``) or local path
    - ``r.is_local`` — ``True`` if already on disk
    - ``r.downloaded`` — ``True`` after a successful download
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    product: str = Field(..., description="Product name (e.g. 'ORBIT', 'CLOCK').")
    source: str = Field(..., description="'local' or 'remote'.")
    uri: str = Field(..., description="Local file path or remote URL.")
    parameters: dict[str, str] = Field(
        default_factory=dict, description="All resolved parameter values."
    )
    date: datetime.datetime | None = Field(
        default=None, description="Target date this resource was resolved for."
    )
    local_path: AnyPath | None = Field(
        default=None, description="Local filesystem path after a successful download."
    )

    # Internal: original SearchTarget, not serialized. Used by DownloadPipeline.
    _query: object | None = PrivateAttr(default=None)

    @property
    def center(self) -> str:
        """Analysis center identifier (e.g. ``'WUM'``), or ``''`` if not applicable."""
        return self.parameters.get("AAA", "")

    @property
    def quality(self) -> str:
        """Solution quality/type (e.g. ``'FIN'``, ``'RAP'``), or ``''`` if not applicable."""
        return self.parameters.get("TTT", "")

    @property
    def is_local(self) -> bool:
        """``True`` if this resource was found on the local filesystem."""
        return self.source == "local"

    @property
    def path(self) -> Path | None:
        """Return the local :class:`Path` if this is a local resource, else ``None``."""
        if self.is_local:
            return Path(self.uri)
        return None

    @property
    def hostname(self) -> str:
        """Server hostname, or ``''`` for local resources."""
        return "" if self.is_local else (urlparse(self.uri).hostname or "")

    @property
    def protocol(self) -> str:
        """Transport protocol (e.g. ``'ftp'``, ``'https'``, ``'file'``)."""
        return "file" if self.is_local else (urlparse(self.uri).scheme or "")

    @property
    def directory(self) -> str:
        """Parent directory of the resource file."""
        raw = self.uri if self.is_local else urlparse(self.uri).path
        return str(Path(raw).parent)

    @property
    def filename(self) -> str:
        """Filename (basename) of the resource."""
        raw = self.uri if self.is_local else urlparse(self.uri).path
        return Path(raw).name

    @property
    def downloaded(self) -> bool:
        """``True`` if the file has been downloaded and exists on disk."""
        return self.local_path is not None and Path(self.local_path).exists()


def found_resources_from_targets(
    ranked: list[SearchTarget],
    date: datetime.datetime | None,
) -> list[FoundResource]:
    """Convert expanded search targets into deduplicated :class:`FoundResource` objects.

    Shared by ``ProductQuery.search`` and ``StationQuery.search``.  Targets are
    deduplicated by ``(hostname, filename)`` preserving *ranked* order; targets
    without a resolved filename are dropped.  The ``SSSS`` station-code
    parameter is uppercased for display.
    """
    results: list[FoundResource] = []
    seen: set[tuple[str, str]] = set()
    for rq in ranked:
        if rq.product.filename is None or rq.product.filename.value is None:
            continue
        hostname = rq.server.hostname
        filename = rq.product.filename.value
        key = (hostname, filename)
        if key in seen:
            continue
        seen.add(key)

        params = {
            p.name: (p.value.upper() if p.name == "SSSS" and p.value else p.value)
            for p in rq.product.parameters
            if p.value is not None
        }
        is_local = (rq.server.protocol or "").upper() in ("FILE", "LOCAL")
        dir_val = rq.directory.value or rq.directory.pattern
        if is_local:
            uri = str(Path(hostname) / dir_val / filename)
        else:
            # Center specs give bare hostnames; network specs include the scheme.
            base = (
                hostname
                if "://" in hostname
                else f"{(rq.server.protocol or 'ftp').lower()}://{hostname}"
            )
            uri = f"{base.rstrip('/')}/{dir_val.strip('/')}/{filename}"

        fr = FoundResource(
            product=rq.product.name,
            source="local" if is_local else "remote",
            uri=uri,
            parameters=params,
            date=date,
        )
        fr._query = rq
        results.append(fr)
    return results


class Resolution(BaseModel):
    """Result of resolving all dependencies for a task."""

    task: str = Field(..., description="Dependency spec name (e.g. 'pride-pppar').")
    paths: list[Path] = Field(
        default_factory=list, description="Local paths of all resolved products."
    )
    lockfile: DependencyLockFile | None = None

    model_config = {"arbitrary_types_allowed": True}


class DiscoveryEntry(BaseModel):
    """A single entry in a discovery report."""

    product: str
    center: str = ""
    quality: str = ""
    source: str = ""
    uri: str = ""


class DiscoveryReport(BaseModel):
    """Structured summary of available products for a date."""

    entries: list[DiscoveryEntry] = Field(default_factory=list)

    @property
    def products(self) -> list[str]:
        """Sorted list of unique product names in this report."""
        return sorted(set(e.product for e in self.entries))

    @property
    def centers(self) -> list[str]:
        """Sorted list of unique center identifiers in this report."""
        return sorted(set(e.center for e in self.entries if e.center))

    def filter(self, product: str | None = None, center: str | None = None) -> list[DiscoveryEntry]:
        """Filter entries by product name and/or center.

        Args:
            product: Product name filter.
            center: Center identifier filter.

        Returns:
            Matching :class:`DiscoveryEntry` instances.
        """
        out = self.entries
        if product:
            out = [e for e in out if e.product == product]
        if center:
            out = [e for e in out if e.center == center]
        return out


class MissingProductError(Exception):
    """Raised when a required product cannot be found during resolve()."""

    def __init__(self, missing: list[str], task: str = ""):
        """Initialise with the list of missing product names.

        Args:
            missing: Product names that could not be found.
            task: Optional task identifier for the error message.
        """
        self.missing = missing
        self.task = task
        products = ", ".join(missing)
        msg = (
            f"Missing required products for task {task!r}: {products}"
            if task
            else f"Missing required products: {products}"
        )
        super().__init__(msg)
