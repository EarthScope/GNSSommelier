# pride-ppp

PRIDE-PPPAR integration for kinematic PPP-AR. Resolves IGS products, writes
the `pdp3` config file, runs the binary, and returns parsed `.kin` / `.res`
output.

## Prerequisites

- `pdp3` from [PRIDE-PPPAR](https://github.com/PrideLab/PRIDE-PPPAR) on
  `$PATH`
- Python ≥ 3.10

## Installation

From the monorepo (development):

```bash
uv sync
```

Standalone:

```bash
uv add pride-ppp
```

---

## Setup

`PrideProcessor` needs two directories:

| Directory | Purpose |
|---|---|
| `pride_dir` | IGS products and `pdp3` working state (`config_file`, ambiguity tables). Organised as `pride_dir/{year}/{doy}/`. |
| `output_dir` | Final `.kin` and `.res` output files. Named `kin_{YYYY}{DOY}_{site}.kin` and `res_{YYYY}{DOY}_{site}.res`. |

```python
from pride_ppp import PrideProcessor, ProcessingMode
from pathlib import Path

processor = PrideProcessor(
    pride_dir=Path("/data/pride"),
    output_dir=Path("/data/output"),
    mode=ProcessingMode.FINAL,     # see Processing modes below
)
```

Construction is eager: all YAML specs are parsed and the product registry is
built at `__init__` time. A single `PrideProcessor` instance is safe to reuse
across many `process()` / `process_batch()` calls.

---

## Processing modes

| Mode | Timeliness accepted | When to use |
|---|---|---|
| `ProcessingMode.DEFAULT` | FIN → RAP → ULT (cascade) | Near-real-time, use best available |
| `ProcessingMode.FINAL` | FIN only | Post-processing, reproducibility required |

`FINAL` mode fails dependency resolution if IGS final products are not yet
available for the requested date (≥13 days latency). Use `DEFAULT` for
processing dates within the last two weeks.

---

## Single file

```python
result = processor.process(
    Path("SITE00USA_R_20250150000_01D_30S_MO.rnx"),
    site="SITE",           # 4-char ID; inferred from first 4 chars of filename if omitted
)
```

Both RINEX 3 (`SSSS00CCC_R_YYYYDDDHHMM_01D_30S_MO.rnx`) and legacy RINEX 2
(`ssss1250.25o`) observation files are accepted. The `site` parameter is
extracted from the leading 4 alphanumeric characters of the filename stem when
not provided — standard RINEX naming makes this reliable. For non-standard
filenames, pass `site=` explicitly.

```python
if result.success:
    df = result.positions()      # see Output below
    print(df.head())
else:
    print(f"pdp3 returned {result.returncode}")
    print(result.stderr)
```

If a valid `.kin` file already exists in `output_dir` for the same site and
date, `process()` returns the cached result immediately. Pass `override=True`
to force a re-run.

---

## Batch processing (year of data)

`process_batch` resolves IGS products **once per unique date** across all
input files, then dispatches `pdp3` in parallel:

```python
rinex_files = sorted(Path("/data/rinex/SITE").glob("*.rnx"))

results = list(processor.process_batch(
    rinex_files,
    max_workers=4,    # concurrent pdp3 subprocesses
    override=False,   # skip dates with valid .kin already on disk
))

succeeded = [r for r in results if r.success]
failed    = [r for r in results if not r.success]
print(f"{len(succeeded)}/{len(results)} days processed successfully")
```

For a 365-day station dataset `process_batch` makes at most 365 product
resolution calls (one per date). Each resolved date writes its products to
`pride_dir/{year}/{doy}/`. Subsequent runs for the same date find the existing
`DependencyLockFile` and skip all network activity.

---

## Product family selection

Default processing tries FIN, RTS, RAP, then ULT. Within each type it
prefers WUM (Wuhan), COD (CODE), GFZ, then ESA. Orbit, clock, ERP, and
bias products must share the generating analysis center, timeliness, and
solution identifier (`AAA`, `TTT`, `PPP`). Attitude is optional in default
mode; FINAL mode accepts only FIN and also requires attitude.

Members of a family may be downloaded from different physical servers.
For each member, alternate locations are tried before abandoning the family.
Server protocol does not affect ranking; equal-ranked locations retain
search discovery order. Existing valid aggregate lockfiles are reused;
force product resolution to reconsider a cached selection.

## Output files

| File | Location | Content |
|---|---|---|
| `kin_{YYYY}{DOY}_{site}.kin` | `output_dir` | Kinematic positions: epoch, X/Y/Z ECEF, σX/σY/σZ |
| `res_{YYYY}{DOY}_{site}.res` | `output_dir` | Measurement residuals and WRMS statistics |
| `config_file` | `pride_dir/{year}/{doy}/` | `pdp3` config used for this date (retained for inspection) |

### Parsing positions

```python
df = result.positions()
# DataFrame columns:
#   Latitude    (degrees, geodetic, IGS20/ITRF2020 for Repro3+ products)
#   Longitude   (degrees, geodetic)
#   Height      (metres, ellipsoidal)
#   Nsat        (number of satellites used in the epoch solution)
#   PDOP        (position dilution of precision)
#   wrms        (phase residual WRMS, mm, per epoch from the .res file)
# Index: UTC epoch timestamp
```

### Parsing residuals

```python
df = result.residuals()
# Returns a DataFrame with WRMS values indexed by epoch
```

---

## Checking dependency resolution

```python
resolution = result.resolution

print(resolution.summary())
# ORBIT   FIN  WUM  downloaded  /data/pride/2025/015/WUM0OPSFIN...SP3
# CLOCK   FIN  WUM  downloaded  ...
# BIA     FIN  WUM  downloaded  ...
# ERP     FIN  WUM  downloaded  ...
# ATTATX  ---  IGS  downloaded  ...

# Check for missing required products
if not resolution.all_required_fulfilled:
    for dep in resolution.missing:
        if dep.required:
            print(f"Missing required product: {dep.spec}")
```

---

## PRIDE-PPPAR installation path

If you have PRIDE-PPPAR installed locally (for additional table files),
register it with `pride_install_dir`:

```python
processor = PrideProcessor(
    pride_dir=Path("/data/pride"),
    output_dir=Path("/data/output"),
    pride_install_dir=Path("/opt/PRIDE-PPPAR"),
)
```

The installer's table directory (ATX, leap-second table, satellite metadata)
is registered as a read-only workspace source. Products found there are used
directly without downloading.

---

## Custom pdp3 flags

Override any `pdp3` CLI flags via `PrideCLIConfig`:

```python
from pride_ppp.specifications.cli import PrideCLIConfig

processor = PrideProcessor(
    pride_dir=Path("/data/pride"),
    output_dir=Path("/data/output"),
    cli_config=PrideCLIConfig(
        sampling_rate=30,      # 30-second epochs (default: 1)
        elevation_cutoff=7,    # degrees
    ),
)
```

---

## API

| Symbol | Description |
|---|---|
| `PrideProcessor` | Main entry point. Owns product registry and workspace. |
| `PrideProcessor.process()` | Process one RINEX file end-to-end. |
| `PrideProcessor.process_batch()` | Process many files, sharing product resolution per date. |
| `ProcessingResult` | Immutable result per file — `.success`, `.positions()`, `.residuals()`, `.resolution`, `.returncode`, `.stderr` |
| `ProcessingMode` | `DEFAULT` (FIN→RAP→ULT) or `FINAL` (FIN only) |
| `PrideCLIConfig` | Typed builder for `pdp3` command-line flags |
| `PRIDEPPPFileConfig` | Read/write `pdp3` config file |

---

## Common issues

**`pdp3` not found**
: Add the PRIDE-PPPAR `bin/` directory to `$PATH`, or pass the full path via
  `PrideCLIConfig`.

**Missing required products**
: Check `result.resolution.summary()`. If `TTT=FIN` products are unavailable,
  switch to `ProcessingMode.DEFAULT` — FIN products are available approximately
  13 days after the observation date.

**`ProcessingMode.FINAL` fails on recent data**
: FIN products from WUM, COD, and ESA are released approximately 13 days after
  the observation date. Processing a file from the last two weeks with
  `mode=ProcessingMode.FINAL` will fail dependency resolution because no FIN
  products exist yet. Use `ProcessingMode.DEFAULT` (FIN → RAP → ULT cascade) for
  data from the current week.

**Empty `.kin` file / low epoch count**
: `result.success` is `True` only when the `.kin` file exists *and* parses to a
  non-empty DataFrame. A sparse or empty output usually indicates insufficient
  satellite visibility or pre-processing failures in `pdp3`. Check
  `result.stderr` for diagnostics and inspect `Nsat` / `PDOP` columns in
  `result.positions()`. Epochs with `Nsat ≤ 4` or `PDOP ≥ 5` are unreliable.

**Wrong coordinates in output (frame mismatch)**
: Coordinates are in whatever ITRF realization the resolved orbit/clock products
  reference. IGS Repro3 and post-2022 products use IGS20 (aligned with
  ITRF2020). Legacy products (pre-2022) use IGS14 / ITRF2014. Ensure the ATX
  file (`igs20.atx`) matches the orbit products; using `igs14.atx` with Repro3
  orbits introduces a ~1–2 cm frame inconsistency.

**Re-processing a date**
: Pass `override=True` to `process()` or `process_batch()` to force a re-run
  even when a valid `.kin` exists.

See [examples/](examples/) for runnable scripts (single file and batch).
