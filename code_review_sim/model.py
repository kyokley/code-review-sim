"""Configuration for the illustrative code review effort model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    """Rates use normalized time units per line; see SPEC.md for assumptions."""

    trials: int = 1000
    seed: int = 42
    agile_block_size: int = 200
    revision_probability: float = 0.1
    write_time_per_line: float = 1.0
    review_time_per_line: float = 0.25
    revision_time_per_line: float = 1.0
    review_setup_time: float = 0.0
