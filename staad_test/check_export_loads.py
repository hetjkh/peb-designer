"""Summarize applied forces in the PEB CONNECT sample STD files.

This deliberately accepts only the load syntax used by these samples. An
unexpected load line raises an error so a missing load cannot silently make
the comparison look correct.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = (ROOT / "PEB_CONNECT_2D_v2.std", ROOT / "PEB_CONNECT_3D_v2.std")
JOINT = re.compile(r"^(\d+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+);$")
MEMBER = re.compile(r"^(\d+)\s+(\d+)\s+(\d+);$")
UNIFORM = re.compile(r"^(\d+) UNI G([XYZ])\s+([\d.eE+-]+)$")
NODAL = re.compile(r"^(\d+)\s+F([XYZ])\s+([\d.eE+-]+)$")
AXIS = {"X": 0, "Y": 1, "Z": 2}


def summarize(path: Path) -> None:
    joints: dict[int, tuple[float, float, float]] = {}
    members: dict[int, tuple[int, int]] = {}
    totals: dict[int, list[float]] = {}
    mode = ""
    case = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        if line == "JOINT COORDINATES":
            mode = "joint"
            continue
        if line == "MEMBER INCIDENCES":
            mode = "member"
            continue
        if re.match(r"^LOAD \d+\b", line):
            case = int(line.split()[1])
            totals[case] = [0.0, 0.0, 0.0]
            mode = ""
            continue
        if line.startswith("LOAD COMB"):
            case = None
            mode = ""
            continue
        if line == "MEMBER LOAD":
            mode = "uniform"
            continue
        if line == "JOINT LOAD":
            mode = "nodal"
            continue
        if mode == "joint":
            match = JOINT.fullmatch(line)
            if match is None:
                mode = ""
            else:
                joints[int(match[1])] = tuple(map(float, match.groups()[1:]))
                continue
        if mode == "member":
            match = MEMBER.fullmatch(line)
            if match is None:
                mode = ""
            else:
                members[int(match[1])] = (int(match[2]), int(match[3]))
                continue
        if mode == "uniform":
            match = UNIFORM.fullmatch(line)
            if match is None:
                raise ValueError(f"Unsupported member load in {path.name}: {line}")
            member = int(match[1])
            a, b = members[member]
            length = math.dist(joints[a], joints[b])
            totals[case][AXIS[match[2]]] += float(match[3]) * length
            continue
        if mode == "nodal":
            match = NODAL.fullmatch(line)
            if match is None:
                raise ValueError(f"Unsupported joint load in {path.name}: {line}")
            totals[case][AXIS[match[2]]] += float(match[3])
    print(f"{path.name}: {len(joints)} joints, {len(members)} members")
    for number, force in totals.items():
        print(
            f"  Load {number}: applied FX={force[0]:+.3f}, "
            f"FY={force[1]:+.3f}, FZ={force[2]:+.3f} kN; "
            f"expected sum of support reactions="
            f"({-force[0]:+.3f}, {-force[1]:+.3f}, {-force[2]:+.3f}) kN"
        )


if __name__ == "__main__":
    for item in (map(Path, sys.argv[1:]) if len(sys.argv) > 1 else FILES):
        summarize(item)
