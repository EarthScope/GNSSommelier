"""
RINEX utility functions.

Extract timestamps and time ranges from RINEX observation files,
and merge RINEX 2 broadcast ephemerides into RINEX 3 BRDM format.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)


def _header_get_time(line: str) -> datetime:
    """Parse a timestamp from a RINEX header line containing ``GPS``.

    Expects the format produced by the ``TIME OF FIRST OBS`` /
    ``TIME OF LAST OBS`` header records::

        2025     1    15     0     0    0.0000000     GPS

    Everything before ``GPS`` is split on whitespace and interpreted as
    ``YYYY MM DD HH MI SS.sss``.

    Args:
        line: A single RINEX header line.

    Returns:
        Parsed UTC datetime (fractional seconds truncated to integer).
    """
    time_values = line.split("GPS")[0].strip().split()
    return datetime(
        year=int(time_values[0]),
        month=int(time_values[1]),
        day=int(time_values[2]),
        hour=int(time_values[3]),
        minute=int(time_values[4]),
        second=int(float(time_values[5])),
    )


def epoch_get_time(line: str) -> datetime:
    """Extract the epoch timestamp from a RINEX observation epoch record.

    Supports both RINEX 2 epoch records (``YY MM DD HH MI SS.sss ...``, a
    2-digit year with no prefix) and RINEX 3/4 epoch records (``>  YYYY MM DD
    HH MI SS.sss ...``, an epoch-flag prefix and a 4-digit year).

    Args:
        line: A single RINEX observation epoch line.

    Returns:
        Parsed UTC datetime.
    """
    tokens = line.strip().split()
    if tokens and tokens[0] == ">":
        tokens = tokens[1:]
    year_token = tokens[0]
    year = int(year_token) if len(year_token) == 4 else 2000 + int(year_token)
    return datetime(
        year=year,
        month=int(tokens[1]),
        day=int(tokens[2]),
        hour=int(tokens[3]),
        minute=int(tokens[4]),
        second=int(float(tokens[5])),
    )


def rinex_get_time_range(source: str | Path) -> tuple[datetime, datetime]:
    """
    Extract the time range from a RINEX observation file.

    Prefers the header's ``TIME OF LAST OBS`` record for the end timestamp,
    since it is authoritative and version-independent.  Falls back to
    scanning epoch records (RINEX 2 or 3/4) when that header field is
    absent, as it is in some older RINEX 2 files.

    Parameters
    ----------
    source : str | Path
        Path to the RINEX observation file.

    Returns
    -------
    Tuple[datetime, datetime]
        Start and end timestamps.

    Raises
    ------
    ValueError
        If the time range cannot be extracted.
    """
    timestamp_data_start = None
    timestamp_data_end = None
    header_done = False

    with open(source) as f:
        lines = f.readlines()

    for line in lines:
        if "TIME OF FIRST OBS" in line:
            timestamp_data_start = _header_get_time(line)
        elif "TIME OF LAST OBS" in line:
            timestamp_data_end = _header_get_time(line)
        elif "END OF HEADER" in line:
            header_done = True
            break

    if timestamp_data_start is None:
        logger.error("Failed to extract time range from %s", source)
        raise ValueError(f"Failed to extract time range from {source}")

    if timestamp_data_end is None or timestamp_data_end < timestamp_data_start:
        # No (valid) TIME OF LAST OBS header field: scan epoch records for
        # the true last observation time instead.
        timestamp_data_end = timestamp_data_start
        year2 = str(timestamp_data_start.year)[2:]
        year4 = str(timestamp_data_start.year)
        in_body = header_done
        for line in lines:
            if not in_body:
                if "END OF HEADER" in line:
                    in_body = True
                continue
            stripped = line.strip()
            token = stripped[1:].strip() if stripped.startswith(">") else stripped
            if token.startswith(year2) or token.startswith(year4):
                try:
                    current_date = epoch_get_time(line)
                    if current_date > timestamp_data_end:
                        timestamp_data_end = current_date
                except Exception:
                    pass

        if timestamp_data_end == timestamp_data_start:
            # No epoch records were found either: assume the file covers the
            # full day rather than reporting a zero-length range.
            timestamp_data_end = datetime(
                year=timestamp_data_start.year,
                month=timestamp_data_start.month,
                day=timestamp_data_start.day,
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
            )

    return timestamp_data_start, timestamp_data_end


# ---------------------------------------------------------------------------
# Broadcast navigation merge (RINEX 2 → RINEX 3 BRDM)
# ---------------------------------------------------------------------------


def _write_brdn(file: Path, prefix: str, fm: IO) -> None:
    """Write GPS broadcast ephemeris records from a RINEX 2 ``.n`` file.

    Args:
        file: Path to the RINEX 2 GPS broadcast file.
        prefix: Constellation prefix character (``'G'``).
        fm: Open file handle for the merged output.
    """
    try:
        with open(file) as fn:
            lines = fn.readlines()
    except Exception as e:
        logger.error("Unable to open or read file %s: %s", file, e)
        return

    in_header = True
    i = 1
    while i < len(lines):
        try:
            if not in_header:
                line = lines[i].replace("D", "e")
                prn = int(line[0:2])
                yyyy = int(line[3:5]) + 2000
                mm = int(line[6:8])
                dd = int(line[9:11])
                hh = int(line[12:14])
                mi = int(line[15:17])
                ss = round(float(line[18:22]))
                num2 = float(line[22:41])
                num3 = float(line[41:60])
                num4 = float(line[60:79])
                fm.write(
                    f"{prefix}{prn:02d} {yyyy:04d} {mm:02d} {dd:02d}"
                    f" {hh:02d} {mi:02d} {ss:02d}"
                    f" {num2:.12e} {num3:.12e} {num4:.12e}\n"
                )

                for t in range(1, 4):
                    line = lines[i + t].replace("D", "e")
                    num1 = float(line[3:22])
                    num2 = float(line[22:41])
                    num3 = float(line[41:60])
                    num4 = float(line[60:79])
                    fm.write(f"    {num1:.12e} {num2:.12e} {num3:.12e} {num4:.12e}\n")

                line = lines[i + 7].replace("D", "e")
                num1 = float(line[3:22])
                num2 = float(line[22:41])
                fm.write(f"    {num1:.12e} {num2:.12e}\n")
                i += 8
                if i >= len(lines):
                    break
            else:
                if "PGM / RUN BY / DATE" == lines[i][60:79]:
                    fm.write(lines[i])
                if "LEAP SECONDS" == lines[i][60:72]:
                    fm.write(lines[i])
                if "END OF HEADER" == lines[i][60:73]:
                    in_header = False
                    fm.write(lines[i])
                i += 1
        except Exception as e:
            logger.error("Error at line %d of file %s: %s", i, file, e)
            break


def _write_brdg(file: Path, prefix: str, fm: IO) -> None:
    """Write GLONASS broadcast ephemeris records from a RINEX 2 ``.g`` file.

    Args:
        file: Path to the RINEX 2 GLONASS broadcast file.
        prefix: Constellation prefix character (``'R'``).
        fm: Open file handle for the merged output.
    """
    try:
        with open(file) as fg:
            lines = fg.readlines()
    except Exception as e:
        logger.error("Unable to open or read file %s: %s", file, e)
        return

    in_header = True
    i = 1
    while i < len(lines):
        try:
            if not in_header:
                line = lines[i].replace("D", "e")
                prn = int(line[0:2])
                yyyy = int(line[3:5]) + 2000
                mm = int(line[6:8])
                dd = int(line[9:11])
                hh = int(line[12:14])
                mi = int(line[15:17])
                ss = round(float(line[18:22]))
                num2 = float(line[22:41])
                num3 = float(line[41:60])
                num4 = float(line[60:79])
                fm.write(
                    f"R{prn:02d} {yyyy:04d} {mm:02d} {dd:02d}"
                    f" {hh:02d} {mi:02d} {int(ss):02d}"
                    f"{num2: .12e}{num3: .12e}{num4: .12e}\n"
                )
                for t in range(1, 4):
                    line = lines[i + t].replace("D", "e")
                    num1 = float(line[3:22])
                    num2 = float(line[22:41])
                    num3 = float(line[41:60])
                    num4 = float(line[60:79])
                    fm.write(f"    {num1: .12e}{num2: .12e}{num3: .12e}{num4: .12e}\n")
                i += 4
                if i >= len(lines):
                    break
            else:
                if "END OF HEADER" == lines[i][60:73]:
                    in_header = False
                i += 1
        except Exception as e:
            logger.error("Error at line %d of file %s: %s", i, file, e)
            break


def merge_broadcast_files(
    brdn: Path,
    brdg: Path,
    output_folder: Path,
) -> Path | None:
    """Merge GPS and GLONASS RINEX 2 broadcast files into a RINEX 3 BRDM file.

    Both input files must have matching day-of-year (characters 4–6) and
    year (characters 9–10) in their filenames — e.g. ``brdn0200.25n`` and
    ``brdg0200.25g``.  A mismatch causes the function to return ``None``
    with an error log.

    Inspired by ``PrideLab/PRIDE-PPPAR/scripts/merge2brdm.py``.

    Args:
        brdn: Path to the GPS broadcast ephemeris (``.n``) file.
        brdg: Path to the GLONASS broadcast ephemeris (``.g``) file.
        output_folder: Directory where the merged BRDM file will be written.

    Returns:
        Path to the merged BRDM file, or ``None`` on failure.
    """
    logger.info("Merging %s and %s into a single BRDM file.", brdn, brdg)

    ddd = brdn.name[4:7]
    yy = brdn.name[9:11]
    if brdg.name[4:7] != ddd or brdg.name[9:11] != yy:
        logger.error("Inconsistent file names: %s vs %s (DOY or year mismatch)", brdn, brdg)
        return None

    brdm = output_folder / f"brdm{ddd}0.{yy}p"
    with open(brdm, "w") as fm:
        fm.write(
            "     3.04           NAVIGATION DATA     M (Mixed)           RINEX VERSION / TYPE\n"
        )
        _write_brdn(brdn, "G", fm)
        _write_brdg(brdg, "R", fm)

    if brdm.exists():
        logger.info("Files merged into %s", brdm)
        return brdm
    return None
