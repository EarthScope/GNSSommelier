# YAML Configuration Reference

The product management system is driven entirely by YAML configuration files
bundled in the [`gnss-management-specs`](../packages/gnss-management-specs/)
package. This separates data from code: adding a new analysis center or product
type requires only a new YAML file.

> Source path: `packages/gnss-management-specs/src/gnss_management_specs/configs/`

---

## `meta/` — Metadata Field Specifications

**File:** `meta_spec.yaml`

The master glossary of all metadata fields used across GNSS product filenames
(`SSSS`, `YYYY`, `AAA`, `FMT`, `GPSWEEK`, etc.). For each field it defines:

- **`pattern`** — Regular expression defining the expected format. Used to
  parse metadata out of existing filenames and to construct valid patterns when
  generating file paths.
- **`description`** — Plain-English explanation of what the field represents.
- **`derivation`** — How the value is obtained: `enum` (chosen from a list) or
  `computed` (dynamically derived, typically from a `datetime` object).

### Computed metadata values

Fields with `derivation: computed` (e.g. `YYYY`, `DDD`, `GPSWEEK`,
`REFFRAME`) are calculated on the fly. Python functions registered with the
`ParameterCatalog` know how to generate these values from a `datetime`, so the
`QueryFactory` can build date-specific filename patterns automatically.

---

## `products/` — Product & Format Specifications

**Files:** `product_spec.yaml`, `format_spec.yaml`

### `product_spec.yaml`

High-level catalogue of all recognized GNSS product *types* (`ORBIT`, `CLOCK`,
`BIA`, `IONEX`, `VMF`, …). Each entry defines:

- Allowed `formats` (linking to `format_spec.yaml`)
- Parameter constraints (e.g. an `ORBIT` must have `CNT=ORB`, `FMT=SP3`)

### `format_spec.yaml`

Concrete filename structures for each data format:

- **Versions and variants** — e.g. RINEX 2 vs 3, observation vs navigation
- **Filename templates** — e.g. `{SSSS}{DDD}0.{YY}{T}` for RINEX 2
  observation
- **Parameters** — metadata fields (from `meta/`) that populate each template

Together these two files let `SearchPlanner` dynamically construct and
match filenames for any product type using the parameter catalog.

---

## `centers/` — Analysis Center Configurations

**Files:** One YAML per center (e.g. `igs_config.yaml`, `gfz_config.yaml`,
`wuhan_config.yaml`)

Each file defines a single IGS analysis center:

- **`id` / `name`** — Short and long identifiers
- **`description` / `website`** — Background and documentation link
- **`servers`** — FTP/FTPS/SFTP/HTTP endpoints with hostnames, protocols, and
  authentication details
- **`products`** — Every product the center offers, with `id`, `parameters`,
  and `directory` templates needed to construct valid remote file paths

These configs are the blueprints for how the system interacts with each data
provider.

### Authentication

Most centers (COD, ESA, WUM) serve products over anonymous FTP and require
no credentials. GFZ serves GNSS products over anonymous SFTP
(`anonymous` / `anonymous@isdc-data.gfz.de`). **CDDIS** (NASA GSFC) has
required authenticated FTPS access since November 2020. Credentials are read
automatically from `~/.netrc`:

```
machine cddis.nasa.gov login <earthdata_username> password <earthdata_password>
```

Register at <https://cddis.nasa.gov/Data_and_Derived_Products/CreateAccount.html>.
Without a valid `.netrc` entry, all CDDIS queries will fail with a 530
authentication error.

---

## `local/` — Local Storage Configuration

**File:** `local_config.yaml`

Dictates how downloaded products are organized on disk:

- **Directory layout** — Time-dependent products go under `{YYYY}/{DDD}/`;
  static reference files go in `table/`.
- **Temporal categories** — `daily`, `hourly`, or `static`, controlling how
  date information maps to storage paths.
- **Product collections:**

| Collection | Contents |
|---|---|
| `products` | Orbits (SP3), clocks (CLK), biases (BIA), attitude (OBX) |
| `rinex` | Observation, navigation, meteorological RINEX |
| `common` | Ionosphere maps (IONEX), troposphere grids (VMF1/VMF3) |
| `table` | Static reference files: leap-second table, satellite parameters (mass, geometry), ANTEX |
| `lockfiles` | Dependency lock files — provenance and SHA-256 hashes for every resolved product |
| `leo` | Level-1B GNSS observation data from LEO satellites (e.g. COSMIC-2, Swarm); uses the same SP3/CLK product types but separate center configs |

### Cloud storage

The `local_config.yaml` directory structure applies equally to local and cloud
paths. Pass an S3 (or GCS/Azure) URI as `base_dir` and the same
`{YYYY}/{DDD}/` layout is mirrored in object storage:

```python
client = GNSSClient.from_defaults(base_dir="s3://my-bucket/gnss-products")
# Products land at:
#   s3://my-bucket/gnss-products/2025/015/products/WUM0OPSFIN...SP3
#   s3://my-bucket/gnss-products/2025/015/common/COD0OPSFIN...INX
#   s3://my-bucket/gnss-products/dependency_lockfiles/pride-ppp_ppp_20250015.json
```

---

## `dependencies/` — Product Dependency Specifications

**Files:** One YAML per processing task (e.g. `pride_pppar.yaml`)

Bundles all GNSS products required for a specific processing engine:

- **`name` / `description`** — What the dependency set covers
- **`package` / `task`** — The broader package or task it serves
- **`preferences`** — A cascade of choices the resolver uses when multiple
  options exist (e.g. prefer `WUM` over others, prefer `FIN` solutions before
  `RAP` or `ULT`)
- **`dependencies`** — The list of required products, each referencing a
  product `spec` (like `ORBIT`, `CLOCK`, `BIA`)

`ResolvePipeline` (via `GNSSClient.resolve_dependencies`) uses these specs to
find, download, and cache a complete, prioritised dataset for any processing
run. The `preferences` list drives the timeliness/center cascade:
FIN → RAP → ULT, with per-parameter fallback ordering.

---

## `query/` — Product Query Specifications

**File:** `query_config.yaml`

Defines the searchable dimensions ("axes") for product queries:

- **Axis definitions** — `date`, `spec`, `center`, `campaign`, `solution`,
  `sampling`. Each axis has a `description`, `type` (`enum` or `computed`),
  whether it's `required`, which metadata fields it `maps_to`, and usage
  `notes`.
- **Product query profiles** — Per-product configurations listing:
  - Applicable axes
  - `extra_axes` for product-specific parameters (e.g. `constellation` for
    broadcast navigation)
  - `format_key` linking to `format_spec.yaml`
  - `temporal` type (`daily`, `hourly`, `static`)
  - `local_collection` mapping to `local_config.yaml`

This file defines the queryable dimensions for product searches. `SearchPlanner`
reads these profiles to know which parameter axes apply to each product and how
to route queries to local vs. remote resources.
