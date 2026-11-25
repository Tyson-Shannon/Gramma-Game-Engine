"""Gramma asset pipeline.

One source asset in, one generated C file per target out. No runtime tools
ship on the console: everything here runs at build time on the host.
"""

from .project import Project, load_project
from .generate import generate
from .budget import check_budget, format_report
from .apidocs import build_api_reference, generate_api_reference

__all__ = [
    "Project", "load_project", "generate", "check_budget", "format_report",
    "build_api_reference", "generate_api_reference",
]
