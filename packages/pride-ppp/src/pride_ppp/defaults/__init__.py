"""Bundled YAML config paths for the pride_ppp package.

Each constant resolves to an absolute ``Path`` pointing at a YAML file
(or directory) shipped inside the ``pride_ppp/configs/`` tree.  These
are consumed by ``PrideProcessor`` during construction to configure
the product environment, workspace, and dependency resolver.

Example::

    from pride_ppp.defaults import PRIDE_PPPAR_SPEC, PRIDE_DIR_SPEC
    print(PRIDE_PPPAR_SPEC)  # .../configs/dependencies/pride_pppar.yaml
"""

from pathlib import Path

_CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"

# Dependency spec: FIN → RTS → RAP → ULT cascade (default processing mode).
PRIDE_PPPAR_SPEC = _CONFIGS_DIR / "dependencies" / "pride_pppar.yaml"

# Dependency spec: FINAL-only products (TTT restricted to [FIN]).
PRIDE_PPPAR_FINAL_SPEC = _CONFIGS_DIR / "dependencies" / "pride_pppar_final.yaml"

# Local workspace spec mapping logical sink "pride" to a physical directory.
PRIDE_DIR_SPEC = _CONFIGS_DIR / "local" / "pride_config.yaml"

# Local workspace spec for an existing PRIDE-PPPAR installation directory.
PRIDE_INSTALL_SPEC = _CONFIGS_DIR / "local" / "pride_install_config.yaml"

# Product spec defining PRIDE-specific products (tables, ocean models, etc.).
PRIDE_PRODUCT_SPEC = _CONFIGS_DIR / "products" / "pride_product_spec.yaml"

# Directory of per-analysis-centre resource YAML files.
PRIDE_CENTERS_DIR = _CONFIGS_DIR / "centers"

__all__ = [
    "PRIDE_PPPAR_SPEC",
    "PRIDE_PPPAR_FINAL_SPEC",
    "PRIDE_DIR_SPEC",
    "PRIDE_INSTALL_SPEC",
    "PRIDE_PRODUCT_SPEC",
    "PRIDE_CENTERS_DIR",
]
