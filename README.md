# GNSSommelier

![GNSSommelier](docs/image.png)

Automated retrieval and management of [IGS](https://igs.org/) analysis center
products for Precise Point Positioning. Provides a Python library for
product discovery, dependency resolution, and download across 18 configured
IGS analysis centers, plus a command-line tool (`gnssommelier`) for interactive
workflows.

## Contents

- [Motivation](#motivation)
- [Packages](#packages)
- [Documentation](#documentation)
- [Supported products](#supported-products)
- [Supported analysis centers & servers](#supported-analysis-centers--servers)
- [Quick start](#quick-start)
- [Examples](#examples)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [References](#references)
- [Contributing](#contributing)
- [License](#license)

## Motivation

Running PPP or PPP-AR requires a constellation of auxiliary products — precise
orbits (SP3), satellite clocks (CLK), code/phase biases (BIA), Earth rotation
parameters (ERP), ionosphere maps (GIM/IONEX), troposphere models, and antenna
calibrations (ATX). These files are scattered across FTP/FTPS/HTTP servers
maintained by different IGS analysis centers, each with its own directory
layout, naming convention, and update cadence.

**GNSSommelier** eliminates the manual bookkeeping. Given a date and a
processing task definition, it resolves every required product across all
registered centers, downloads and decompresses the files into a structured
local workspace, and tracks what was fetched in reproducible lock files. For
PRIDE-PPPAR users, a second package wraps `pdp3` in a Python pipeline that
handles product resolution, config-file generation, and output parsing in a
single call.

## Packages

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
containing four packages:

| Package | Purpose |
|---|---|
| [`gpm-specs`](packages/gpm-specs/) | Pluggable YAML specification data for GNSS products, centers, formats, and storage layouts |
| [`gnss-product-management`](packages/gnss-product-management/) | YAML-driven product discovery, query expansion, dependency resolution, and download from IGS analysis centers |
| [`gpm-cli`](packages/gpm-cli/) | Command-line tool (`gnssommelier`) for search, download, and configuration |
| [`pride-ppp`](packages/pride-ppp/) | Concurrent-safe PRIDE-PPPAR integration — RINEX in, kinematic positions out |

### gpm-specs

A data-only package shipping the bundled YAML specifications that describe
GNSS product catalogs, analysis center endpoints, file-naming formats,
dependency graphs, and local storage layouts. Separated from the core library
so that future specification sets (e.g. ocean-acoustic, seismic) can be added
as independent packages without modifying `gnss-product-management`.

### gnss-product-management

The core library. A five-layer architecture (Configuration → Specification →
Catalog → Orchestration → Interface) keeps concerns separated so adding a new
center or product type requires only a new YAML file. The `defaults` module
wires the bundled `gpm-specs` into pre-built singletons
(`DefaultProductEnvironment`, `DefaultWorkSpace`); users who need a different
spec set can build their own `ProductEnvironment` via its `add_*` methods.

### gpm-cli

A `typer`-based CLI installed as the `gnssommelier` entry point. Provides subcommands
for searching products across configured centers, downloading resolved
dependencies, and managing the user config file (`~/.config/gnssommelier/config.toml`).

### pride-ppp

A processing facade built on top of `gnss-product-management`. Resolves all
dependencies for a PRIDE-PPPAR run, writes the `pdp3` config file, executes
the binary in an isolated temp directory, and returns structured
`ProcessingResult` objects with lazy DataFrame access to `.kin` positions and
`.res` residuals.

## Documentation

See [`docs/INDEX.md`](docs/INDEX.md) for a full table of contents. Key docs:

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Five-layer design of `gnss-product-management` |
| [PPP Products](docs/ppp-products.md) | GNSS product naming conventions and file formats |
| [Config Reference](docs/config-reference.md) | Guide to the YAML configuration system |

## Supported products

Product types currently defined in the bundled specifications:

| Product | Format | Description |
|---|---|---|
| **Orbit** | SP3 | Precise satellite ephemerides (15 min) |
| **Clock** | CLK | Satellite & station clock corrections (30 s / 5 min) |
| **Bias** | BIA | OSB/FCB code and phase biases — required for PPP-AR integer ambiguity fixing |
| **ERP** | ERP | Polar motion (x_p, y_p), UT1-UTC, LOD — ITRF↔ICRF transformation |
| **GIM** | IONEX | Global ionosphere TEC maps |
| **Navigation** | RINEX NAV | Broadcast ephemerides (merged BRDC) |
| **ATX** | ANTEX | Satellite & receiver antenna phase center calibrations |
| **OBX** | OBX | Satellite attitude quaternions |
| **Troposphere** | VMF1/VMF3 | Vienna Mapping Functions (gridded) |
| **Orography** | GRID | Orography grids for VMF |
| **Leap seconds** | — | IERS leap second table |
| **Sat parameters** | — | Satellite metadata (mass, geometry, SRP) |

## Supported analysis centers & servers

All 18 configured centers. See [docs/data-centers.md](docs/data-centers.md) for full details.

| Center | Institution | Server | Protocol |
|---|---|---|---|
| **BKG** | [Federal Agency for Cartography and Geodesy](https://igs.bkg.bund.de/) | `igs.bkg.bund.de` | HTTPS |
| **CAS** | [Chinese Academy of Sciences (GIPP)](http://www.gipp.org.cn/) | `ftp.gipp.org.cn` | FTP |
| **CDDIS** | [NASA GSFC](https://cddis.nasa.gov/) | `gdc.cddis.eosdis.nasa.gov` | FTPS |
| **COD** | [AIUB, Univ. of Bern](https://www.aiub.unibe.ch/research/gnss/) | `ftp.aiub.unibe.ch` | FTP |
| **ESA** | [ESA/ESOC](https://navigation.esa.int/) | `gssc.esa.int` | FTP |
| **EUREF** | [EUREF Permanent GNSS Network](https://epncb.oma.be/) | `epncb.oma.be` | HTTPS |
| **GFZ** | [GFZ Potsdam](https://www.gfz-potsdam.de/) | `isdc-data.gfz.de` | SFTP |
| **GRGS** | [CNES/CLS](https://igsac-cnes.cls.fr/) | `ftpsedr.cls.fr` | FTP |
| **IGS** | [IGS combined products](https://igs.org/) | `igs.ign.fr` / `files.igs.org` | FTP / HTTPS |
| **JPL** | [NASA JPL](https://sideshow.jpl.nasa.gov/) | `sideshow.jpl.nasa.gov` | HTTPS |
| **KASI** | [Korea Astronomy and Space Science Institute](https://gnss.kasi.re.kr/) | `nfs.kasi.re.kr` | FTP |
| **NGII** | [National Geographic Information Institute, Korea](https://www.ngii.go.kr/) | `nfs.kgps.go.kr` | FTP |
| **NRCan** | [Natural Resources Canada (CSRS)](https://www.nrcan.gc.ca/home) | `ftp.nrcan.gc.ca` | FTP |
| **SIO** | [Scripps Institution of Oceanography / SOPAC](https://sopac-csrc.ucsd.edu/) | `garner.ucsd.edu` | FTP (defunct) |
| **TUG** | [Graz University of Technology (ITSG)](https://www.tugraz.at/institute/ifg/) | via CDDIS | FTPS |
| **VMF** | [TU Wien](https://vmf.geo.tuwien.ac.at/) | `vmf.geo.tuwien.ac.at` | HTTPS |
| **WUM** | [Wuhan University](http://www.igs.gnsswhu.cn/) | `igs.gnsswhu.cn` | FTP |

> **CDDIS authentication:** CDDIS FTPS requires an EarthData account. Add
> `machine cddis.nasa.gov login <user> password <pass>` to `~/.netrc`.
> Register at <https://cddis.nasa.gov/Data_and_Derived_Products/CreateAccount.html>.
>
> **SIO / NGII:** These centers have `available: false` on all products —
> SIO's FTP is decommissioned; NGII is only reachable from within Korea.

## Quick start

```bash
# Clone and install
git clone https://github.com/EarthScope/GNSSommelier.git
cd GNSSommelier
uv sync --all-packages
```

### Use the CLI

```bash
# Install the CLI tool
uv tool install packages/gpm-cli

# Search for final orbit products from COD and ESA
gnssommelier search ORBIT --date 2025-01-02 --sources COD --sources ESA --where TTT=FIN

# Show / edit configuration
gnssommelier config show
gnssommelier config set base-dir /data/gnss-products
```

### Search for products across all centers

```python
from datetime import datetime, timezone
from gnss_product_management import GNSSClient

client = GNSSClient.from_defaults()
date = datetime(2025, 1, 2, tzinfo=timezone.utc)

results = (
    client.query()
    .for_product("ORBIT")
    .on(date)
    .where(TTT="FIN")
    .sources("COD", "ESA")
    .search()
)
for r in results:
    print(r.hostname, r.filename)
```

### Resolve & download all dependencies

```python
from datetime import datetime, timezone
from pathlib import Path
from gnss_product_management import GNSSClient

client = GNSSClient.from_defaults(base_dir=Path("/data/gnss-products"))
date = datetime(2025, 1, 2, tzinfo=timezone.utc)

resolution, lockfile_path = client.resolve_dependencies(
    "path/to/your/dependency_spec.yaml", date, sink_id="local"
)
print(resolution.table())
```

### Run PRIDE-PPPAR processing

```python
from pathlib import Path
from pride_ppp import PrideProcessor

processor = PrideProcessor(
    pride_dir=Path("/data/pride"),
    output_dir=Path("/data/output"),
)
result = processor.process(Path("SITE00USA_R_20250010000_01D_30S_MO.rnx"))

if result.success:
    print(result.positions().head())
```

> **Prerequisite:** The `pdp3` binary from
> [PRIDE-PPPAR](https://github.com/PrideLab/PRIDE-PPPAR) must be on `$PATH`.

## Examples

Runnable scripts in each package's `examples/` directory:

| Package | Script | Description |
|---|---|---|
| gnss-product-management | [search_products.py](packages/gnss-product-management/examples/search_products.py) | Search all centers for a product type on a given date |
| gnss-product-management | [download_from_center.py](packages/gnss-product-management/examples/download_from_center.py) | Download a specific product from a single center |
| pride-ppp | [process_rinex.py](packages/pride-ppp/examples/process_rinex.py) | Process one RINEX file end-to-end |
| pride-ppp | [batch_process.py](packages/pride-ppp/examples/batch_process.py) | Batch-process multiple RINEX files |

## Project structure

```
GNSSommelier/
├── pyproject.toml                        # Workspace root
├── docs/                                 # Architecture & reference docs
├── packages/
│   ├── gpm-specs/            # Pluggable YAML specification data
│   │   └── src/gpm_specs/
│   │       └── configs/                  # YAML specs (centers, products, formats, etc.)
│   │           ├── centers/              # Analysis center endpoint definitions (18 centers)
│   │           ├── local/                # Local storage layout specs
│   │           ├── meta/                 # Parameter & metadata specs
│   │           ├── products/             # Product catalog specs
│   │           └── query/                # Query template specs
│   ├── gnss-product-management/          # Product discovery & download
│   │   ├── src/gnss_product_management/
│   │   │   ├── defaults/           # Wires gpm-specs into singletons
│   │   │   ├── environments/       # ProductRegistry, WorkSpace
│   │   │   ├── factories/          # SearchPlanner, WormHole, ConnectionPoolFactory, pipelines
│   │   │   ├── specifications/     # Pydantic models (Parameter, FormatSpec, ProductSpec)
│   │   │   ├── lockfile/           # LockfileManager, DependencyLockFile, operations
│   │   │   └── utilities/          # Date math, decompression, path helpers
│   │   └── test/
│   ├──gpm-cli/                 # CLI tool
│   │   └── src/gpm_cli/
│   │       ├── app.py                    # Entry point — `gnssommelier` command
│   │       ├── cmd_config.py             # `gnss config` subcommands
│   │       ├── cmd_download.py           # `gnss download` subcommand
│   │       ├── cmd_probe.py              # `gnss probe` subcommand
│   │       ├── cmd_search.py             # `gnss search` subcommand
│   │       └── config.py                 # UserConfig / ConfigLoader
│   └── pride-ppp/                        # PRIDE-PPPAR integration
│       └── src/pride_ppp/
│           ├── factories/
│           │   ├── processor.py          # PrideProcessor — main entry point
│           │   ├── output.py             # .kin/.res file parsing
│           │   └── rinex.py              # RINEX utilities
│           └── specifications/
│               ├── cli.py                # pdp3 command-line builder
│               ├── config.py             # PRIDE config-file I/O
│               └── output.py            # Pydantic models for .kin records
```

## Requirements

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- `gfortran` + `gcc` + `make` if building PRIDE-PPPAR from source

## References

- [International GNSS Service — Products](https://igs.org/products/)
- [IGS Product Access](https://igs.org/products-access/)
- [PRIDE-PPPAR (Wuhan University)](https://pride.whu.edu.cn/pppar/)
- [IGS Long Product Filenames](https://igs.org/formats-and-standards/)
- [Vienna Mapping Functions](https://vmf.geo.tuwien.ac.at/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for step-by-step guides covering the
three most common spec extensions:

- Adding a new analysis center (`configs/centers/`)
- Adding a new product type (`product_spec.yaml` + `format_spec.yaml`)
- Adding a new metadata parameter (`meta_spec.yaml`)

## License

See [LICENSE](LICENSE) for details.
