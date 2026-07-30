"""ResourceCatalog — resolve a ResourceSpec against a ProductCatalog into queryable products."""

from itertools import product as iterproduct

from gnss_product_management.specifications.catalog import Catalog
from gnss_product_management.specifications.parameters.parameter import Parameter
from gnss_product_management.specifications.remote.resource import (
    ResourceSpec,
    SearchTarget,
    Server,
)


def _cartesian_product(
    param_groups: dict[str, list[Parameter]],
) -> list[list[Parameter]]:
    """Expand ``{name: [vals...]}`` into a list of parameter combinations.

    Args:
        param_groups: Mapping of parameter names to their possible values.

    Returns:
        A list of parameter lists, one per Cartesian combination.
    """
    names = list(param_groups.keys())
    if not names:
        return [[]]
    value_lists = [param_groups[n] for n in names]
    return [list(combo) for combo in iterproduct(*value_lists)]


def _merge_parameters(
    base_params: list[Parameter],
    overrides: list[Parameter],
) -> list[Parameter]:
    """Return base params with overrides applied by name.

    Args:
        base_params: Original parameters from the product.
        overrides: Parameter overrides from the resource spec.

    Returns:
        A list of merged :class:`Parameter` instances.
    """
    result = {p.name: p.model_copy(deep=True) for p in base_params}
    for override in overrides:
        if override.name in result:
            result[override.name] = result[override.name].model_copy(
                update=override.model_dump(exclude_none=True), deep=True
            )
        else:
            result[override.name] = override.model_copy(deep=True)
    return list(result.values())


class ResourceCatalog(Catalog):
    """Resolves a ResourceSpec against a ProductCatalog into queryable products.

    Attributes:
        id: Center identifier.
        name: Display name.
        description: Human-readable description.
        website: Center website URL.
        servers: Server endpoints for this center.
        queries: Expanded :class:`SearchTarget` objects.
    """

    id: str
    name: str
    description: str | None = None
    website: str | None = None
    servers: list[Server]
    queries: list[SearchTarget]

    @classmethod
    def build(cls, resource_spec: ResourceSpec, product_catalog) -> "ResourceCatalog":
        """Build concrete queries by expanding a ResourceSpec against a ProductCatalog.

        Args:
            resource_spec: Raw resource specification for a data center.
            product_catalog: Resolved product catalog.

        Returns:
            A :class:`ResourceCatalog` containing all expanded queries.
        """
        queries = []
        for rp_spec in resource_spec.products:
            if not rp_spec.available:
                continue

            version_catalog = product_catalog.products.get(rp_spec.product_name)
            if version_catalog is None:
                continue

            versions = rp_spec.product_version or list(version_catalog.versions.keys())
            if isinstance(versions, str):
                versions = [versions]

            param_groups: dict[str, list[Parameter]] = {}
            for p in rp_spec.parameters:
                param_groups.setdefault(p.name, []).append(p)

            combos = _cartesian_product(param_groups)

            server = next(s for s in resource_spec.servers if s.id == rp_spec.server_id)

            for ver_key in versions:
                variant_catalog = version_catalog.versions.get(ver_key)
                if variant_catalog is None:
                    continue
                for variant_name, base_product in variant_catalog.variants.items():
                    for combo in combos:
                        merged_params = _merge_parameters(base_product.parameters, combo)
                        pinned_product = base_product.model_copy(
                            update={
                                "parameters": merged_params,
                                "name": rp_spec.product_name,
                            },
                            deep=True,
                        )
                        queries.append(
                            SearchTarget(
                                product=pinned_product,
                                server=server,
                                directory=rp_spec.directory,
                                checksum=rp_spec.checksum,
                            ).narrow()
                        )

        return cls(
            id=resource_spec.id,
            name=resource_spec.name,
            description=resource_spec.description,
            website=resource_spec.website,
            servers=resource_spec.servers,
            queries=queries,
        )
