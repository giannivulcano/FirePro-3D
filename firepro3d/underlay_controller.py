# firepro3d/underlay_controller.py
"""UnderlayController — the underlay/import concern lifted off Model_Space.

Decomposition slice (governing spec: docs/specs/model-space-architecture.md §5).
A PLAIN object (not a QObject): the async worker uses lambda slots and
`underlaysChanged` stays defined on the scene, so no QObject affinity is wanted.
Owns the underlay list, the async DXF worker bridge, and the place_import
transient state; back-references the scene for scene-graph mutation + signal
emission. The freeze controller is NOT owned here — it stays `scene._underlay_freeze`.
"""
from __future__ import annotations

import logging
import os

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QProgressDialog,
)
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

from .constants import Z_UNDERLAY, UNDERLAY_LINE_WIDTH_PX
from .dxf_import_worker import DxfImportWorker
from .underlay import Underlay
from .underlay_freeze import _UnderlayPathItem

log = logging.getLogger("FirePro3D")


class UnderlayController:
    def __init__(self, scene):
        self._scene = scene
        self.items: list = []               # was Model_Space.underlays
        self._dxf_worker = None
        self._dxf_progress = None
        self._dxf_import_params = None
        self._place_import_params = None
        self._place_import_ghost = None
        self._place_import_bounds = QRectF(-50, -50, 100, 100)
        self._place_import_preserve_mgmt = None
        self._place_import_remove_old = None

    def reset(self) -> None:
        """Clear the underlay list in place (routes the former `underlays = []`)."""
        self.items = []

    def import_dxf(self, file_path, color=QColor("white"), line_weight=0,
                   x=0.0, y=0.0, layers=None, _record: Underlay = None,
                   layout: str = "", skip_sanitize: bool = False):
        """
        Import a DXF file as an underlay using a background thread.

        Supported entities: LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE, POLYLINE,
        SPLINE, TEXT, MTEXT.

        Parameters
        ----------
        layers : list[str] | None
            If given, only import entities on these layers. None = all layers.
        """
        parent_widget = self._scene.views()[0] if self._scene.views() else None

        # Create progress dialog
        progress = QProgressDialog("Importing DXF…", "Cancel", 0, 100, parent_widget)
        progress.setWindowTitle("DXF Import")
        progress.setMinimumDuration(0)   # show immediately
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        # Create and configure worker (no Qt objects passed — created on main thread later)
        worker = DxfImportWorker(file_path, layers, layout=layout,
                                 skip_sanitize=skip_sanitize)

        # Store references so they don't get garbage-collected
        self._dxf_worker = worker
        self._dxf_progress = progress
        self._dxf_import_params = {
            "file_path": file_path, "color": color, "line_weight": line_weight,
            "x": x, "y": y, "layers": layers, "_record": _record,
            "layout": layout,
        }

        # Wire signals
        worker.progress.connect(lambda cur, tot: self._on_dxf_progress(progress, cur, tot))
        worker.status.connect(lambda msg: progress.setLabelText(msg))
        worker.finished_data.connect(lambda geom_list: self._on_dxf_finished(geom_list, progress))
        worker.error.connect(lambda msg: self._on_dxf_error(msg, progress))
        progress.canceled.connect(worker.cancel)

        worker.start()

    def _on_dxf_progress(self, progress: QProgressDialog, current: int, total: int):
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(current)

    def _on_dxf_finished(self, geom_list: list, progress: QProgressDialog):
        """Receives raw geometry dicts from the worker and creates QGraphicsItems
        on the main thread (required by Qt)."""
        params = self._dxf_import_params

        if not geom_list:
            progress.close()
            self._cleanup_dxf_worker()
            return

        color = params.get("color", QColor("#c0c0c0"))

        # Apply spatial bounds filter (area selection at import time)
        record = params.get("_record")
        if record is not None and record.import_bounds is not None:
            from .dwg_converter import filter_geoms_by_bounds
            geom_list = filter_geoms_by_bounds(
                geom_list, [tuple(record.import_bounds)])

        # Write geometry cache (filtered, pre-transform)
        cache_source = params.get("_dwg_source_path", params["file_path"])
        _cache_written = self._scene._write_underlay_cache(
            cache_source, geom_list,
            page=0,
            selected_layers=params.get("layers"),
            layout=params.get("layout", ""),
            import_bounds=(record.import_bounds
                           if record is not None else None))

        # Snapshot raw geom for cache-on-save (before transform mutates)
        _raw_geom = geom_list

        # Apply import transform if reloading from a record with baked params
        if record is not None and (record.import_scale != 1.0
                                    or record.import_base_x != 0.0
                                    or record.import_base_y != 0.0):
            from .dwg_converter import apply_import_transform
            geom_list = apply_import_transform(
                geom_list, record.import_scale,
                record.import_base_x, record.import_base_y)

        record = params["_record"] or Underlay(
            type=params.get("file_type", "dxf"), path=params["file_path"],
            x=params["x"], y=params["y"],
            colour=color.name(),
            line_weight=params.get("line_weight", UNDERLAY_LINE_WIDTH_PX),
            levels=[self._scene.active_level],
            layout=params.get("layout", ""),
        )

        result = self._build_batched_underlay_group(geom_list, record)

        if result is None:
            progress.close()
            self._cleanup_dxf_worker()
            return

        group, all_layers = result
        group.setPos(params["x"], params["y"])

        _TYPE_LABELS = {"pdf": "PDF Underlay", "dxf": "DXF Underlay", "dwg": "DWG Underlay"}
        group.setData(0, _TYPE_LABELS.get(record.type, "DXF Underlay"))
        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        group.setData(2, all_layers)

        self.items.append((record, group))

        progress.close()
        self._cleanup_dxf_worker()

        # Clean up temp DWG->DXF conversion output (async-safe)
        dwg_cleanup = params.get("_dwg_cleanup_path")
        if dwg_cleanup:
            from .dwg_converter import cleanup_converted_dxf
            cleanup_converted_dxf(dwg_cleanup)

        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()

        self._scene._show_status(f"Imported DXF: {params['file_path']}")

    @staticmethod
    def _build_pen_cache(geom_list: list[dict], line_width: float) -> dict:
        """Build a ``{hex_color: (QPen, QColor)}`` cache from geometry dicts."""
        cache: dict[str, tuple] = {}
        for g in geom_list:
            c = g.get("color")
            if c and c not in cache:
                qc = QColor(c)
                p = QPen(qc, line_width)
                p.setCosmetic(True)
                cache[c] = (p, qc)
        return cache

    @staticmethod
    def _append_geom_to_path(path: QPainterPath, g: dict):
        """Append a single geometry dict to a batched QPainterPath.

        Thin shim delegating to the single shared builder
        :func:`firepro3d.dwg_converter.append_geom_to_path` (kept as a
        staticmethod so existing ``self._append_geom_to_path`` / test callers
        stay stable). Used for batched underlay rendering where one
        QPainterPath per layer replaces one QGraphicsItem per geometry.
        """
        from .dwg_converter import append_geom_to_path
        append_geom_to_path(path, g)

    def _build_batched_underlay_group(
        self,
        geom_list: list[dict],
        record: Underlay,
    ) -> tuple[QGraphicsItemGroup, list[str]] | None:
        """Build a batched underlay group from geometry dicts.

        Instead of one QGraphicsItem per geometry (which freezes on large
        files), batches all geometry into one QPainterPath per DXF layer.
        Each layer gets up to two path items: one for stroked geometry
        (lines, arcs, circles, polylines) and one for filled text.

        Pens are per-layer and record-driven (spec §16.3): each layer's
        stroke item gets ``underlay_layer_pen(record, layer)`` (always
        cosmetic — constant on-screen width regardless of zoom or import
        scale); text items are NoPen with a brush in the layer's
        effective colour.

        Returns ``(group, sorted_layer_list)`` or ``None`` if no items.
        """
        from .model_space import underlay_layer_pen, _pdf_width_to_px

        # Group geometry by layer
        by_layer: dict[str, list[dict]] = {}
        for g in geom_list:
            layer = g.get("layer", "0")
            by_layer.setdefault(layer, []).append(g)

        items: list[QGraphicsItem] = []

        for layer, geoms in by_layer.items():
            geom_path = QPainterPath()
            text_path = QPainterPath()

            for g in geoms:
                if g.get("kind") == "text":
                    self._append_geom_to_path(text_path, g)
                else:
                    self._append_geom_to_path(geom_path, g)

            has_override = bool(record.effective_layer_weight(layer))
            if not geom_path.isEmpty() and has_override:
                # Per-file/layer Line-Weight override wins: single pen, flat
                # width for the whole layer (today's look).
                item = _UnderlayPathItem(geom_path)
                item.setPen(underlay_layer_pen(record, layer))
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                item.setZValue(Z_UNDERLAY)
                item.setData(1, layer)  # layer tag for visibility toggling
                items.append(item)
            elif not has_override:
                # No override -> preserve source line-width hierarchy: one path
                # (one pen width) per distinct stroke width. DXF geoms carry no
                # "width" -> all bucket at 0.0 -> UNDERLAY_LINE_WIDTH_PX (today).
                by_width: dict[float, QPainterPath] = {}
                for g in geoms:
                    if g.get("kind") == "text":
                        continue
                    w = round(float(g.get("width", 0.0)), 2)
                    self._append_geom_to_path(
                        by_width.setdefault(w, QPainterPath()), g)
                colour = QColor(record.effective_layer_colour(layer))
                for w, wpath in by_width.items():
                    if wpath.isEmpty():
                        continue
                    pen = QPen(colour, _pdf_width_to_px(w))
                    pen.setCosmetic(True)
                    item = _UnderlayPathItem(wpath)
                    item.setPen(pen)
                    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    item.setZValue(Z_UNDERLAY)
                    item.setData(1, layer)  # layer tag for visibility toggling
                    item.setData(7, w)      # source stroke width (pt) for repen
                    items.append(item)

            if not text_path.isEmpty():
                item = _UnderlayPathItem(text_path)
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setBrush(QBrush(QColor(
                    record.effective_layer_colour(layer))))
                item.setZValue(Z_UNDERLAY)
                item.setData(1, layer)
                items.append(item)

        if not items:
            return None

        old_method = self._scene.itemIndexMethod()
        self._scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        for item in items:
            self._scene.addItem(item)
        group = self._scene.createItemGroup(items)
        group.setZValue(Z_UNDERLAY)
        self._scene.setItemIndexMethod(old_method)

        all_layers = sorted(by_layer.keys())
        return group, all_layers

    def _attach_snap_index(self, group: QGraphicsItemGroup,
                           geom_list: list[dict], record: Underlay):
        """Build a spatial snap index and attach it to the underlay group.

        The index stores geometry dicts for lazy snap queries by the snap
        engine, replacing invisible QGraphicsItems in the scene BSP.
        """
        from .underlay_snap_index import UnderlaySnapIndex
        index = UnderlaySnapIndex(geom_list, record.hidden_layers, record)
        group.setData(4, index)

    def _on_dxf_error(self, msg: str, progress: QProgressDialog):
        progress.close()
        self._scene._show_status(f"DXF error: {msg}")
        self._cleanup_dxf_worker()

    def _cleanup_dxf_worker(self):
        if hasattr(self, "_dxf_worker") and self._dxf_worker is not None:
            self._dxf_worker.quit()
            self._dxf_worker.wait()
        self._dxf_worker = None
        self._dxf_progress = None
        self._dxf_import_params = None

    def import_pdf(self, file_path, dpi=150, page=0, x=0.0, y=0.0,
                   _record: Underlay = None, import_mode: str = "auto"):
        """Import a PDF page as an underlay.

        When *_record* is provided (reload / refresh-from-disk) and the
        original import used vector extraction (``import_mode`` is
        ``"vectors"`` or ``"auto"``), vectors are re-extracted from the
        PDF and rendered as QGraphicsItems — matching the quality of
        the original import-dialog placement.

        Falls back to raster rendering when vector extraction is
        unavailable or ``import_mode`` is ``"raster"``.
        """
        import os
        if not os.path.isfile(file_path):
            self._scene._show_status(f"PDF not found: {file_path}")
            log.warning("PDF not found: %s", file_path)
            return

        # -----------------------------------------------------------------
        # Vector path — re-extract from PDF when reloading a vector import
        # -----------------------------------------------------------------
        effective_mode = _record.import_mode if _record else import_mode
        if effective_mode in ("vectors", "auto"):
            try:
                from .pdf_import_worker import extract_pdf_vectors_sync
                p = _record.page if _record else page
                geom_list, _layers = extract_pdf_vectors_sync(file_path, page=p)
            except Exception as exc:
                log.warning("PDF vector extraction failed, falling back to raster: %s", exc)
                geom_list = []

            if geom_list:
                self._import_pdf_vectors(
                    file_path, geom_list, x=x, y=y,
                    _record=_record, import_mode=effective_mode,
                    dpi=dpi, page=_record.page if _record else page,
                )
                return

        # -----------------------------------------------------------------
        # Raster fallback
        # -----------------------------------------------------------------
        pixmap = None

        # --- Strategy 1: PyMuPDF (fitz) — fast, synchronous, reliable ----
        try:
            import fitz
            doc = fitz.open(file_path)
            if page < 0 or page >= len(doc):
                doc.close()
                self._scene._show_status(
                    f"Page {page} out of range (0–{len(doc)-1})")
                return
            pg = doc[page]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            qimg = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg.copy())   # .copy() detaches from fitz buffer
            doc.close()
        except ImportError:
            pass  # fitz not installed — fall through to QPdfDocument
        except Exception as e:
            log.warning("fitz PDF render failed: %s", e)

        # --- Strategy 2: QPdfDocument (Qt built-in) ----------------------
        if pixmap is None:
            try:
                doc = QPdfDocument(self._scene)
                err = doc.load(file_path)
                # Give Qt a chance to finish async loading if needed
                if doc.pageCount() == 0:
                    QApplication.processEvents()
                page_count = doc.pageCount()
                if page_count == 0:
                    raise RuntimeError(
                        f"QPdfDocument loaded 0 pages (load error: {err})")
                if page < 0 or page >= page_count:
                    raise IndexError(
                        f"Page {page} out of range (0–{page_count-1})")

                page_size = doc.pagePointSize(page)
                if not page_size.isValid():
                    raise RuntimeError("Invalid page size from PDF")

                width_px = int(page_size.width() * dpi / 72.0)
                height_px = int(page_size.height() * dpi / 72.0)

                options = QPdfDocumentRenderOptions()
                image = doc.render(page, QSize(width_px, height_px), options)
                if image.isNull():
                    raise RuntimeError("QPdfDocument.render() returned null")

                pixmap = QPixmap.fromImage(image)
            except Exception as e:
                self._scene._show_status(f"Error importing PDF: {e}")
                log.warning("QPdfDocument PDF render failed: %s", e)
                return

        if pixmap is None or pixmap.isNull():
            self._scene._show_status("Failed to render PDF page")
            return

        item = QGraphicsPixmapItem(pixmap)
        item.setZValue(Z_UNDERLAY)
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        # When reloading from a saved project (_record provided), always use
        # the stored position exactly.  For a fresh import with no explicit
        # position, centre the pixmap on the scene origin.
        if _record is not None:
            item.setPos(x, y)
        elif x != 0.0 or y != 0.0:
            item.setPos(x, y)
        else:
            item.setPos(-pixmap.width() / 2, -pixmap.height() / 2)
        item.setData(0, "PDF Underlay")
        self._scene.addItem(item)

        record = _record or Underlay(
            type="pdf", path=file_path,
            x=item.pos().x(), y=item.pos().y(),
            dpi=dpi, page=page,
            levels=[self._scene.active_level],
            import_mode=import_mode,
        )

        # Apply saved display settings
        self._apply_underlay_display(item, record)

        self.items.append((record, item))
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()
        self._scene._show_status(f"Imported PDF '{file_path}' page {page} at {dpi} DPI")

    def _import_pdf_vectors(self, file_path: str, geom_list: list[dict],
                            x: float = 0.0, y: float = 0.0,
                            _record: Underlay = None,
                            import_mode: str = "auto",
                            dpi: int = 150, page: int = 0):
        """Build vector QGraphicsItems from PDF geometry dicts.

        Mirrors the DXF reload path: apply stored import transform
        (scale + base-point shift), convert to QGraphicsItems via
        ``_build_batched_underlay_group()``, and register the underlay.
        """
        # Apply spatial bounds filter (area selection at import time) —
        # parity with _on_dxf_finished; keeps build + cache filtered.
        if _record is not None and _record.import_bounds is not None:
            from .dwg_converter import filter_geoms_by_bounds
            geom_list = filter_geoms_by_bounds(
                geom_list, [tuple(_record.import_bounds)])

        # Write geometry cache (filtered, pre-transform)
        _cache_written = self._scene._write_underlay_cache(
            file_path, geom_list, page=page,
            selected_layers=None,
            import_bounds=(_record.import_bounds
                           if _record is not None else None))

        # Snapshot raw geom for cache-on-save (before transform mutates)
        _raw_geom = geom_list

        # Apply import transform if reloading from a record with baked params
        if _record is not None and (_record.import_scale != 1.0
                                     or _record.import_base_x != 0.0
                                     or _record.import_base_y != 0.0):
            from .dwg_converter import apply_import_transform
            geom_list = apply_import_transform(
                geom_list, _record.import_scale,
                _record.import_base_x, _record.import_base_y)

        record = _record or Underlay(
            type="pdf", path=file_path,
            x=x, y=y,
            dpi=dpi, page=page,
            levels=[self._scene.active_level],
            import_mode=import_mode,
        )

        # Filter the render geometry by the record's selected layers. The
        # cache holds the FULL page (layer-agnostic); only what is drawn is
        # filtered — mirroring how the DXF worker filters by layer. The
        # per-layer Manager hide (hidden_layers) still composes on top via
        # _apply_underlay_hidden_layers below. selected_layers is None → all.
        from .dwg_converter import filter_geoms_by_layers
        geom_list = filter_geoms_by_layers(geom_list, record.selected_layers)

        result = self._build_batched_underlay_group(geom_list, record)

        if result is None:
            log.warning("PDF vector extraction yielded 0 items for %s", file_path)
            return

        group, all_layers = result
        group.setPos(x, y)
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        group.setData(0, "PDF Underlay")
        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        group.setData(2, all_layers)

        self.items.append((record, group))
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()

        self._scene._show_status(
            f"Imported PDF '{file_path}' page {page} as vectors")

    # -------------------------------------------------------------------------
    # UNDERLAYS — MANAGEMENT

    def _apply_underlay_display(self, item: QGraphicsItem, record: Underlay):
        """Apply transform origin, scale, rotation, opacity, visibility, and lock state."""
        self._scene._underlay_freeze.abort()   # spec §18: edits apply instantly
        # Pivot: vector underlays must rotate about the *base point*, matching
        # the import-dialog preview (which does setTransformOriginPoint(bx, by)).
        # apply_import_transform bakes ``coord -> (coord-base)*scale`` into the
        # geometry, so the base point sits at group-local (0, 0). Rotating about
        # the centroid instead swung the base point away from the insert point,
        # flinging "Insert at origin" imports far from the preview (and subtly
        # mis-placing off-centre-base non-origin imports too). Raster pixmaps
        # have no base point — they are centred on the origin at import — so they
        # keep the centroid pivot.
        if isinstance(item, QGraphicsItemGroup):
            item.setTransformOriginPoint(0.0, 0.0)
        else:
            item.setTransformOriginPoint(item.boundingRect().center())
        item.setScale(record.scale)
        item.setRotation(record.rotation)
        item.setOpacity(record.opacity)
        if not record.visible:
            item.setVisible(False)
        if record.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def _apply_underlay_hidden_layers(self, item: QGraphicsItem,
                                       data: Underlay):
        """Hide child items whose source layer is in data.hidden_layers.

        Stale layer names (no longer in the file) are silently dropped.
        """
        if not data.hidden_layers or not hasattr(item, "childItems"):
            return
        actual_layers = set()
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name is not None:
                actual_layers.add(layer_name)
        data.hidden_layers = [
            ln for ln in data.hidden_layers if ln in actual_layers
        ]
        hidden_set = set(data.hidden_layers)
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name in hidden_set:
                child.setVisible(False)

    def _create_underlay_placeholder(self, data: Underlay) -> QGraphicsItem:
        """Create a placeholder rect for a missing underlay file."""
        rect = QGraphicsRectItem(0, 0, 200, 150)
        pen = QPen(QColor("#ff0000"), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        rect.setPen(pen)
        rect.setBrush(QBrush(QColor(255, 0, 0, 30)))
        rect.setPos(data.x, data.y)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        rect.setData(0, "missing_underlay")

        filename = os.path.basename(data.path)
        label = QGraphicsSimpleTextItem(
            f"{filename}\nMissing — right-click to relink", rect)
        font = QFont()
        font.setPointSize(8)
        label.setFont(font)
        label.setBrush(QBrush(QColor("#ff0000")))

        self._scene.addItem(rect)
        self.items.append((data, rect))
        self._scene.underlaysChanged.emit()
        return rect

    def find_underlay_for_item(self, item: QGraphicsItem):
        """Return the (Underlay, QGraphicsItem) tuple for a scene item, or None."""
        for data, scene_item in self.items:
            if scene_item is item:
                return data, scene_item
        return None

    def remove_underlay(self, data: Underlay, item: QGraphicsItem):
        """Remove an underlay from the scene and the tracking list."""
        self._scene._underlay_freeze.abort()
        pair = (data, item)
        if pair in self.items:
            self.items.remove(pair)
        if item.scene() is self._scene:
            if isinstance(item, QGraphicsItemGroup):
                # destroyItemGroup re-parents children back to the scene rather
                # than deleting them, so we must remove each child first.
                for child in item.childItems():
                    self._scene.removeItem(child)
                self._scene.destroyItemGroup(item)
            else:
                self._scene.removeItem(item)
        self._scene.underlaysChanged.emit()
        self._scene._show_status(f"Removed underlay: {data.path}")

    def refresh_underlay(self, data: Underlay, item: QGraphicsItem,
                         sync_from_item: bool = True):
        """Re-import an underlay from disk, preserving position/scale/rotation/opacity.

        Args:
            sync_from_item: When True (default, refresh-from-disk), the item's
                current transform is written back to the record before rebuild.
                The Modify flow passes False so the NEW scale/rotation already
                on the record (from import params) survive the rebuild.
        """
        self._scene._underlay_freeze.abort()
        # Sync current transform state back to record
        if sync_from_item:
            data.x = item.scenePos().x()
            data.y = item.scenePos().y()
            data.scale = item.scale()
            data.rotation = item.rotation()
            data.opacity = item.opacity()

        # Check file exists before re-import
        if not os.path.exists(data.path):
            # Replace with placeholder
            if item.scene() is self._scene:
                self._scene.removeItem(item)
            # Remove old entry from underlays list
            old_entries = [(i, d) for i, (d, it) in enumerate(self.items) if d is data]
            for i, _ in reversed(old_entries):
                self.items.pop(i)
            self._create_underlay_placeholder(data)
            self._scene._show_status(f"Missing underlay: {data.path}")
            return

        # Remove old entry from underlays list BEFORE re-import.
        # DXF import is async (worker thread) — if we clean up after,
        # the duplicate check races with _on_dxf_finished appending.
        self.items = [(d, it) for d, it in self.items if d is not data]
        if item.scene() is self._scene:
            self._scene.removeItem(item)

        # Re-import (appends a fresh entry to self.items)
        if data.type == "pdf":
            self.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=data.x, y=data.y, _record=data,
                import_mode=data.import_mode,
            )
        elif data.type in ("dxf", "dwg"):
            dxf_path = data.path
            if data.type == "dwg":
                from .dwg_converter import (
                    find_oda_converter, convert_dwg_to_dxf,
                )
                oda = find_oda_converter()
                if oda is None:
                    self._create_underlay_placeholder(data)
                    self._scene._show_status("DWG refresh failed: ODA File Converter not found")
                    return
                proj = getattr(self._scene, "_project_path", None)
                proj_dir = os.path.dirname(proj) if proj else None
                converted = convert_dwg_to_dxf(oda, data.path, project_dir=proj_dir)
                if converted is None:
                    self._create_underlay_placeholder(data)
                    self._scene._show_status(f"DWG refresh failed: conversion error for {data.path}")
                    return
                dxf_path = converted

            self.import_dxf(
                dxf_path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=data.x, y=data.y, layers=data.selected_layers,
                _record=data,
                layout=data.layout,
                skip_sanitize=(data.type == "dwg"),  # ODA output is clean
            )

            # Store DWG metadata on import params for async cleanup
            if data.type == "dwg" and self._dxf_import_params:
                self._dxf_import_params["_dwg_source_path"] = data.path
                self._dxf_import_params["_dwg_cleanup_path"] = dxf_path
                self._dxf_import_params["layout"] = data.layout

        self._scene._show_status(f"Refreshed underlay: {data.path}")

    def refresh_all_underlays(self):
        """Re-import every underlay from disk."""
        # Take a snapshot since refresh modifies the list
        snapshot = list(self.items)
        for data, item in snapshot:
            self.refresh_underlay(data, item)

    def replace_underlay(self, record: Underlay, params, position=None):
        """Re-place an underlay's geometry from new import params, preserving
        the record's identity, draw position, list index, and management fields.

        Args:
            position: Optional ``QPointF`` overriding the on-canvas anchor. When
                ``None`` (default) the underlay keeps its current position
                (in-situ Modify). When a point is given, the rebuilt group and
                record are anchored there instead (used by the Modify
                "Insert at origin" mode → ``QPointF(0, 0)``).

        The Modify flow re-opens the import dialog pre-filled, lets the user
        change scale/placement/layers, and re-places the geometry WHILE
        preserving manager-owned fields (levels, colour, line_weight_name,
        layer_overrides, hidden_layers, visible, snap, locked, opacity).

        Geometry+placement fields are overwritten via
        ``apply_import_params_preserving_management`` BEFORE rebuild, so even
        the async DXF path rebuilds from the preserved+updated record.

        Note (async DXF): DXF import runs on a worker thread, so the rebuilt
        group lands later in ``_on_dxf_finished``. Field preservation and the
        record's path update happen synchronously here; list-index preservation
        is applied synchronously for the sync (PDF) path and is best-effort
        (the fresh entry appends at the end) for the async DXF path.
        """
        self._scene._underlay_freeze.abort()
        from .underlay import apply_import_params_preserving_management
        from .model_space import _record_levels

        # 1. Locate the current (record, item) pair and its list index.
        original_index = None
        item = None
        for i, (d, it) in enumerate(self.items):
            if d is record:
                original_index = i
                item = it
                break
        if item is None:
            log.warning("replace_underlay: record not found in underlays list")
            return

        # Preserve the on-canvas anchor — Modify changes geometry/scale, not
        # where the underlay sits in the scene. A caller-supplied `position`
        # overrides this (Modify "Insert at origin" passes QPointF(0, 0)).
        if position is not None:
            old_x, old_y = position.x(), position.y()
        else:
            try:
                old_x = item.scenePos().x()
                old_y = item.scenePos().y()
            except RuntimeError:
                old_x, old_y = record.x, record.y

        # 2. Build an `incoming` Underlay carrying ONLY geometry+placement.
        #    Mirror _commit_place_import: params.scale bakes into the geometry
        #    via import_scale/import_base_*, NOT the display transform. The
        #    display `scale` is preserved (no-op overwrite from the record).
        incoming = Underlay(
            type=params.file_type,
            path=params.file_path,
            page=getattr(params, "pdf_page", record.page),
            dpi=getattr(params, "pdf_dpi", record.dpi),
            scale=record.scale,                 # preserve display transform
            rotation=getattr(params, "rotation", record.rotation),
            x=old_x, y=old_y,
            import_scale=getattr(params, "scale", record.import_scale),
            import_base_x=getattr(params, "base_x", record.import_base_x),
            import_base_y=getattr(params, "base_y", record.import_base_y),
            selected_layers=getattr(params, "selected_layers", None),
            layout=getattr(params, "layout", record.layout),
            import_bounds=getattr(params, "import_bounds", None),
            import_mode=getattr(params, "import_mode", record.import_mode),
            levels=_record_levels(params, self._scene.active_level),
            scale_verified=getattr(params, "scale_verified", False),
            name=getattr(params, "name", record.name),
        )

        # 3. Derive the authoritative layer set from the new geometry.
        layers = None
        geom_list = getattr(params, "geom_list", None)
        if geom_list:
            layers = sorted({g.get("layer", "0") for g in geom_list})
        elif params.selected_layers is not None:
            layers = list(params.selected_layers)

        # 4. Overwrite geometry+placement, preserve management, prune overrides.
        apply_import_params_preserving_management(
            record, incoming, new_layer_names=layers)

        # 5. Rebuild the group in place WITHOUT syncing the old item's
        #    transform back (that would clobber the new scale/rotation).
        self.refresh_underlay(record, item, sync_from_item=False)

        # 6. Restore the original list index for the sync (PDF) path.
        #    refresh_underlay appends the fresh entry at the end; underlay
        #    ordering influences z-stacking among underlays, so keep it stable.
        if original_index is not None:
            new_entry = None
            for entry in self.items:
                if entry[0] is record:
                    new_entry = entry
                    break
            if new_entry is not None:
                cur = self.items.index(new_entry)
                if cur != original_index and original_index < len(self.items):
                    self.items.pop(cur)
                    self.items.insert(original_index, new_entry)
                    self._scene.underlaysChanged.emit()

    # Management fields NOT owned by the import dialog (everything outside
    # _GEOMETRY_PLACEMENT_FIELDS). Carried across a Modify "Pick new position"
    # re-placement so colour/opacity/locked/snap/visible/overrides survive.
    _UNDERLAY_MGMT_FIELDS = (
        "opacity", "locked", "colour", "line_weight", "snap", "visible",
        "hidden_layers", "layer_overrides", "line_weight_name",
    )

    def begin_replace_underlay_placement(self, record: Underlay, params):
        """Modify "Pick new position": re-place an underlay interactively.

        Starts the same cursor-follow placement a fresh import uses
        (``begin_place_import``), but stashes the old record's MANAGEMENT fields
        (colour, opacity, locked, snap, visibility, hidden layers, per-layer
        overrides, line-weight name) plus a reference to the OLD underlay so the
        eventual ``_commit_place_import`` can, on the click:
          1. remove the old underlay, then
          2. apply the carried-over management fields onto the fresh record.

        Cancel behaviour (non-destructive by construction): the destructive
        removal is DEFERRED to commit — a cancelled pick (Esc / mode change)
        never removed the old underlay, so it stays exactly where it was. The
        trade-off is the original underlay remains visible under the ghost while
        the user picks the new point; the swap happens atomically on click.
        """
        # Locate the (record, item) pair to remove on commit.
        old_item = None
        for d, it in self.items:
            if d is record:
                old_item = it
                break
        if old_item is None:
            log.warning(
                "begin_replace_underlay_placement: record not in underlays list")
            # Fall back to a straight in-situ replace so nothing is lost.
            self.replace_underlay(record, params)
            return

        # Snapshot management fields to carry across the re-placement.
        preserve_mgmt = {
            f: getattr(record, f) for f in self._UNDERLAY_MGMT_FIELDS
            if hasattr(record, f)
        }

        # Start the fresh-import interactive placement, then stash the
        # management payload + the old underlay to remove on commit.
        # (begin_place_import clears these, so set them AFTER it.)
        self._scene.begin_place_import(params)
        self._place_import_preserve_mgmt = preserve_mgmt
        self._place_import_remove_old = (record, old_item)

    def repen_underlay(self, record: Underlay):
        """Re-apply effective per-layer pens/brushes + opacity in place (§16.3).

        Never rebuilds the group (callable from any context, incl. DM live
        preview). Guards deleted C++ objects like the §7.2 pass.
        """
        from .model_space import underlay_layer_pen, _pdf_width_to_px
        self._scene._underlay_freeze.abort()
        for data, group in self.items:
            if data is not record or group is None:
                continue
            try:
                children = group.childItems()
            except RuntimeError:
                return
            for child in children:
                layer = child.data(1)
                if layer is None or not isinstance(child, QGraphicsPathItem):
                    continue
                if child.pen().style() == Qt.PenStyle.NoPen:
                    # text batch: colour rides the brush fill
                    child.setBrush(QBrush(QColor(
                        record.effective_layer_colour(layer))))
                elif record.effective_layer_weight(layer):
                    # override wins: flat weight for the whole layer
                    child.setPen(underlay_layer_pen(record, layer))
                else:
                    # no override: preserve the child's source PDF width, recolour
                    src_w = child.data(7)
                    if src_w is None:
                        child.setPen(underlay_layer_pen(record, layer))
                    else:
                        p = QPen(QColor(record.effective_layer_colour(layer)),
                                 _pdf_width_to_px(float(src_w)))
                        p.setCosmetic(True)
                        child.setPen(p)
            group.setOpacity(record.opacity)
            return

    def set_underlay_layer_hidden(self, record: Underlay, group,
                                  layer_name: str, hidden: bool):
        """Single choke point for hidden_layers edits (§16.6 — one state,
        two surfaces: browser tree and DM tab both route through here).
        No push_undo_state here — callers decide (browser pushes, DM never)."""
        self._scene._underlay_freeze.abort()
        if hidden and layer_name not in record.hidden_layers:
            record.hidden_layers.append(layer_name)
        elif not hidden and layer_name in record.hidden_layers:
            record.hidden_layers.remove(layer_name)
        else:
            return
        try:
            for child in group.childItems():
                if child.data(1) == layer_name:
                    child.setVisible(not hidden)
        except RuntimeError:
            return
        self._scene.underlaysChanged.emit()

    # -------------------------------------------------------------------------
    # UNDERLAYS — INTERACTIVE PLACEMENT (place_import)

    def begin_place_import(self, params):
        """
        Start the interactive placement of a DXF block after the preview dialog.

        The scene enters 'place_import' mode.  A ghost bounding-box preview
        follows the cursor.  Clicking commits the placement.

        Parameters
        ----------
        params : ImportParams
            Result from UnderlayImportDialog.get_import_params()
        """
        self._place_import_params = params
        self._place_import_ghost = None
        # Fresh import carries no management/remove-old payload. The Modify
        # "Pick new position" path re-sets these AFTER calling this method.
        self._place_import_preserve_mgmt = None
        self._place_import_remove_old = None

        # Build a bounding rect for the (scaled, base-point-adjusted) geometry
        if params.geom_list:
            xs, ys = [], []
            s = params.scale
            bx, by = params.base_x, params.base_y
            for g in params.geom_list:
                kind = g.get("kind")
                if kind == "line":
                    xs += [(g["x1"] - bx) * s, (g["x2"] - bx) * s]
                    ys += [(g["y1"] - by) * s, (g["y2"] - by) * s]
                elif kind in ("circle", "arc"):
                    x0 = (g.get("x", g.get("rx", 0)) - bx) * s
                    y0 = (g.get("y", g.get("ry", 0)) - by) * s
                    xs += [x0, x0 + g.get("w", g.get("rw", 0)) * s]
                    ys += [y0, y0 + g.get("h", g.get("rh", 0)) * s]
                elif kind == "path_points":
                    for pt in g.get("points", []):
                        xs.append((pt[0] - bx) * s)
                        ys.append((pt[1] - by) * s)
                elif kind == "text":
                    xs.append((g["x"] - bx) * s)
                    ys.append((g["y"] - by) * s)
            if xs and ys:
                self._place_import_bounds = QRectF(
                    min(xs), min(ys),
                    max(xs) - min(xs), max(ys) - min(ys)
                )
            else:
                self._place_import_bounds = QRectF(-50, -50, 100, 100)
        else:
            self._place_import_bounds = QRectF(-50, -50, 100, 100)

        self._scene.set_mode("place_import")

    def _update_place_import_ghost(self, pos: QPointF):
        """Reposition the ghost bounding rect at cursor position."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self._scene:
                self._scene.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        r = self._place_import_bounds
        ghost = QGraphicsRectItem(r)  # local coords
        pen = QPen(QColor("#4fa3e0"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ghost.setPen(pen)
        ghost.setBrush(QBrush(QColor(79, 163, 224, 20)))
        ghost.setZValue(200)
        ghost.setPos(pos)
        # Show rotation from import params
        rotation = getattr(self._place_import_params, "rotation", 0.0)
        if rotation != 0.0:
            ghost.setRotation(rotation)
        self._scene.addItem(ghost)
        self._place_import_ghost = ghost

    def _commit_place_import(self, insert_pt: QPointF):
        """Finalize placement: create the underlay group at insert_pt."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self._scene:
                self._scene.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        params = self._place_import_params
        if not params or not params.geom_list:
            self._scene.set_mode(None)
            return

        # Write geometry cache (raw, pre-transform)
        _cache_written = self._scene._write_underlay_cache(
            params.file_path, params.geom_list,
            page=getattr(params, "pdf_page", 0),
            selected_layers=getattr(params, "selected_layers", None),
            layout=getattr(params, "layout", ""),
            import_bounds=getattr(params, "import_bounds", None))

        s = params.scale
        bx, by = params.base_x, params.base_y

        # Transform geometry: shift by base point and apply scale.
        from .dwg_converter import apply_import_transform
        transformed = apply_import_transform(params.geom_list, s, bx, by)

        file_type = getattr(params, "file_type", "dxf")
        rotation = getattr(params, "rotation", 0.0)
        from .model_space import _record_levels
        record = Underlay(
            type=file_type, path=params.file_path,
            x=insert_pt.x(), y=insert_pt.y(),
            rotation=rotation,
            colour="#c0c0c0",
            line_weight=UNDERLAY_LINE_WIDTH_PX,
            # PDF page/dpi MUST persist or any later re-extraction (refresh,
            # cache miss) silently rebuilds from page 0 — the cover sheet.
            page=getattr(params, "pdf_page", 0),
            dpi=getattr(params, "pdf_dpi", 150),
            import_scale=s,
            import_base_x=bx,
            import_base_y=by,
            selected_layers=getattr(params, "selected_layers", None),
            levels=_record_levels(params, self._scene.active_level),
            scale_verified=getattr(params, "scale_verified", False),
            import_mode=getattr(params, "import_mode", "auto"),
            layout=getattr(params, "layout", ""),
            import_bounds=getattr(params, "import_bounds", None),
            name=getattr(params, "name", ""),
        )

        # Modify "Pick new position": carry the old record's management fields
        # (colour/opacity/locked/snap/visible/hidden_layers/overrides/…) onto
        # the freshly built record before display is applied, so the re-placed
        # underlay keeps its look. Applying to a record we may still discard
        # (build failure below) is harmless — the DESTRUCTIVE removal of the old
        # underlay is deferred until the build is known good.
        preserve_mgmt = getattr(self, "_place_import_preserve_mgmt", None)
        remove_old = getattr(self, "_place_import_remove_old", None)
        if preserve_mgmt:
            for f, v in preserve_mgmt.items():
                setattr(record, f, v)

        result = self._build_batched_underlay_group(transformed, record)
        if result is None:
            # Build failed — do NOT remove the old underlay; leave it in place.
            self._scene.set_mode(None)
            return

        # Build succeeded → this pick is committing. Remove the old underlay
        # now (deferred removal keeps a cancelled/failed pick non-destructive)
        # and clear the payloads so set_mode(None) below is a no-op for them.
        if remove_old is not None:
            old_rec, old_item = remove_old
            self.remove_underlay(old_rec, old_item)
        self._place_import_preserve_mgmt = None
        self._place_import_remove_old = None

        group, all_layers = result
        group.setPos(insert_pt)
        _TYPE_LABELS = {"pdf": "PDF Underlay", "dxf": "DXF Underlay", "dwg": "DWG Underlay"}
        group.setData(0, _TYPE_LABELS.get(file_type, "DXF Underlay"))
        group.setData(2, all_layers)
        # Snapshot the FILTERED raw geoms — storing the full page extraction
        # here poisoned the per-bounds cache on save (loads then rebuilt the
        # whole sheet: 4x geometry, ~10x slower repaints).
        _raw_for_cache = params.geom_list
        if record.import_bounds is not None:
            from .dwg_converter import filter_geoms_by_bounds
            _raw_for_cache = filter_geoms_by_bounds(
                _raw_for_cache, [tuple(record.import_bounds)])
        group.setData(5, _raw_for_cache)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, transformed, record)
        self.items.append((record, group))
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()

        self._scene.set_mode(None)
