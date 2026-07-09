# GNSS Data Center Catalog

All data centers and servers currently configured in the `gpm-specs` package.
Each center has a YAML config file under
[`packages/gpm-specs/src/gpm_specs/configs/centers/`](../packages/gpm-specs/src/gpm_specs/configs/centers/).

---

## Configured Centers

| ID | Full Name | Config File | Role |
|----|-----------|-------------|------|
| [BKG](#bkg) | Federal Agency for Cartography and Geodesy | [`bkg_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/bkg_config.yaml) | IGS Global Data Center |
| [CAS](#cas) | Chinese Academy of Sciences (GIPP) | [`cas_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/cas_config.yaml) | IGS Analysis Center |
| [CDDIS](#cddis) | NASA Crustal Dynamics Data Information System | [`cddis_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/cddis_config.yaml) | IGS Global Data Center |
| [COD](#cod) | Center for Orbit Determination in Europe (AIUB) | [`cod_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/cod_config.yaml) | IGS Analysis Center |
| [ESA](#esa) | European Space Agency / ESOC | [`esa_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/esa_config.yaml) | IGS Analysis Center |
| [EUREF](#euref) | EUREF Permanent GNSS Network (EPN) | [`euref_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/euref_config.yaml) | European Regional DC |
| [GFZ](#gfz) | GFZ German Research Centre for Geosciences | [`gfz_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/gfz_config.yaml) | IGS Analysis Center |
| [GRGS](#grgs) | Groupe de Recherche de Géodésie Spatiale (CNES/CLS) | [`grgs_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/grgs_config.yaml) | IGS Analysis Center |
| [IGS](#igs) | International GNSS Service | [`igs_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/igs_config.yaml) | IGS Combined Products |
| [JPL](#jpl) | NASA Jet Propulsion Laboratory | [`jpl_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/jpl_config.yaml) | IGS Analysis Center |
| [KASI](#kasi) | Korea Astronomy and Space Science Institute | [`kasi_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/kasi_config.yaml) | IGS Global Data Center |
| [NGII](#ngii) | National Geographic Information Institute (Korea) | [`ngii_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/ngii_config.yaml) | IGS Regional Data Center |
| [NRCan](#nrcan) | Natural Resources Canada (CSRS) | [`nrcan_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/nrcan_config.yaml) | IGS Analysis Center |
| [TUG](#tug) | Graz University of Technology (ITSG) | [`tug_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/tug_config.yaml) | IGS Analysis Center |
| [VMF](#vmf) | TU Wien — Vienna Mapping Functions | [`vmf_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/vmf_config.yaml) | Troposphere Products |
| [WUM](#wum) | Wuhan University GNSS Research Center | [`wuhan_config.yaml`](../packages/gpm-specs/src/gpm_specs/configs/centers/wuhan_config.yaml) | IGS Analysis Center |

---

## Server Reference

The table below lists every server endpoint configured across all centers.

| Center | Server ID | Hostname | Protocol | Auth | Products Served |
|--------|-----------|----------|----------|------|-----------------|
| BKG | `bkg_https` | `https://igs.bkg.bund.de` | HTTPS | None | ORBIT, CLOCK, ERP, BIA, IONEX, SINEX, RNX3_BRDC |
| CAS | `cas_gipp_ftp` | `ftp://ftp.gipp.org.cn` | FTP | None | IONEX, BIA |
| CDDIS | `cddis_ftps` | `ftp://gdc.cddis.eosdis.nasa.gov` | FTPS (anon) | None | ORBIT, CLOCK, ERP, BIA, SINEX, IONEX, ATTOBX, TROP, RNX3_BRDC |
| COD | `code_ftp` | `ftp://ftp.aiub.unibe.ch` | FTP | None | ORBIT, CLOCK, ERP, BIA, IONEX, SINEX, TROP |
| ESA | `esa_ftp` | `ftp://gssc.esa.int` | FTP | None | ORBIT, CLOCK, ERP, BIA, IONEX, SINEX |
| EUREF | `euref_https` | `https://epncb.oma.be` | HTTPS | None | SINEX (ETRS89 station coords) |
| GA | `ga_s3` | `https://ga-gnss-products-v1.s3.amazonaws.com` | HTTPS (S3) | None | SINEX (APREF), ORBIT†, CLOCK†, ERP† |
| GFZ | `gfz_sftp` | `sftp://anonymous@isdc-data.gfz.de` | SFTP | Anonymous (`anonymous` / `anonymous@isdc-data.gfz.de`) | ORBIT, CLOCK, ERP, SINEX, TROP |
| GRGS | `grgs_ftp` | `ftp://ftpsedr.cls.fr` | FTP | None | ORBIT, CLOCK, ERP, BIA, SINEX, ATTOBX |
| IGS | `ign_ftp` | `ftp://igs.ign.fr` | FTP | None | ORBIT, CLOCK, ERP, BIA, ATTOBX, IONEX, SINEX, TROP, RNX3_BRDC |
| IGS | `igs_http` | `https://files.igs.org` | HTTPS | None | ANTEX (ATX), station logs |
| JPL | `jpl_sideshow` | `https://sideshow.jpl.nasa.gov` | HTTPS | None | ORBIT, CLOCK, ERP, BIA, IONEX, TROP, SINEX |
| KASI | `kasi_ftp` | `ftp://nfs.kasi.re.kr` | FTP | None | ORBIT, CLOCK, ERP, BIA, ATTOBX, SINEX, IONEX, RNX3_BRDC |
| NGII | `ngii_ftp` | `ftp://nfs.kgps.go.kr` | FTP | None* | RNX3_BRDC (all `available: false`) |
| NRCan | `nrcan_ftp` | `ftp://ftp.nrcan.gc.ca` | FTP | None | ORBIT, CLOCK, ERP, BIA, SINEX |
| SIO | `sio_ftp` | `ftp://garner.ucsd.edu` | FTP | None* | ORBIT, CLOCK, ERP, SINEX (all `available: false`) |
| TUG | `cddis_mirror` | `ftp://gdc.cddis.eosdis.nasa.gov` | FTPS (anon) | None | ORBIT, CLOCK, ERP, BIA, ATTOBX (via CDDIS) |
| VMF | `vmf_https` | `https://vmf.geo.tuwien.ac.at` | HTTPS | None | VMF1, VMF3, OROGRAPHY |
| WUM | `wuhan_ftp` | `ftp://igs.gnsswhu.cn` | FTP | None | ORBIT, CLOCK, ERP, BIA, ATTOBX, IONEX, RNX3_BRDC, LEAP_SEC, SAT_PARAMS |

\* Not accessible from outside Korea.
† Experimental Ginan products — not official IGS combined products.

---

## Center Details

### BKG

**Federal Agency for Cartography and Geodesy**
Website: <https://igs.bkg.bund.de/>

Full HTTPS mirror of the IGS combined product archive. No authentication required.
Serves IGS final, rapid, and ultra-rapid orbit/clock/ERP solutions from GPS week 1
to present, merged RINEX 3 broadcast navigation, SINEX, and ionosphere (GIM) files.
Products use AAA=`IGS`.

---

### CAS

**Chinese Academy of Sciences — GNSS Research Center (GIPP)**
Website: <http://www.gipp.org.cn/>

CAS produces Global Ionosphere Maps (GIM, AAA=`CAS`) and differential code bias
(DCB/OSB) files. Products are on the GIPP FTP server at `ftp.gipp.org.cn`.

---

### CDDIS

**NASA Crustal Dynamics Data Information System**
Website: <https://cddis.nasa.gov/>

The primary IGS Global Data Center. Hosts products from all IGS and MGEX Analysis
Centers organized in GPS-week subdirectories (`gnss/products/{GPSWEEK}/`). Requires
FTPS (explicit TLS); anonymous login with an email address. RINEX data at
`gnss/data/daily/{YYYY}/{DDD}/{YY}?/`.

---

### COD

**Center for Orbit Determination in Europe (CODE / AIUB)**
Website: <https://www.aiub.unibe.ch/research/gnss/>

CODE is one of the original seven IGS Analysis Centers. Produces precise orbits,
clocks, ERP, ionosphere maps (one of the primary GIM producers), signal biases, and
troposphere delay products. AC code `COD`. FTP at `ftp.aiub.unibe.ch`.

---

### ESA

**European Space Agency / ESOC**
Website: <https://navigation.esa.int/>

ESA/ESOC produces precise orbits, clocks, ERP, biases, and GIM products (AC code
`ESA`). ESA uses `CNT=BIA` instead of `CNT=OSB` in long filenames. FTP at
`gssc.esa.int`.

---

### EUREF

**EUREF Permanent GNSS Network (EPN)**
Website: <https://epncb.oma.be/>

EPN is a European regional GNSS reference station network coordinated by the Royal
Observatory of Belgium. Provides RINEX observation data from 400+ European
stations and weekly SINEX coordinate solutions in ETRS89. HTTPS only — no FTP.
Does **not** host IGS combined orbit/clock products.

---

### GA

**Geoscience Australia**
Website: <https://www.ga.gov.au/scientific-topics/positioning-navigation/geodesy>

IGS Regional Data Center for the Asia-Pacific region. Hosts the Australian Regional
GNSS Network (ARGN) and APREF SINEX coordinate solutions. Also publishes
experimental orbit/clock/ERP products from the open-source
[Ginan](https://github.com/GeoscienceAustralia/ginan) software (AC code `GAG`).
Served over public AWS S3 / HTTPS.

---

### GFZ

**GFZ German Research Centre for Geosciences (Potsdam)**
Website: <https://www.gfz-potsdam.de/>

GFZ publishes OPS-only precise orbit, clock, ERP, troposphere, and SINEX
products at `isdc-data.gfz.de/gnss/products/`, organized into `final/`,
`rapid/`, and `ultra/` weekly archives. The service is reachable via anonymous
SFTP (`anonymous` / `anonymous@isdc-data.gfz.de`). GFZ does not publish bias
files on this endpoint — use CDDIS or KASI mirrors instead.

---

### GRGS

**Groupe de Recherche de Géodésie Spatiale (CNES/CLS)**
Website: <https://igsac-cnes.cls.fr/>

GRGS is a French IGS Analysis Center (AC code `GRG`). Produces precise orbits,
clocks, ERP, signal biases, and attitude ORBEX files. Orbits, clocks, and
attitude files must be used together as radial orbit and attitude differences
are compensated in the clock products. FTP at `ftpsedr.cls.fr`.

---

### IGS

**International GNSS Service — combined products**
Website: <https://www.igs.org/>

The IGS Combined Products (AAA=`IGS`) are produced by the Analysis Center
Coordinator and distributed via IGN France FTP (`igs.ign.fr`) and mirrored at
CDDIS, BKG, and KASI. The `files.igs.org` HTTPS server hosts supplementary files
such as ANTEX antenna calibrations.

---

### JPL

**NASA Jet Propulsion Laboratory**
Website: <https://sideshow.jpl.nasa.gov/>

JPL is one of the original seven IGS Analysis Centers (AC code `JPL`). Products
include orbit, clock, ERP, bias, ionosphere (GIM), troposphere, and SINEX. Available
via HTTPS at `sideshow.jpl.nasa.gov/pub/jpligsac/{GPSWEEK}/`.

---

### KASI

**Korea Astronomy and Space Science Institute**
Website: <https://gnss.kasi.re.kr/>

KASI is an IGS Global Data Center providing a comprehensive full-parity FTP mirror
of IGS and MGEX products from all major Analysis Centers (`nfs.kasi.re.kr`).
Products are organized under `gnss/products/{GPSWEEK}/`. KASI is a reliable
alternative/fallback to CDDIS when FTPS access is not available.

---

### NGII

**National Geographic Information Institute (Korea)**
Website: <https://www.ngii.go.kr/>

IGS Regional Data Center for the Korean GNSS network (KGPS). Hosts RINEX
observation data from Korean CORS stations. The FTP server (`nfs.kgps.go.kr`) is
not accessible from outside Korea. All products are marked `available: false`.
For Korea-region IGS products use KASI instead.

---

### NRCan

**Natural Resources Canada — Canadian Spatial Reference System (CSRS)**
Website: <https://webapp.geod.nrcan.gc.ca/>

NRCan is an IGS Analysis Center (AC code `EMR`). Produces precise orbits, clocks,
ERP, biases, and SINEX solutions for the North American region. FTP at
`ftp.nrcan.gc.ca` under `gnss/products/{GPSWEEK}/`.

---

### SIO

**Scripps Institution of Oceanography / SOPAC**
Website: <https://sopac-csrc.ucsd.edu/>

SIO operated as an IGS Global Data Center and Analysis Center under the SOPAC
program until its absorption into EarthScope/UNAVCO in 2020. The historical FTP
at `garner.ucsd.edu` is no longer operational. SIO continues to contribute as an
IGS Analysis Center (AC code `SIO0`) — its products are available via KASI, CDDIS,
and BKG mirrors. All products in this config are marked `available: false`.

---

### TUG

**Graz University of Technology (ITSG)**
Website: <https://www.tugraz.at/institute/ifg/>

TUG (ITSG) is an IGS Associate Analysis Center producing GNSS orbit, clock, ERP,
and SINEX products (AC code `TUG`). Products are not hosted on a dedicated TUG
server — they are distributed via CDDIS under `gnss/products/{GPSWEEK}/`.

---

### VMF

**TU Wien — Vienna Mapping Functions**
Website: <https://vmf.geo.tuwien.ac.at/>

TU Wien hosts the Vienna Mapping Functions (VMF1 and VMF3) numerical troposphere
grids used for precise GNSS data reduction. Served over HTTPS at
`vmf.geo.tuwien.ac.at`. Products include VMF1 (2.5×2° grid), VMF3 (1×1° and 5×5°
grids), and the orography height grids required for interpolation.

---

### WUM

**Wuhan University GNSS Research Center**
Website: <http://www.igs.gnsswhu.cn/>

Wuhan University is an IGS Analysis Center (AC codes `WUM`, `WMC`) contributing
GNSS orbit, clock, and ERP products. FTP at `igs.gnsswhu.cn`. Products organized
under `pub/gps/products/{GPSWEEK}/` (weekly) and `pub/whu/phasebias/{YYYY}/orbit/`
(phase-bias orbit products).
