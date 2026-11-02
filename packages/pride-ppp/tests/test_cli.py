from pride_ppp.specifications.cli import PrideCLIConfig


def test_frequency_combinations_are_separate_arguments() -> None:
    config = PrideCLIConfig(frequency=["G12", "R12", "E17", "C27", "J12"])

    command = config.generate_pdp_command("NTH1", "/tmp/nth1.rnx")

    index = command.index("--frequency")
    assert command[index + 1 : index + 6] == ["G12", "R12", "E17", "C27", "J12"]
