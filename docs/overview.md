# Overview

GNSSommelier automates the retrieval of IGS analysis center products required
for Precise Point Positioning. Given a date and a product dependency
specification, it resolves every required file across all registered centers,
downloads and decompresses them into a structured local workspace, and records
provenance in lock files. For PRIDE-PPPAR users a companion package
(`pride-ppp`) wraps product resolution, `pdp3` config generation, and output
parsing into a single call.

---

## If you work with GNSS products

The query engine speaks IGS parameter codes directly. `TTT` is the solution
timeliness code — `FIN` (final, available ≥13 days after observation),
`RAP` (rapid, ≤17 hours), `ULT` (ultra-rapid, ≤3 hours). `AAA` is the
analysis center code.

```python
from datetime import datetime, timezone
from gnss_product_management import GNSSClient

client = GNSSClient.from_defaults()
date = datetime(2025, 1, 15, tzinfo=timezone.utc)

# Find all final SP3 orbits from COD and WUM for 2025-015
results = (
    client.query()
    .for_product("ORBIT")
    .on(date)
    .where(TTT="FIN")
    .sources("COD", "WUM", "GFZ")
    .prefer(TTT=["FIN", "RAP", "ULT"], AAA=["WUM", "COD", "GFZ"])
    .search()
)
for r in results:
    print(r.center, r.quality, r.filename)
    # COD  FIN  COD0OPSFIN_2025015000_01D_05M_ORB.SP3
    # WUM  FIN  WUM0OPSFIN_2025015000_01D_05M_ORB.SP3
```

Products are named using the [IGS long filename
convention](https://igs.org/formats-and-standards/):
`AC0TYPE_YYYYDDDHHMM_LEN_SMP_CNT.FMT`. The parameter catalog maps `YYYY`,
`DDD`, `GPSWEEK`, and related fields automatically from the query date —
you only need to specify the dimensions you want to constrain.

For full dependency resolution (orbit + clock + bias + ERP + tables in one
call), see [Dependency resolution](#dependency-resolution) below.

---

## If you are building a processing pipeline

`GNSSClient` is stateless after construction and safe to reuse across calls.
`max_connections` controls the per-host FTP/HTTPS connection pool — tune it
against the rate limits of the centers you query (CDDIS enforces strict limits;
most FTP centers tolerate 4–8 connections).

```python
client = GNSSClient.from_defaults(
    base_dir="s3://my-bucket/gnss-products",   # S3 workspace
    max_connections=6,
)
```

Cloud paths (`s3://`, `gs://`, `az://`) work identically to local paths
throughout — search, download, and lockfile I/O all route through
[cloudpathlib](https://cloudpathlib.drivendata.org/). Multiple workers
sharing the same S3 prefix coordinate via lock files: a worker that finds an
existing `DependencyLockFile` for `(package, task, date)` returns immediately.

For date-range searches the query builder parallelises internally:

```python
results = (
    client.query()
    .for_product("CLOCK")
    .on_range(start_date, end_date)   # parallel across dates, up to 8 workers
    .where(TTT="FIN")
    .search()
)
```

See [Architecture](#architecture) for the connection pool and pipeline
internals, and [Cloud workspace](#cloud-workspace) for S3 setup details.

---

## If you are processing RINEX with PRIDE-PPPAR

`PrideProcessor` is the single entry point. It owns product resolution, config
generation, and `pdp3` invocation. Construct it once, call `process_batch()`
for a full station-year.

```python
from pride_ppp import PrideProcessor, ProcessingMode
from pathlib import Path

processor = PrideProcessor(
    pride_dir=Path("/data/pride"),        # products + working dirs land here
    output_dir=Path("/data/output"),      # .kin and .res files land here
    mode=ProcessingMode.FINAL,            # only accept FIN products
)

rinex_files = sorted(Path("/data/rinex/SITE").glob("*.rnx"))
for result in processor.process_batch(rinex_files, max_workers=4):
    if result.success:
        df = result.positions()           # DataFrame: epoch, X, Y, Z, σ
        print(f"{result.date}  {len(df)} epochs")
    else:
        print(f"{result.date}  FAILED  rc={result.returncode}")
```

`process_batch` resolves products **once per unique date** across all RINEX
files for that date before dispatching `pdp3`, so a year of data from a
single station requires at most 365 product resolution calls rather than
one per file.

For `ProcessingMode.DEFAULT` the resolver cascades through FIN → RAP → ULT,
using the best available solution at run time. Use `FINAL` for post-processing
where reproducibility matters.

---

## Installation

```bash
git clone https://github.com/EarthScope/GNSSommelier.git
cd GNSSommelier
uv sync --all-packages
```

Standalone:

```bash
uv add gnss-product-management          # product retrieval only
uv add pride-ppp                        # includes gnss-product-management
```

> `pdp3` from [PRIDE-PPPAR](https://github.com/PrideLab/PRIDE-PPPAR) must be
> on `$PATH` to use `pride-ppp`.

---

## Packages

| Package | Role |
|---|---|
| `gnss-management-specs` | YAML data bundle — centers, products, formats, storage layouts |
| `gnss-product-management` | Discovery, resolution, and download engine |
| `pride-ppp` | PRIDE-PPPAR integration — RINEX in, kinematic positions out |

---

## Dependency resolution

A `DependencySpec` YAML lists every product a processing task requires and
encodes the timeliness/center preference cascade:

```yaml
name: pride_pppar
package: pride-ppp
task: kinematic_ppp
preferences:
  - parameter: TTT
    sorting: [FIN, RAP, ULT]
  - parameter: AAA
    sorting: [WUM, COD, ESA, GFZ]
dependencies:
  - spec: ORBIT
    required: true
  - spec: CLOCK
    required: true
  - spec: BIA
    required: false   # Float PPP runs without BIA; PPP-AR integer fixing requires it
  - spec: ERP
    required: true
  - spec: ATTATX
    required: true
```

```python
client = GNSSClient.from_defaults(base_dir="/data/gnss-products")

resolution, lockfile_path = client.resolve_dependencies(
    "pride_pppar.yaml", date, sink_id="local"
)
print(resolution.summary())
# ORBIT  FIN  WUM  downloaded  /data/gnss-products/2025/015/WUM0OPSFIN...SP3
# CLOCK  FIN  WUM  downloaded  /data/gnss-products/2025/015/WUM0OPSFIN...CLK
# BIA    FIN  WUM  downloaded  ...
# ERP    FIN  WUM  downloaded  ...
# ATTATX ---  IGS  downloaded  ...

if resolution.all_required_fulfilled:
    for spec, path in resolution.product_paths().items():
        print(f"{spec:10s} {path}")
```

The resolver checks the local workspace first. If a `DependencyLockFile` for
`(package, task, date, version)` already exists, resolution returns
immediately — no network calls.

---

## Cloud workspace

Any `base_dir` URI supported by
[cloudpathlib](https://cloudpathlib.drivendata.org/) works as a workspace:

```python
# S3
client = GNSSClient.from_defaults(base_dir="s3://my-bucket/gnss/products")

# Google Cloud Storage
client = GNSSClient.from_defaults(base_dir="gs://my-bucket/gnss/products")
```

Lock files are written under `base_dir/dependency_lockfiles/`, giving
distributed workers a shared coordination point. A worker that detects a
valid lockfile for the requested date skips all network activity.

---

## Architecture

```
┌────────────────────────────────────────────────┐
│  Layer 4 — Interface                           │
│  GNSSClient · ProductQuery                     │
│  ProductRegistry · WorkSpace (setup)           │
├────────────────────────────────────────────────┤
│  Layer 3 — Orchestration                       │
│  SearchPlanner · WormHole                      │
│  ConnectionPoolFactory (fsspec-backed)         │
│  DownloadPipeline · ResolvePipeline            │
│  LockfileWriter · LockfileManager              │
├────────────────────────────────────────────────┤
│  Layer 2 — Catalog                             │
│  FormatCatalog · ProductCatalog                │
│  ResourceCatalog · SourcePlanner (Protocol)    │
├────────────────────────────────────────────────┤
│  Layer 1 — Specification (Pydantic)            │
│  FormatSpec · ProductSpec · SearchTarget       │
│  DependencySpec · LockProduct                  │
├────────────────────────────────────────────────┤
│  Layer 0 — Configuration                       │
│  Bundled YAML · as_path() · hash_file()        │
└────────────────────────────────────────────────┘
```

Each layer depends only on layers below it. `ProductRegistry` and `WorkSpace`
both satisfy the `SourcePlanner` protocol, giving `SearchPlanner` a uniform
interface to remote and local resources. All local/cloud path operations route
through `as_path()`, which dispatches to `pathlib.Path` or `cloudpathlib`
based on the URI scheme.

Full detail: [Architecture](architecture.md) · [Class Reference](class-reference.md)

---

## Supported products

| Product | Format | Sampling | Description |
|---|---|---|---|
| ORBIT | SP3 | 15 min | Precise satellite ephemerides (ITRF2020 / IGb20 for Repro3+ products) |
| CLOCK | CLK | 30 s / 5 min | Satellite and station clock corrections |
| BIA | BIA | daily | OSB/FCB code and phase biases — required for PPP-AR integer fixing |
| ERP | ERP | daily | Polar motion (x_p, y_p), UT1-UTC, LOD |
| GIM | IONEX | 1–2 h | Global ionosphere TEC maps |
| NAVIGATION | RINEX NAV | — | Broadcast ephemerides (merged BRDC) |
| ATTATX | ANTEX | static | Satellite and receiver antenna phase-center calibrations |
| ATTOBX | OBX | 5 min | Satellite attitude quaternions |
| TROPOSPHERE | VMF1/VMF3 | 6 h | Vienna Mapping Functions (gridded) |
| OROGRAPHY | GRID | static | Orography for VMF |
| LEAPSECOND | — | static | IERS leap-second table |
| SAT\_PARAMETERS | — | static | Satellite mass, geometry, SRP metadata |

---

## Supported analysis centers

| Center | Institution | Protocol | Products |
|--------|-------------|----------|---------|
| [BKG](data-centers.md#bkg) | Federal Agency for Cartography and Geodesy | HTTPS | BIA, CLOCK, ERP, IONEX, ORBIT, RNX3\_BRDC, SINEX |
| [CAS](data-centers.md#cas) | Chinese Academy of Sciences (GIPP) | FTP | BIA, IONEX |
| [CDDIS](data-centers.md#cddis) | NASA Crustal Dynamics Data Information System | FTPS | ATTOBX, BIA, CLOCK, ERP, IONEX, LEAP\_SEC, ORBIT, RNX3\_BRDC, SINEX, TROP |
| [COD](data-centers.md#cod) | Center for Orbit Determination in Europe (AIUB) | FTP | BIA, CLOCK, ERP, IONEX, ORBIT, SINEX, TROP |
| [ESA](data-centers.md#esa) | European Space Agency / ESOC | FTP | BIA, CLOCK, ERP, IONEX, ORBIT, SINEX |
| [EUREF](data-centers.md#euref) | EUREF Permanent GNSS Network (EPN) | HTTPS | SINEX |
| [GFZ](data-centers.md#gfz) | GFZ German Research Centre for Geosciences | SFTP | CLOCK, ERP, ORBIT, SINEX, TROP |
| [GRGS](data-centers.md#grgs) | Groupe de Recherche de Géodésie Spatiale (CNES/CLS) | FTP | ATTOBX, BIA, CLOCK, ERP, ORBIT, SINEX |
| [IGS](data-centers.md#igs) | International GNSS Service | FTP / HTTPS | ATTATX, ATTOBX, BIA, CLOCK, ERP, IONEX, ORBIT, RNX3\_BRDC, SINEX, TROP |
| [JPL](data-centers.md#jpl) | NASA Jet Propulsion Laboratory | HTTPS | BIA, CLOCK, ERP, IONEX, ORBIT, SINEX, TROP |
| [KASI](data-centers.md#kasi) | Korea Astronomy and Space Science Institute | FTP | ATTOBX, BIA, CLOCK, ERP, IONEX, ORBIT, RNX3\_BRDC, SINEX |
| [NGII](data-centers.md#ngii) | National Geographic Information Institute (Korea) | FTP | RNX3\_BRDC *(unavailable outside Korea)* |
| [NRCan](data-centers.md#nrcan) | Natural Resources Canada (CSRS) | FTP | BIA, CLOCK, ERP, ORBIT, SINEX |
| [TUG](data-centers.md#tug) | Graz University of Technology (ITSG) | FTPS | ATTOBX, BIA, CLOCK, ERP, ORBIT |
| [VMF](data-centers.md#vmf) | TU Wien — Vienna Mapping Functions | HTTPS | OROGRAPHY, VMF |
| [WUM](data-centers.md#wum) | Wuhan University GNSS Research Center | FTP | ATTOBX, BIA, CLOCK, ERP, IONEX, LEAP\_SEC, ORBIT, RNX3\_BRDC, SAT\_PARAMS, SINEX |

---

## References

- [IGS Products](https://igs.org/products/) — accuracy and latency specifications
- [IGS Long Filename Convention](https://igs.org/formats-and-standards/)
- [PRIDE-PPPAR](https://pride.whu.edu.cn/pppar/)
- [Vienna Mapping Functions](https://vmf.geo.tuwien.ac.at/)
- [cloudpathlib](https://cloudpathlib.drivendata.org/) — cloud storage support
- [fsspec](https://filesystem-spec.readthedocs.io/) — FTP/FTPS/SFTP/HTTPS connection pooling
