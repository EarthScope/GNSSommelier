"""Default singleton instances for the GNSS PPP product environment.

Constructs pre-configured :data:`DefaultProductEnvironment` and
:data:`DefaultWorkSpace` from the bundled YAML specifications
shipped with the ``gnss-management-specs`` package.

Users who need a different spec set should build their own
:class:`ProductRegistry` via its ``add_*`` methods rather than
importing these defaults.
"""

from pathlib import Path

from gpm_specs.configs import (
    CENTERS_RESOURCE_DIR,
    FORMAT_SPEC_YAML,
    LOCAL_SPEC_DIR,
    META_SPEC_YAML,
    NETWORKS_RESOURCE_DIR,
    PRODUCT_SPEC_YAML,
)

from gnss_product_management.environments import ProductRegistry, WorkSpace
from gnss_product_management.environments.gnss_station_network import GNSSNetworkRegistry

# Pre-built environment with all bundled parameter, format, product, and center specs.
DefaultProductEnvironment = ProductRegistry()
DefaultProductEnvironment.add_parameter_spec(META_SPEC_YAML)
DefaultProductEnvironment.add_format_spec(FORMAT_SPEC_YAML)
DefaultProductEnvironment.add_product_spec(PRODUCT_SPEC_YAML)
for path in Path(CENTERS_RESOURCE_DIR).glob("*.yaml"):
    DefaultProductEnvironment.add_resource_spec(path)
DefaultProductEnvironment.build()

# Pre-built network registry with all bundled network configs.
DefaultNetworkRegistry = GNSSNetworkRegistry.from_config(NETWORKS_RESOURCE_DIR)
DefaultNetworkRegistry.bind(DefaultProductEnvironment)

# Register concrete protocol implementations.
from gnss_product_management.defaults.catalog_protocols import (  # noqa: E402
    GAProtocol,
    IGSProtocol,
    NOAACORSProtocol,
    RBMCProtocol,
)
from gnss_product_management.defaults.earthscope.earthscope import EarthScopeProtocol  # noqa: E402
from gnss_product_management.defaults.m3g.m3g_protocol import M3GNetworkProtocol  # noqa: E402

DefaultNetworkRegistry.register_protocol(NOAACORSProtocol())
DefaultNetworkRegistry.register_protocol(EarthScopeProtocol())
DefaultNetworkRegistry.register_protocol(GAProtocol())
DefaultNetworkRegistry.register_protocol(IGSProtocol())
DefaultNetworkRegistry.register_protocol(RBMCProtocol())

# Register M3G-backed protocols for all remaining networks without a dedicated protocol.
for _net_id in DefaultNetworkRegistry.network_ids:
    if _net_id not in DefaultNetworkRegistry._network_protocols:
        try:
            DefaultNetworkRegistry.register_protocol(M3GNetworkProtocol(_net_id))
        except (AssertionError, KeyError):
            pass

# Backward-compatible alias.
DefaultNetworkEnvironment = DefaultNetworkRegistry

# Workspace pre-loaded with local resource layout specs.
DefaultWorkSpace = WorkSpace()
for path in Path(LOCAL_SPEC_DIR).glob("*.yaml"):
    DefaultWorkSpace.add_resource_spec(path)
