"""pride_ppp — PRIDE PPP-AR integration package.

Provides a concurrent-safe ``PrideProcessor`` that resolves GNSS products,
runs the pdp3 binary, and returns structured ``ProcessingResult`` objects
with lazy DataFrame access for kinematic positions and residuals.

Lower-level utilities (CLI config, config-file I/O, output parsing, RINEX
helpers) are re-exported for advanced use cases.

Example
-------
>>> from pathlib import Path
>>> from pride_ppp import PrideProcessor, ProcessingMode
>>>
>>> proc = PrideProcessor(
...     pride_dir=Path("/data/pride"),
...     output_dir=Path("/data/output"),
...     mode=ProcessingMode.FINAL,
... )
>>> result = proc.process(Path("/data/rinex/NCC12540.25o"))
>>> if result.success:
...     df = result.positions()
"""

from .factories.output import (
    get_wrms_from_res,
    kin_to_kin_position_df,
    plot_kin_results_wrms,
    read_kin_data,
    validate_kin_file,
)
from .factories.processor import (
    MissingProductsError,
    PrideProcessor,
    ProcessingMode,
    ProcessingResult,
)
from .factories.rinex import merge_broadcast_files, rinex_get_time_range
from .specifications.cli import PrideCLIConfig
from .specifications.config import PRIDEPPPFileConfig, SatelliteProducts
from .specifications.output import PridePPP

__all__ = [
    # Primary API
    "PrideProcessor",
    "ProcessingMode",
    "ProcessingResult",
    "MissingProductsError",
    # CLI / config
    "PrideCLIConfig",
    "PRIDEPPPFileConfig",
    "SatelliteProducts",
    # Output parsing
    "PridePPP",
    "kin_to_kin_position_df",
    "validate_kin_file",
    "get_wrms_from_res",
    "plot_kin_results_wrms",
    "read_kin_data",
    # RINEX utilities
    "merge_broadcast_files",
    "rinex_get_time_range",
]
