"""Tests for pride_ppp.factories.rinex — RINEX time-range extraction."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pride_ppp.factories.rinex import epoch_get_time, rinex_get_time_range

RINEX2_HEADER = (
    "     2.11           OBSERVATION DATA    G (GPS)             RINEX VERSION / TYPE\n"
    "gnsstools           EarthScope          20250815 000000 UTC PGM / RUN BY / DATE\n"
    "NTH1                                                        MARKER NAME\n"
    "  2025     8    15     0     0    0.0000000     GPS         TIME OF FIRST OBS\n"
    "                                                            END OF HEADER\n"
)

RINEX2_EPOCHS = (
    " 25  8 15  0  0  0.0000000  0  1\n"
    "G01  20000000.000\n"
    " 25  8 15 12  0  0.0000000  0  1\n"
    "G01  20000000.000\n"
    " 25  8 15 23 58 30.0000000  0  1\n"
    "G01  20000000.000\n"
)

RINEX4_HEADER_WITH_LAST_OBS = (
    "     4.02           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\n"
    "gnsstools           EarthScope          20250815 000000 UTC PGM / RUN BY / DATE\n"
    "NTH100USA                                                   MARKER NAME\n"
    "  2025     8    15     0     0   11.0000000     GPS         TIME OF FIRST OBS\n"
    "  2025     8    15    23    58   53.6000000     GPS         TIME OF LAST OBS\n"
    "                                                            END OF HEADER\n"
)

RINEX4_EPOCH = "> 2025 08 15 00 00 11.0000000  0 18\nG01  20000000.000\n"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class TestEpochGetTime:
    def test_rinex2_two_digit_year(self):
        assert epoch_get_time(" 25  8 15 23 58 30.0000000  0  1") == datetime(
            2025, 8, 15, 23, 58, 30
        )

    def test_rinex34_epoch_flag_and_four_digit_year(self):
        assert epoch_get_time("> 2025 08 15 00 00 11.0000000  0 18") == datetime(
            2025, 8, 15, 0, 0, 11
        )


class TestRinexGetTimeRange:
    def test_rinex2_without_last_obs_header_scans_epochs(self, tmp_path):
        # Older RINEX 2 files from this pipeline omit TIME OF LAST OBS, so the
        # true end time must come from scanning epoch records.
        path = _write(tmp_path, "obs.25o", RINEX2_HEADER + RINEX2_EPOCHS)
        start, end = rinex_get_time_range(path)
        assert start == datetime(2025, 8, 15, 0, 0, 0)
        assert end == datetime(2025, 8, 15, 23, 58, 30)

    def test_rinex4_prefers_header_last_obs(self, tmp_path):
        # RINEX 3/4 output includes TIME OF LAST OBS; it should be used
        # directly rather than falling back to (broken) epoch-line scanning.
        path = _write(tmp_path, "obs.rnx", RINEX4_HEADER_WITH_LAST_OBS + RINEX4_EPOCH)
        start, end = rinex_get_time_range(path)
        assert start == datetime(2025, 8, 15, 0, 0, 11)
        assert end == datetime(2025, 8, 15, 23, 58, 53)

    def test_no_epochs_and_no_last_obs_falls_back_to_end_of_day(self, tmp_path):
        path = _write(tmp_path, "empty.25o", RINEX2_HEADER)
        start, end = rinex_get_time_range(path)
        assert start == datetime(2025, 8, 15, 0, 0, 0)
        assert end == datetime(2025, 8, 15, 23, 59, 59, 999999)

    def test_missing_time_of_first_obs_raises(self, tmp_path):
        path = _write(tmp_path, "no_start.25o", "                                    END OF HEADER\n")
        with pytest.raises(ValueError):
            rinex_get_time_range(path)
