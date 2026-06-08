"""SOC2BOX - Self-hosted SOC 2 evidence collector and control tracker.

A zero-dependency engine for tracking SOC 2 Trust Services Criteria controls,
collecting and aging evidence, and reporting audit readiness.
"""
from .core import (
    Control,
    Evidence,
    Program,
    DEFAULT_CONTROLS,
    load_program,
    save_program,
    add_evidence,
    control_status,
    program_readiness,
    gap_list,
)

TOOL_NAME = "soc2box"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Control",
    "Evidence",
    "Program",
    "DEFAULT_CONTROLS",
    "load_program",
    "save_program",
    "add_evidence",
    "control_status",
    "program_readiness",
    "gap_list",
    "TOOL_NAME",
    "TOOL_VERSION",
]
