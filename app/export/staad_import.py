"""STAAD reference import: inspect supported data and retain the entire native input.

This is deliberately not a STAAD solver. Untranslated commands remain in the
native document; an imported model must never go through the simplified solver.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Sequence

from app.core.models import (LoadCase, LoadCombination, Member, MemberUniformLoad,
                             Node, NodalLoad, StructuralModel, Support, SupportType)

_LENGTH = {"METER": 1., "METE": 1., "M": 1., "MM": .001, "MMS": .001,
           "CM": .01, "CMS": .01, "FEET": .3048, "FOOT": .3048,
           "FT": .3048, "INCH": .0254, "INCHES": .0254}
_FORCE = {"KN": 1., "NEWTON": .001, "NEW": .001, "N": .001,
          "KIP": 4.4482216152605, "KIPS": 4.4482216152605,
          "POUND": .0044482216152605, "POUNDS": .0044482216152605,
          "KG": .00980665, "MTON": 9.80665}


def _preprocess(text: str) -> list[str]:
    out, pending = [], ""
    for raw in text.splitlines():
        line = raw.split("*", 1)[0].strip()
        if not line:
            continue
        pending += (" " if pending else "") + line.removesuffix("-").rstrip()
        if not line.endswith("-"):
            out.append(pending)
            pending = ""
    if pending:
        raise ValueError("Unfinished STAAD continuation line")
    return out


def statements(text: str) -> list[str]:
    return [part.strip() for line in _preprocess(text) for part in line.split(";") if part.strip()]


def _expand_ids(tokens: Sequence[str]) -> list[int]:
    """Strict ID lists, including TO and BY; never turn dimensions into IDs."""
    ids, i = [], 0
    while i < len(tokens):
        start = int(tokens[i])
        if start < 1:
            raise ValueError("STAAD IDs must be positive")
        i += 1
        if i < len(tokens) and tokens[i].upper() == "TO":
            end = int(tokens[i + 1])
            i += 2
            step = 1
            if i < len(tokens) and tokens[i].upper() == "BY":
                step = int(tokens[i + 1])
                i += 2
            if step < 1 or end < start:
                raise ValueError("Invalid STAAD ID range")
            ids.extend(range(start, end + 1, step))
        else:
            ids.append(start)
    return ids


def _ids(text: str, available: dict) -> list[int]:
    tokens = text.upper().split()
    if tokens and tokens[0] in ("MEMB", "MEMBER", "JOINT"):
        tokens = tokens[1:]
    ids = list(available) if tokens == ["ALL"] else _expand_ids(tokens)
    missing = set(ids) - set(available)
    if missing:
        raise ValueError(f"Unknown STAAD IDs: {sorted(missing)}")
    return ids


def _number(text: str) -> float:
    v = float(text)
    if not math.isfinite(v):
        raise ValueError("Non-finite STAAD number")
    return v


def _infer_member_type(a: Node, b: Node) -> str:
    dx, dy, dz = (abs(x-y) for x, y in zip(a.coords, b.coords))
    if dx < 1e-6 and dz < 1e-6 and dy > 1e-6:
        return "column"
    if dz < 1e-6 and dx > 1e-6:
        return "rafter"
    return "generic"


def model_fingerprint(model: StructuralModel) -> str:
    """Guard lossless re-export against silent edits to the imported model."""
    data = {name: [asdict(v) for _, v in sorted(getattr(model, name).items())]
            for name in ("nodes", "members", "supports", "load_cases", "combinations")}
    data.update(member_loads=[asdict(v) for v in model.member_loads],
                nodal_loads=[asdict(v) for v in model.nodal_loads],
                native=model.metadata["staad_native"])
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def preserved_staad_text(model: StructuralModel) -> str:
    if (model_fingerprint(model) != model.metadata.get("staad_import_fingerprint")
            or model.metadata.get("export_frame_z") is not None):
        raise ValueError("Imported STAAD model has changed. Native commands cannot safely be "
                         "rewritten from a partial import; edit the STD in STAAD and re-import.")
    return model.metadata["staad_native"]["source_text"]


def import_staad_std(path: str | Path) -> StructuralModel:
    path = Path(path)
    model = parse_staad_std(path.read_text(encoding="utf-8-sig", errors="replace"), source=str(path))
    # Results are attached only when their echoed input matches this exact model.
    anl = next((p for p in path.parent.iterdir()
                if p.stem.lower() == path.stem.lower() and p.suffix.lower() == ".anl"), None)
    if anl:
        from app.export.staad_results import attach_staad_results
        attach_staad_results(model, anl)
    return model


def parse_staad_std(text: str, *, source: str = "") -> StructuralModel:
    model = StructuralModel()
    native = {"source_text": text, "properties": {}, "materials": {}, "specifications": {},
              "design_parameters": {}, "loads": {}, "definitions": [], "envelopes": [],
              "analysis_commands": [], "checked_members": [], "untranslated": [],
              "support_commands": [], "code": ""}
    model.metadata.update(imported_from=source or "std text", staad_native=native,
                          requires_staad_analysis=True, audit_warnings=[])
    mode, case, material = "", None, None
    length, force = None, None
    table, parameter_set = "", ""
    for line in statements(text):
        u, parts = line.upper(), line.upper().split()
        if u.startswith("UNIT "):
            l = [v for k, v in _LENGTH.items() if k in parts[1:]]
            f = [v for k, v in _FORCE.items() if k in parts[1:]]
            if len(l) != 1 or len(f) != 1:
                raise ValueError(f"Unsupported STAAD units: {line}")
            length, force = l[0], f[0]
            continue
        if u == "JOINT COORDINATES": mode = "nodes"; continue
        if u == "MEMBER INCIDENCES": mode = "members"; continue
        if u.startswith("MEMBER PROPERTY"):
            mode, table = "properties", u.removeprefix("MEMBER PROPERTY").strip()
            continue
        if u == "DEFINE MATERIAL START": mode = "materials"; continue
        if u == "END DEFINE MATERIAL": mode = ""; continue
        if u.startswith("ISOTROPIC ") and mode == "materials":
            material = parts[1]
            native["materials"][material] = {"commands": [], "length_unit_m": length, "force_unit_kn": force}
            continue
        if mode == "materials":
            if material is None:
                native["untranslated"].append(line)
            else:
                native["materials"][material]["commands"].append(line)
                if parts[0] in ("E", "POISSON", "DENSITY", "ALPHA", "DAMP"):
                    value = _number(parts[1])
                    if length is None or force is None:
                        raise ValueError("UNIT is required before material definitions")
                    key, scale = {"E": ("E_kn_m2", force/length**2),
                                  "DENSITY": ("density_kn_m3", force/length**3)}.get(parts[0], (parts[0].lower(), 1))
                    native["materials"][material][key] = value * scale
            continue
        if u == "CONSTANTS": mode = "constants"; continue
        if u.startswith("MATERIAL ") and mode == "constants":
            for mid in _ids(" ".join(parts[2:]), model.members):
                model.replace_member(replace(model.members[mid], material=parts[1]))
            continue
        if u.startswith("BETA ") and mode == "constants":
            for mid in _ids(" ".join(parts[2:]), model.members):
                native["specifications"].setdefault(mid, {})["beta_deg"] = _number(parts[1])
            continue
        if u in ("MEMBER RELEASE", "MEMBER TENSION", "MEMBER COMPRESSION", "MEMBER TRUSS"):
            mode = u.lower(); continue
        if u == "SUPPORTS": mode = "supports"; continue
        if u.startswith("DEFINE "):
            mode = "envelope" if u == "DEFINE ENVELOPE" else "definition"
            if mode == "definition": native["definitions"].append(line)
            continue
        if u.startswith("END DEFINE"): mode = ""; continue
        match = re.match(r"LOAD\s+COMB(?:INATION)?\s+(\d+)\s*(.*)", line, re.I)
        if match:
            case, name = match.groups()
            if case in model.combinations or case in model.load_cases:
                raise ValueError(f"Duplicate load ID {case}")
            model.combinations[case] = LoadCombination(case, name, {}, "STAAD native")
            mode = "combination"
            continue
        match = re.match(r"LOAD\s+(\d+)\b(.*)", line, re.I)
        if match:
            case, description = match.groups()
            if case in model.load_cases or case in model.combinations:
                raise ValueError(f"Duplicate load ID {case}")
            kind = re.search(r"LOADTYPE\s+(\S+)", description, re.I)
            title = re.search(r"TITLE\s+(.*)", description, re.I)
            model.load_cases[case] = LoadCase(case, title[1] if title else description.strip(),
                                            kind[1].lower() if kind else "other")
            native["loads"][case] = []
            mode = "load"
            continue
        if u in ("MEMBER LOAD", "JOINT LOAD", "REPEAT LOAD") and case in native["loads"]:
            mode = u.lower()
            native["loads"][case].append({"command": line, "length_unit_m": length, "force_unit_kn": force})
            continue
        if u.startswith(("PERFORM ", "PDELTA ", "CHANGE")):
            native["analysis_commands"].append(line); mode = ""; continue
        if u.startswith("PARAMETER "):
            mode, parameter_set = "parameter", parts[1]; continue
        if u.startswith("CODE "):
            native["code"] = line; continue
        if u.startswith("CHECK CODE "):
            native["checked_members"].extend(_ids(" ".join(parts[2:]), model.members))
            mode = ""; continue
        if u.startswith(("LOAD LIST ", "STEEL TAKE OFF", "PRINT ")):
            native.setdefault("design_commands", []).append(line); continue
        if u.startswith(("STAAD ", "START JOB", "END JOB", "ENGINEER ", "INPUT WIDTH", "FINISH")):
            mode = ""; continue

        if mode in ("nodes", "members"):
            if length is None:
                raise ValueError("Explicit UNIT is required before JOINT COORDINATES")
            size = 4 if mode == "nodes" else 3
            if len(parts) != size:
                raise ValueError(f"Unsupported or malformed {mode}: {line}")
            if mode == "nodes":
                nid = int(parts[0])
                model.add_node(Node(nid, *(_number(t)*length for t in parts[1:]), label=f"N{nid}"))
            else:
                mid, n1, n2 = map(int, parts)
                if n1 not in model.nodes or n2 not in model.nodes:
                    raise ValueError(f"Unknown endpoint for member {mid}")
                if math.dist(model.nodes[n1].coords, model.nodes[n2].coords) < 1e-9:
                    raise ValueError(f"Zero length member {mid}")
                model.add_member(Member(mid, n1, n2, _infer_member_type(model.nodes[n1], model.nodes[n2]), label=f"M{mid}"))
        elif mode == "properties":
            match = re.match(r"(.+?)\s+(TAPERED|PRIS|TABLE)\s+(.+)", u)
            if not match:
                native["untranslated"].append(line); mode = ""; continue
            idtext, kind, definition = match.groups()
            prop = {"kind": kind, "table": table, "definition": definition, "length_unit_m": length}
            if kind == "TAPERED":
                dims = [_number(t)*length for t in definition.split()]
                if len(dims) != 7 or min(dims) <= 0:
                    raise ValueError(f"Invalid tapered dimensions: {line}")
                prop["dimensions_m"] = dict(zip(("depth_start", "web_thickness", "depth_end", "top_width", "top_thickness", "bottom_width", "bottom_thickness"), dims))
            section = re.sub(r"^ST\s+", "", definition) if kind == "TABLE" else kind + " " + definition
            section = re.sub(r"^ISMB\s*(\d+)$", r"ISMB \1", section)
            for mid in _ids(idtext, model.members):
                native["properties"][mid] = dict(prop)
                model.replace_member(replace(model.members[mid], section=section))
        elif mode == "supports":
            native["support_commands"].append(line)
            match = re.fullmatch(r"(.+?)\s+(PINNED|FIXED)(?:\s+BUT\s+(.+))?", u)
            if not match:
                native["untranslated"].append(line); mode = ""; continue
            idtext, kind, free = match.groups()
            dofs = (free or "").split()
            if any(d not in ("FX", "FY", "FZ", "MX", "MY", "MZ") for d in dofs):
                native["untranslated"].append(line); continue
            flags = [True]*3 + [kind == "FIXED"]*3
            for d in dofs: flags[("FX", "FY", "FZ", "MX", "MY", "MZ").index(d)] = False
            for nid in _ids(idtext, model.nodes):
                model.set_support(Support(nid, SupportType(kind.lower()), *flags))
        elif mode.startswith("member ") and mode not in ("member load",):
            if mode == "member release":
                match = re.fullmatch(r"(.+?)\s+(START|END)\s+(.+)", u)
                if not match:
                    native["untranslated"].append(line); mode = ""; continue
                idtext, end, release = match.groups()
                for mid in _ids(idtext, model.members):
                    native["specifications"].setdefault(mid, {}).setdefault("releases", {})[end] = release
            else:
                for mid in _ids(u, model.members):
                    native["specifications"].setdefault(mid, {})[mode.split()[1]] = True
                    if mode == "member tension":
                        model.replace_member(replace(model.members[mid], member_type="bracing"))
        elif mode in ("load", "member load", "joint load", "repeat load"):
            record = {"command": line, "length_unit_m": length, "force_unit_kn": force, "represented": False}
            native["loads"][case].append(record)
            # Only exact, full-member global UDLs and force-only joint loads can
            # be displayed by the app. Local/partial/generated loads stay native.
            match = re.fullmatch(r"(.+?)\s+UNI\s+(GX|GY|GZ)\s+(\S+)", u)
            if mode == "member load" and match:
                idtext, axis, value = match.groups()
                values = {"f"+axis[-1].lower()+"_kn_m": _number(value)*force/length}
                for mid in _ids(idtext, model.members):
                    model.member_loads.append(MemberUniformLoad(mid, case, **values))
                record["represented"] = True
            elif mode == "joint load":
                match = re.fullmatch(r"(.+?)\s+((?:F[XYZ]\s+[-+\d.eE]+\s*)+)", line, re.I)
                if match:
                    values = {axis.lower()+"_kn": _number(v)*force for axis, v in re.findall(r"(F[XYZ])\s+(\S+)", match[2].upper())}
                    for nid in _ids(match[1], model.nodes):
                        model.nodal_loads.append(NodalLoad(nid, case, **values))
                    record["represented"] = True
            elif mode == "repeat load":
                native.setdefault("repeat_loads", {})[case] = line
        elif mode == "combination":
            if len(parts) % 2:
                raise ValueError(f"Malformed load combination {case}: {line}")
            for j in range(0, len(parts), 2):
                int(parts[j])  # disallow command text masquerading as an ID
                factors = model.combinations[case].factors
                factors[parts[j]] = factors.get(parts[j], 0) + _number(parts[j+1])
        elif mode == "definition":
            native["definitions"].append(line)
        elif mode == "envelope":
            native["envelopes"].append(line)
            match = re.match(r"(.+?)\s+ENVELOPE\s+\d+\s+TYPE\s+(\S+)", u)
            if match:
                for cid in _expand_ids(match[1].split()):
                    key = str(cid)
                    if key in model.combinations:
                        model.combinations[key] = replace(model.combinations[key], source=match[2].title())
        elif mode == "parameter":
            match = re.fullmatch(r"(\w+)\s+(\S+)\s+(.+)", u)
            if match:
                key, value, idtext = match.groups()
                # Keep original units as well as engineering units for display.
                value = _number(value)
                scale = length if key in ("LX", "LY", "LZ") else force/length**2 if key in ("FYLD", "FU") else 1
                for mid in _ids(idtext, model.members):
                    native["design_parameters"].setdefault(mid, {})[key] = {"value": value, "value_si": value*scale, "set": parameter_set}
            else:
                native["untranslated"].append(line)
        else:
            native["untranslated"].append(line)

    if not model.nodes: raise ValueError("No JOINT COORDINATES found in STD file.")
    if not model.members: raise ValueError("No MEMBER INCIDENCES found in STD file.")
    for combo in model.combinations.values():
        if set(combo.factors) - set(model.load_cases):
            model.metadata["audit_warnings"].append(f"Combination {combo.id} references cases outside the primary load list.")
    xs, ys, zs = zip(*(n.coords for n in model.nodes.values()))
    model.metadata.update(span_m=max(xs)-min(xs), length_m=max(zs)-min(zs),
                          ridge_height_m=max(ys)-min(ys), ffl_level_m=min(ys),
                          number_of_frames=len(set(zs)), description="Native STAAD reference (read-only)")
    # Do not infer eaves or a parametric clear span from an arbitrary 3D model.
    native["checked_members"] = sorted(set(native["checked_members"]))
    model.metadata["staad_import_fingerprint"] = model_fingerprint(model)
    return model
