"""Capture the revision once, so a running process cannot claim newer disk code."""
import subprocess
from datetime import datetime, timezone
from .config import ROOT

STARTED_AT = datetime.now(timezone.utc).isoformat()
try:
    REVISION = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
        stderr=subprocess.DEVNULL, text=True, timeout=3,
    ).strip()
except (OSError, subprocess.SubprocessError):
    REVISION = "local"
