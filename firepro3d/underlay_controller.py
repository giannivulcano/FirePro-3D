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

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QBrush, QColor, QImage, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsItemGroup, QGraphicsPixmapItem,
    QGraphicsScene, QProgressDialog,
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

        self._scene._apply_underlay_display(group, record)
        self._scene._apply_underlay_hidden_layers(group, record)
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
        self._scene._apply_underlay_display(item, record)

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

        self._scene._apply_underlay_display(group, record)
        self._scene._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        group.setData(2, all_layers)

        self.items.append((record, group))
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()

        self._scene._show_status(
            f"Imported PDF '{file_path}' page {page} as vectors")
