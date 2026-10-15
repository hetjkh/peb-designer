"""PyVista / Qt interactive 3D structural viewer."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.core.models import StructuralModel

MEMBER_COLORS = {
    "column": "#2F5D8C",
    "rafter": "#C45C26",
    "mezzanine_beam": "#E8913A",
    "mezzanine_column": "#E8913A",
    "generic": "#555555",
}


class StructuralViewer3D(QWidget):
    """Embeddable interactive 3D viewer for a StructuralModel."""

    member_picked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._plotter = QtInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plotter.interactor)

        self._show_node_ids = True
        self._show_member_ids = True
        self._show_loads = True
        self._show_utilization = True
        self._model: Optional[StructuralModel] = None
        self._selected_member_id: Optional[int] = None

        self._configure_scene()

    def _configure_scene(self) -> None:
        self._plotter.set_background("#F5F5F5", top="#DEDEDE")
        self._plotter.show_axes()
        self._plotter.enable_trackball_style()

    @property
    def show_node_ids(self) -> bool:
        return self._show_node_ids

    @show_node_ids.setter
    def show_node_ids(self, value: bool) -> None:
        self._show_node_ids = bool(value)
        if self._model is not None:
            self.display_model(self._model)

    @property
    def show_member_ids(self) -> bool:
        return self._show_member_ids

    @show_member_ids.setter
    def show_member_ids(self, value: bool) -> None:
        self._show_member_ids = bool(value)
        if self._model is not None:
            self.display_model(self._model)

    @property
    def show_loads(self) -> bool:
        return self._show_loads

    @show_loads.setter
    def show_loads(self, value: bool) -> None:
        self._show_loads = bool(value)
        if self._model is not None:
            self.display_model(self._model)

    @property
    def show_utilization(self) -> bool:
        return self._show_utilization

    @show_utilization.setter
    def show_utilization(self, value: bool) -> None:
        self._show_utilization = bool(value)
        if self._model is not None:
            self.display_model(self._model)

    def clear(self) -> None:
        self._model = None
        self._selected_member_id = None
        self._plotter.clear()
        self._configure_scene()
        self._plotter.add_text(
            "Enter geometry and click GENERATE",
            position="upper_left",
            font_size=10,
            color="#666666",
            name="hint",
        )

    def select_member(self, member_id: Optional[int]) -> None:
        self._selected_member_id = member_id
        if self._model is not None:
            self.display_model(self._model)

    def display_model(self, model: StructuralModel) -> None:
        """Render nodes, members, optional loads and utilization."""
        camera = self._plotter.camera_position if self._model is not None else None
        self._model = model
        self._plotter.clear()
        self._configure_scene()

        if not model.nodes:
            self.clear()
            return

        batches = {}
        label_points, member_labels = [], []
        for member, n0, n1 in model.iter_member_endpoints():
            points = np.array([n0.coords, n1.coords], dtype=float)
            color = MEMBER_COLORS.get(member.member_type, MEMBER_COLORS["generic"])
            width = 4
            if self._show_utilization and member.id in model.design_results:
                util = model.design_results[member.id].max_utilization
                if model.design_results[member.id].status == "FAIL":
                    color = "#C62828"
                elif util > 0.85:
                    color = "#EF6C00"
                elif model.design_results[member.id].status == "PASS":
                    color = "#2E7D32"
            elif self._show_utilization and model.metadata.get("staad_native"):
                color = "#808080"  # No native design result, not PASS.
            if self._selected_member_id == member.id:
                color = "#6A1B9A"
                width = 8
            batches.setdefault((color, width), []).extend(points)

            if self._show_member_ids:
                mid = (points[0] + points[1]) / 2.0
                label = f"M{member.id}"
                if member.id in model.design_results:
                    label += f" {model.design_results[member.id].max_utilization:.2f}"
                label_points.append(mid)
                member_labels.append(label)

        for index, ((color, width), points) in enumerate(batches.items()):
            points = np.array(points)
            cells = np.array([[2, i, i+1] for i in range(0, len(points), 2)]).ravel()
            mesh = pv.PolyData(points, lines=cells)
            self._plotter.add_mesh(mesh, color=color, line_width=width, name=f"members_{index}", render=False)
        if label_points:
            self._plotter.add_point_labels(label_points, member_labels, font_size=9,
                text_color="#1A1A1A", point_size=0, shape=None, always_visible=True,
                name="member_labels", render=False)

        node_pts = np.array([n.coords for n in model.node_list()], dtype=float)
        cloud = pv.PolyData(node_pts)
        self._plotter.add_mesh(
            cloud,
            color="#1B3A4B",
            point_size=12,
            render_points_as_spheres=True,
            name="nodes",
        )

        # Supports as cones
        for sid, support in model.supports.items():
            n = model.nodes[sid]
            cone = pv.Cone(
                center=(n.x, n.y - 0.25, n.z),
                direction=(0, 1, 0),
                height=0.5,
                radius=0.25,
            )
            color = "#455A64" if support.support_type.value == "fixed" else "#78909C"
            self._plotter.add_mesh(cone, color=color, name=f"support_{sid}")

        if self._show_node_ids:
            labels = [f"N{n.id}" for n in model.node_list()]
            self._plotter.add_point_labels(
                node_pts,
                labels,
                font_size=10,
                text_color="#0D47A1",
                point_size=0,
                shape=None,
                always_visible=True,
                name="node_labels",
            )

        if self._show_loads and model.member_loads and not model.metadata.get("staad_native"):
            self._draw_loads(model)

        span = float(model.metadata.get("span_m", 0.0) or 0.0)
        length = float(model.metadata.get("length_m", 0.0) or 0.0)
        if span > 0 and length > 0 and not model.metadata.get("staad_native"):
            for i, edge in enumerate(
                (
                    pv.Line((0.0, 0.0, 0.0), (span, 0.0, 0.0)),
                    pv.Line((span, 0.0, 0.0), (span, 0.0, length)),
                    pv.Line((span, 0.0, length), (0.0, 0.0, length)),
                    pv.Line((0.0, 0.0, length), (0.0, 0.0, 0.0)),
                )
            ):
                self._plotter.add_mesh(
                    edge, color="#9AA5B1", line_width=1, opacity=0.6, name=f"footprint_{i}"
                )

        n_frames = model.metadata.get("number_of_frames", "?")
        extra = ""
        if model.analysis:
            extra = f"  |  Analysis: {model.analysis.status}"
        if model.metadata.get("staad_native"):
            extra += "\nNative ANL: red = FAIL; green/orange = PASS; gray = no result"
            extra += "\nNative load diagrams: inspect in STAAD.Pro"
        self._plotter.add_text(
            f"{model.summary()}  |  Frames: {n_frames}{extra}",
            position="upper_left",
            font_size=10,
            color="#223344",
            name="summary",
        )

        if camera is None:
            self._plotter.reset_camera()
            self._plotter.view_isometric()
        else:
            self._plotter.camera_position = camera

    def _draw_loads(self, model: StructuralModel) -> None:
        # Draw a subset of DL gravity arrows on rafters + WL on windward columns
        count = 0
        for mload in model.member_loads:
            if count > 80:
                break
            if mload.load_case_id not in ("DL", "WL"):
                continue
            member = model.members.get(mload.member_id)
            if member is None:
                continue
            n0 = model.nodes[member.start_node]
            n1 = model.nodes[member.end_node]
            mid = np.array(
                [(n0.x + n1.x) / 2, (n0.y + n1.y) / 2, (n0.z + n1.z) / 2], dtype=float
            )
            if abs(mload.fy_kn_m) > 1e-9:
                end = mid + np.array([0.0, 0.8 if mload.fy_kn_m > 0 else -0.8, 0.0])
                color = "#1565C0"
            elif abs(mload.fx_kn_m) > 1e-9:
                end = mid + np.array([0.8 if mload.fx_kn_m > 0 else -0.8, 0.0, 0.0])
                color = "#C62828"
            else:
                continue
            arrow = pv.Arrow(
                start=mid,
                direction=end - mid,
                tip_length=0.35,
                tip_radius=0.08,
                shaft_radius=0.03,
                scale="auto",
            )
            self._plotter.add_mesh(arrow, color=color, name=f"load_{count}")
            count += 1

    def reset_camera(self) -> None:
        self._plotter.reset_camera()
        self._plotter.view_isometric()
