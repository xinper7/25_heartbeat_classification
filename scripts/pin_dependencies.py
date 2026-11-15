"""Record exact installed dependency closure for tested Windows/Python runtime."""

from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
roots = []
for line in (ROOT / "backend/requirements.txt").read_text().splitlines():
    if line and not line.startswith(("#", "--")):
        roots.append(Requirement(line).name)
visited = {}


def visit(name):
    key = canonicalize_name(name)
    if key in visited:
        return
    dist = metadata.distribution(name)
    visited[key] = (dist.metadata["Name"], dist.version)
    for item in dist.requires or []:
        requirement = Requirement(item)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            visit(requirement.name)


for name in roots:
    visit(name)
header = "# Resolved and verified on Windows x64 / Python 3.13\n--extra-index-url https://download.pytorch.org/whl/cpu\n"
(ROOT / "backend/requirements.lock.txt").write_text(
    header + "\n".join(f"{n}=={v}" for _, (n, v) in sorted(visited.items())) + "\n",
    encoding="utf-8",
)
dev = {
    canonicalize_name(d.metadata["Name"]): (d.metadata["Name"], d.version)
    for d in metadata.distributions()
}
(ROOT / "backend/requirements-dev.lock.txt").write_text(
    header
    + "\n".join(
        f"{n}=={v}"
        for _, (n, v) in sorted(dev.items())
        if canonicalize_name(n) not in ("pip",)
    )
    + "\n",
    encoding="utf-8",
)
print("Locked runtime packages:", len(visited), "development packages:", len(dev))
