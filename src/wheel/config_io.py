"""Config loading at the IO edge, shared by every entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


def load_config(config_path: str | Path = "config.yaml") -> Mapping[str, Any]:
    """Parse the operator's YAML config."""

    return yaml.safe_load(Path(config_path).read_text())


def wheelops_dir(config: Mapping[str, Any]) -> Path:
    """The operational sibling folder (AGENTS.md §3). Never inside the repo."""

    return Path(config["paths"]["wheelops"]).expanduser()
