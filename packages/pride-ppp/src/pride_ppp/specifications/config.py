"""
PRIDE PPP-AR configuration file models.

Read/write the ``config_file`` format consumed by the ``pdp3`` binary.
"""

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Default satellite table (all active GNSS PRNs, variance = 1)
# Keys follow the format "{constellation}{PRN:02d}", e.g. "G01" for GPS PRN 1.
# Values are PRN variance weights used by pdp3 (1 = nominal, higher = down-weighted).
# ---------------------------------------------------------------------------
pride_default_satellites: dict[str, int] = {
    "G01": 1,
    "G02": 1,
    "G03": 1,
    "G04": 1,
    "G05": 1,
    "G06": 1,
    "G07": 1,
    "G08": 1,
    "G09": 1,
    "G10": 1,
    "G11": 1,
    "G12": 1,
    "G13": 1,
    "G14": 1,
    "G15": 1,
    "G16": 1,
    "G17": 1,
    "G18": 1,
    "G19": 1,
    "G20": 1,
    "G21": 1,
    "G22": 1,
    "G23": 1,
    "G24": 1,
    "G25": 1,
    "G26": 1,
    "G27": 1,
    "G28": 1,
    "G29": 1,
    "G30": 1,
    "G31": 1,
    "G32": 1,
    "R01": 1,
    "R02": 1,
    "R03": 1,
    "R04": 1,
    "R05": 1,
    "R06": 1,
    "R07": 1,
    "R08": 1,
    "R09": 1,
    "R10": 1,
    "R11": 1,
    "R12": 1,
    "R13": 1,
    "R14": 1,
    "R15": 1,
    "R16": 1,
    "R17": 1,
    "R18": 1,
    "R19": 1,
    "R20": 1,
    "R21": 1,
    "R22": 1,
    "R23": 1,
    "R24": 1,
    "E01": 1,
    "E02": 1,
    "E03": 1,
    "E04": 1,
    "E05": 1,
    "E06": 1,
    "E07": 1,
    "E08": 1,
    "E09": 1,
    "E10": 1,
    "E11": 1,
    "E12": 1,
    "E13": 1,
    "E14": 1,
    "E15": 1,
    "E16": 1,
    "E17": 1,
    "E18": 1,
    "E19": 1,
    "E20": 1,
    "E21": 1,
    "E22": 1,
    "E23": 1,
    "E24": 1,
    "E25": 1,
    "E26": 1,
    "E27": 1,
    "E28": 1,
    "E29": 1,
    "E30": 1,
    "E31": 1,
    "E32": 1,
    "E33": 1,
    "E34": 1,
    "E35": 1,
    "E36": 1,
    "C06": 1,
    "C07": 1,
    "C08": 1,
    "C09": 1,
    "C10": 1,
    "C11": 1,
    "C12": 1,
    "C13": 1,
    "C14": 1,
    "C15": 1,
    "C16": 1,
    "C17": 1,
    "C18": 3,
    "C19": 1,
    "C20": 1,
    "C21": 1,
    "C22": 1,
    "C23": 1,
    "C24": 1,
    "C25": 1,
    "C26": 1,
    "C27": 1,
    "C28": 1,
    "C29": 1,
    "C30": 1,
    "C31": 1,
    "C32": 1,
    "C33": 1,
    "C34": 1,
    "C35": 1,
    "C36": 1,
    "C37": 1,
    "C38": 1,
    "C39": 1,
    "C40": 1,
    "C41": 1,
    "C42": 1,
    "C43": 1,
    "C44": 1,
    "C45": 1,
    "C46": 1,
    "C47": 1,
    "C48": 1,
    "C56": 1,
    "C57": 1,
    "C58": 1,
    "J01": 1,
    "J02": 1,
    "J03": 1,
}


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------


class ObservationConfig(BaseModel):
    """Observation section of the pdp3 config file.

    Attributes
    ----------
    table_directory : str
        Path to the directory containing ANTEX, leap-second, and
        satellite metadata tables required by pdp3.
    frequency_combination : str
        Frequency combination string (e.g. ``"Default"``).
    interval : str
        Processing interval in seconds, or ``"Default"`` for auto.
    time_window : float
        Observation time window tolerance in seconds.
    session_time : datetime | str
        Session time template.  When a string, pdp3 substitutes
        date/time placeholders at runtime.
    """

    table_directory: str
    frequency_combination: str = "Default"
    interval: str = "Default"
    time_window: float = 0.01
    session_time: datetime | str = Field(
        default="-YYYY- -MM- -DD- -HH- -MI- -SS- -SE-",
    )


class SatelliteProducts(BaseModel):
    """Satellite product file paths for the pdp3 config file.

    Each field holds the filename (not full path) of a specific GNSS
    product.  ``product_directory`` is the common parent directory.
    When set to ``"Default"``, pdp3 resolves the file automatically.

    Attributes
    ----------
    product_directory : str, optional
        Directory containing all satellite product files.
    satellite_orbit : str, optional
        SP3 precise orbit filename (must end in ``.SP3``).
    satellite_clock : str, optional
        CLK precise clock filename (must end in ``.CLK``).
    erp : str, optional
        Earth rotation parameters filename (must end in ``.ERP``).
    quaternions : str, optional
        Satellite attitude quaternions filename (must end in ``.OBX``), or
        ``NONE`` to disable attitude corrections.
    code_phase_bias : str, optional
        Observable-specific signal bias filename (must end in ``.BIA``).
    leo_quaternions : str, optional
        LEO satellite quaternions filename.
    """

    product_directory: str | None = Field(
        default="Default",
        description="Directory for satellite products",
    )
    # Patterns accept the literal "Default" as well as a real filename: pdp3.sh
    # compares this field's raw config-file text with `!= Default` to decide
    # whether to resolve the product itself, so the sentinel has to survive
    # into the file unchanged. A previous version of this pattern only
    # accepted a real filename and relied on a validator to rewrite "Default"
    # to e.g. "Default.OBX" to satisfy it — but that rewritten value then got
    # written to the config file as-is, which pdp3.sh's strict `!= Default`
    # check doesn't recognize, so it would try to fetch a file literally named
    # "Default.OBX" instead of self-resolving.
    satellite_orbit: str | None = Field(
        default="Default",
        pattern=r"^Default$|.*\.SP3",
        description="File name of SP3 file",
    )
    satellite_clock: str | None = Field(
        default="Default",
        pattern=r"^Default$|.*\.CLK",
        description="File name of CLK file",
    )
    erp: str | None = Field(
        default="Default",
        pattern=r"^Default$|.*\.ERP",
        description="File name of ERP file",
    )
    quaternions: str | None = Field(
        default="Default",
        pattern=r"^(Default|NONE)$|.*\.OBX",
        description="File name of quaternions file",
    )
    code_phase_bias: str | None = Field(
        default="Default",
        pattern=r"^Default$|.*\.BIA",
        description="File name of code/phase bias file",
    )
    leo_quaternions: str | None = Field(
        default="Default",
        description="File name of LEO quaternions file",
    )


class DataProcessingStrategies(BaseModel):
    """Data processing strategy defaults for the pdp3 config file.

    Attributes
    ----------
    strict_editing : str
        ``"YES"``/``"NO"``/``"Default"``.  Set to ``"NO"`` for
        high-dynamic data with poor quality.
    rck_model : str
        Receiver clock model: ``"WNO"`` (white noise) or ``"STO"``
        (random walk).
    isb_model : str
        GNSS receiver inter-system biases to be processed.
    ztd_model : str
        Zenith troposphere delay model: ``"PWC:60"`` (piece-wise
        constant, 60 min) or ``"STO"`` (random walk).
    htg_model : str
        Horizontal troposphere gradient model: ``"PWC"``/``"STO"``/``"NON"``.
    iono_2nd : str
        ``"YES"`` to correct 2nd-order ionospheric delays.
    tides : str
        Tidal corrections to apply (e.g. ``"SOLID/OCEAN/POLE"``).
    multipath : str
        ``"YES"``/``"NO"`` — enable multipath correction model.
    """

    strict_editing: str = "Default"
    rck_model: str = "Default"
    isb_model: str = "Default"
    ztd_model: str = "Default"
    htg_model: str = "Default"
    iono_2nd: str = "Default"
    tides: str = "SOLID/OCEAN/POLE"
    multipath: str = "Default"


class AmbiguityFixingOptions(BaseModel):
    """Ambiguity resolution parameters for the pdp3 config file.

    Attributes
    ----------
    ambiguity_co_var : str
        ``"YES"`` to use LAMBDA method for ambiguity fixing.
    ambiguity_duration : int
        Minimum time duration in seconds for a resolvable ambiguity.
    ai_ambiguity_validation : str
        ``"YES"``/``"NO"`` — validate ambiguity fixing with SVM.  Required
        by pdp3 (v3.2.10+); omitting the key crashes its ``sed`` handling
        and every run silently produces 0 KIN files.
    cutoff_elevation : int
        Cutoff mean elevation angle (degrees) for eligible ambiguities.
    pco_on_wide_lane : str
        ``"YES"``/``"NO"`` — apply PCO corrections on Melbourne-Wübbena.
    widelane_decision : List[float]
        ``[deviation, sigma, threshold]`` in cycles for wide-lane ambiguities.
    narrowlane_decision : List[float]
        ``[deviation, sigma, threshold]`` in cycles for narrow-lane ambiguities.
    critical_search : List[float]
        ``[max_exclude, min_reserve, fixed_float, ratio_threshold]``.
    truncate_at_midnight : str
        ``"YES"`` to truncate ambiguities at midnight (avoids day-boundary
        discontinuities).
    verbose_output : str
        ``"YES"``/``"NO"`` — output detailed ambiguity resolution info.
    """

    ambiguity_co_var: str = "Default"
    ambiguity_duration: int = 600
    ai_ambiguity_validation: str = "YES"
    cutoff_elevation: int = 15
    pco_on_wide_lane: str = "YES"
    widelane_decision: list[float] = Field(default_factory=lambda: [0.20, 0.15, 1000.0])
    narrowlane_decision: list[float] = Field(default_factory=lambda: [0.15, 0.15, 1000.0])
    critical_search: list[float] = Field(default_factory=lambda: [3, 4, 1.8, 3.0])
    truncate_at_midnight: str = "Default"
    verbose_output: str = "NO"


class SatelliteList(BaseModel):
    """List of active GNSS satellites and their PRN variances."""

    satellites: dict[str, int] = Field(
        default_factory=lambda: pride_default_satellites,
        description=(
            "Dictionary of satellites with their respective codes and PRN variances. "
            "Keys are satellite codes (e.g., 'G01', 'R01') and values are their PRN variances."
        ),
    )


class StationUsed(BaseModel):
    """Station configuration entry in the pdp3 config file.

    Each field corresponds to a column in the ``+Station used`` block
    of the PRIDE-PPPAR config_file.  Default values are placeholder
    tokens that pdp3 replaces at runtime.

    Attributes
    ----------
    name : str
        4-character station identifier.
    tp : str
        Positioning mode (``S`` static, ``P`` piece-wise, ``K`` kinematic,
        ``F`` fixed).
    map : str
        Mapping function code (``NIE``, ``GMF``, ``VM1``, ``VM3``).
    clkm : int
        Receiver clock model noise in mm.
    podm : str
        Position/orbit determination mode.
    ev : str
        Elevation-dependent weighting strategy.
    ztdm : float
        Zenith troposphere delay model noise in m.
    htgm : float
        Horizontal troposphere gradient model noise in m.
    ragm : float
        Receiver antenna geocenter model noise in m.
    phsc : float
        Phase screen model noise in cycles.
    polns : str
        Pole / nutation series identifier.
    poxem : float
        A priori coordinate sigma in X/East direction (m).
    poynm : float
        A priori coordinate sigma in Y/North direction (m).
    pozhm : float
        A priori coordinate sigma in Z/Height direction (m).
    """

    name: str = Field(default="xxxx", description="Station name")
    tp: str = Field(default="X", description="TP value")
    map: str = Field(default="XXX", description="MAP value")
    clkm: int = Field(default=9000, description="CLKM value")
    podm: str = Field(default="xxxxx", description="PODM value")
    ev: str = Field(default="xx", description="EV value")
    ztdm: float = Field(default=0.20, description="ZTDM value")
    htgm: float = Field(default=0.005, description="HTGM value")
    ragm: float = Field(default=0.3, description="RAGM value")
    phsc: float = Field(default=0.01, description="PHSC value")
    polns: str = Field(default="xxxxx", description="POLNS value")
    poxem: float = Field(default=10.00, description="POXEM value")
    poynm: float = Field(default=10.00, description="POYNM value")
    pozhm: float = Field(default=10.00, description="POZHM value")


class PRIDEPPPFileConfig(BaseModel):
    """Top-level pdp3 ``config_file`` model with read/write support.

    Mirrors every section of the PRIDE-PPPAR 3 config template.  Instances
    can be serialised to disk via ``write_config_file`` and deserialised
    with ``read_config_file`` or ``load_default``.

    Attributes
    ----------
    observation : ObservationConfig
        Observation-related settings (table dir, interval, time window).
    satellite_products : SatelliteProducts
        Paths to resolved GNSS product files (SP3, CLK, ERP, …).
    processing : DataProcessingStrategies
        Processing strategy flags (clock model, tides, troposphere).
    ambiguity : AmbiguityFixingOptions
        Ambiguity resolution thresholds and decision criteria.
    satellites : SatelliteList
        Active satellite PRNs and their variance weights.
    station_used : List[StationUsed]
        Per-station processing parameters.

    Example
    -------
    >>> cfg = PRIDEPPPFileConfig.load_default()
    >>> cfg.write_config_file("/tmp/config_file")
    """

    observation: ObservationConfig = Field(
        description="Observation configuration for the PRIDE PPP processing.",
    )
    satellite_products: SatelliteProducts = Field(
        description="Satellite product configuration for the PRIDE PPP processing.",
    )
    processing: DataProcessingStrategies = Field(
        default_factory=DataProcessingStrategies,
        description="Data processing strategies for the PRIDE PPP configuration.",
    )
    ambiguity: AmbiguityFixingOptions = Field(
        default_factory=AmbiguityFixingOptions,
        description="Options for ambiguity fixing in the processing.",
    )
    satellites: SatelliteList = Field(
        default_factory=SatelliteList,
        description="List of satellites used in the processing.",
    )
    station_used: list[StationUsed] = Field(
        default_factory=lambda: [StationUsed()],
        description="List of stations used in the processing.",
    )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_config_file(self, filepath: str | Path):
        """Write the PRIDE PPP configuration to a file.

        Parent directories are created automatically.  Note: modifies
        ``self.ambiguity.critical_search`` in-place, converting the first
        two elements to integers before serialising.

        Parameters
        ----------
        filepath : str | Path
            Destination path.  Parent directories are created if needed.
        """
        if isinstance(filepath, str):
            filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        # fix critical search params so first 2 values in the list are integers
        for i in range(2):
            self.ambiguity.critical_search[i] = int(self.ambiguity.critical_search[i])

        with open(filepath, "w") as f:
            f.write("# Configuration template for PRIDE PPP-AR 3\n\n")

            # Observation configuration
            f.write("## Observation configuration\n")
            obs = self.observation
            f.write(f"Frequency combination  = {obs.frequency_combination}\n")
            f.write(f"Interval               = {obs.interval} \n")
            f.write(f"Time window            = {obs.time_window}\n")
            f.write(f"Session time           = {obs.session_time}\n")
            f.write(f"Table directory        = {obs.table_directory}\n\n")

            # Satellite product
            f.write("## Satellite product\n")
            sat = self.satellite_products
            f.write(f"Product directory      = {sat.product_directory}\n")
            f.write(f"Satellite orbit        = {sat.satellite_orbit}\n")
            f.write(f"Satellite clock        = {sat.satellite_clock}\n")
            f.write(f"ERP                    = {sat.erp}\n")
            f.write(f"Quaternions            = {sat.quaternions}\n")
            f.write(f"Code/phase bias        = {sat.code_phase_bias}\n")
            f.write(f"LEO quaternions        = {sat.leo_quaternions}\n\n")

            # Data processing strategies
            f.write("## Data processing strategies\n")
            proc = self.processing
            f.write(
                f"Strict editing         = {proc.strict_editing}                 ! change to NO if using high-dynamic data with bad quality\n"
            )
            f.write(
                f"RCK model              = {proc.rck_model}                 ! receiver clock (WNO/STO). WNO, white noise\n"
            )
            f.write(
                f"ISB model              = {proc.isb_model}                 ! GNSS receiver inter-system biases to be processed\n"
            )
            f.write(
                f"ZTD model              = {proc.ztd_model}                 ! zenith troposphere delay (PWC/STO). PWC:60, piece-wise constant for 60 min. STO, random walk\n"
            )
            f.write(
                f"HTG model              = {proc.htg_model}                 ! horizontal troposphere gradient (PWC/STO/NON)\n"
            )
            f.write(
                f"Iono 2nd               = {proc.iono_2nd}                 ! change to YES if correcting 2-order ionospheric delays\n"
            )
            f.write(
                f"Tides                  = {proc.tides}        ! remove any to shut it down, or changed to NON if not correcting tidal errors\n"
            )
            f.write(
                f"Multipath              = {proc.multipath}                 ! use the multipath correction model (YES/NO)\n\n"
            )

            # Ambiguity fixing options
            f.write("## Ambiguity fixing options\n")
            amb = self.ambiguity
            f.write(
                f"Ambiguity co-var       = {amb.ambiguity_co_var}                 ! change to YES if the Ambiguity fixing method is LAMBDA\n"
            )
            f.write(
                f"Ambiguity duration     = {amb.ambiguity_duration}                     ! time duration in seconds for a resolvable ambiguity\n"
            )
            f.write(
                f"AI Ambiguity validation = {amb.ai_ambiguity_validation}                     ! Ambiguity fixing validation is SVM or not\n"
            )
            f.write(
                f"Cutoff elevation       = {amb.cutoff_elevation}                      ! cutoff mean elevation for eligible ambiguities to be resolved\n"
            )
            f.write(
                f"PCO on wide-lane       = {amb.pco_on_wide_lane}                     ! pco corrections on Melbourne-Wubbena or not\n"
            )
            f.write(
                f"Widelane decision      = {' '.join(map(str, amb.widelane_decision))}         ! deviation (cycle), sigma (cycle) and decision threshold for WL ambiguities\n"
            )
            f.write(
                f"Narrowlane decision    = {' '.join(map(str, amb.narrowlane_decision))}        ! deviation (cycle), sigma (cycle) and decision threshold for NL ambiguities\n"
            )
            f.write(
                f"Critical search        = {' '.join(map(str, amb.critical_search))}             ! highest number of ambiguities to be excluded, lowest number to be reserved, fixed/float, ratio threshold\n"
            )
            f.write(
                f"Truncate at midnight   = {amb.truncate_at_midnight}                 ! truncate all ambiguities at midnight to avoid day boundary discontinuity\n"
            )
            f.write(
                f"Verbose output         = {amb.verbose_output}                      ! output detailed information of ambiguity resolution\n\n"
            )

            # Satellite list
            f.write("## Satellite list\n")
            f.write(
                "# Inserting `#' at the beginning of individual GNSS PRN means not to use this satellite\n"
            )
            f.write("+GNSS satellites\n")
            f.write("*PRN variance\n")
            sats = self.satellites.satellites
            for satellite, prn_variance in sats.items():
                f.write(f" {satellite:>3}   {prn_variance}\n")
            f.write("-GNSS satellites\n\n")

            # Option line header
            f.write("## Option line\n")
            f.write("# There should be only one option line to be processed\n")
            f.write("# Arguments can be replaced by command-line automatically\n")
            f.write("# Available positioning mode:  S -- static\n")
            f.write("#                              P -- piec-wise\n")
            f.write("#                              K -- kinematic\n")
            f.write("#                              F -- fixed\n")
            f.write("# Available mapping function:  NIE -- Niell Mapping Function (NMF)\n")
            f.write("#                              GMF -- Global Mapping Function (GMF)\n")
            f.write("#                              VM1 -- Vienna Mapping Function (VMF1)\n")
            f.write("#                              VM3 -- Vienna Mapping Function (VMF3)\n")
            f.write("# Other arguments can be kept if you are not familiar with them\n")

            # Station used
            if self.station_used:
                f.write("+Station used\n")
                f.write(
                    "*NAME TP MAP CLKm  PoDm EV ZTDm  PoDm HTGm  PoDm RAGm PHSc PoLns PoXEm PoYNm PoZHm\n"
                )
                for station in self.station_used:
                    f.write(
                        f" {station.name} {station.tp}  {station.map} {station.clkm} {station.podm} {station.ev} "
                        f"{station.ztdm:.2f} {station.podm} {station.htgm} {station.podm} {station.ragm} "
                        f"{station.phsc:.2f} {station.polns} {station.poxem:.2f} {station.poynm:.2f} {station.pozhm:.2f}\n"
                    )
                f.write("-Station used\n")

    # ------------------------------------------------------------------
    # Read / parse
    # ------------------------------------------------------------------

    @classmethod
    def read_config_file(cls, file_path: str) -> "PRIDEPPPFileConfig":
        """Parse a PRIDE PPP ``config_file`` from disk.

        Note: the ``station_used`` section is not fully parsed; a single
        default :class:`StationUsed` instance is always returned regardless
        of the file contents.

        Parameters
        ----------
        file_path : str
            Path to an existing PRIDE-PPPAR config file.

        Returns
        -------
        PRIDEPPPFileConfig
            Populated config model.
        """
        with open(file_path) as file:
            text = file.read()

        def get_value(line):
            return line.split("=", 1)[-1].strip().split("!")[0].strip()

        def parse_satellite_list(lines):
            satellites = {}
            for line in lines:
                if (
                    not line.strip()
                    or line.startswith("#")
                    or line.startswith("+")
                    or line.startswith("-")
                    or line.startswith("*")
                ):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    prn, var = parts[0], int(parts[1])
                    satellites[prn.lstrip("#")] = var
            return satellites

        # Split into sections
        lines = text.splitlines()
        sections: dict[str, list] = {}
        current_section = None
        section_lines: list = []
        for line in lines:
            if line.startswith("##"):
                if current_section:
                    sections[current_section] = section_lines
                current_section = line.strip("# ").strip().lower().replace(" ", "_")
                section_lines = []
            else:
                section_lines.append(line)
        if current_section:
            sections[current_section] = section_lines

        # Parse Observation configuration
        obs_lines = sections.get("observation_configuration", [])
        obs_kwargs: dict = {}
        for line in obs_lines:
            if "Frequency combination" in line:
                obs_kwargs["frequency_combination"] = get_value(line)
            elif "Interval" in line:
                obs_kwargs["interval"] = get_value(line)
            elif "Time window" in line:
                obs_kwargs["time_window"] = float(get_value(line))
            elif "Session time" in line:
                obs_kwargs["session_time"] = get_value(line)
            elif "Table directory" in line:
                obs_kwargs["table_directory"] = get_value(line)
        observation = ObservationConfig(**obs_kwargs)

        # Parse Satellite product
        prod_lines = sections.get("satellite_product", [])
        prod_kwargs: dict = {}
        for line in prod_lines:
            if "Product directory" in line:
                prod_kwargs["product_directory"] = get_value(line)
            elif "Satellite orbit" in line:
                prod_kwargs["satellite_orbit"] = get_value(line)
            elif "Satellite clock" in line:
                prod_kwargs["satellite_clock"] = get_value(line)
            elif "ERP" in line and "Quaternions" not in line:
                prod_kwargs["erp"] = get_value(line)
            elif "Quaternions" in line and "LEO" not in line:
                prod_kwargs["quaternions"] = get_value(line)
            elif "Code/phase bias" in line:
                prod_kwargs["code_phase_bias"] = get_value(line)
            elif "LEO quaternions" in line:
                prod_kwargs["leo_quaternions"] = get_value(line)
        satellite_product = SatelliteProducts(**prod_kwargs)

        # Parse Data processing strategies
        proc_lines = sections.get("data_processing_strategies", [])
        proc_kwargs: dict = {}
        for line in proc_lines:
            if "Strict editing" in line:
                proc_kwargs["strict_editing"] = get_value(line)
            elif "RCK model" in line:
                proc_kwargs["rck_model"] = get_value(line)
            elif "ISB model" in line:
                proc_kwargs["isb_model"] = get_value(line)
            elif "ZTD model" in line:
                proc_kwargs["ztd_model"] = get_value(line)
            elif "HTG model" in line:
                proc_kwargs["htg_model"] = get_value(line)
            elif "Iono 2nd" in line:
                proc_kwargs["iono_2nd"] = get_value(line)
            elif "Tides" in line:
                proc_kwargs["tides"] = get_value(line)
            elif "Multipath" in line:
                proc_kwargs["multipath"] = get_value(line)
        processing = DataProcessingStrategies(**proc_kwargs)

        # Parse Ambiguity fixing options
        amb_lines = sections.get("ambiguity_fixing_options", [])
        amb_kwargs: dict = {}
        for line in amb_lines:
            if "Ambiguity co-var" in line:
                amb_kwargs["ambiguity_co_var"] = get_value(line)
            elif "Ambiguity duration" in line:
                amb_kwargs["ambiguity_duration"] = int(get_value(line))
            elif "AI Ambiguity validation" in line:
                amb_kwargs["ai_ambiguity_validation"] = get_value(line)
            elif "Cutoff elevation" in line:
                amb_kwargs["cutoff_elevation"] = int(get_value(line))
            elif "PCO on wide-lane" in line:
                amb_kwargs["pco_on_wide_lane"] = get_value(line)
            elif "Widelane decision" in line:
                amb_kwargs["widelane_decision"] = [float(x) for x in get_value(line).split()]
            elif "Narrowlane decision" in line:
                amb_kwargs["narrowlane_decision"] = [float(x) for x in get_value(line).split()]
            elif "Critical search" in line:
                amb_kwargs["critical_search"] = [float(x) for x in get_value(line).split()]
            elif "Truncate at midnight" in line:
                amb_kwargs["truncate_at_midnight"] = get_value(line)
            elif "Verbose output" in line:
                amb_kwargs["verbose_output"] = get_value(line)
        ambiguity = AmbiguityFixingOptions(**amb_kwargs)

        # Parse Satellite list
        sat_start = None
        sat_end = None
        for i, line in enumerate(lines):
            if "+GNSS satellites" in line:
                sat_start = i + 2  # skip header lines
            if "-GNSS satellites" in line:
                sat_end = i
        satellites = {}
        if sat_start and sat_end:
            satellites = parse_satellite_list(lines[sat_start:sat_end])
        satellite_list = SatelliteList(satellites=satellites)

        # Parse Station used (simple version)
        station_used = [StationUsed()]

        return cls(
            observation=observation,
            satellite_products=satellite_product,
            processing=processing,
            ambiguity=ambiguity,
            satellites=satellite_list,
            station_used=station_used,
        )

    @classmethod
    def load_default(cls) -> "PRIDEPPPFileConfig":
        """Load the default ``config_template`` shipped with PRIDE-PPPAR.

        Searches ``~/.PRIDE_PPPAR_BIN`` first, then any ``.PRIDE_PPPAR_BIN``
        directory on ``$PATH`` (how pixi-based installs expose it), then
        falls back to ``/opt/PRIDE-PPPAR/.PRIDE_PPPAR_BIN``.

        Returns
        -------
        PRIDEPPPFileConfig
            Config populated from the template.

        Raises
        ------
        FileNotFoundError
            If none of the installation paths exist.
        """
        pdp_home = Path.home() / ".PRIDE_PPPAR_BIN"
        if not pdp_home.exists():
            pdp_home = next(
                (
                    Path(entry)
                    for entry in os.environ.get("PATH", "").split(os.pathsep)
                    if entry.endswith(".PRIDE_PPPAR_BIN") and Path(entry).exists()
                ),
                Path("/opt/PRIDE-PPPAR/.PRIDE_PPPAR_BIN"),
            )
            if not pdp_home.exists():
                raise FileNotFoundError(f"PRIDE PPPAR directory not found: {pdp_home}")

        config_path = pdp_home / "config_template"
        if not config_path.exists():
            raise FileNotFoundError(f"PRIDE PPPAR config template not found: {config_path}")
        return cls.read_config_file(config_path)
