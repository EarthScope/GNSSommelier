"""
PRIDE-PPP output parsing and validation.

Helpers for reading ``.kin`` / ``.res`` files into DataFrames and
validating pdp3 output.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from pride_ppp.specifications.output import PridePPP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RES file helpers
# ---------------------------------------------------------------------------


def get_wrms_from_res(res_path):
    """Compute per-epoch phase residual WRMS from a pdp3 ``.res`` file.

    The WRMS is computed as :math:`\\sqrt{\\sum w_i r_i^2 / \\sum w_i}` where
    :math:`r_i` are the double-differenced phase residuals (cycles) and
    :math:`w_i` are the corresponding weights, then converted to millimetres.

    Parameters
    ----------
    res_path : str or Path
        Path to the pdp3 residual output file (``res_{YYYY}{DOY}_{site}.res``).

    Returns
    -------
    pd.DataFrame
        Two-column DataFrame:

        * ``date``  \u2014 UTC epoch timestamp
        * ``wrms``  \u2014 phase residual WRMS (mm) for that epoch
    """
    with open(res_path) as res_file:
        timestamps = []
        data = []
        wrms = 0
        sumOfSquares = 0
        sumOfWeights = 0
        line = res_file.readline()  # first line is header

        while True:
            if line == "":
                break
            line_data = line.split()
            if line_data[0] == "TIM":
                sumOfSquares = 0
                sumOfWeights = 0

                # PRIDE occasionally formats a rounded epoch with seconds
                # equal to 60.0000000.  Constructing an ISO timestamp with
                # second=60 is invalid; adding the seconds as a timedelta
                # correctly carries it into the following minute/day.
                timestamp = datetime(
                    int(line_data[1]),
                    int(line_data[2]),
                    int(line_data[3]),
                    int(line_data[4]),
                    int(line_data[5]),
                    tzinfo=timezone.utc,
                ) + timedelta(seconds=float(line_data[6]))
                timestamps.append(timestamp)

                line = res_file.readline()
                line_data = line.split()
                while not line.startswith("TIM"):
                    phase_residual = float(line_data[1])
                    phase_weight = float(line_data[3].replace("D", "E"))
                    sumOfSquares += phase_residual**2 * phase_weight
                    sumOfWeights += phase_weight
                    line = res_file.readline()
                    if line == "":
                        break
                    line_data = line.split()
                wrms = (sumOfSquares / sumOfWeights) ** 0.5 * 1000  # in mm
                data.append(wrms)
            else:
                line = res_file.readline()

    wrms_df = pd.DataFrame({"date": timestamps, "wrms": data})
    return wrms_df


def plot_kin_results_wrms(kin_df, title=None, save_as=None):
    """Plot kinematic results with WRMS in a 6-panel figure.

    Subplots (top → bottom): Latitude, Longitude, Height,
    Nsat (red = ≤ 4), PDOP on log scale (red = ≥ 5), WRMS (mm).

    Expects DataFrame columns: ``Latitude``, ``Longitude``, ``Height``,
    ``Nsat``, ``PDOP``, ``wrms``.

    Parameters
    ----------
    kin_df : pd.DataFrame
        Output from ``read_kin_data`` merged with WRMS residuals.
    title : str, optional
        RINEX filename or label used in the figure title.
    save_as : str, optional
        If provided, save the figure to this path.
    """
    import matplotlib.pyplot as plt

    size = 3
    bad_nsat = kin_df[kin_df["Nsat"] <= 4]
    bad_pdop = kin_df[kin_df["PDOP"] >= 5]
    fig, axs = plt.subplots(6, 1, figsize=(10, 10), sharex=True)
    axs[0].scatter(kin_df.index, kin_df["Latitude"], s=size)
    axs[0].set_ylabel("Latitude")
    axs[1].scatter(kin_df.index, kin_df["Longitude"], s=size)
    axs[1].set_ylabel("Longitude")
    axs[2].scatter(kin_df.index, kin_df["Height"], s=size)
    axs[2].set_ylabel("Height")
    axs[3].scatter(kin_df.index, kin_df["Nsat"], s=size)
    axs[3].scatter(bad_nsat.index, bad_nsat["Nsat"], s=size * 2, color="red")
    axs[3].set_ylabel("Nsat")
    axs[4].scatter(kin_df.index, kin_df["PDOP"], s=size)
    axs[4].scatter(bad_pdop.index, bad_pdop["PDOP"], s=size * 2, color="red")
    axs[4].set_ylabel("log PDOP")
    axs[4].set_yscale("log")
    axs[4].set_ylim(1, 100)
    axs[5].scatter(kin_df.index, kin_df["wrms"], s=size)
    axs[5].set_ylabel("wrms mm")
    axs[0].ticklabel_format(axis="y", useOffset=False, style="plain")
    axs[1].ticklabel_format(axis="y", useOffset=False, style="plain")
    for ax in axs:
        ax.grid(True, c="lightgrey", zorder=0, lw=1, ls=":")
    plt.xticks(rotation=70)
    fig.suptitle(f"PRIDE-PPPAR results for {os.path.basename(title)}")
    fig.tight_layout()
    if save_as is not None:
        plt.savefig(save_as)


# ---------------------------------------------------------------------------
# KIN file reading
# ---------------------------------------------------------------------------


def kin_to_kin_position_df(source: str | Path) -> pd.DataFrame | None:
    """Parse a pdp3 ``.kin`` file into a DataFrame with optional WRMS residuals.

    Reads the kinematic position records after the ``END OF HEADER`` marker
    and converts them to a DataFrame indexed by UTC timestamp.  Attempts to
    merge WRMS residuals from a co-located ``.res`` file (same directory,
    stem derived from the ``.kin`` filename); the ``wrms`` column will be
    ``None`` if the ``.res`` file is missing or cannot be parsed.

    Parameters
    ----------
    source : str | Path
        Path to the pdp3 ``.kin`` output file.

    Returns
    -------
    pd.DataFrame | None
        DataFrame with columns including ``time``, ``latitude``,
        ``longitude``, ``height``, ``pdop``, and ``wrms``, indexed by
        record number.  Returns ``None`` if the file has no header or
        contains no valid data records.
    """
    logger.info(f"Parsing KIN file: {source}")
    with open(source) as file:
        lines = file.readlines()

    end_header_index = next(
        (i for i, line in enumerate(lines) if line.strip() == "END OF HEADER"), None
    )

    data = []
    if end_header_index is None:
        logger.error(f"GNSS: No header found in FILE {str(source)}")
        return None

    for idx, line in enumerate(lines[end_header_index + 2 :]):
        split_line = line.strip().split()
        selected_columns = split_line[:9] + [split_line[-1]]
        try:
            ppp: PridePPP | ValidationError = PridePPP.from_kin_file(selected_columns)
            data.append(ppp)
        except Exception:
            pass

    if not data:
        logger.error(f"GNSS: No data found in FILE {source}")
        return None

    dataframe = pd.DataFrame([dict(pride_ppp) for pride_ppp in data])
    dataframe["time"] = dataframe["time"].dt.tz_localize("UTC")
    dataframe.set_index("time", inplace=True)
    logger.info(f"Parsed {len(dataframe)} records from KIN file {source}")

    # Add residuals data
    try:
        source_path = Path(source)
        res_pattern = source_path.stem.replace("kin_", "res_").replace(".kin", "")
        res_file = source_path.parent / f"{res_pattern}.res"

        if res_file.exists():
            logger.info(f"Adding residuals from {res_file}")
            wrms_df = get_wrms_from_res(res_file)

            if not wrms_df.empty:
                wrms_df.set_index("date", inplace=True)
                dataframe_sorted = dataframe.sort_index()
                wrms_sorted = wrms_df.sort_index()
                dataframe = pd.merge_asof(
                    dataframe_sorted,
                    wrms_sorted,
                    left_index=True,
                    right_index=True,
                    direction="nearest",
                    tolerance=pd.Timedelta(seconds=0.01),
                )
                logger.info(
                    f"Added WRMS residuals for {dataframe['wrms'].notna().sum()} of {len(dataframe)} records"
                )
            else:
                logger.warning(f"No WRMS data found in {res_file}")
                dataframe["wrms"] = None
        else:
            logger.warning(f"No corresponding RES file found for {source}")
            dataframe["wrms"] = None
    except Exception as e:
        logger.error(f"Error adding residuals: {e}")
        dataframe["wrms"] = None

    dataframe = dataframe.drop(columns=["modified_julian_date", "second_of_day"], errors="ignore")
    dataframe.reset_index(inplace=True)
    logger.info(f"GNSS Parser: {dataframe.shape[0]} shots from FILE {str(source)}")
    return dataframe


def read_kin_data(kin_path):
    r"""Read a ``.kin`` file into a DataFrame using fixed-width column specs.

    The column widths match the pdp3 output format (PRIDE-PPPAR 3).
    The resulting DataFrame is indexed by UTC timestamps derived from
    MJD + seconds-of-day.

    Parameters
    ----------
    kin_path : str
        Path to the ``.kin`` file.

    Returns
    -------
    pd.DataFrame
        Fixed-width columns: Mjd, Sod, \*, X, Y, Z, Latitude, Longitude,
        Height, Nsat, G (GPS sats), R (GLONASS), E (Galileo), C2 (BDS-2),
        C3 (BDS-3), J (QZSS), PDOP.  Indexed by UTC datetime derived from
        MJD + seconds-of-day.
    """
    with open(kin_path) as kin_file:
        for i, line in enumerate(kin_file):
            if "END OF HEADER" in line:
                end_of_header = i + 1
                break

    cols = [
        "Mjd",
        "Sod",
        "*",
        "X",
        "Y",
        "Z",
        "Latitude",
        "Longitude",
        "Height",
        "Nsat",
        "G",
        "R",
        "E",
        "C2",
        "C3",
        "J",
        "PDOP",
    ]
    colspecs = [
        (0, 6),
        (6, 16),
        (16, 18),
        (18, 32),
        (32, 46),
        (46, 60),
        (60, 77),
        (77, 94),
        (94, 108),
        (108, 114),
        (114, 117),
        (117, 120),
        (120, 123),
        (123, 126),
        (126, 129),
        (129, 132),
        (132, 140),
    ]
    kin_df = pd.read_fwf(
        kin_path,
        header=end_of_header,
        colspecs=colspecs,
        names=cols,
        on_bad_lines="skip",
    )
    kin_df.set_index(
        pd.to_datetime(kin_df["Mjd"] + 2400000.5, unit="D", origin="julian")
        + pd.to_timedelta(kin_df["Sod"], unit="sec"),
        inplace=True,
    )
    return kin_df


def validate_kin_file(source: str | Path) -> bool:
    """Validate a kin file.

    This is done by checking if it can be parsed into a DataFrame and
    contains data.

    Parameters
    ----------
    source : str | Path
        The path to the kin file.

    Returns
    -------
    bool
        True if the kin file is valid, False otherwise.
    """
    if not isinstance(source, (str, Path)):
        logger.error(f"Invalid source type: {type(source)}")
        return False

    source = Path(source)
    if not source.exists():
        return False

    df = kin_to_kin_position_df(source)
    if df is None or df.empty:
        logger.error(f"Kin file {source} is invalid or contains no data")
        return False
    return True
