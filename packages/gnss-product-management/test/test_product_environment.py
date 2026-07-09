"""Tests for ProductRegistry — construction, build, and classify."""

from pathlib import Path

import pytest
from gnss_product_management.factories import ProductRegistry
from gpm_specs.configs import (
    CENTERS_RESOURCE_DIR,
    FORMAT_SPEC_YAML,
    META_SPEC_YAML,
    PRODUCT_SPEC_YAML,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def env():
    """A fully built ProductRegistry with all bundled specs."""
    e = ProductRegistry()
    e.add_parameter_spec(META_SPEC_YAML)
    e.add_format_spec(FORMAT_SPEC_YAML)
    e.add_product_spec(PRODUCT_SPEC_YAML)
    for path in Path(CENTERS_RESOURCE_DIR).glob("*.yaml"):
        e.add_resource_spec(path)
    e.build()
    return e


# ── Construction ──────────────────────────────────────────────────


class TestIncrementalConstruction:
    """Environment built via add_*() + build()."""

    def test_has_product_catalog(self, env):
        assert env._product_catalog is not None
        assert len(env._product_catalog.products) > 0

    def test_has_parameter_catalog(self, env):
        assert env._parameter_catalog is not None
        assert len(env._parameter_catalog.parameters) > 0

    def test_has_format_catalog(self, env):
        assert env._format_catalog is not None

    def test_has_remote_resource_factory(self, env):
        assert env._catalogs is not None

    def test_duplicate_parameter_spec_raises(self):
        e = ProductRegistry()
        e.add_parameter_spec(META_SPEC_YAML)
        with pytest.raises(AssertionError, match="already exists"):
            e.add_parameter_spec(META_SPEC_YAML)

    def test_duplicate_format_spec_raises(self):
        e = ProductRegistry()
        e.add_format_spec(FORMAT_SPEC_YAML)
        with pytest.raises(AssertionError, match="already exists"):
            e.add_format_spec(FORMAT_SPEC_YAML)

    def test_nonexistent_spec_raises(self):
        e = ProductRegistry()
        with pytest.raises(AssertionError, match="not found"):
            e.add_parameter_spec("/nonexistent/path.yaml")


# ── Classify ──────────────────────────────────────────────────────


class TestClassify:
    """classify() parses filenames into product metadata dicts."""

    @pytest.mark.parametrize(
        "filename, expected_product, expected_params",
        [
            (
                "WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz",
                "ORBIT",
                {
                    "AAA": "WUM",
                    "TTT": "FIN",
                    "CNT": "ORB",
                    "FMT": "SP3",
                    "YYYY": "2024",
                },
            ),
            (
                "COD0OPSRAP_20251000000_01D_30S_CLK.CLK.gz",
                "CLOCK",
                {"AAA": "COD", "TTT": "RAP", "CNT": "CLK", "FMT": "CLK"},
            ),
            (
                "GFZ0OPSRAP_20251000000_01D_01D_ERP.ERP.gz",
                "ERP",
                {"AAA": "GFZ", "TTT": "RAP", "CNT": "ERP", "FMT": "ERP"},
            ),
            (
                "WUM0MGXFIN_20240010000_01D_01D_OSB.BIA.gz",
                "BIA",
                {"AAA": "WUM", "TTT": "FIN", "CNT": "OSB", "FMT": "BIA"},
            ),
            ("igs20.atx", "ATTATX", {"REFFRAME": "igs20"}),
        ],
    )
    def test_classify_product(self, env, filename, expected_product, expected_params):
        result = env.classify(filename)
        assert result is not None
        assert result["product"] == expected_product
        for key, val in expected_params.items():
            assert result["parameters"][key] == val

    def test_classify_returns_dict_shape(self, env):
        result = env.classify("WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz")
        assert isinstance(result, dict)
        assert "product" in result
        assert "format" in result
        assert "version" in result
        assert "variant" in result
        assert "parameters" in result
        assert result["format"] == "PRODUCT"
        assert result["version"] == "1"
        assert result["variant"] == "default"

    def test_classify_returns_parameters(self, env):
        result = env.classify("WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz")
        assert result["parameters"]["AAA"] == "WUM"
        assert result["parameters"]["YYYY"] == "2024"

    def test_classify_unknown_returns_none(self, env):
        result = env.classify("totally_unknown_file.xyz")
        assert result is None

    def test_classify_uncompressed(self, env):
        result = env.classify("IGS0OPSRAP_20251000000_01D_15M_ORB.SP3")
        assert result is not None
        assert result["product"] == "ORBIT"
        assert result["parameters"]["AAA"] == "IGS"

    def test_classify_strips_path(self, env):
        result = env.classify("/data/products/WUM/WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz")
        assert result is not None
        assert result["product"] == "ORBIT"
        assert result["parameters"]["AAA"] == "WUM"

    def test_classify_with_constraint_parameters(self, env):
        from gnss_product_management.specifications.parameters.parameter import (
            Parameter,
        )

        params = [Parameter(name="CNT", value="ORB")]
        result = env.classify("WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz", parameters=params)
        assert result is not None
        assert result["product"] == "ORBIT"

    def test_classify_conflicting_parameters_returns_none(self, env):
        from gnss_product_management.specifications.parameters.parameter import (
            Parameter,
        )

        params = [Parameter(name="CNT", value="CLK")]
        result = env.classify("WUM0MGXFIN_20240010000_01D_05M_ORB.SP3.gz", parameters=params)
        assert result is None
