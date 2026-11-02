"""Server, ResourceSpec, SearchTarget — remote resource models (Layer 1)."""

from pathlib import Path

import yaml
from pydantic import BaseModel

from gnss_product_management.specifications.parameters.parameter import Parameter
from gnss_product_management.specifications.products.product import (
    PathTemplate,
    Product,
)
from gnss_product_management.utilities.helpers import _PassthroughDict


class Server(BaseModel):
    """A remote or local server endpoint.

    Attributes:
        id: Unique identifier for the server.
        hostname: Server hostname or URL.
        protocol: Protocol (``'ftp'``, ``'http'``, ``'https'``, etc.).
        auth_required: Whether authentication is needed.
        listing_url: Optional URL template for servers whose directory listing
            is exposed separately from their download root.  ``{directory}``
            is replaced with the URL-quoted directory being searched.
        description: Human-readable server description.
    """

    id: str
    hostname: str
    protocol: str | None = None
    auth_required: bool | None = False
    listing_url: str | None = None
    description: str | None = None


class ResourceProductSpec(BaseModel):
    """A product offering within a resource/center.

    Maps a catalog product to a server with parameter overrides.

    Attributes:
        id: Unique identifier for the product offering.
        server_id: Server that hosts this product.
        available: Whether the product is currently available.
        product_name: Catalog product name (e.g. ``'ORBIT'``).
        product_version: Version filter(s) or ``None`` for all.
        description: Human-readable description.
        parameters: Parameter overrides (values pinned by this center).
        directory: Directory template for this product.
        checksum: Expected ``sha256:<hex>`` of the served file, as
            downloaded (i.e. before any decompression).  Only meaningful
            for entries that resolve to exactly one file — static tables
            pinned to an immutable source.  When set, downloads and cache
            hits are validated against it.
    """

    id: str
    server_id: str
    available: bool = True
    product_name: str
    product_version: list[str] | str | None = None
    description: str | None = None
    parameters: list[Parameter]
    directory: PathTemplate
    checksum: str | None = None


class ResourceSpec(BaseModel):
    """Root resource specification for a data center.

    Attributes:
        id: Unique center identifier.
        name: Display name for the center.
        description: Human-readable description.
        website: Center website URL.
        servers: Server endpoints for this center.
        products: Product offerings hosted by this center.
    """

    id: str
    name: str
    description: str | None = None
    website: str | None = None
    servers: list[Server] = []
    products: list[ResourceProductSpec] = []

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ResourceSpec":
        """Load a resource specification from a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            A :class:`ResourceSpec` instance.
        """
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        return cls.model_validate(raw)


class SearchTarget(BaseModel):
    """A single concrete query target — one combination of parameter values.

    Attributes:
        product: The product being queried.
        server: The server endpoint to query.
        directory: Directory path template for the product.
        checksum: Expected ``sha256:<hex>`` of the served file, carried
            from the resource spec.  ``None`` when the source declares no
            checksum.
    """

    product: Product
    server: Server
    directory: PathTemplate
    checksum: str | None = None

    def narrow(self) -> "SearchTarget":
        """Substitute already-known parameter values into directory/filename patterns.

        Returns:
            ``self``, mutated in place.
        """
        to_update = {p.name: p for p in self.product.parameters if p.value is not None}
        format_dict = _PassthroughDict({k: p.value for k, p in to_update.items()})

        if self.product.filename:
            self.product = self.product.model_copy(
                deep=True,
                update={
                    "filename": PathTemplate(
                        pattern=self.product.filename.pattern.format_map(format_dict)
                    )
                },
            )
        self.directory = PathTemplate(pattern=self.directory.pattern.format_map(format_dict))

        return self
