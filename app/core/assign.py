"""Assign sections, materials, and supports to a generated geometry model."""

from __future__ import annotations

from app.core.models import Member, StructuralModel, Support, SupportType
from app.database.sections import default_section_for_type


def assign_defaults(
    model: StructuralModel,
    *,
    column_section: str = "ISMB 400",
    rafter_section: str = "ISMB 350",
    material: str = "E350",
    support_type: SupportType = SupportType.PINNED,
) -> StructuralModel:
    """Fill section/material on members and supports on base nodes."""
    ffl = float(model.metadata.get("ffl_level_m", 0.0) or 0.0)

    for mid, member in list(model.members.items()):
        if member.member_type in ("column", "lean_column", "monitor_column"):
            sec = column_section
        elif member.member_type in ("rafter", "lean_rafter", "canopy", "roof_extension", "monitor_rafter"):
            sec = rafter_section
        else:
            sec = default_section_for_type(member.member_type)
        model.replace_member(
            Member(
                id=member.id,
                start_node=member.start_node,
                end_node=member.end_node,
                member_type=member.member_type,
                section=sec,
                material=material,
                label=member.label,
            )
        )

    # Base supports at FFL
    mz_meta = model.metadata.get("mezzanine") or {}
    mz_conn = str(mz_meta.get("connection_type", "pinned") or "pinned").lower()
    mz_support = (
        SupportType.FIXED if mz_conn == "fixed" else SupportType.PINNED
    )
    mezz_base_nodes = set()
    for member in model.member_list():
        if member.member_type == "mezzanine_column":
            n0 = model.nodes[member.start_node]
            n1 = model.nodes[member.end_node]
            base = n0 if n0.y <= n1.y else n1
            mezz_base_nodes.add(base.id)

    for node in model.node_list():
        if abs(node.y - ffl) > 1e-9:
            continue
        st = mz_support if node.id in mezz_base_nodes or mz_meta.get("flat_roof_mezz_only") else support_type
        override = model.metadata.get("support_overrides", {}).get(node.id)
        if override:
            st = SupportType(override.lower())
        if st == SupportType.FIXED:
            model.set_support(
                Support(
                    node_id=node.id,
                    support_type=SupportType.FIXED,
                    ux=True,
                    uy=True,
                    uz=True,
                    rx=True,
                    ry=True,
                    rz=True,
                )
            )
        else:
            model.set_support(
                Support(
                    node_id=node.id,
                    support_type=SupportType.PINNED,
                    ux=True,
                    uy=True,
                    uz=True,
                    rx=False,
                    ry=False,
                    rz=False,
                )
            )

    model.metadata["default_material"] = material
    model.metadata["column_section"] = column_section
    model.metadata["rafter_section"] = rafter_section
    model.metadata["support_type"] = support_type.value
    return model
