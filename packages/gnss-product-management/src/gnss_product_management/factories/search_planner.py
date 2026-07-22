"""SearchPlanner — lazy narrowing query builder."""

import datetime
import logging
from typing import Literal

from gnss_product_management.environments import ProductRegistry, WorkSpace
from gnss_product_management.environments.gnss_station_network import (
    GNSSNetworkRegistry,
    GNSSStation,
)
from gnss_product_management.factories.protocols import QueryPlanner
from gnss_product_management.specifications.parameters.parameter import Parameter
from gnss_product_management.specifications.products.product import (
    PathTemplate,
    Product,
    VariantCatalog,
    VersionCatalog,
)
from gnss_product_management.specifications.remote.resource import SearchTarget
from gnss_product_management.utilities.helpers import _listify, expand_dict_combinations

logger = logging.getLogger(__name__)

# Maps the short variant codes used in the public API to the variant key
# stored in the ProductCatalog (sourced from the format spec YAML).
_RINEX_VARIANT_NAMES: dict[str, str] = {
    "OBS": "observation",
    "NAV": "navigation",
    "MET": "meteorological",
}


class SearchPlanner:
    """Lazy search planner — narrows parameter ranges, resolves on demand.

    Uses ``ProductRegistry`` for remote resource catalogs,
    ``WorkSpace`` for local resource resolution,
    ``ProductCatalog`` (nested version→variant→Product hierarchy),
    and ``ParameterCatalog`` for fallback regex patterns and computed
    date-field resolution.

    Attributes:
        _env: The product registry backing this planner.
        _workspace: Workspace with registered local resources.

    Usage::

        sp = SearchPlanner(
            product_registry=registry,
            workspace=workspace,
        )

        results = sp.get(
            datetime.date(2024, 1, 1),
            product={"name": "ORBIT"},
            parameters={"AAA": ["WUM", "COD"]},
        )
    """

    def __init__(
        self,
        product_registry: ProductRegistry,
        workspace: WorkSpace,
        gnss_network_registry: GNSSNetworkRegistry | None = None,
    ):
        """Initialise the search planner.

        Args:
            product_registry: Built :class:`ProductRegistry` with
                catalogs and remote resource catalogs ready.
            workspace: :class:`WorkSpace` with registered local resources.
            gnss_network_registry: Optional network registry for station queries.
        """
        self._product_registry: ProductRegistry = product_registry
        self._gnss_network_registry = gnss_network_registry
        self._workspace: WorkSpace = workspace
        self._workspace.bind(product_registry)
        if gnss_network_registry is not None:
            gnss_network_registry.bind(product_registry)

    def get_product_templates(
        self,
        product_name_query: str,
        product_version_query: list[str] | str,
        product_variant_query: list[str] | str,
    ) -> list[Product]:
        """Get product templates matching the query product spec and parameter constraints.

        Args:
            product_name: Name of the product.
            versions: List of versions of the product.
            variants: List of variants of the product.
        Returns:
            A list of :class:`Product` templates matching the query spec.
        Raises:
            ValueError: If the product, version, or variant is not found.
        """
        product_version_query = _listify(product_version_query)
        product_variant_query = _listify(product_variant_query)
        product_templates = []
        product_version_catalog: VersionCatalog | None = (
            self._product_registry._product_catalog.products.get(product_name_query)
        )
        if product_version_catalog is None:
            raise ValueError(f"Product {product_name_query!r} not found in ProductCatalog")
        versions = product_version_query or list(product_version_catalog.versions.keys())
        for version in versions:
            variant_cat: VariantCatalog | None = product_version_catalog.versions.get(version)
            if variant_cat is None:
                raise ValueError(
                    f"Version {version!r} not found for product {product_name_query!r}"
                )
            variants = product_variant_query or list(variant_cat.variants.keys())
            for variant in variants:
                if variant not in variant_cat.variants:
                    raise ValueError(
                        f"Variant {variant!r} not found for product {product_name_query!r} version {version!r}"
                    )
                product_templates.append(variant_cat.variants[variant].model_copy(deep=True))
        return product_templates

    def update_templates_with_date_fields(
        self,
        templates: list[Product],
        date: datetime.datetime,
    ) -> list[Product]:
        """Update product templates with date-resolved parameter values.

        Args:
            templates: List of product templates to update.
            date: Target date for resolving computed metadata fields.

        Returns:
            List of updated product templates with date-resolved parameters.
        """
        for template in templates:
            update_date_params = self._product_registry._parameter_catalog.resolve_params(
                template.parameters, date
            )
            template.parameters = update_date_params

    def narrow_parameters(
        self,
        templates: list[Product],
        parameter_constraints: dict[str, str | list[str]],
    ) -> list[Product]:
        """Narrow product templates by substituting parameter constraints.

        Constraints whose name is absent from a template are appended as new
        parameters rather than ignored — station queries rely on this to pin
        ``SSSS``/``CCC`` on RINEX templates that do not declare them.

        Args:
            templates: List of product templates to narrow.
            parameter_constraints: User constraints on metadata fields.  Unset
                fields remain as wildcard regex patterns.

        Returns:
            List of narrowed product templates with substituted parameter values.
        """
        narrowed_templates = []
        for name, values in parameter_constraints.items():
            parameter_constraints[name] = _listify(values)

        if parameter_constraints:
            parameter_combinations = expand_dict_combinations(parameter_constraints)
            for template in templates:
                for combo in parameter_combinations:
                    updated = template.model_copy(deep=True)
                    for k, v in combo.items():
                        param_index = next(
                            (i for i, p in enumerate(updated.parameters) if p.name == k),
                            None,
                        )
                        if param_index is not None:
                            updated.parameters[param_index].value = v
                        else:
                            updated.parameters.append(
                                Parameter(
                                    name=k,
                                    value=v,
                                    pattern=None,
                                    description=None,
                                    derivation=None,
                                    compute=None,
                                )
                            )
                    if updated.filename is not None:
                        updated.filename.derive(updated.parameters)
                    narrowed_templates.append(updated)
        else:
            narrowed_templates = templates

        return narrowed_templates

    def get(
        self,
        date: datetime.datetime,
        product: dict[str, str | list[str]],
        parameters: dict[str, str | list[str]] | None = None,
        local_resources: list[str] | None = None,
        remote_resources: list[str] | None = None,
    ) -> list[SearchTarget]:
        """Narrow parameter ranges and return searchable resources.

        Args:
            date: Target date for computed metadata fields.
            product_name: Name of the product.
            version: Optional version of the product.
            variant: Optional variant of the product.
            parameters: User constraints on metadata fields.  Unset
                fields remain as wildcard regex patterns.
            local_resources: If given, restrict to these local collection IDs.
            remote_resources: If given, restrict to these remote center IDs.

        Returns:
            A list of :class:`SearchTarget` objects.

        Raises:
            ValueError: If the product, version, or variant is not found.
        """
        parameters = parameters or {}
        local_resources = _listify(local_resources)
        remote_resources = _listify(remote_resources)
        out: list[SearchTarget] = []

        # 1. Get product templates matching the query product spec
        product_templates: list[Product] = []

        product_name_query = product.get("name")
        product_version_query = _listify(product.get("version"))
        product_variant_query = _listify(product.get("variant"))

        product_templates = self.get_product_templates(
            product_name_query=product_name_query,
            product_version_query=product_version_query,
            product_variant_query=product_variant_query,
        )

        # 2. Resolve date fields via ParameterCatalog
        self.update_templates_with_date_fields(product_templates, date)

        # 3. Narrow parameter ranges by query constraints
        product_templates_1: list[Product] = self.narrow_parameters(product_templates, parameters)

        # 5.1 Local resources
        local_out = self.build_queries_from_planner(
            templates=product_templates_1,
            date=date,
            query_planner=self._workspace,
            resource_selection=local_resources,
        )
        out.extend(local_out)

        # 5.2 Remote resources
        remote_out = self.build_queries_from_planner(
            templates=product_templates_1,
            date=date,
            query_planner=self._product_registry,
            resource_selection=remote_resources,
        )
        if not remote_out:
            logger.debug(
                "No remote search targets found for product query %s on date %s.",
                product,
                date.date(),
            )
        out.extend(remote_out)

        # 6. Replace unresolved placeholders with regex patterns
        for rq in out:
            for param in rq.product.parameters:
                if param.value is None:
                    param.value = param.pattern
            if rq.product.filename is not None:
                rq.product.filename.derive(rq.product.parameters)

        return out

    @staticmethod
    def build_queries_from_planner(
        templates: list[Product],
        date: datetime.datetime,
        query_planner: QueryPlanner,
        resource_selection: list[str] | None = None,
    ) -> list[SearchTarget]:
        """Build search queries from a given planner and resource selection.

        Args:
            templates: List of product templates to build queries from.
            date: Target date for resolving computed directory fields.
            query_planner: A :class:`WorkSpace` (local) or
                :class:`ProductRegistry` (remote) with ``resource_ids``
                and ``source_product`` interface.
            resource_selection: Optional list of resource IDs to restrict to.

        Returns:
            A list of :class:`SearchTarget` objects built from the planner.
        """
        out = []
        for template in templates:
            for resource_id in query_planner.resource_ids:
                if resource_selection and resource_id not in resource_selection:
                    continue
                try:
                    resolved_queries: list[SearchTarget] = query_planner.source_product(
                        template, resource_id
                    )
                except KeyError as e:
                    logger.debug(
                        "KeyError resolving product %s on resource %s: %s",
                        template.name,
                        resource_id,
                        e,
                    )
                    continue
                for rq in resolved_queries:
                    if query_planner._parameter_catalog is not None:
                        resolved_dir: str = query_planner._parameter_catalog.interpolate(
                            rq.directory.pattern, date, computed_only=True
                        )
                        rq.directory = PathTemplate(pattern=resolved_dir)
                    out.append(rq)
        return out

    def get_stations(
        self,
        date: datetime.datetime,
        version: Literal["2", "3", "4"],
        stations: list[GNSSStation] | None = None,
        station_ids: list[str] | str | None = None,
        variant: Literal["OBS", "NAV", "MET"] = "OBS",
        network_ids: list[str] | str | None = None,
        local_resource_ids: list[str] | str | None = None,
        country_codes: list[str] | str | None = None,
    ) -> list[SearchTarget]:
        """Build per-station RINEX search targets for the given date and RINEX version.

        Searches both local workspace resources and registered GNSS networks.
        Station codes are sourced from *stations* (resolved :class:`GNSSStation`
        objects) and/or explicit *station_ids*.  Filename patterns and directory
        templates come from the product catalog and network/workspace configs —
        no RINEX naming convention is hardcoded here.

        Args:
            date: Target date (timezone-aware).
            version: RINEX version — ``"2"``, ``"3"``, or ``"4"``.
            stations: Pre-resolved station objects; ``site_code`` is used as SSSS.
            station_ids: Explicit 4-char station codes to include.
            variant: RINEX file type — ``"OBS"``, ``"NAV"``, or ``"MET"``.
                Defaults to ``"OBS"``.
            network_ids: Restrict GNSS network search to these network IDs.
                ``None`` searches all registered networks.
            local_resource_ids: Restrict local search to these workspace resource
                IDs.  ``None`` searches all registered local resources.
            country_codes: Pin the ``CCC`` parameter (3-char data center/agency).

        Returns:
            A list of :class:`SearchTarget` objects — one per station × resource
            × matching product spec combination.

        Raises:
            ValueError: If *version* or *variant* is not recognised.
        """
        if version not in {"2", "3", "4"}:
            raise ValueError(f"Unsupported RINEX version: {version!r}")
        if variant not in {"OBS", "NAV", "MET"}:
            raise ValueError(f"Unsupported RINEX variant: {variant!r}")

        catalog_variant = _RINEX_VARIANT_NAMES[variant]
        product_templates = self.get_product_templates(
            product_name_query=f"RINEX_{variant}",
            product_version_query=_listify(version),
            product_variant_query=[catalog_variant],
        )
        self.update_templates_with_date_fields(product_templates, date)

        # Pin version and collect station codes from both sources.
        parameter_constraints: dict[str, str | list[str]] = {"V": version}
        codes: list[str] = []
        if stations:
            codes.extend(s.site_code for s in stations)
        if station_ids:
            codes.extend(_listify(station_ids))
        if codes:
            parameter_constraints["SSSS"] = codes
        if country_codes:
            parameter_constraints["CCC"] = _listify(country_codes)

        narrowed = self.narrow_parameters(product_templates, parameter_constraints)

        out: list[SearchTarget] = []

        # Local workspace resources.
        local_out = self.build_queries_from_planner(
            templates=narrowed,
            date=date,
            query_planner=self._workspace,
            resource_selection=_listify(local_resource_ids),
        )
        out.extend(local_out)

        # GNSS network resources.
        if self._gnss_network_registry is not None:
            network_out = self.build_queries_from_planner(
                templates=narrowed,
                date=date,
                query_planner=self._gnss_network_registry,
                resource_selection=_listify(network_ids),
            )
            # Build server→network lookup from the registry so the data-
            # center filter only applies within the same network.
            server_to_network: dict[str, str] = {}
            for nid in self._gnss_network_registry.resource_ids:
                cfg = self._gnss_network_registry.config_for(nid)
                for srv in cfg.servers:
                    server_to_network[srv.id] = nid
            network_out = self._filter_by_data_center(
                network_out,
                stations or [],
                server_to_network,
            )
            out.extend(network_out)

        # Replace any unresolved placeholders with their regex patterns.
        for rq in out:
            for param in rq.product.parameters:
                if param.value is None:
                    param.value = param.pattern
            if rq.product.filename is not None:
                rq.product.filename.derive(rq.product.parameters)

        return out

    @staticmethod
    def _filter_by_data_center(
        targets: list[SearchTarget],
        stations: list[GNSSStation],
        server_to_network: dict[str, str] | None = None,
    ) -> list[SearchTarget]:
        """Route each station's targets to its preferred data-center server.

        For every station that carries a ``data_center`` value, only targets
        whose ``server.id`` matches that value are kept — but only when the
        target's server belongs to the **same network** as the station.
        Targets from other networks are always retained.

        If no configured server matches within the station's own network
        (e.g. the station's data center is JPL, PGC, GA, or SIO — none of
        which have their own server entry), *all* targets for that station
        within its network are retained so the WormHole can fall back to
        whichever server actually has the file (typically CDDIS).

        Stations without a ``data_center`` or ``network_id`` are unaffected.

        Args:
            targets: Network search targets to filter.
            stations: Station metadata returned by the spatial query.
            server_to_network: Optional mapping of server_id → network_id.
                When provided, the data-center filter is scoped to targets
                whose server belongs to the same network as the station.

        Returns:
            Filtered list of search targets.
        """
        # Build site_code → (preferred_server_id, network_id) mapping.
        site_to_dc: dict[str, str] = {
            s.site_code: s.data_center for s in stations if s.data_center is not None
        }
        site_to_network: dict[str, str] = {
            s.site_code: s.network_id for s in stations if s.network_id is not None
        }
        if not site_to_dc:
            return targets

        # Per-network available server IDs for fallback detection.
        network_server_ids: dict[str, set[str]] = {}
        for t in targets:
            nid = server_to_network.get(t.server.id) if server_to_network else None
            if nid is not None:
                network_server_ids.setdefault(nid, set()).add(t.server.id)

        # Flat fallback when no server→network mapping is provided.
        all_server_ids: set[str] = {t.server.id for t in targets}

        filtered: list[SearchTarget] = []
        for target in targets:
            ssss = next(
                (p.value for p in target.product.parameters if p.name == "SSSS"),
                None,
            )
            station_nid = site_to_network.get(ssss)  # type: ignore[arg-type]
            target_nid = server_to_network.get(target.server.id) if server_to_network else None

            # Cross-network check first: always drop targets whose server
            # belongs to a different network than the station.  This prevents
            # ERT/CORS stations from generating spurious IGS targets (and vice
            # versa) even when the station has no data_center annotation.
            if station_nid and target_nid and station_nid != target_nid:
                continue

            dc = site_to_dc.get(ssss)  # type: ignore[arg-type]
            if dc is None:
                # Station has no data_center annotation — keep (same network or
                # network unknown).
                filtered.append(target)
                continue

            # Within the correct network: apply data-center routing.
            avail = (
                network_server_ids.get(station_nid, all_server_ids)
                if station_nid
                else all_server_ids
            )
            if dc not in avail:
                # Data center not configured — keep all same-network targets as
                # fallback (e.g. JPL/PGC/GA/SIO stations fall back to CDDIS).
                filtered.append(target)
            elif target.server.id == dc:
                # Matches preferred server — keep.
                filtered.append(target)
            # else: wrong server for this station within its own network — drop.
        return filtered
