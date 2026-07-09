# gnss-product-management

Specification-driven discovery, resolution, and download of IGS GNSS products
from analysis center servers.

## What it does

- Resolves IGS long filenames from a date and product name using the parameter
  catalog (`TTT`, `AAA`, `YYYY`, `DDD`, `GPSWEEK`, etc.)
- Queries FTP, FTPS, SFTP, and HTTP servers at registered analysis centers, lists
  directories, and matches filenames by regex
- Downloads and decompresses `.gz` files into a structured local workspace or
  cloud storage bucket
- Resolves a complete `DependencySpec` (orbit + clock + bias + ERP + …) in
  one call, with a lockfile fast-path for repeat runs

## Installation

From the monorepo (development):

```bash
uv sync
```

Standalone:

```bash
uv add gnss-product-management
# or
pip install gnss-product-management
```

---

## Product parameters

Every IGS long filename encodes a set of named fields. This library uses the
same names as keys throughout:

| Parameter | IGS field | Meaning | Common values |
|---|---|---|---|
| `TTT` | solution type | Timeliness/quality class | `FIN` (final ≥13 d), `RAP` (rapid ≤17 h), `ULT` (ultra-rapid ≤3 h), `NRT` (near-real-time), `PRD` (predicted) |
| `AAA` | analysis center | Producing AC | `COD`, `ESA`, `GFZ`, `WUM`, `IGS`, … |
| `YYYY` | year | 4-digit year | computed from date |
| `DDD` | day-of-year | Day of year | computed from date |
| `GPSWEEK` | GPS week | GPS week number | computed from date |
| `SMP` | sampling interval | File sampling | `05M`, `30S`, `01H`, … |
| `FMT` | format | File extension | `SP3`, `CLK`, `BIA`, … |

Computed fields (`YYYY`, `DDD`, `GPSWEEK`, etc.) are resolved automatically
from the query date. You only need to specify the fields you want to pin.

---

## Quick start

### Search across centers

```python
from datetime import datetime, timezone
from gnss_product_management import GNSSClient

client = GNSSClient.from_defaults()
date = datetime(2025, 1, 15, tzinfo=timezone.utc)  # 2025 DOY 015

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
    print(r.center, r.quality, r.filename, r.uri)
```

### Download one product

```python
client = GNSSClient.from_defaults(base_dir="/data/gnss-products")

paths = (
    client.query()
    .for_product("ORBIT")
    .on(date)
    .where(TTT="FIN")
    .sources("WUM")
    .download(sink_id="local", limit=1)
)
```

### Search a date range

```python
from datetime import timedelta

results = (
    client.query()
    .for_product("CLOCK")
    .on_range(start_date, end_date, step=timedelta(days=1))
    .where(TTT="FIN")
    .sources("COD")
    .search()
)
# Searches run in parallel across dates (up to 8 concurrent threads)
```

### Resolve all dependencies

```python
resolution, lockfile_path = client.resolve_dependencies(
    "path/to/pride_pppar.yaml",
    date,
    sink_id="local",
)
print(resolution.summary())

if resolution.all_required_fulfilled:
    for spec, path in resolution.product_paths().items():
        print(f"{spec:12s}  {path}")
```

---

## DependencySpec YAML

A `DependencySpec` encodes which products a processing task needs, from which
centers to prefer them, and the timeliness cascade:

```yaml
name: my_task
package: my-package
task: ppp_processing
preferences:
  - parameter: TTT                    # prefer final products
    sorting: [FIN, RAP, ULT]
  - parameter: AAA                    # prefer WUM then COD
    sorting: [WUM, COD, ESA, GFZ]
dependencies:
  - spec: ORBIT
    required: true
  - spec: CLOCK
    required: true
  - spec: BIA
    required: false                   # optional for float PPP; required for PPP-AR integer fixing
  - spec: ERP
    required: true
  - spec: ATTATX
    required: true
    constraints:
      TTT: FIN                        # per-dependency overrides
```

The `spec` field must match a product name registered in the catalog
(`ORBIT`, `CLOCK`, `BIA`, `ERP`, `GIM`, `ATTATX`, etc.). The `preferences`
list is evaluated top-down; when multiple products match, the one ranked
highest by the preference cascade is used.

---

## Cloud workspace

Any URI scheme supported by
[cloudpathlib](https://cloudpathlib.drivendata.org/) works as `base_dir`:

```python
# Amazon S3
client = GNSSClient.from_defaults(base_dir="s3://my-bucket/gnss/products")

# Google Cloud Storage
client = GNSSClient.from_defaults(base_dir="gs://my-bucket/gnss/products")

# Azure Blob Storage
client = GNSSClient.from_defaults(base_dir="az://my-container/gnss/products")
```

Lock files are stored under `base_dir/dependency_lockfiles/`. When multiple
workers share the same prefix, the first to complete a dependency resolution
writes the lockfile; subsequent workers detect it and skip all network
activity.

---

## Connection pool configuration

`max_connections` sets the per-hostname connection pool size. The default of
4 is conservative; adjust based on the center's documented limits:

```python
client = GNSSClient.from_defaults(
    base_dir="/data/gnss",
    max_connections=8,      # increase for less restrictive servers
)
```

CDDIS (NASA) enforces strict anonymous FTPS connection limits — keep
`max_connections` at 2–4 for CDDIS queries. Less restrictive FTP / SFTP
centers (COD, WUM, GFZ) generally tolerate 6–8. When a limit is exceeded the pool blocks until a
slot is free; no requests are dropped.

---

## Custom registry

To load your own center or product specs instead of the bundled defaults:

```python
from gnss_product_management.environments import ProductRegistry, WorkSpace
from gnss_product_management import GNSSClient

registry = ProductRegistry()
registry.add_parameter_spec("path/to/meta_spec.yaml")
registry.add_format_spec("path/to/format_spec.yaml")
registry.add_product_spec("path/to/product_spec.yaml")
registry.add_resource_spec("path/to/my_center.yaml")   # one per center
registry.build()

workspace = WorkSpace()
workspace.add_resource_spec("path/to/local_config.yaml")
workspace.register_spec(base_dir="/data/gnss", spec_ids=["local_config"])

client = GNSSClient(product_registry=registry, workspace=workspace)
```

---

## API reference

| Symbol | Description |
|---|---|
| `GNSSClient` | Single entry point — search, download, resolve |
| `GNSSClient.from_defaults()` | Build from bundled specs |
| `GNSSClient.query()` | Returns a `ProductQuery` fluent builder |
| `GNSSClient.search()` | Direct search (bypasses builder) |
| `GNSSClient.download()` | Download pre-searched `FoundResource` list |
| `GNSSClient.resolve_dependencies()` | Full spec-driven dependency resolution |
| `GNSSClient.display()` | Print loaded products and registered centers |
| `ProductQuery` | Builder: `.for_product()` `.on()` `.where()` `.sources()` `.prefer()` `.on_range()` `.search()` `.download()` |
| `FoundResource` | Discovered file — `.center`, `.quality`, `.filename`, `.uri`, `.is_local`, `.downloaded` |
| `DependencySpec` | Parsed YAML dependency specification |
| `DependencyResolution` | Result of `resolve_dependencies()` — `.summary()`, `.table()`, `.product_paths()`, `.missing` |

---

## Supported analysis centers

| Center | Institution | Protocol | Products |
|---|---|---|---|
| CDDIS | NASA GSFC | FTPS | clock, GIM, leap seconds, navigation, orbit |
| COD | AIUB / Univ. Bern | FTP | bias, clock, ERP, GIM, orbit |
| ESA | ESA/ESOC | FTP | clock, GIM, orbit |
| GFZ | GFZ Potsdam | SFTP | clock, ERP, orbit, SINEX, TROP |
| IGS | IGS combined products (files.igs.org) | FTP / HTTPS | ATX, bias, clock, ERP, navigation, OBX, orbit |
| VMF | TU Wien | HTTPS | orography, VMF1, VMF3 |
| WUM | Wuhan University (WHU) | FTP | bias, clock, ERP, GIM, leap seconds, navigation, OBX, orbit, sat_parameters |

> **CDDIS authentication:** CDDIS requires an EarthData login for FTPS
> access. Add credentials for `cddis.nasa.gov` to your `~/.netrc` file.
> Registration: <https://cddis.nasa.gov/Data_and_Derived_Products/CreateAccount.html>
