#!/usr/bin/env python3
"""Audit non-EarthScope GNSS station coordinates.

Collects station lists from every non-EarthScope server/network configured
in this codebase, cross-references them against the spatial-index station
catalogs (YAML/JSON/GeoJSON), and reports stations that are missing lat/lon.

Networks audited:
  - CORS  (NOAA)           — cors_stations.yaml
  - IGS   (multi-center)   — igs_stations.yaml
  - RBMC  (IBGE Brazil)    — rbmc_stations.yaml
  - IBGE  (FTP)            — live listing of RINEX 3 files
  - GeoNet (NZ)            — live S3 listing of RINEX files
  - M3G   (95 EU networks) — M3G REST API / GeoJSON cache

Usage:
    uv run dev/audit_station_coordinates.py
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "packages" / "gpm-specs" / "src" / "gpm_specs" / "configs" / "networks"
GPM_DEFAULTS = (
    ROOT / "packages" / "gnss-product-management" / "src" / "gnss_product_management" / "defaults"
)

# ──────────────────────────────────────────────────────────────────────
# 1. Load all local spatial-index catalogs
# ──────────────────────────────────────────────────────────────────────


def load_yaml_stations(path: Path) -> dict[str, dict]:
    """Return {site_code: {lat, lon, ...}} from a YAML station catalog."""
    with open(path) as f:
        data = yaml.safe_load(f)
    out: dict[str, dict] = {}
    for s in data.get("stations", []):
        code = s["site_code"].lower()
        out[code] = {"lat": s["lat"], "lon": s["lon"], "source": path.name}
    return out


def _stations_from_features(features: list[dict], source: str) -> dict[str, dict]:
    """Return {site_code: {lat, lon, source}} from a list of GeoJSON features."""
    out: dict[str, dict] = {}
    for feat in features:
        coords = feat.get("geometry", {}).get("coordinates")
        nine_char = feat.get("properties", {}).get("id", "")
        code = nine_char[:4].lower() if nine_char else ""
        if code and coords and len(coords) >= 2:
            out[code] = {"lat": coords[1], "lon": coords[0], "source": source}
    return out


def load_m3g_cache(cache_file: Path) -> dict[str, dict]:
    """Return {site_code: {lat, lon}} from the consolidated M3G GeoJSON cache."""
    out: dict[str, dict] = {}
    if not cache_file.exists():
        return out
    with open(cache_file) as f:
        cache = json.load(f)
    for network, features in cache.items():
        out.update(_stations_from_features(features, f"m3g_cache/{network}"))
    return out


# ──────────────────────────────────────────────────────────────────────
# 2. Query live servers for station lists
# ──────────────────────────────────────────────────────────────────────


def fetch_geonet_stations() -> set[str]:
    """Get station codes by listing GeoNet S3 bucket keys for one DOY."""
    logger.info("Fetching GeoNet station list from S3 bucket...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    codes: set[str] = set()
    # List RINEX files for a recent DOY
    url = (
        "https://geonet-open-data.s3-ap-southeast-2.amazonaws.com/"
        "?prefix=gnss/rinex/2024/001/&max-keys=2000&delimiter="
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read().decode("utf-8", errors="replace")
        keys = re.findall(r"<Key>([^<]+)</Key>", data)
        for key in keys:
            # RINEX 2: .../ssss0010.24o.gz
            m = re.search(r"/([a-z0-9]{4})\d{3}[a-z0-9]?\.\d{2}[od]", key, re.I)
            if m:
                codes.add(m.group(1).lower())
                continue
            # RINEX 3: .../SSSS00NZL_R_...MO.crx.gz
            m = re.search(r"/([A-Z0-9]{4})00NZL", key)
            if m:
                codes.add(m.group(1).lower())
        logger.info("GeoNet: found %d unique station codes", len(codes))
    except Exception as e:
        logger.warning("GeoNet fetch failed: %s", e)
    return codes


def fetch_ibge_stations() -> set[str]:
    """Get station codes by listing IBGE FTP RINEX3 directory for one DOY."""
    import ftplib

    logger.info("Fetching IBGE station list from FTP...")
    codes: set[str] = set()
    try:
        ftp = ftplib.FTP(timeout=20)
        ftp.connect("geoftp.ibge.gov.br", 21)
        ftp.login()
        ftp.set_pasv(True)
        ftp.cwd("/informacoes_sobre_posicionamento_geodesico/rbmc/dados_RINEX3/2024/001")
        files = ftp.nlst()
        ftp.quit()
        for fname in files:
            m = re.match(r"([A-Z0-9]{4})00BRA", fname, re.I)
            if m:
                codes.add(m.group(1).lower())
        logger.info("IBGE FTP: found %d unique station codes", len(codes))
    except Exception as e:
        logger.warning("IBGE fetch failed: %s", e)
    return codes


def fetch_m3g_network_stations(network_id: str, max_pages: int = 40) -> dict[str, dict]:
    """Fetch station coordinates for a single M3G network from the API."""
    base = "https://gnss-metadata.eu/v1/sitelog/geojson"
    out: dict[str, dict] = {}
    page = 1
    per_page = 50
    while page <= max_pages:
        url = f"{base}?network={urllib.parse.quote(network_id)}&page={page}&per-page={per_page}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            batch = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("M3G API failed for %s page %d: %s", network_id, page, e)
            break
        if not batch:
            break
        for feat in batch:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates")
            props = feat.get("properties", {})
            nine_char = props.get("id", "")
            code = nine_char[:4].lower() if nine_char else ""
            if code and coords and len(coords) >= 2:
                out[code] = {
                    "lat": coords[1],
                    "lon": coords[0],
                    "source": f"m3g_api/{network_id}",
                }
        if len(batch) < per_page:
            break
        page += 1
    return out


def fetch_all_m3g_stations(
    m3g_manifest_path: Path,
    cache_file: Path,
) -> dict[str, dict]:
    """Fetch/load stations for ALL 95 M3G networks.

    Uses cached GeoJSON where available, falls back to live API.
    E-GVAP is skipped — it's a weather observation network with 1000+
    sites that causes API timeouts and isn't a GNSS CORS network.
    """
    # E-GVAP is EUMETNET's weather-GNSS network (1000+ sites, API hangs)
    SKIP_NETWORKS = {"E-GVAP"}

    with open(m3g_manifest_path) as f:
        networks = yaml.safe_load(f)

    all_stations: dict[str, dict] = {}
    cached_networks = set()
    cache: dict[str, list] = {}

    # Load from the consolidated cache first
    if cache_file.exists():
        with open(cache_file) as f:
            cache = json.load(f)
        for network, features in cache.items():
            cached_networks.add(network)
            all_stations.update(_stations_from_features(features, f"m3g_cache/{network}"))

    # Fetch remaining from API
    fetched = 0
    failed = []
    for network in networks:
        nid = network["id"]
        safe = nid.replace(" ", "_").replace("/", "_")
        if safe in cached_networks:
            continue
        if nid in SKIP_NETWORKS:
            logger.info("Skipping %s (known-large non-CORS network)", nid)
            continue
        logger.info("Fetching M3G network: %s", nid)
        try:
            stations = fetch_m3g_network_stations(nid)
            all_stations.update(stations)
            fetched += 1

            # Store as GeoJSON features in the consolidated cache
            if stations:
                cache[safe] = [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [info["lon"], info["lat"]],
                        },
                        "properties": {"id": code.upper() + "0000"},
                    }
                    for code, info in stations.items()
                ]
        except Exception as e:
            failed.append(nid)
            logger.warning("Failed to fetch %s: %s", nid, e)

    if fetched:
        with open(cache_file, "w") as f:
            json.dump(cache, f)

    logger.info(
        "M3G: loaded from %d cached networks, fetched %d live, %d failed",
        len(cached_networks),
        fetched,
        len(failed),
    )
    if failed:
        logger.warning("Failed M3G networks: %s", ", ".join(failed))

    return all_stations


# ──────────────────────────────────────────────────────────────────────
# 3. Build master index and find gaps
# ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 72)
    print("Non-EarthScope GNSS Station Coordinate Audit")
    print("=" * 72)

    # ── Load all local catalogs ──────────────────────────────────────
    master_index: dict[str, dict] = {}  # site_code -> {lat, lon, source}

    cors_yaml = load_yaml_stations(CONFIGS / "cors_stations.yaml")
    igs_yaml = load_yaml_stations(CONFIGS / "igs_stations.yaml")
    rbmc_yaml = load_yaml_stations(CONFIGS / "rbmc_stations.yaml")

    for label, catalog in [
        ("CORS YAML", cors_yaml),
        ("IGS YAML", igs_yaml),
        ("RBMC YAML", rbmc_yaml),
    ]:
        before = len(master_index)
        master_index.update(catalog)
        print(f"  Loaded {label}: {len(catalog)} stations (+{len(master_index) - before} new)")

    # ── Load M3G cache ──────────────────────────────────────────────
    m3g_cache = load_m3g_cache(GPM_DEFAULTS / "m3g" / "m3g_cache.json")
    before = len(master_index)
    master_index.update(m3g_cache)
    print(f"  Loaded M3G cache: {len(m3g_cache)} stations (+{len(master_index) - before} new)")

    print(f"\n  Total indexed stations with lat/lon: {len(master_index)}")
    print()

    # ── Fetch live station lists from servers ───────────────────────
    print("-" * 72)
    print("Querying live servers for station inventories...")
    print("-" * 72)

    # All station codes seen on non-EarthScope servers, keyed by network
    server_stations: dict[str, set[str]] = {}

    # CORS — already fully indexed via YAML, just verify
    server_stations["CORS"] = set(cors_yaml.keys())

    # IGS — from YAML
    server_stations["IGS"] = set(igs_yaml.keys())

    # RBMC — from YAML
    server_stations["RBMC"] = set(rbmc_yaml.keys())

    # GeoNet NZ — live S3 query
    server_stations["GeoNet_NZ"] = fetch_geonet_stations()

    # IBGE — live FTP query
    server_stations["IBGE"] = fetch_ibge_stations()

    # M3G — fetch all 95 networks (uses cache first)
    print("\nFetching M3G networks (95 total, using cache where available)...")
    m3g_all = fetch_all_m3g_stations(
        CONFIGS / "m3g_networks.yaml",
        GPM_DEFAULTS / "m3g" / "m3g_cache.json",
    )
    # Update master index with any new M3G stations
    before = len(master_index)
    master_index.update(m3g_all)
    print(f"  M3G total: {len(m3g_all)} unique stations (+{len(master_index) - before} new)")
    server_stations["M3G"] = set(m3g_all.keys())

    # ── Cross-reference ─────────────────────────────────────────────
    print()
    print("=" * 72)
    print("RESULTS")
    print("=" * 72)

    all_server_codes: set[str] = set()
    for codes in server_stations.values():
        all_server_codes |= codes

    missing: dict[str, list[str]] = defaultdict(list)  # code -> [networks]
    found: dict[str, list[str]] = defaultdict(list)

    for network, codes in sorted(server_stations.items()):
        net_missing = 0
        for code in sorted(codes):
            if code in master_index:
                found[code].append(network)
            else:
                missing[code].append(network)
                net_missing += 1
        total = len(codes)
        indexed = total - net_missing
        pct = (indexed / total * 100) if total else 0
        print(
            f"  {network:15s}: {total:5d} stations, {indexed:5d} indexed ({pct:.1f}%), {net_missing:4d} MISSING"
        )

    print()
    total_unique = len(all_server_codes)
    total_indexed = sum(1 for c in all_server_codes if c in master_index)
    total_missing = total_unique - total_indexed
    print(f"  TOTAL unique station codes across all servers: {total_unique}")
    print(f"  Stations WITH lat/lon in spatial index:        {total_indexed}")
    print(f"  Stations MISSING lat/lon:                      {total_missing}")

    # ── Detailed missing list ───────────────────────────────────────
    if missing:
        print()
        print("=" * 72)
        print("STATIONS MISSING LAT/LON (by network)")
        print("=" * 72)

        by_network: dict[str, list[str]] = defaultdict(list)
        for code, networks in sorted(missing.items()):
            for net in networks:
                by_network[net].append(code)

        for network in sorted(by_network.keys()):
            codes = sorted(by_network[network])
            print(f"\n  {network} ({len(codes)} stations):")
            for i in range(0, len(codes), 10):
                chunk = codes[i : i + 10]
                print(f"    {', '.join(chunk)}")

    # ── Write missing list to file ──────────────────────────────────
    output_path = ROOT / "dev" / "missing_station_coordinates.txt"
    with open(output_path, "w") as f:
        f.write("# Non-EarthScope stations MISSING lat/lon in spatial indexes\n")
        f.write("# Generated by audit_station_coordinates.py\n")
        f.write(f"# Total missing: {total_missing}\n\n")

        f.write(f"{'site_code':<12s} {'networks'}\n")
        f.write("-" * 60 + "\n")
        for code in sorted(missing.keys()):
            networks = ", ".join(sorted(missing[code]))
            f.write(f"{code:<12s} {networks}\n")

    print(f"\n  Written missing stations list to: {output_path.relative_to(ROOT)}")

    # ── Also output stations with coordinates for verification ──────
    coords_path = ROOT / "dev" / "all_station_coordinates.csv"
    with open(coords_path, "w") as f:
        f.write("site_code,lat,lon,source\n")
        for code in sorted(master_index.keys()):
            info = master_index[code]
            f.write(f"{code},{info['lat']},{info['lon']},{info['source']}\n")

    print(f"  Written all indexed coordinates to: {coords_path.relative_to(ROOT)}")
    print()


if __name__ == "__main__":
    main()
