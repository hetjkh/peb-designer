"""Shared nodes and split members for attachments in the analytical model."""
from dataclasses import replace
from math import dist

from app.core.models import Member, Node


def node_at(model, x, y, z):
    for node in model.nodes.values():
        if dist(node.coords, (x, y, z)) < 1e-7:
            return node.id
    nid = max(model.nodes, default=0) + 1
    model.add_node(Node(nid, x, y, z))
    return nid


def member_between(model, a, b, kind):
    if a == b:
        return
    for member in model.members.values():
        if {a, b} == {member.start_node, member.end_node}:
            return
    mid = max(model.members, default=0) + 1
    model.add_member(Member(mid, a, b, member_type=kind))


def connect_intersections(model):
    """Merge coincident joints, split members at joints, remove overlaps."""
    canonical = {}
    remap = {}
    for node in list(model.nodes.values()):
        key = tuple(round(v, 7) for v in node.coords)
        if key in canonical:
            remap[node.id] = canonical[key]
            del model.nodes[node.id]
        else:
            canonical[key] = node.id
            remap[node.id] = node.id
    old = list(model.members.values())
    previous_lengths = model.metadata.get("physical_member_lengths_m", {})
    physical_lengths = {}
    model.members.clear()
    seen = set()
    next_id = max((m.id for m in old), default=0) + 1
    for member in old:
        a, b = model.nodes[remap[member.start_node]], model.nodes[remap[member.end_node]]
        length = dist(a.coords, b.coords)
        if length < 1e-8:
            continue
        points = [(0.0, a.id), (length, b.id)]
        for node in model.nodes.values():
            if node.id in (a.id, b.id):
                continue
            d = dist(a.coords, node.coords)
            if abs(d + dist(node.coords, b.coords) - length) < 1e-8:
                points.append((d, node.id))
        points.sort()
        for index, ((_, n0), (_, n1)) in enumerate(zip(points, points[1:])):
            key = tuple(sorted((n0, n1)))
            if key in seen:
                continue
            seen.add(key)
            mid = member.id if index == 0 else next_id
            if index:
                next_id += 1
            model.add_member(replace(member, id=mid, start_node=n0, end_node=n1))
            physical_lengths[mid] = previous_lengths.get(member.id, length)
    model.metadata["physical_member_lengths_m"] = physical_lengths


def add_extensions(model, params, profile):
    from app.geometry.peb_frame import _interp_profile_y
    ffl = params.ffl_level_m
    support_overrides = {}
    for z in params.frame_stations_z:
        for side, x, sign in (("left", 0.0, -1), ("right", params.span_m, 1)):
            eave = _interp_profile_y(profile, x)
            ext = params.extensions
            lean = getattr(ext, "lean_to_" + side)
            if lean.enabled:
                h = lean.conn_height_m if lean.conn_height_m is not None else eave
                tip = h - lean.width_m * lean.slope_x10 / 10
                base = node_at(model, x + sign * lean.width_m, ffl, z)
                top = node_at(model, x + sign * lean.width_m, ffl + tip, z)
                attach = node_at(model, x, ffl + h, z)
                member_between(model, base, top, "lean_column")
                member_between(model, attach, top, "lean_rafter")
                support_overrides[base] = lean.base
            roof = getattr(ext, "roof_ext_" + side)
            if roof.enabled:
                p0, p1 = (profile[0], profile[1]) if side == "left" else (profile[-2], profile[-1])
                gradient = (p1[1]-p0[1]) / (p1[0]-p0[0])
                member_between(model, node_at(model, x, ffl + eave, z),
                               node_at(model, x + sign * roof.projection_m, ffl + eave + sign * roof.projection_m * gradient, z), "roof_extension")
            canopy = getattr(ext, "canopy_" + side)
            if canopy.enabled:
                h = canopy.height_on_col_m
                member_between(model, node_at(model, x, ffl + h, z),
                               node_at(model, x + sign * canopy.width_m,
                                       ffl + h - canopy.width_m * canopy.slope_x10 / 10, z), "canopy")
        monitor = params.resolved_roof_monitor()
        if monitor.enabled:
            center = params.resolved_ridge_x()
            x0, x1 = center - monitor.throat_width_m / 2, center + monitor.throat_width_m / 2
            top_y = max(y for _, y, _ in profile) + monitor.height_m + ffl
            rise = min(0.35, monitor.height_m * 0.2)
            peak = node_at(model, center, top_y + rise, z)
            tops = []
            for x in (x0, x1):
                base = node_at(model, x, ffl + _interp_profile_y(profile, x), z)
                post_top_y = top_y + rise * monitor.extension_m / (monitor.throat_width_m / 2 + monitor.extension_m)
                top = node_at(model, x, post_top_y, z)
                member_between(model, base, top, "monitor_column")
                tops.append(top)
                member_between(model, top, peak, "monitor_rafter")
            for x, sign, top in ((x0, -1, tops[0]), (x1, 1, tops[1])):
                if monitor.extension_m:
                    member_between(model, top, node_at(model, x + sign * monitor.extension_m, top_y, z), "monitor_rafter")
    model.metadata["support_overrides"] = support_overrides


def add_secondary_members(model, purlin_spacing, girt_spacing):
    """Secondary longitudinal members connect actual split frame joints."""
    import math
    stations = sorted({n.z for n in model.nodes.values()})
    patterns = set()
    for m in list(model.members.values()):
        a, b = model.nodes[m.start_node], model.nodes[m.end_node]
        if abs(a.z - stations[0]) > 1e-7 or abs(b.z - stations[0]) > 1e-7:
            continue
        if m.member_type not in ("column", "rafter"):
            continue
        spacing = purlin_spacing if m.member_type == "rafter" else girt_spacing
        kind = "purlin" if m.member_type == "rafter" else "girt"
        count = max(1, math.ceil(dist(a.coords, b.coords) / spacing))
        for i in range(count + 1):
            if kind == "girt" and i == 0:
                continue
            t = i / count
            patterns.add((a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), kind))
    for x, y, kind in sorted(patterns):
        nodes = [node_at(model, x, y, z) for z in stations]
        for a, b in zip(nodes, nodes[1:]):
            member_between(model, a, b, kind)
    connect_intersections(model)
