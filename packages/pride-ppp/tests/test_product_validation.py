from __future__ import annotations

from pathlib import Path

from gnss_product_management.specifications.dependencies.dependencies import (
    DependencyResolution,
    ResolvedDependency,
)
from pride_ppp.factories.product_validation import (
    bias_phase_bands,
    bias_phase_observables,
    rinex_phase_bands,
    rinex_phase_observables,
    validate_pride_products,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_phase_band_parsers_cover_all_observed_constellations(tmp_path: Path) -> None:
    rinex = _write(
        tmp_path / "obs.rnx",
        "G    4 C1C L1C C2W L2W                              SYS / # / OBS TYPES\n"
        "E    6 C1C L1C C7Q L7Q C5Q                          SYS / # / OBS TYPES\n"
        "       L5Q                                              SYS / # / OBS TYPES\n"
        "                                                            END OF HEADER\n",
    )
    bias = _write(
        tmp_path / "test.BIA",
        "+BIAS/SOLUTION\n"
        " OSB  G01           L1C  2026:001:00000 2026:002:00000 ns 0.0\n"
        " OSB  G01           L2W  2026:001:00000 2026:002:00000 ns 0.0\n"
        " OSB  E01           L1C  2026:001:00000 2026:002:00000 ns 0.0\n"
        "-BIAS/SOLUTION\n",
    )

    assert rinex_phase_bands([rinex]) == {"G": {"1", "2"}, "E": {"1", "5", "7"}}
    assert bias_phase_bands(bias) == {"G": {"1", "2"}, "E": {"1"}}
    assert rinex_phase_observables([rinex])["E"] == {"L1C", "L5Q", "L7Q"}
    assert bias_phase_observables(bias)["E"] == {"L1C"}


def test_validation_is_advisory_and_reports_partial_coverage(tmp_path: Path) -> None:
    rinex = _write(
        tmp_path / "obs.rnx",
        "E    4 C1C L1C C7Q L7Q                              SYS / # / OBS TYPES\n"
        "  2026     8    18     0     0    0.0000000     GPS         TIME OF FIRST OBS\n"
        "  2026     8    18    23    59   30.0000000     GPS         TIME OF LAST OBS\n"
        "                                                            END OF HEADER\n",
    )
    bias = _write(
        tmp_path / "test.BIA",
        " OSB  E01           L1C  2026:230:00000 2026:231:00000 ns 0.0\n",
    )
    orbit = _write(
        tmp_path / "test.SP3",
        "*  2026  8 18  1  0  0.00000000\n*  2026  8 18 23  0  0.00000000\n",
    )
    resolution = DependencyResolution(
        spec_name="test",
        resolved=[
            ResolvedDependency(
                spec="BIA", required=True, status="downloaded", local_path=str(bias)
            ),
            ResolvedDependency(
                spec="ORBIT", required=True, status="downloaded", local_path=str(orbit)
            ),
        ],
    )

    messages = validate_pride_products([rinex], resolution, ["E17"])

    assert any("missing bands ['7']" in message for message in messages)
    assert any("ORBIT: partial epoch coverage" in message for message in messages)
    assert resolution.all_required_fulfilled


def test_missing_bias_has_one_clear_diagnostic(tmp_path: Path) -> None:
    rinex = _write(
        tmp_path / "obs.rnx",
        "E    4 C1C L1C C7Q L7Q                              SYS / # / OBS TYPES\n"
        "  2026     8    18     0     0    0.0000000     GPS         TIME OF FIRST OBS\n"
        "  2026     8    18     1     0    0.0000000     GPS         TIME OF LAST OBS\n"
        "                                                            END OF HEADER\n",
    )
    resolution = DependencyResolution(spec_name="test", resolved=[])

    messages = validate_pride_products([rinex], resolution, ["E17"])

    assert messages == ["BIA unavailable; phase-bias capability cannot be evaluated"]
