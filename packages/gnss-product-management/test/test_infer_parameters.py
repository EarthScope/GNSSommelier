"""Tests for infer_from_regex — reverse-parsing filenames via FormatRegistry."""

import pytest
from gnss_product_management.specifications.format.spec import (
    FormatRegistry,
    FormatSpecCollection,
)
from gnss_product_management.specifications.parameters.parameter import (
    Parameter,
    ParameterCatalog,
)
from gnss_product_management.specifications.products.product import (
    PathTemplate,
    infer_from_regex,
)

# ── Paths ──────────────────────────────────────────────────────────
from gpm_specs.configs import FORMAT_SPEC_YAML, META_SPEC_YAML

# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def parameter_catalog() -> ParameterCatalog:
    return ParameterCatalog.from_yaml(META_SPEC_YAML)


@pytest.fixture(scope="module")
def format_catalog(parameter_catalog) -> FormatRegistry:
    fsc = FormatSpecCollection.from_yaml(FORMAT_SPEC_YAML)
    return FormatRegistry.build(fsc, parameter_catalog)


def _build_regex_and_params(
    format_catalog: FormatRegistry,
    format_name: str,
    version: str,
    variant: str,
    **overrides: str,
) -> tuple[str, list[Parameter]]:
    """Build a derived regex and parameter list from a FormatCatalog entry.

    Simulates what SearchPlanner does: starts from the template, fills in
    *overrides* as concrete values and leaves the rest as their regex
    patterns, then derives to produce the final regex string.

    Returns ``(regex, parameters)`` — both ready for ``infer_from_regex``.
    """
    ver = format_catalog.get_version(format_name, version)
    template = ver.file_templates[variant]
    params: list[Parameter] = []
    for name, field in ver.metadata.items():
        if field is None or not field.pattern:
            continue
        value = overrides.get(name, field.pattern)
        params.append(Parameter(name=name, value=value, pattern=field.pattern))
    pp = PathTemplate(pattern=template)
    pp.derive(params)
    return pp.pattern, params


# ── PRODUCT/1/default ──────────────────────────────────────────────


class TestProductDefaultInfer:
    """Infer parameters from PRODUCT v1 default-variant filenames."""

    def test_standard_orbit_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="WUM",
            PPP="MGX",
            TTT="FIN",
            YYYY="2024",
            DDD="001",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="05M",
            CNT="ORB",
            FMT="SP3",
        )
        result = infer_from_regex(regex, "WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["AAA"] == "WUM"
        assert values["V"] == "0"
        assert values["PPP"] == "MGX"
        assert values["TTT"] == "FIN"
        assert values["YYYY"] == "2024"
        assert values["DDD"] == "001"
        assert values["HH"] == "00"
        assert values["MM"] == "00"
        assert values["LEN"] == "01D"
        assert values["SMP"] == "05M"
        assert values["CNT"] == "ORB"
        assert values["FMT"] == "SP3"

    def test_clock_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="COD",
            PPP="OPS",
            TTT="RAP",
            YYYY="2025",
            DDD="100",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="30S",
            CNT="CLK",
            FMT="CLK",
        )
        result = infer_from_regex(regex, "COD0OPSRAP_20251000000_01D_30S_CLK.CLK.gz", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["AAA"] == "COD"
        assert values["TTT"] == "RAP"
        assert values["CNT"] == "CLK"
        assert values["SMP"] == "30S"

    def test_uncompressed_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="IGS",
            PPP="OPS",
            TTT="RAP",
            YYYY="2025",
            DDD="100",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="15M",
            CNT="ORB",
            FMT="SP3",
        )
        result = infer_from_regex(regex, "IGS0OPSRAP_20251000000_01D_15M_ORB.SP3", params)
        assert result is not None
        assert next(p for p in result if p.name == "AAA").value == "IGS"

    def test_no_match_returns_none(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="WUM",
            PPP="MGX",
            TTT="FIN",
            YYYY="2024",
            DDD="001",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="05M",
            CNT="ORB",
            FMT="SP3",
        )
        assert infer_from_regex(regex, "garbage_file.txt", params) is None

    def test_bias_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="WUM",
            PPP="MGX",
            TTT="FIN",
            YYYY="2024",
            DDD="001",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="01D",
            CNT="ABS",
            FMT="BIA",
        )
        result = infer_from_regex(regex, "WUM0MGXFIN_20240010000_01D_01D_ABS.BIA.gz", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["CNT"] == "ABS"
        assert values["FMT"] == "BIA"

    def test_erp_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "PRODUCT",
            "1",
            "default",
            AAA="GFZ",
            PPP="OPS",
            TTT="RAP",
            YYYY="2025",
            DDD="100",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="01D",
            CNT="ERP",
            FMT="ERP",
        )
        result = infer_from_regex(regex, "GFZ0OPSRAP_20251000000_01D_01D_ERP.ERP.gz", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["AAA"] == "GFZ"
        assert values["CNT"] == "ERP"
        assert values["FMT"] == "ERP"


# ── ANTENNAE/1 ─────────────────────────────────────────────────────


class TestAntennaeInfer:
    def test_default_variant(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "ANTENNAE",
            "1",
            "default",
            REFFRAME="igs20",
        )
        result = infer_from_regex(regex, "igs20.atx", params)
        assert result is not None
        assert next(p for p in result if p.name == "REFFRAME").value == "igs20"

    def test_archive_variant_with_gpsweek(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "ANTENNAE",
            "1",
            "archive",
            REFFRAME="igs20",
            GPSWEEK="2345",
        )
        result = infer_from_regex(regex, "igs20_2345.atx", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["REFFRAME"] == "igs20"
        assert values["GPSWEEK"] == "2345"


# ── VIENNA_MAPPING_FUNCTIONS/1 ─────────────────────────────────────


class TestVMFInfer:
    def test_default_vmf_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "VIENNA_MAPPING_FUNCTIONS",
            "1",
            "default",
            PRODUCT="VMF3",
            YYYY="2025",
            MONTH="01",
            DAY="15",
            VMFHH="H06",
        )
        result = infer_from_regex(regex, "VMF3_20250115.H06", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["PRODUCT"] == "VMF3"
        assert values["YYYY"] == "2025"
        assert values["MONTH"] == "01"
        assert values["DAY"] == "15"
        assert values["VMFHH"] == "H06"

    def test_orography_variant(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "VIENNA_MAPPING_FUNCTIONS",
            "1",
            "orography",
            RESOLUTION="5x5",
        )
        result = infer_from_regex(regex, "orography_ell_5x5", params)
        assert result is not None
        assert next(p for p in result if p.name == "RESOLUTION").value == "5x5"


# ── RINEX/2 ────────────────────────────────────────────────────────


class TestRinex2Infer:
    def test_observation_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "RINEX",
            "2",
            "observation",
            SSSS="ALIC",
            DDD="015",
            YY="25",
            T="o",
        )
        result = infer_from_regex(regex, "ALIC0150.25o", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["SSSS"] == "ALIC"
        assert values["DDD"] == "015"
        assert values["YY"] == "25"
        assert values["T"] == "o"

    def test_navigation_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "RINEX",
            "2",
            "navigation",
            SSSS="BRST",
            DDD="015",
            YY="25",
            T="n",
        )
        result = infer_from_regex(regex, "BRST0150.25n", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["SSSS"] == "BRST"
        assert values["T"] == "n"


# ── RINEX/3 ────────────────────────────────────────────────────────


class TestRinex3Infer:
    def test_observation_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "RINEX",
            "3",
            "observation",
            SSSS="ALIC",
            MONUMENT="0",
            R="0",
            CCC="AUS",
            S="R",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            DDU="01D",
            FRU="30S",
            D="M",
        )
        result = infer_from_regex(regex, "ALIC00AUS_R_20250150000_01D_30S_MO.rnx", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["SSSS"] == "ALIC"
        assert values["MONUMENT"] == "0"
        assert values["R"] == "0"
        assert values["CCC"] == "AUS"
        assert values["S"] == "R"
        assert values["YYYY"] == "2025"
        assert values["DDD"] == "015"
        assert values["DDU"] == "01D"
        assert values["FRU"] == "30S"
        assert values["D"] == "M"

    def test_navigation_file(self, format_catalog):
        regex, params = _build_regex_and_params(
            format_catalog,
            "RINEX",
            "3",
            "navigation",
            SSSS="BRDC",
            MONUMENT="0",
            R="0",
            CCC="IGN",
            S="R",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            DDU="01D",
            D="M",
        )
        result = infer_from_regex(regex, "BRDC00IGN_R_20250150000_01D_MN.rnx", params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["SSSS"] == "BRDC"
        assert values["CCC"] == "IGN"
        assert values["D"] == "M"


# ── resource_probe.json scenarios ──────────────────────────────────


class TestResourceProbeScenarios:
    """Tests using exact regex/filename pairs from resource_probe.json."""

    @staticmethod
    def _product_params(**overrides) -> list[Parameter]:
        """Build PRODUCT/1/default parameters in template order."""
        specs = [
            ("AAA", "[a-zA-Z0-9]{3}"),
            ("V", "[0-9]"),
            ("PPP", "[A-Z0-9]{3}"),
            ("TTT", "[A-Z]{3}"),
            ("YYYY", r"\d{4}"),
            ("DDD", r"\d{3}"),
            ("HH", r"\d{2}"),
            ("MM", r"\d{2}"),
            ("LEN", r"\d{2}[DHMS]"),
            ("SMP", r"\d{2}[DHMS]"),
            ("CNT", "[A-Z]{3}"),
            ("FMT", "[A-Z0-9]{3}"),
        ]
        params = []
        for name, pattern in specs:
            value = overrides.get(name, pattern)
            params.append(Parameter(name=name, value=value, pattern=pattern))
        return params

    def test_wmc_orbit(self):
        """WMC orbit from resource_probe.json."""
        regex = r"WMC[0-9]DEMFIN_20250150000_01D_05M_ORB\.SP3.*"
        filename = "WMC0DEMFIN_20250150000_01D_05M_ORB.SP3.gz"
        params = self._product_params(
            AAA="WMC",
            PPP="DEM",
            TTT="FIN",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="05M",
            CNT="ORB",
            FMT="SP3",
        )
        result = infer_from_regex(regex, filename, params)
        assert result is not None
        assert next(p for p in result if p.name == "V").value == "0"

    def test_cod_orbit(self):
        """COD orbit from resource_probe.json."""
        regex = r"COD[0-9]OPSFIN_20250150000_01D_05M_ORB\.SP3.*"
        filename = "COD0OPSFIN_20250150000_01D_05M_ORB.SP3.gz"
        params = self._product_params(
            AAA="COD",
            PPP="OPS",
            TTT="FIN",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="05M",
            CNT="ORB",
            FMT="SP3",
        )
        result = infer_from_regex(regex, filename, params)
        assert result is not None
        assert next(p for p in result if p.name == "V").value == "0"

    def test_esa_rap_orbit(self):
        """ESA rapid orbit from resource_probe.json."""
        regex = r"ESA[0-9]OPSRAP_20250150000_01D_15M_ORB\.SP3.*"
        filename = "ESA0OPSRAP_20250150000_01D_15M_ORB.SP3.gz"
        params = self._product_params(
            AAA="ESA",
            PPP="OPS",
            TTT="RAP",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="15M",
            CNT="ORB",
            FMT="SP3",
        )
        result = infer_from_regex(regex, filename, params)
        assert result is not None
        assert next(p for p in result if p.name == "V").value == "0"
        assert next(p for p in result if p.name == "SMP").value == "15M"

    def test_all_params_inferred(self):
        """All parameters left as patterns get inferred from filename."""
        regex = r"[a-zA-Z0-9]{3}[0-9][A-Z0-9]{3}[A-Z]{3}_\d{4}\d{3}\d{2}\d{2}_\d{2}[DHMS]_\d{2}[DHMS]_[A-Z]{3}\.[A-Z0-9]{3}.*"
        filename = "COD0OPSFIN_20250150000_01D_05M_ORB.SP3.gz"
        params = self._product_params()  # all unresolved

        result = infer_from_regex(regex, filename, params)
        assert result is not None
        values = {p.name: p.value for p in result}
        assert values["AAA"] == "COD"
        assert values["V"] == "0"
        assert values["PPP"] == "OPS"
        assert values["TTT"] == "FIN"
        assert values["YYYY"] == "2025"
        assert values["DDD"] == "015"
        assert values["HH"] == "00"
        assert values["MM"] == "00"
        assert values["LEN"] == "01D"
        assert values["SMP"] == "05M"
        assert values["CNT"] == "ORB"
        assert values["FMT"] == "SP3"

    def test_no_match_returns_none(self):
        regex = r"WMC[0-9]DEMFIN_20250150000_01D_05M_ORB\.SP3.*"
        params = self._product_params(
            AAA="WMC",
            PPP="DEM",
            TTT="FIN",
            YYYY="2025",
            DDD="015",
            HH="00",
            MM="00",
            LEN="01D",
            SMP="05M",
            CNT="ORB",
            FMT="SP3",
        )
        assert infer_from_regex(regex, "totally_different.txt", params) is None
