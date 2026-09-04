"""
PRIDE PPP-AR CLI configuration.

Builds the ``pdp3`` command line from processing parameters.
"""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PRIDE_NATIVE_FREQUENCIES = ("G12", "R12", "E15", "C26", "J12")
DEFAULT_FREQUENCIES = ("G12", "R12", "E17", "C27", "J12")


class Constellations(str, Enum):
    """GNSS constellation identifiers for pdp3 ``--system`` flag."""

    GPS = "G"
    GLONASS = "R"
    GALILEO = "E"
    BDS = "C"
    BDS_TWO = "2"
    BDS_THREE = "3"
    QZSS = "J"

    @classmethod
    def print_options(cls):
        """Print available constellation codes to stdout."""
        print("System options are:")
        for option in cls:
            print(f"{option.value} for {option.name}")


class Tides(str, Enum):
    """Tidal correction identifiers for pdp3 ``--tides`` flag."""

    SOLID = "S"
    OCEAN = "O"
    POLAR = "P"

    @classmethod
    def print_options(cls):
        """Print available tide correction codes to stdout."""
        print("Tide options are:")
        for option in cls:
            print(f"{option.value} for {option.name}")


class PrideCLIConfig(BaseModel):
    """
    Configuration for generating ``pdp3`` CLI commands.

    Attributes
    ----------
    sample_frequency : float
        Processing sample rate passed to pdp3 via the ``-i`` flag, in
        samples per second (Hz).  A value of ``1`` means 1 Hz (one epoch
        per second).  Default: ``1``.
    system : str
        Constellation string, e.g. ``"GREC23J"``.
    frequency : list
        Frequency combination per constellation.
    loose_edit : bool
        Enable loose editing (recommended for high-dynamic data).
    cutoff_elevation : int
        Elevation cutoff angle in degrees (0-60).
    interval : float, optional
        Processing interval in seconds (0.02-30).
    high_ion : bool, optional
        Correct 2nd-order ionospheric delay.
    tides : str
        Tide corrections (any combination of ``S``, ``O``, ``P``).
    local_pdp3_path : str, optional
        Explicit path to the ``pdp3`` binary.
    override : bool
        Re-process even if outputs already exist.
    override_products_download : bool
        Re-download products even if already present.
    pride_configfile_path : Path, optional
        Path to a PRIDE config file to pass via ``--config``.
    """

    sample_frequency: float = 1
    system: str = "GREC23J"
    frequency: list[str] = Field(default_factory=lambda: list(DEFAULT_FREQUENCIES))
    loose_edit: bool = True
    cutoff_elevation: int = 7
    interval: float | None = None
    high_ion: bool | None = None
    tides: str = "SOP"
    mapping_function: Literal["NIE", "GMF", "VM1", "VM3"] | None = None

    pride_configfile_path: Path | None = Field(
        None,
        title="Path to Pride Config File",
        description="Path to the Pride config file. If not provided, the default config will be used.",
    )

    def __post_init__(self):
        """Validate ``system`` and ``tides`` characters against allowed enums.

        Raises
        ------
        ValueError
            If *system* contains a character not in ``Constellations`` or
            *tides* contains a character not in ``Tides``.
        """
        system = self.system.upper()
        for char in system:
            if char not in Constellations._value2member_map_:
                Constellations.print_options()
                raise ValueError(f"Invalid constellation character: {char}")

        tides = self.tides.upper()
        for char in tides:
            if char not in Tides._value2member_map_:
                Tides.print_options()
                raise ValueError(f"Invalid tide character: {char}")

    def generate_pdp_command(self, site: str, local_file_path: str) -> list[str]:
        """Generate the ``pdp3`` command-line argument list.

        Builds the full argument vector by comparing each config field
        against its default value and only emitting flags that differ.

        Parameters
        ----------
        site : str
            4-character station identifier (e.g. ``"NCC1"``).
        local_file_path : str
            Path to the RINEX observation file.

        Returns
        -------
        List[str]
            Argument list suitable for ``subprocess.run()``.

        Example
        -------
        >>> cfg = PrideCLIConfig(cutoff_elevation=10)
        >>> cmd = cfg.generate_pdp_command("NCC1", "/data/NCC12540.25o")
        >>> cmd[:5]
        ['pdp3', '-m', 'K', '-i', '1']
        """

        command = ["pdp3"]

        command.extend(["-m", "K"])
        command.extend(["-i", str(self.sample_frequency)])

        if self.system != "GREC23J":
            command.extend(["--system", self.system])

        # Our E1/E5b and B1/B2 defaults intentionally differ from pdp3's
        # native E1/E5a and B1/B3 defaults, so they must be passed explicitly.
        if tuple(self.frequency) != PRIDE_NATIVE_FREQUENCIES:
            # pdp3.sh consumes each three-character frequency combination as
            # a separate argv item until it reaches the next option.
            command.extend(["--frequency", *self.frequency])

        if self.loose_edit:
            command.append("--loose-edit")

        if self.cutoff_elevation != 7:
            command.extend(["--cutoff-elev", str(self.cutoff_elevation)])

        if self.interval:
            command.extend(["--interval", str(self.interval)])

        if self.high_ion:
            command.append("--high-ion")

        if self.tides != "SOP":
            command.extend(["--tide-off", self.tides])

        if self.mapping_function:
            command.extend(["--mapping-func", self.mapping_function])

        command.extend(["--site", site])

        if self.pride_configfile_path:
            command.extend(["--config", str(self.pride_configfile_path)])

        command.append(str(local_file_path))

        return command
