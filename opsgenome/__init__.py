"""OpsGenome: The Operational Memory Engine.

Watches how engineers actually fix production, turns raw activity into
structured, queryable memory, and closes the loop by preventing recurring incidents.
"""

__version__ = "1.0.0"

import os
from pathlib import Path


def _load_env() -> None:
    """Safely loads environment variables from local .env without overwriting existing shell vars."""
    try:
        from dotenv import load_dotenv

        for candidate in [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            Path.home() / ".opsgenome" / ".env",
        ]:
            if candidate.is_file():
                load_dotenv(dotenv_path=candidate, override=False)
                return
    except Exception:
        # Fallback manual line parser if python-dotenv is missing
        for candidate in [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]:
            if candidate.is_file():
                try:
                    for line in candidate.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.removeprefix("export ").strip()
                            v = v.strip("\"' ")
                            if k and k not in os.environ:
                                os.environ[k] = v
                except Exception:
                    pass


_load_env()

