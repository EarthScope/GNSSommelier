"""Tests for pride_ppp.factories.output — kin/res parsing functions."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pride_ppp.factories.output import (
    get_wrms_from_res,
    kin_to_kin_position_df,
    validate_kin_file,
)

# ---------------------------------------------------------------------------
# kin_to_kin_position_df
# ---------------------------------------------------------------------------


class TestKinToKinPositionDf:
    """Tests for the primary .kin → DataFrame parser."""

    def test_returns_dataframe(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert isinstance(df, pd.DataFrame)

    def test_has_rows(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert len(df) > 0

    def test_expected_columns_present(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        for col in ("time", "latitude", "longitude", "height", "pdop"):
            assert col in df.columns, f"Missing column: {col}"

    def test_time_column_is_datetime(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert pd.api.types.is_datetime64_any_dtype(df["time"])

    def test_time_is_utc(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert df["time"].dt.tz is not None
        assert str(df["time"].dt.tz) == "UTC"

    def test_coordinates_are_numeric(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        for col in ("latitude", "longitude", "height"):
            assert pd.api.types.is_numeric_dtype(df[col]), f"{col} is not numeric"

    def test_latitude_in_valid_range(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert df["latitude"].between(-90, 90).all(), "Latitude out of range"

    def test_longitude_in_valid_range(self, kin_file: Path):
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert df["longitude"].between(0, 360).all(), "Longitude out of range"

    def test_wrms_column_present(self, kin_file: Path):
        """wrms column is always added (even if no .res file was found)."""
        df = kin_to_kin_position_df(kin_file)
        assert df is not None
        assert "wrms" in df.columns

    def test_raises_for_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            kin_to_kin_position_df(tmp_path / "nonexistent.kin")

    def test_returns_none_for_empty_file(self, tmp_path: Path):
        empty = tmp_path / "empty.kin"
        empty.write_text("")
        result = kin_to_kin_position_df(empty)
        assert result is None

    def test_returns_none_for_header_only_file(self, tmp_path: Path):
        """A file with a header but no data rows should return None."""
        header_only = tmp_path / "header_only.kin"
        header_only.write_text(
            "bako                                                        STATION\n"
            "                                                            END OF HEADER\n"
        )
        result = kin_to_kin_position_df(header_only)
        assert result is None


# ---------------------------------------------------------------------------
# validate_kin_file
# ---------------------------------------------------------------------------


class TestValidateKinFile:
    """Tests for validate_kin_file."""

    def test_valid_file_returns_true(self, kin_file: Path):
        assert validate_kin_file(kin_file) is True

    def test_missing_file_returns_false(self, tmp_path: Path):
        assert validate_kin_file(tmp_path / "missing.kin") is False

    def test_empty_file_returns_false(self, tmp_path: Path):
        empty = tmp_path / "empty.kin"
        empty.write_text("")
        assert validate_kin_file(empty) is False

    def test_accepts_string_path(self, kin_file: Path):
        assert validate_kin_file(str(kin_file)) is True

    def test_invalid_type_returns_false(self):
        assert validate_kin_file(12345) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_wrms_from_res
# ---------------------------------------------------------------------------


class TestGetWrmsFromRes:
    """Tests for the .res → WRMS DataFrame parser."""

    def test_returns_dataframe(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert isinstance(df, pd.DataFrame)

    def test_has_rows(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert len(df) > 0

    def test_expected_columns(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert "date" in df.columns
        assert "wrms" in df.columns

    def test_date_column_is_datetime(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_wrms_is_numeric(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert pd.api.types.is_numeric_dtype(df["wrms"])

    def test_wrms_values_are_positive(self, res_file: Path):
        df = get_wrms_from_res(res_file)
        assert (df["wrms"] >= 0).all(), "WRMS values should be non-negative"

    def test_wrms_values_in_mm_range(self, res_file: Path):
        """WRMS in mm — typical GNSS phase residuals are sub-centimetre."""
        df = get_wrms_from_res(res_file)
        assert (df["wrms"] < 1000).all(), "WRMS suspiciously large (> 1000 mm)"

    def test_seconds_equal_sixty_roll_into_next_minute(self, tmp_path: Path):
        res = tmp_path / "res_rollover.res"
        res.write_text(
            "Residuals COMMENT\n"
            "TIM 2026 8 24 19 9 60.0000000 61276 69000.00\n"
            "G01 0.0010 0.0000 1.0 1.0 0 45.0 90.0 L1C L2W C1C C2W\n"
        )

        df = get_wrms_from_res(res)

        assert df.loc[0, "date"] == pd.Timestamp("2026-08-24T19:10:00Z")
        assert df.loc[0, "wrms"] == pytest.approx(1.0)
