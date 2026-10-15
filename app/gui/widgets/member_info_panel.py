"""Member information panel for selected member."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from app.core.models import StructuralModel


class MemberInfoPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setPlaceholderText("Select a member to view section, forces, and design checks.")
        layout.addWidget(self.body)

    def clear(self) -> None:
        self.body.clear()

    def show_member(self, model: StructuralModel, member_id: int) -> None:
        member = model.members.get(member_id)
        if member is None:
            self.body.setPlainText(f"Member M{member_id} not found.")
            return
        n0 = model.nodes[member.start_node]
        n1 = model.nodes[member.end_node]
        length = (
            (n1.x - n0.x) ** 2 + (n1.y - n0.y) ** 2 + (n1.z - n0.z) ** 2
        ) ** 0.5

        lines = [
            f"Member: M{member.id}",
            f"Label: {member.label or '—'}",
            f"Type: {member.member_type}",
            f"Section: {member.section or '—'}",
            f"Material: {member.material or '—'}",
            f"Length: {length:.3f} m",
            f"Nodes: N{member.start_node} → N{member.end_node}",
            "",
        ]

        native = model.metadata.get("staad_native")
        if native:
            prop = native["properties"].get(member_id, {})
            if prop.get("table"):
                lines.append(f"STAAD section table: {prop['table']}")
            for key, value in prop.get("dimensions_m", {}).items():
                lines.append(f"  {key.replace('_', ' ')}: {value * 1000:g} mm")
            mat = native["materials"].get(member.material, {})
            if "E_kn_m2" in mat:
                lines.append(f"Elastic modulus: {mat['E_kn_m2']/1000:g} MPa")
            if "density_kn_m3" in mat:
                lines.append(f"Weight density: {mat['density_kn_m3']:g} kN/m3")
            lines.append("Specifications: " + str(native["specifications"].get(member_id, {})))
            params = native["design_parameters"].get(member_id, {})
            if params:
                lines.append("Native design parameters (m, kN):")
                for key, value in params.items():
                    unit = " m" if key in ("LX", "LY", "LZ") else " kN/m2" if key in ("FYLD", "FU") else ""
                    lines.append(f"  {key}: {value['value_si']:g}{unit}")
            if member_id not in native["checked_members"]:
                lines.append("Outside native CHECK CODE list: unchecked.")
            if model.metadata.get("staad_results", {}).get("attached"):
                lines.append("Results below are from the matching STAAD ANL, not app calculations.")
            lines.append("")

        if model.analysis and model.analysis.status == "ok":
            forces = model.analysis.forces_for_member(member_id)
            if forces:
                # Show envelope
                nmax = max(f.n_max_abs for f in forces)
                vmax = max(f.v_max_abs for f in forces)
                mmax = max(f.m_max_abs for f in forces)
                lines += [
                    "Analysis envelope (all combos):",
                    f"  |Axial| max: {nmax:.2f} kN",
                    f"  |Shear| max: {vmax:.2f} kN",
                    f"  |Moment| max: {mmax:.2f} kN·m",
                    "",
                ]
                # Detail first few combos
                lines.append("By combination:")
                for f in forces[:6]:
                    lines.append(
                        f"  {f.combination_id}: N={f.n_start_kn:.1f}/{f.n_end_kn:.1f}  "
                        f"V={f.v_start_kn:.1f}/{f.v_end_kn:.1f}  "
                        f"M={f.m_start_knm:.1f}/{f.m_end_knm:.1f}"
                    )
                lines.append("")

        design = model.design_results.get(member_id)
        if design:
            lines += [
                f"Design STATUS: {design.status}",
                f"Max utilization: {design.max_utilization:.3f}",
                "",
            ]
            for chk in design.checks:
                lines.append(
                    f"  {chk.name}: {chk.status}  util={chk.utilization:.3f}"
                )
                if chk.detail:
                    lines.append(f"    {chk.detail}")
            lines.append("")
            lines.append("Not validated for construction design.")
        else:
            lines.append("No design results for this member.")

        self.body.setPlainText("\n".join(lines))
