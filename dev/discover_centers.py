"""Probe candidate GNSS product servers and enumerate available products.

For each candidate server, this script:
  1. Connects via FTP/FTPS/HTTP (anonymous where possible)
  2. Lists the IGS GPS-week directory for a reference date
  3. Groups filenames by IGS long-name fields (AAA, CNT, TTT, FMT)
  4. Prints a summary table and a candidate YAML snippet for config authoring

Usage (from repo root):
    uv run packages/gnss-product-management/dev/discover_centers.py

Adjust PROBE_DATE and CANDIDATES as needed.  The output is informational —
paste the YAML snippets into the appropriate center config file after
verifying connectivity.

Notes:
  - Results reflect server state at the time of the run.
  - Some servers may require authentication (marked below).
  - CDDIS requires EarthData credentials in ~/.netrc.
  - Timeout is generous (30 s) to accommodate slow FTP list operations.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any

# ── IGS long filename regex ──────────────────────────────────────────────────
# Matches:  AAA V PPP TTT _ YYYY DDD HHMM _ LEN _ SMP _ CNT . FMT [.gz]
_IGS_LONG = re.compile(
    r"^(?P<AAA>[A-Z0-9]{3})"
    r"(?P<V>\d)"
    r"(?P<PPP>[A-Z0-9]{3})"
    r"(?P<TTT>[A-Z]{3})"
    r"_(?P<YYYY>\d{4})(?P<DDD>\d{3})(?P<HHMM>\d{4})"
    r"_(?P<LEN>\d{2}[DHMS])"
    r"_(?P<SMP>\d{2}[DHMS])"
    r"_(?P<CNT>[A-Z]{3})\.(?P<FMT>[A-Z0-9]{2,4})"
    r"(?:\.gz)?$",
    re.IGNORECASE,
)

# ── CNT → human-readable product type ───────────────────────────────────────
_CNT_LABEL: dict[str, str] = {
    "ORB": "ORBIT (SP3)",
    "CLK": "CLOCK (CLK)",
    "ERP": "ERP",
    "OSB": "BIAS/OSB (BIA)",
    "ATT": "ATTITUDE/OBX",
    "GIM": "IONEX/GIM",
    "TRO": "TROPOSPHERE",
    "SNX": "SINEX",
}


@dataclass
class ProductHit:
    aaa: str
    cnt: str
    ttt: str
    smp: str
    ppp: str
    fmt: str
    example: str


@dataclass
class CandidateServer:
    id: str
    name: str
    hostname: str
    protocol: str  # ftp | ftps | https
    auth_required: bool
    description: str
    # GPS-week sub-path template; use {GPSWEEK} placeholder
    directory_template: str
    # Expected AC codes as a hint for filtering (empty = accept all)
    expected_aaa: list[str] = field(default_factory=list)
    website: str = ""


# ── Candidate servers to probe ───────────────────────────────────────────────
# Add new candidates here.  Only anonymous (or .netrc-based) authentication
# is attempted; interactive login is not supported.

CANDIDATES: list[CandidateServer] = [
    # ── Currently configured ── (validate existing paths) ───────────────
    CandidateServer(
        id="ign_ftp",
        name="IGN France FTP (current)",
        hostname="ftp://igs.ign.fr",
        protocol="ftp",
        auth_required=False,
        description="IGS operational products. Already in igs_config.yaml.",
        directory_template="pub/igs/products/{GPSWEEK}/",
        expected_aaa=["IGS"],
    ),
    CandidateServer(
        id="wuhan_ftp",
        name="Wuhan University FTP (current)",
        hostname="ftp://igs.gnsswhu.cn",
        protocol="ftp",
        auth_required=False,
        description="WUM products. Already in wuhan_config.yaml.",
        directory_template="pub/gps/products/{GPSWEEK}/",
        expected_aaa=["WUM", "WMC"],
    ),
    CandidateServer(
        id="gfz_sftp",
        name="GFZ ISDC SFTP (current)",
        hostname="sftp://anonymous@isdc-data.gfz.de",
        protocol="sftp",
        auth_required=False,
        description="GFZ products. Already in gfz_config.yaml.",
        directory_template="/gnss/products/final/w{GPSWEEK}/",
        expected_aaa=["GFZ"],
    ),
    # ── New candidates ────────────────────────────────────────────────────
    CandidateServer(
        id="jpl_ftp",
        name="JPL Sideshow FTP",
        hostname="ftp://sideshow.jpl.nasa.gov",
        protocol="ftp",
        auth_required=False,
        description=(
            "JPL Jet Propulsion Laboratory — one of the 7 original IGS ACs. "
            "Produces GPS+GNSS orbits/clocks/ERP/biases. "
            "Target config: jpl_config.yaml."
        ),
        directory_template="pub/JPL_GNSS_Products/{GPSWEEK}/",
        expected_aaa=["JPL"],
        website="https://sideshow.jpl.nasa.gov/",
    ),
    CandidateServer(
        id="grgs_ftp",
        name="GRGS OMP FTP",
        hostname="ftp://tab.obs-mip.fr",
        protocol="ftp",
        auth_required=False,
        description=(
            "GRGS (Groupe de Recherche de Géodésie Spatiale) — French IGS AC. "
            "IGS product code GRG. "
            "Target config: grgs_config.yaml."
        ),
        directory_template="pub/gnss/products/final/week{GPSWEEK}/",
        expected_aaa=["GRG"],
        website="https://grgs.obs-mip.fr/",
    ),
    CandidateServer(
        id="bkg_ftp",
        name="BKG IGS Data Center FTP",
        hostname="ftp://igs.bkg.bund.de",
        protocol="ftp",
        auth_required=False,
        description=(
            "BKG (Bundesamt für Kartographie und Geodäsie) IGS Data Center. "
            "Mirrors operational IGS products and some BKG-specific solutions."
        ),
        directory_template="IGS/products/{GPSWEEK}/",
        expected_aaa=["IGS", "BKG"],
        website="https://igs.bkg.bund.de/",
    ),
    CandidateServer(
        id="nrcan_https",
        name="NRCan GNSS Products (HTTPS)",
        hostname="https://hpiers.obspm.fr",
        protocol="https",
        auth_required=False,
        description=(
            "Natural Resources Canada / NRCan. Candidate for Canadian NAD83 "
            "aligned orbit solutions. Requires path verification."
        ),
        directory_template="iers/series/online/finals.all",
        expected_aaa=["NRC"],
        website="https://webapp.geod.nrcan.gc.ca/",
    ),
]

# ── Date to use for probing ──────────────────────────────────────────────────
# Use a date 30+ days ago to ensure final products are available.
PROBE_DATE = datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc)


def _gps_week(dt: datetime.datetime) -> int:
    """Compute GPS week number for a datetime."""
    gps_epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc)
    delta = dt - gps_epoch
    return delta.days // 7


def _fill_template(template: str, dt: datetime.datetime) -> str:
    week = _gps_week(dt)
    return (
        template.replace("{GPSWEEK}", str(week))
        .replace("{YYYY}", str(dt.year))
        .replace("{DDD}", f"{dt.timetuple().tm_yday:03d}")
    )


def _probe_ftp(server: CandidateServer, directory: str) -> list[str]:
    """List an FTP directory, returning bare filenames."""
    try:
        import fsspec  # noqa: PLC0415
    except ImportError:
        print("  [SKIP] fsspec not installed — run: uv add fsspec")
        return []

    url = server.hostname.rstrip("/") + "/" + directory.lstrip("/")
    try:
        if server.protocol == "ftps":
            fs = fsspec.filesystem("ftp", host=url.split("/")[2], ssl=True)
        else:
            fs = fsspec.filesystem("ftp", host=server.hostname.split("//")[-1])

        path = "/" + directory.lstrip("/")
        entries: list[Any] = fs.ls(path, detail=False)
        return [e.split("/")[-1] for e in entries]

    except Exception as exc:
        print(f"  [ERR ] {type(exc).__name__}: {exc}")
        return []


def _probe_https(server: CandidateServer, directory: str) -> list[str]:
    """Attempt a simple HTTP GET to verify reachability (not a directory listing)."""
    try:
        import urllib.request  # noqa: PLC0415

        url = server.hostname.rstrip("/") + "/" + directory.lstrip("/")
        req = urllib.request.Request(url, headers={"User-Agent": "GNSSommelier/probe"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"  [OK  ] HTTP {resp.status} — {url}")
        return []
    except Exception as exc:
        print(f"  [ERR ] {type(exc).__name__}: {exc}")
        return []


def parse_filenames(names: list[str]) -> list[ProductHit]:
    hits: list[ProductHit] = []
    for name in names:
        m = _IGS_LONG.match(name)
        if m:
            hits.append(
                ProductHit(
                    aaa=m.group("AAA").upper(),
                    cnt=m.group("CNT").upper(),
                    ttt=m.group("TTT").upper(),
                    smp=m.group("SMP").upper(),
                    ppp=m.group("PPP").upper(),
                    fmt=m.group("FMT").upper(),
                    example=name,
                )
            )
    return hits


def summarise(server: CandidateServer, hits: list[ProductHit]) -> None:
    if not hits:
        print("  No IGS long-format files found.")
        return

    # Group by (AAA, CNT)
    groups: dict[tuple[str, str], list[ProductHit]] = {}
    for h in hits:
        key = (h.aaa, h.cnt)
        groups.setdefault(key, []).append(h)

    aaa_set = sorted({h.aaa for h in hits})
    print(f"  Found {len(hits)} IGS long-format files  |  ACs: {', '.join(aaa_set)}")
    print()

    for (aaa, cnt), group in sorted(groups.items()):
        label = _CNT_LABEL.get(cnt, cnt)
        ttt_vals = sorted({h.ttt for h in group})
        smp_vals = sorted({h.smp for h in group})
        ppp_vals = sorted({h.ppp for h in group})
        print(
            f"    {aaa:4s}  {label:<24s}  TTT:{','.join(ttt_vals):<12s}"
            f"  SMP:{','.join(smp_vals):<12s}  PPP:{','.join(ppp_vals)}"
        )
        print(f"          example: {group[0].example}")

    # YAML snippet
    print()
    print("  ── YAML snippet (paste into center config) ──────────────────")

    template_pattern = server.directory_template.replace("{GPSWEEK}", "{GPSWEEK}")

    groups_by_product: dict[str, list[ProductHit]] = {}
    _CNT_TO_SPEC = {
        "ORB": "ORBIT",
        "CLK": "CLOCK",
        "ERP": "ERP",
        "OSB": "BIA",
        "ATT": "ATTOBX",
        "GIM": "IONEX",
    }
    for h in hits:
        spec = _CNT_TO_SPEC.get(h.cnt)
        if spec:
            groups_by_product.setdefault(spec, []).append(h)

    for spec, group in sorted(groups_by_product.items()):
        aaa_vals = sorted({h.aaa for h in group})
        ttt_vals = sorted({h.ttt for h in group})
        ppp_vals = sorted({h.ppp for h in group})
        smp_vals = sorted({h.smp for h in group})
        slug = server.id.split("_")[0]
        print(f"  - id: {slug}_{spec.lower()}")
        print(f"    product_name: {spec}")
        print(f"    server_id: {server.id}")
        print("    available: true")
        print("    parameters:")
        for v in aaa_vals:
            print(f"      - {{name: AAA, value: {v}}}")
        for v in ttt_vals:
            print(f"      - {{name: TTT, value: {v}}}")
        for v in ppp_vals:
            print(f"      - {{name: PPP, value: {v}}}")
        for v in smp_vals:
            print(f"      - {{name: SMP, value: {v}}}")
        print(f'    directory: {{pattern: "{template_pattern}"}}')
        print()


def main() -> None:
    dt = PROBE_DATE
    gpsweek = _gps_week(dt)
    print(
        f"Probing GNSS product servers\n"
        f"  Reference date : {dt.date()}  (GPS week {gpsweek})\n"
        f"  Servers to probe: {len(CANDIDATES)}\n"
    )

    for server in CANDIDATES:
        print(f"{'=' * 70}")
        print(f"  {server.name}")
        if server.website:
            print(f"  {server.website}")
        print(f"  {server.hostname}  [{server.protocol.upper()}]")
        print(f"  {server.description}")
        print()

        directory = _fill_template(server.directory_template, dt)
        print(f"  Probing: {server.hostname}/{directory}")

        if server.protocol in ("ftp", "ftps"):
            names = _probe_ftp(server, directory)
        elif server.protocol == "https":
            _probe_https(server, directory)
            names = []
        else:
            print(f"  [SKIP] Unsupported protocol: {server.protocol}")
            names = []

        if names:
            hits = parse_filenames(names)
            hits_filtered = (
                [h for h in hits if h.aaa in server.expected_aaa] if server.expected_aaa else hits
            )
            summarise(server, hits_filtered or hits)
        print()

    print("Done. Add or update center YAML configs in:")
    print("  packages/gpm-specs/src/gpm_specs/configs/centers/")


if __name__ == "__main__":
    main()
