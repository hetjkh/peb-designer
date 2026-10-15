"""Live 2D cross-section preview — technical PEB frame drawing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

# Monochrome technical drawing; accent colours for mezz / crane / monitor.
BG = QColor("#171717")
STRUCTURE = QColor("#F0F0F0")
STRUCTURE_DIM = QColor("#B0B0B0")
NODE_FILL = QColor("#FFFFFF")
DIM_COLOR = QColor("#A0A0A0")
GROUND = QColor("#606060")
TEXT_PRIMARY = QColor("#E6E6E6")
TEXT_MUTED = QColor("#909090")
SUPPORT = QColor("#D0D0D0")
MEZZ = QColor("#E8913A")
CRANE = QColor("#F5C518")
MONITOR = QColor("#E85A9B")
LEAN = QColor("#6EB5FF")
ROOF_EXT = QColor("#B57BFF")  # purple
FASCIA = QColor("#E85A9B")  # pink
CANOPY = QColor("#5FBF6A")  # green


class FramePreview2D(QWidget):
    """Draws the transverse frame profile with dimensions (STAAD-style sketch)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self._profile: List[Tuple[float, float, str]] = []
        self._column_xs: List[float] = []
        self._meta: Dict[str, Any] = {}
        self._analytical_model = None
        self._frame_station = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._dragging = False
        self._last_pos = QPointF()
        self._crane_phase = 0.0  # 0..1 trolley position (ping-pong)
        self._crane_dir = 1.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(40)  # ~25 fps
        self._anim_timer.timeout.connect(self._tick_crane)
        self.setToolTip("")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def clear_preview(self) -> None:
        self._analytical_model = None
        self._profile = []
        self._column_xs = []
        self._meta = {}
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._anim_timer.stop()
        self.update()

    def set_from_metadata(self, metadata: Dict[str, Any]) -> None:
        self._analytical_model = None
        profile = metadata.get("profile_xy") or []
        self._profile = [(float(x), float(y), str(r)) for x, y, r in profile]
        self._column_xs = [float(x) for x in (metadata.get("column_xs") or [])]
        self._meta = dict(metadata)
        self._sync_crane_animation()
        self.update()

    def set_model(self, model, station=None) -> None:
        """Render the same joints/members used for calculations and export."""
        self.set_from_metadata(model.metadata)
        self._analytical_model = model
        self._frame_station = station
        self._anim_timer.stop()
        self.update()

    def _paint_analytical(self, painter, width, height):
        from app.export.staad import extract_transverse_frame
        from app.loads.engine import tributary_widths
        model = self._analytical_model
        native = bool(model.metadata.get("staad_native"))
        widths = {} if native else tributary_widths(model)
        station = self._frame_station if self._frame_station is not None else model.metadata.get("export_frame_z")
        if station is None:
            station = max(widths, key=widths.get) if widths else min(n.z for n in model.nodes.values())
        if native:
            # Geometry slice only: longitudinal loads/specifications cannot be
            # represented by an independent transverse analysis model.
            from app.core.models import StructuralModel
            nodes = {i: n for i, n in model.nodes.items() if abs(n.z-station) < 1e-6}
            frame = StructuralModel(nodes=nodes,
                members={i: m for i, m in model.members.items() if m.start_node in nodes and m.end_node in nodes},
                supports={i: s for i, s in model.supports.items() if i in nodes})
        else:
            frame = extract_transverse_frame(model, station)
        if not frame.nodes:
            return
        xs = [n.x for n in frame.nodes.values()]
        ys = [n.y for n in frame.nodes.values()]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        scale = min(max(1, width-140)/max(1, xmax-xmin), max(1, height-135)/max(1, ymax-ymin)) * self._zoom
        sx = lambda x: width/2 + (x-(xmin+xmax)/2)*scale + self._pan_x
        sy = lambda y: height/2 - (y-(ymin+ymax)/2)*scale + self._pan_y
        painter.setPen(TEXT_PRIMARY)
        painter.setFont(QFont("Segoe UI", 10))
        heading = (f"REFERENCE GEOMETRY SLICE   Z = {station:g} m (not a separate analysis model)" if native else
                   f"ANALYTICAL FRAME   Z = {station:g} m   |   Tributary width = {widths.get(round(station, 6), 0):g} m")
        painter.drawText(16, 24, heading)
        painter.setFont(QFont("Segoe UI", 8))
        for member, a, b in frame.iter_member_endpoints():
            color = MEZZ if "mezzanine" in member.member_type else (
                LEAN if member.member_type.startswith("lean") else
                MONITOR if member.member_type.startswith("monitor") else
                CANOPY if member.member_type in ("canopy", "roof_extension", "fascia") else STRUCTURE)
            if native:
                result = model.design_results.get(member.id)
                color = QColor("#E45454") if result and result.status == "FAIL" else QColor("#5FBF6A") if result and result.status == "PASS" else STRUCTURE_DIM
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(sx(a.x), sy(a.y)), QPointF(sx(b.x), sy(b.y)))
        painter.setPen(QPen(STRUCTURE, 1))
        painter.setBrush(NODE_FILL)
        for node in frame.nodes.values():
            painter.drawEllipse(QPointF(sx(node.x), sy(node.y)), 2.3, 2.3)
        for nid, support in frame.supports.items():
            node = frame.nodes[nid]
            if support.support_type.value == "fixed":
                painter.setPen(QPen(SUPPORT, 3))
                painter.drawLine(QPointF(sx(node.x)-9, sy(node.y)+3), QPointF(sx(node.x)+9, sy(node.y)+3))
                for offset in (-8, -4, 0, 4, 8):
                    painter.drawLine(QPointF(sx(node.x)+offset, sy(node.y)+3), QPointF(sx(node.x)+offset-3, sy(node.y)+9))
            else:
                self._draw_pin_support(painter, sx(node.x), sy(node.y))
        self._draw_h_dimension(painter, sx(xmin), sx(xmax), sy(ymin)+40, f"{xmax-xmin:.3g} m")
        self._draw_v_dimension(painter, sx(xmin)-35, sy(ymin), sy(ymax), f"{ymax-ymin:.3g} m")
        painter.setPen(TEXT_MUTED)
        note = f"{len(frame.nodes)} joints | {len(frame.members)} members | Actual connected geometry"
        if model.metadata.get("crane", {}).get("enabled"):
            note += " | Crane annotation excluded from analytical model"
        painter.drawText(16, height-12, note)

    def set_profile(
        self,
        profile: Sequence[Tuple[float, float, str]],
        column_xs: Sequence[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._profile = list(profile)
        self._column_xs = list(column_xs)
        self._meta = dict(metadata or {})
        self._sync_crane_animation()
        self.update()

    def _sync_crane_animation(self) -> None:
        crane = self._meta.get("crane") or {}
        if crane.get("enabled"):
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_timer.stop()

    def _tick_crane(self) -> None:
        crane = self._meta.get("crane") or {}
        if not crane.get("enabled") or not self._profile:
            self._anim_timer.stop()
            return
        self._crane_phase += 0.012 * self._crane_dir
        if self._crane_phase >= 1.0:
            self._crane_phase = 1.0
            self._crane_dir = -1.0
        elif self._crane_phase <= 0.0:
            self._crane_phase = 0.0
            self._crane_dir = 1.0
        self.update()

    def render_to_image(self, width: int = 900, height: int = 420) -> QImage:
        """Render the current 2D preview to an image (for tests / exports)."""
        image = QImage(QSize(width, height), QImage.Format.Format_ARGB32)
        image.fill(BG)
        painter = QPainter(image)
        self._paint_scene(painter, width, height, interactive_hints=False)
        painter.end()
        return image

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        self._paint_scene(painter, self.width(), self.height(), interactive_hints=True)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not self._profile and self._analytical_model is None:
            return
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else (1 / 1.12)
        self._zoom = max(0.45, min(4.0, self._zoom * factor))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            pos = event.position()
            self._pan_x += pos.x() - self._last_pos.x()
            self._pan_y += pos.y() - self._last_pos.y()
            self._last_pos = pos
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    def _draw_side_extensions(
        self,
        painter: QPainter,
        sx,
        sy,
        *,
        width: float,
        eave: float,
        pitch_n: float,
        ext: Dict[str, Any],
    ) -> None:
        """Draw lean-to, roof extension (purple), fascia (pink), canopy (green)."""
        n = max(pitch_n, 1e-6)

        def lean(side: str, data: dict) -> None:
            if not data.get("enabled"):
                return
            w = float(data.get("width_m", 0) or 0)
            if w <= 0:
                return
            slope_x = float(data.get("slope_x10", 1) or 1)
            # rise over width for lean-to roof: slope X:10 → N=10/X
            ln = 10.0 / slope_x if slope_x > 0 else n
            conn = data.get("conn_height_m")
            h_conn = float(conn) if conn not in (None, "") else eave
            # Outer eave is lower (typical lean-to drains away from main)
            rise = w / ln
            h_outer = max(0.5, h_conn - rise)
            if side == "left":
                x_wall, x_out = 0.0, -w
            else:
                x_wall, x_out = width, width + w
            painter.setPen(QPen(LEAN, 2.2))
            painter.drawLine(QPointF(sx(x_out), sy(0)), QPointF(sx(x_out), sy(h_outer)))
            painter.drawLine(
                QPointF(sx(x_out), sy(h_outer)), QPointF(sx(x_wall), sy(h_conn))
            )
            self._draw_pin_support(painter, sx(x_out), sy(0))

        def roof_extension(side: str, data: dict) -> None:
            if not data.get("enabled"):
                return
            proj = float(data.get("projection_m", 0) or 0)
            if proj <= 0:
                return
            # Continue roof slope beyond eave (purple)
            rise = proj / n
            if side == "left":
                x0, y0 = 0.0, eave
                x1, y1 = -proj, eave - rise
            else:
                x0, y0 = width, eave
                x1, y1 = width + proj, eave - rise
            painter.setPen(QPen(ROOF_EXT, 2.6))
            painter.drawLine(QPointF(sx(x0), sy(y0)), QPointF(sx(x1), sy(y1)))
            # Small purple tick at tip
            painter.drawLine(
                QPointF(sx(x1), sy(y1)),
                QPointF(sx(x1), sy(max(0.0, y1 - 0.35))),
            )

        def fascia(side: str, data: dict) -> None:
            if not data.get("enabled"):
                return
            h = float(data.get("height_m", 0) or 0)
            if h <= 0:
                return
            x = 0.0 if side == "left" else width
            painter.setPen(QPen(FASCIA, 2.4))
            painter.drawLine(QPointF(sx(x), sy(eave)), QPointF(sx(x), sy(eave - h)))
            # Accent arrow at eave
            painter.setBrush(QBrush(FASCIA))
            tip = QPolygonF(
                [
                    QPointF(sx(x), sy(eave)),
                    QPointF(sx(x) - 5 if side == "left" else sx(x) + 5, sy(eave) + 8),
                    QPointF(sx(x) + 5 if side == "left" else sx(x) - 5, sy(eave) + 8),
                ]
            )
            painter.drawPolygon(tip)

        def canopy(side: str, data: dict) -> None:
            if not data.get("enabled"):
                return
            w = float(data.get("width_m", 0) or 0)
            ht = float(data.get("height_on_col_m", 0) or 0)
            if w <= 0 or ht <= 0:
                return
            slope_x = float(data.get("slope_x10", 1) or 1)
            ln = 10.0 / slope_x if slope_x > 0 else n
            drop = w / ln
            h_tip = max(0.2, ht - drop)
            if side == "left":
                x0, x1 = 0.0, -w
            else:
                x0, x1 = width, width + w
            painter.setPen(QPen(CANOPY, 2.4))
            # Bracket on column + sloping canopy
            painter.drawLine(QPointF(sx(x0), sy(ht)), QPointF(sx(x1), sy(h_tip)))
            painter.drawLine(
                QPointF(sx(x0), sy(ht)), QPointF(sx(x0), sy(max(0.0, ht - 0.4)))
            )
            # Tip hanger
            painter.drawLine(
                QPointF(sx(x1), sy(h_tip)), QPointF(sx(x1), sy(max(0.0, h_tip - 0.3)))
            )

        lean("left", ext.get("lean_to_left") or {})
        lean("right", ext.get("lean_to_right") or {})
        roof_extension("left", ext.get("roof_ext_left") or {})
        roof_extension("right", ext.get("roof_ext_right") or {})
        fascia("left", ext.get("fascia_left") or {})
        fascia("right", ext.get("fascia_right") or {})
        canopy("left", ext.get("canopy_left") or {})
        canopy("right", ext.get("canopy_right") or {})

    def _frame_type_label(self) -> str:
        raw = str(self._meta.get("frame_type", "") or "")
        mapping = {
            "clear_span": "Clear Span",
            "single_gable": "Clear Span",
            "multi_span": "Multi-Span",
            "multi_gable": "Multi-Gable",
            "mono_slope": "Mono-Slope",
            "asym_gable": "Asym Gable",
        }
        return mapping.get(raw, raw.replace("_", " ").title() or "Frame")

    def _paint_scene(
        self,
        painter: QPainter,
        width_px: int,
        height_px: int,
        *,
        interactive_hints: bool,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, 0, width_px, height_px, BG)
        if self._analytical_model is not None:
            self._paint_analytical(painter, width_px, height_px)
            return

        if not self._profile:
            painter.setPen(TEXT_MUTED)
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                0,
                0,
                width_px,
                height_px,
                Qt.AlignmentFlag.AlignCenter,
                "Your frame preview appears here\n\nSet the building parameters, then select Generate model.",
            )
            return

        width = float(self._meta.get("span_m", 1) or 1)
        eave = float(self._meta.get("eave_height_m", 1) or 1)
        block = float(self._meta.get("blockwall_height_m", 0) or 0)
        ffl = float(self._meta.get("ffl_level_m", 0) or 0)
        pitch_n = float(self._meta.get("roof_pitch_1_to_n", 10) or 10)
        ridge_h_abs = float(self._meta.get("ridge_height_m", eave + ffl) or (eave + ffl))
        ridge_rel = ridge_h_abs - ffl

        max_y = eave
        for _x, y, _r in self._profile:
            max_y = max(max_y, y)
        max_y = max(max_y, ridge_rel, 1e-6)

        mz = self._meta.get("mezzanine") or {}
        crane = self._meta.get("crane") or {}
        ext = self._meta.get("extensions") or {}
        monitor = self._meta.get("roof_monitor") or ext.get("roof_monitor") or {}

        # Side overhangs for lean-to / canopy / roof extension
        left_extra = 0.0
        right_extra = 0.0
        for key, side in (("lean_to_left", "left"), ("lean_to_right", "right")):
            lt = ext.get(key) or {}
            if lt.get("enabled"):
                w = float(lt.get("width_m", 0) or 0)
                if side == "left":
                    left_extra = max(left_extra, w)
                else:
                    right_extra = max(right_extra, w)
        for key, side in (("canopy_left", "left"), ("canopy_right", "right")):
            c = ext.get(key) or {}
            if c.get("enabled"):
                w = float(c.get("width_m", 0) or 0)
                if side == "left":
                    left_extra = max(left_extra, w)
                else:
                    right_extra = max(right_extra, w)
        for key, side in (("roof_ext_left", "left"), ("roof_ext_right", "right")):
            r = ext.get(key) or {}
            if r.get("enabled"):
                w = float(r.get("projection_m", 0) or 0)
                if side == "left":
                    left_extra = max(left_extra, w)
                else:
                    right_extra = max(right_extra, w)

        x_min = -left_extra
        x_max = width + right_extra
        span_draw = max(x_max - x_min, 1e-6)

        # Account for roof monitor height in view bounds
        if monitor.get("enabled"):
            mh = float(monitor.get("height_m", 0) or 0)
            max_y = max(max_y, ridge_rel + mh + 0.5)

        # Title strip
        painter.setPen(TEXT_PRIMARY)
        painter.setFont(QFont("Segoe UI", 9))
        title = (
            f"{self._frame_type_label()}  |  B {width:.1f} m  |  Eave {eave:.1f} m"
        )
        painter.drawText(14, 20, title)

        if interactive_hints:
            painter.setPen(TEXT_MUTED)
            painter.setFont(QFont("Segoe UI", 8))
            hint = "scroll = zoom · drag = pan · dbl-click = reset"
            painter.drawText(
                0,
                height_px - 18,
                width_px - 12,
                16,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                hint,
            )

        # Plot area with zoom/pan
        margin_l, margin_r, margin_t, margin_b = 72, 36, 44, 56
        plot_w = max(10, width_px - margin_l - margin_r)
        plot_h = max(10, height_px - margin_t - margin_b)

        # Fit content with slight padding in model space
        pad_x = span_draw * 0.04
        pad_y = max_y * 0.08

        def sx(x: float) -> float:
            u = (x - x_min + pad_x) / (span_draw + 2 * pad_x)
            return margin_l + u * plot_w * self._zoom + self._pan_x

        def sy(y_rel: float) -> float:
            v = (y_rel + pad_y) / (max_y + 2 * pad_y)
            return margin_t + plot_h - v * plot_h * self._zoom + self._pan_y

        # Ground hatch
        self._draw_ground(painter, sx(x_min), sx(x_max), sy(0.0))

        # Blockwall (if any)
        if block > 0:
            painter.setPen(QPen(QColor("#888888"), 5))
            painter.drawLine(QPointF(sx(0), sy(0)), QPointF(sx(0), sy(block)))
            painter.drawLine(QPointF(sx(width), sy(0)), QPointF(sx(width), sy(block)))

        # Columns
        painter.setPen(QPen(STRUCTURE, 2.4))
        col_tops: Dict[float, float] = {}
        for x in self._column_xs:
            top = eave
            for px, py, _r in self._profile:
                if abs(px - x) < 1e-6:
                    top = py
                    break
            else:
                # project onto roof polyline
                top = self._interp_y(self._profile, x)
            col_tops[x] = top
            painter.drawLine(QPointF(sx(x), sy(0)), QPointF(sx(x), sy(top)))

        # Rafters / roof polyline
        painter.setPen(QPen(STRUCTURE, 2.4))
        for (x0, y0, _), (x1, y1, _) in zip(self._profile[:-1], self._profile[1:]):
            painter.drawLine(QPointF(sx(x0), sy(y0)), QPointF(sx(x1), sy(y1)))

        # ---- Side extensions (lean-to / roof ext / fascia / canopy) ----
        self._draw_side_extensions(
            painter, sx, sy, width=width, eave=eave, pitch_n=pitch_n, ext=ext
        )
        if mz.get("enabled"):
            flat = bool(mz.get("flat_roof_mezz_only"))
            levels = mz.get("levels") or []
            if not levels:
                # legacy single-level metadata
                levels = [
                    {
                        "height_m": mz.get("height_m", 0),
                        "start_m": mz.get("start_m", 0),
                        "width_m": mz.get("width_m", 0),
                        "col_spacings_m": mz.get("col_spacings_m")
                        or (
                            [mz.get("col_spacing_m")]
                            if mz.get("col_spacing_m")
                            else []
                        ),
                    }
                ]
            painter.setPen(QPen(MEZZ, 2.0))
            for lv in levels:
                mh = float(lv.get("height_m", 0) or 0)
                mstart = float(lv.get("start_m", 0) or 0)
                mw = float(lv.get("width_m", 0) or 0)
                if mh <= 0 or mw <= 0:
                    continue
                spacings = [float(s) for s in (lv.get("col_spacings_m") or []) if float(s) > 0]
                xs = [mstart]
                x = mstart
                for sp in spacings:
                    x += sp
                    xs.append(x)
                end = mstart + mw
                if abs(xs[-1] - end) > 1e-6:
                    if xs[-1] < end:
                        xs.append(end)
                    else:
                        xs[-1] = end

                if flat:
                    # Highlight flat roof beam + all columns in mezz colour
                    for xi in xs:
                        painter.drawLine(
                            QPointF(sx(xi), sy(0)), QPointF(sx(xi), sy(mh))
                        )
                    painter.drawLine(
                        QPointF(sx(xs[0]), sy(mh)), QPointF(sx(xs[-1]), sy(mh))
                    )
                    painter.setPen(MEZZ)
                    painter.setFont(QFont("Segoe UI", 8))
                    painter.drawText(
                        int(sx((xs[0] + xs[-1]) / 2) - 36),
                        int(sy(mh) - 8),
                        f"Mezz {mh:g} m",
                    )
                    # Bay dims under mezz
                    painter.setPen(QPen(MEZZ, 1.0))
                    for a, b in zip(xs[:-1], xs[1:]):
                        mid = 0.5 * (a + b)
                        painter.drawText(
                            int(sx(mid) - 14),
                            int(sy(0) + 28),
                            f"{b - a:.1f} m",
                        )
                else:
                    # Interior mezz columns (skip main exterior lines at 0 / width)
                    for xi in xs:
                        if abs(xi) < 1e-6 or abs(xi - width) < 1e-6:
                            continue
                        painter.drawLine(
                            QPointF(sx(xi), sy(0)), QPointF(sx(xi), sy(mh))
                        )
                    # Floor beam
                    painter.drawLine(
                        QPointF(sx(xs[0]), sy(mh)), QPointF(sx(xs[-1]), sy(mh))
                    )
                    painter.setPen(MEZZ)
                    painter.setFont(QFont("Segoe UI", 8))
                    painter.drawText(
                        int(sx(xs[0]) + 6),
                        int(sy(mh) - 8),
                        f"Mezz {mh:g} m",
                    )
                    painter.setPen(QPen(MEZZ, 1.0))
                    for a, b in zip(xs[:-1], xs[1:]):
                        mid = 0.5 * (a + b)
                        painter.drawText(
                            int(sx(mid) - 14),
                            int(sy(0) + 28),
                            f"{b - a:.1f} m",
                        )

        if crane.get("enabled"):
            rh = float(
                crane.get("effective_height_m")
                or crane.get("hook_height_m")
                or crane.get("runway_height_m")
                or 0
            )
            if rh > 0:
                # Thick yellow runway beam across the clear span (inset from eaves)
                inset = max(width * 0.02, 0.4)
                x0, x1 = inset, width - inset
                painter.setPen(QPen(CRANE, 3.6))
                painter.drawLine(QPointF(sx(x0), sy(rh)), QPointF(sx(x1), sy(rh)))
                # End brackets
                painter.setPen(QPen(CRANE, 2.2))
                for xe in (x0, x1):
                    painter.drawLine(
                        QPointF(sx(xe), sy(rh + 0.25)),
                        QPointF(sx(xe), sy(rh - 0.15)),
                    )
                # Moving trolley + hook
                t = max(0.0, min(1.0, self._crane_phase))
                tx = x0 + t * (x1 - x0)
                painter.setBrush(QBrush(CRANE))
                painter.setPen(QPen(CRANE, 1.4))
                tw, th = 0.55, 0.28
                painter.drawRect(
                    QRectF(sx(tx - tw / 2), sy(rh + th), sx(tx + tw / 2) - sx(tx - tw / 2), sy(rh) - sy(rh + th))
                )
                # Hook cable + hook
                painter.drawLine(
                    QPointF(sx(tx), sy(rh)),
                    QPointF(sx(tx), sy(rh - 0.55)),
                )
                hook = QPolygonF(
                    [
                        QPointF(sx(tx - 0.18), sy(rh - 0.55)),
                        QPointF(sx(tx + 0.18), sy(rh - 0.55)),
                        QPointF(sx(tx), sy(rh - 0.85)),
                    ]
                )
                painter.drawPolygon(hook)
                # Motion arrows
                painter.setPen(QPen(CRANE, 1.2))
                ay = sy(rh + 0.45)
                painter.drawLine(QPointF(sx(tx) - 14, ay), QPointF(sx(tx) + 14, ay))
                painter.drawLine(QPointF(sx(tx) - 14, ay), QPointF(sx(tx) - 8, ay - 4))
                painter.drawLine(QPointF(sx(tx) - 14, ay), QPointF(sx(tx) - 8, ay + 4))
                painter.drawLine(QPointF(sx(tx) + 14, ay), QPointF(sx(tx) + 8, ay - 4))
                painter.drawLine(QPointF(sx(tx) + 14, ay), QPointF(sx(tx) + 8, ay + 4))
                painter.setPen(CRANE)
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                painter.drawText(
                    int(sx(width * 0.35)),
                    int(sy(rh) - 10),
                    f"{crane.get('name', 'Crane 1')} @ {rh:g} m",
                )

        # Roof monitor (pink) on the ridge
        if monitor.get("enabled"):
            throat = float(monitor.get("throat_width_m", 0) or 0)
            mh = float(monitor.get("height_m", 0) or 0)
            ext = float(monitor.get("extension_m", 0) or 0)
            if throat > 0 and mh > 0:
                # Ridge location from profile
                ridge_pts = [(x, y) for x, y, r in self._profile if r == "ridge"]
                if ridge_pts:
                    rx, ry = max(ridge_pts, key=lambda p: p[1])
                else:
                    rx, ry = width / 2.0, ridge_rel
                left = rx - throat / 2.0
                right = rx + throat / 2.0
                top = ry + mh
                roof_l = left - ext
                roof_r = right + ext
                painter.setPen(QPen(MONITOR, 2.2))
                # Side walls
                painter.drawLine(QPointF(sx(left), sy(ry)), QPointF(sx(left), sy(top)))
                painter.drawLine(QPointF(sx(right), sy(ry)), QPointF(sx(right), sy(top)))
                # Monitor roof (slight pitch)
                peak = top + min(0.35, mh * 0.2)
                poly = QPolygonF(
                    [
                        QPointF(sx(roof_l), sy(top)),
                        QPointF(sx(rx), sy(peak)),
                        QPointF(sx(roof_r), sy(top)),
                    ]
                )
                painter.drawPolyline(poly)
                # Base sill on main ridge
                painter.drawLine(QPointF(sx(left), sy(ry)), QPointF(sx(right), sy(ry)))
                painter.setPen(MONITOR)
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                ridge_abs = float(self._meta.get("ridge_height_m", ry + ffl) or (ry + ffl))
                painter.drawText(
                    int(sx(rx) - 36),
                    int(sy(peak) - 8),
                    f"Ridge {ridge_abs + mh:.1f} m",
                )

        # Support triangles at each column base
        for x in self._column_xs:
            self._draw_pin_support(painter, sx(x), sy(0))
        # Mezz interior column supports
        if mz.get("enabled") and not mz.get("flat_roof_mezz_only"):
            levels = mz.get("levels") or [
                {
                    "start_m": mz.get("start_m", 0),
                    "width_m": mz.get("width_m", 0),
                    "col_spacings_m": mz.get("col_spacings_m")
                    or (
                        [mz.get("col_spacing_m")]
                        if mz.get("col_spacing_m")
                        else []
                    ),
                }
            ]
            for lv in levels:
                mstart = float(lv.get("start_m", 0) or 0)
                mw = float(lv.get("width_m", 0) or 0)
                spacings = [float(s) for s in (lv.get("col_spacings_m") or []) if float(s) > 0]
                xs = [mstart]
                x = mstart
                for sp in spacings:
                    x += sp
                    xs.append(x)
                end = mstart + mw
                if xs and abs(xs[-1] - end) > 1e-6:
                    if xs[-1] < end:
                        xs.append(end)
                    else:
                        xs[-1] = end
                for xi in xs:
                    if abs(xi) < 1e-6 or abs(xi - width) < 1e-6:
                        continue
                    self._draw_pin_support(painter, sx(xi), sy(0))

        # Nodes (joints)
        painter.setPen(QPen(STRUCTURE, 1.4))
        painter.setBrush(QBrush(NODE_FILL))
        node_r = 4.2
        # base nodes
        for x in self._column_xs:
            painter.drawEllipse(QPointF(sx(x), sy(0)), node_r, node_r)
        # profile nodes
        for x, y, _role in self._profile:
            painter.drawEllipse(QPointF(sx(x), sy(y)), node_r, node_r)

        # Pitch triangles on each sloping roof segment
        for (x0, y0, _), (x1, y1, _) in zip(self._profile[:-1], self._profile[1:]):
            if abs(x1 - x0) < 1e-9:
                continue
            if abs(y1 - y0) < 1e-9:
                continue
            self._draw_pitch_mark(
                painter,
                sx,
                sy,
                x0,
                y0,
                x1,
                y1,
                pitch_n,
            )

        # Dimension: span (bottom)
        self._draw_h_dimension(
            painter,
            sx(0),
            sx(width),
            sy(0) + 28,
            f"{width:.1f} m",
        )

        # Dimension: eave height (left)
        self._draw_v_dimension(
            painter,
            sx(0) - 28,
            sy(0),
            sy(eave),
            f"Eave {eave:.1f}m",
        )

        # Ridge label(s)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        for x, y, role in self._profile:
            if role != "ridge":
                continue
            label_h = ffl + y
            painter.setPen(STRUCTURE)
            painter.drawText(
                int(sx(x) - 42),
                int(sy(y) - 12),
                f"Ridge {label_h:.2f}m",
            )

        if ffl > 0:
            painter.setPen(TEXT_MUTED)
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(int(sx(0) + 8), int(sy(0) - 6), f"FFL {ffl:g} m")

    @staticmethod
    def _interp_y(profile: Sequence[Tuple[float, float, str]], x: float) -> float:
        pts = [(p[0], p[1]) for p in profile]
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            if x0 - 1e-9 <= x <= x1 + 1e-9:
                if abs(x1 - x0) < 1e-12:
                    return y0
                t = (x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return pts[-1][1] if pts else 0.0

    def _draw_ground(self, painter: QPainter, x0: float, x1: float, y: float) -> None:
        painter.setPen(QPen(GROUND, 1.5))
        painter.drawLine(QPointF(x0 - 10, y), QPointF(x1 + 10, y))
        # hatch ticks
        painter.setPen(QPen(GROUND, 1.0))
        step = 10.0
        x = x0 - 6
        while x <= x1 + 6:
            painter.drawLine(QPointF(x, y), QPointF(x - 6, y + 8))
            x += step

    def _draw_pin_support(self, painter: QPainter, cx: float, cy: float) -> None:
        size = 10.0
        tri = QPolygonF(
            [
                QPointF(cx, cy),
                QPointF(cx - size, cy + size * 1.15),
                QPointF(cx + size, cy + size * 1.15),
            ]
        )
        painter.setPen(QPen(SUPPORT, 1.5))
        painter.setBrush(QBrush(QColor(126, 200, 227, 40)))
        painter.drawPolygon(tri)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_pitch_mark(
        self,
        painter: QPainter,
        sx,
        sy,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        pitch_n: float,
    ) -> None:
        """Pitch triangle floating ABOVE the rafter (gap, not touching).

        Hypotenuse is parallel to the rafter; right-angle corner is outside.
        Matches CAD-style slope marks sitting clear of the member line.
        """
        dx = x1 - x0
        dy = y1 - y0
        if abs(dx) < 1e-9 or abs(dy) < 1e-9:
            return

        seg_len = (dx * dx + dy * dy) ** 0.5
        # Outward unit normal (above the roof)
        nx, ny = -dy / seg_len, dx / seg_len
        if ny < 0:
            nx, ny = -nx, -ny

        run_m = min(abs(dx) * 0.16, 2.8)
        if run_m * 1.5 > abs(dx):
            run_m = abs(dx) * 0.30
        if run_m < 0.7:
            return

        # Clearance so the mark does not touch the rafter
        gap = max(0.45, run_m * 0.22)

        t0 = 0.32
        if dy > 0:
            # Ascending: low left → high right on rafter, then lift
            lx = x0 + t0 * dx
            ly = y0 + t0 * dy
            ux = lx + run_m
            t1 = (ux - x0) / dx
            if t1 <= 0.08 or t1 >= 0.95:
                return
            uy = y0 + t1 * dy
            rise_left = True
        else:
            # Descending: high left → low right on rafter, then lift
            ux = x0 + t0 * dx
            uy = y0 + t0 * dy
            lx = ux + run_m
            t1 = (lx - x0) / dx
            if t1 <= 0.08 or t1 >= 0.95:
                return
            ly = y0 + t1 * dy
            rise_left = False

        # Lift both hyp points off the rafter (parallel copy)
        lo = (lx + nx * gap, ly + ny * gap)
        hi = (ux + nx * gap, uy + ny * gap)
        # Right-angle corner outside: same x as low, same y as high
        # (works for both sides because lo is always the lower hyp end)
        if lo[1] <= hi[1]:
            low_pt, high_pt = lo, hi
        else:
            low_pt, high_pt = hi, lo
        corner = (low_pt[0], high_pt[1])

        a = QPointF(sx(low_pt[0]), sy(low_pt[1]))
        b = QPointF(sx(high_pt[0]), sy(high_pt[1]))
        c = QPointF(sx(corner[0]), sy(corner[1]))

        painter.setPen(QPen(STRUCTURE, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Full closed triangle (hyp parallel to rafter, clear of it)
        painter.drawLine(a, b)  # hypotenuse
        painter.drawLine(a, c)  # vertical
        painter.drawLine(c, b)  # horizontal

        n_label = (
            f"{pitch_n:.0f}" if abs(pitch_n - round(pitch_n)) < 1e-6 else f"{pitch_n:g}"
        )
        painter.setPen(TEXT_PRIMARY)
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))

        # "10" above the horizontal leg
        run_mid_x = (corner[0] + high_pt[0]) / 2.0
        run_mid_y = corner[1]
        painter.drawText(
            QPointF(sx(run_mid_x) - 6, sy(run_mid_y) - 8),
            n_label,
        )

        # "1" beside the vertical leg
        rise_mid_x = corner[0]
        rise_mid_y = (low_pt[1] + corner[1]) / 2.0
        rise_x = sx(rise_mid_x) + (-12 if rise_left else 6)
        painter.drawText(QPointF(rise_x, sy(rise_mid_y) + 4), "1")

    def _draw_h_dimension(
        self, painter: QPainter, x0: float, x1: float, y: float, label: str
    ) -> None:
        painter.setPen(QPen(DIM_COLOR, 1.2))
        # end ticks
        tick = 6
        painter.drawLine(QPointF(x0, y - tick), QPointF(x0, y + tick))
        painter.drawLine(QPointF(x1, y - tick), QPointF(x1, y + tick))
        painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        # arrow heads
        ah = 7
        painter.drawLine(QPointF(x0, y), QPointF(x0 + ah, y - ah * 0.45))
        painter.drawLine(QPointF(x0, y), QPointF(x0 + ah, y + ah * 0.45))
        painter.drawLine(QPointF(x1, y), QPointF(x1 - ah, y - ah * 0.45))
        painter.drawLine(QPointF(x1, y), QPointF(x1 - ah, y + ah * 0.45))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.setPen(TEXT_PRIMARY)
        mid = (x0 + x1) / 2
        painter.drawText(QRectF(mid - 40, y + 4, 80, 16), Qt.AlignmentFlag.AlignCenter, label)

    def _draw_v_dimension(
        self, painter: QPainter, x: float, y0: float, y1: float, label: str
    ) -> None:
        # y0 is ground (lower on screen? no — sy maps larger y_rel higher on screen, so sy(eave) < sy(0))
        painter.setPen(QPen(DIM_COLOR, 1.2))
        tick = 6
        painter.drawLine(QPointF(x - tick, y0), QPointF(x + tick, y0))
        painter.drawLine(QPointF(x - tick, y1), QPointF(x + tick, y1))
        painter.drawLine(QPointF(x, y0), QPointF(x, y1))
        ah = 7
        # arrows toward ends
        painter.drawLine(QPointF(x, y0), QPointF(x - ah * 0.45, y0 - ah))
        painter.drawLine(QPointF(x, y0), QPointF(x + ah * 0.45, y0 - ah))
        painter.drawLine(QPointF(x, y1), QPointF(x - ah * 0.45, y1 + ah))
        painter.drawLine(QPointF(x, y1), QPointF(x + ah * 0.45, y1 + ah))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.setPen(TEXT_PRIMARY)
        # rotate label beside the dimension
        painter.save()
        mid_y = (y0 + y1) / 2
        painter.translate(x - 14, mid_y)
        painter.rotate(-90)
        painter.drawText(QRectF(-50, -10, 100, 20), Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()
