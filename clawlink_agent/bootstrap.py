"""Runtime dependency bootstrap for CLAWLINK-AGENT.

This module provides a pragmatic safety net for environments where the
package was copied manually or installed incompletely. It does not replace
packaging metadata in pyproject.toml, but it can self-heal missing runtime
Python dependencies on first CLI execution.
"""

from __future__ import annotations

import importlib
import logging
import subprocess
import sys
from typing import Iterable

logger = logging.getLogger(__name__)

_REQUIRED_PACKAGES: dict[str, str] = {
    "fastapi": "fastapi>=0.100.0",
    "uvicorn": "uvicorn[standard]>=0.23.0",
    "pydantic": "pydantic>=2.0.0",
    "aiofiles": "aiofiles>=23.0",
    "yaml": "pyyaml>=6.0",
    "httpx": "httpx>=0.24.0",
}


def _missing_imports(modules: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(module_name)
    return missing


def ensure_runtime_dependencies(auto_install: bool = True) -> list[str]:
    """Ensure core runtime dependencies are importable.

    Returns a list of missing module names after attempting installation.
    """
    missing = _missing_imports(_REQUIRED_PACKAGES.keys())
    if not missing:
        return []

    if not auto_install:
        return missing

    packages = [_REQUIRED_PACKAGES[name] for name in missing]
    logger.warning("Missing runtime dependencies detected: %s", ", ".join(missing))
    logger.info("Attempting automatic dependency bootstrap via pip")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *packages],
        check=True,
    )
    return _missing_imports(missing)
