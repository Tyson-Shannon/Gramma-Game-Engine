"""Gramma asset pipeline.

One source asset in, one generated C file per target out. No runtime tools
ship on the console: everything here runs at build time on the host.
"""

from .project import Project, load_project
from .generate import generate
from .budget import (check_budget, check_budget_detailed, format_report,
                     nes_mapper_config)
from .apidocs import build_api_reference, generate_api_reference
from .schema import (MANIFEST_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION,
                     SERVICE_CONTRACT_VERSION)

__all__ = [
    "Project", "load_project", "generate", "check_budget",
    "check_budget_detailed", "format_report", "nes_mapper_config",
    "build_api_reference",
    "generate_api_reference", "MANIFEST_SCHEMA_VERSION",
    "PROJECT_SCHEMA_VERSION", "SERVICE_CONTRACT_VERSION",
]
