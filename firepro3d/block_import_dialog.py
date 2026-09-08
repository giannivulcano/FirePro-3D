"""BlockImportDialog — a flattened, block-specific variant of the underlay
import dialog: single canvas + a right panel with Source/Content/Placement all
visible at once; no step-rail, no levels, no underlay name. Reuses the parent's
load/extract/preview/scale/layer machinery. See docs/specs/block-system.md."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QHBoxLayout

from .underlay_import_dialog import UnderlayImportDialog


class BlockImportDialog(UnderlayImportDialog):
    """Flattened import dialog for the Block Editor.

    Inherits all of the parent's file-load/extract/preview/scale/layer/
    base-point machinery. Differences from the plan-view import dialog:

    * Title: "Import Geometry"
    * No left step-rail (detached on construction).
    * No levels picker (``include_levels=False``).
    * No name field (``include_name=False``).
    * The three panel pages (Source / Content / Placement) are stacked
      vertically in a single scrollable right column instead of a
      QStackedWidget that shows one at a time.
    """

    def __init__(self, parent=None, *, scale_manager=None, default_dir=""):
        super().__init__(
            parent,
            scale_manager=scale_manager,
            default_dir=default_dir,
            levels=[],
            current_level="",
            modify_record=None,
            include_name=False,
            include_levels=False,
        )
        self.setObjectName("BlockImportDialog")
        self.setWindowTitle("Import Geometry")
        # Retitle the HouseDialog shell header (best-effort; harmless if absent).
        try:
            self._shell_title_lbl.setText("Import Geometry")
        except Exception:
            pass
        self._flatten_layout()

    # ------------------------------------------------------------------
    # Layout restructure
    # ------------------------------------------------------------------

    def _flatten_layout(self):
        """Remove the step-rail and collapse the 3-page QStackedWidget into one
        scrollable vertical panel (Source over Content over Placement).

        The parent builds::

            body (QHBoxLayout inside _body_container)
              ├─ _rail       (SideTabs)
              ├─ prev_wrap   (QWidget — preview workspace)
              ├─ seam        (1-px QWidget)
              └─ _panel_stack (QStackedWidget, 3 pages, fixed width 324)

        After flattening::

            body
              ├─ prev_wrap   (unchanged)
              └─ _flat_panel (QScrollArea wrapping all 3 pages stacked vertically)

        ``_controls_panel`` is left pointing at the first visible container
        (``_flat_panel``) so ``_set_controls_enabled`` still works.
        """
        stack = self._panel_stack

        # ── Detach the rail ────────────────────────────────────────────────
        rail = getattr(self, "_rail", None)
        if rail is not None:
            rail.setParent(None)
            rail.hide()
            # Remove the attribute so _update_all's hasattr guard fires cleanly.
            del self._rail

        # ── Pull the three pages out of the stack ─────────────────────────
        # Order: source(0), content(1), place(2).
        order = sorted(self._panel_pages.items(), key=lambda kv: kv[1])
        pages = [stack.widget(idx) for _key, idx in order]

        # Build the vertical scroll column that will replace the stack.
        col_host = QWidget()
        col_host.setObjectName("blockImportColumn")
        col = QVBoxLayout(col_host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        for pg in pages:
            # Reparent each page out of the stack into the column host. The stack
            # hides its non-current pages (setVisible(False)); that state persists
            # after reparenting, so force each page visible in the flat column.
            pg.setParent(col_host)
            pg.setVisible(True)
            col.addWidget(pg)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(col_host)
        scroll.setObjectName("detailsPanel")
        scroll.setFixedWidth(340)
        self._flat_panel = scroll

        # ── Find the HBoxLayout that owns seam + stack and swap ───────────
        # The parent's _build_ui adds widgets to a local ``body`` QHBoxLayout
        # that lives inside ``_body_container``.  Walk the top-level layout
        # (outer VBoxLayout on _body_container) to find the HBoxLayout item
        # containing _panel_stack, then swap the stack for the scroll area.
        body_layout = self._find_layout_containing(stack)
        if body_layout is not None:
            # Also remove the 1-px seam that sits just before the stack.
            seam = self._find_seam_before(body_layout, stack)
            if seam is not None:
                body_layout.removeWidget(seam)
                seam.setParent(None)
                seam.hide()

            stack_idx = body_layout.indexOf(stack)
            if stack_idx != -1:
                body_layout.removeWidget(stack)
                body_layout.insertWidget(stack_idx, scroll)

            # Also remove the rail from the layout if it's still there.
            # (setParent(None) already removed it from Qt's ownership, but
            #  the layout item slot may still exist as a spacer-like entry.)

        # Hide and unparent the now-empty stack.
        stack.setParent(None)
        stack.hide()

        # Point _controls_panel at the scroll container so _set_controls_enabled
        # disables the whole column during extraction (prevents layer-toggle /
        # Import clicks on a half-built _all_geoms).
        self._controls_panel = scroll

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_layout_containing(self, widget):
        """Return the QLayout that directly contains *widget*, or None.

        Searches breadth-first through the layout tree rooted at this dialog's
        top-level layout.
        """
        root = self.layout()
        if root is None:
            return None
        # _body_container is inserted via set_body(); its layout is `outer`
        # (a QVBoxLayout).  We need to find the QHBoxLayout inside it.
        return self._search_layout(root, widget)

    def _search_layout(self, layout, widget):
        """Recursively find the layout that directly contains *widget*.

        Descends into BOTH nested sub-layouts AND child widgets' own layouts —
        the parent nests the ``body`` HBox inside ``_body_container`` (a widget),
        so a layout-only walk would miss it.
        """
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is widget:
                return layout
            child_layout = item.layout()
            if child_layout is not None:
                result = self._search_layout(child_layout, widget)
                if result is not None:
                    return result
            # Descend into a child widget's own layout (e.g. _body_container).
            if w is not None and w.layout() is not None:
                result = self._search_layout(w.layout(), widget)
                if result is not None:
                    return result
        return None

    @staticmethod
    def _find_seam_before(layout, widget):
        """Return the widget at index (indexOf(widget) - 1) if it is a 1-px
        seam widget (``fixedWidth == 1``), else None."""
        idx = layout.indexOf(widget)
        if idx <= 0:
            return None
        prev_item = layout.itemAt(idx - 1)
        if prev_item is None:
            return None
        w = prev_item.widget()
        if w is not None and w.maximumWidth() == 1:
            return w
        return None

    # ------------------------------------------------------------------
    # Multi-layout default
    # ------------------------------------------------------------------

    def _on_dxf_read(self, path, doc):
        """Auto-preview the ``Model`` layout for multi-layout DXF/DWG files.

        The shared dialog leaves a multi-layout file's layout combo unselected
        ("Select a layout to preview.") so a multi-sheet underlay import lets the
        user pick a sheet. For block authoring the user wants the CAD geometry,
        which lives in model space — so when a ``Model`` layout exists and nothing
        is selected yet, select it (which kicks off extraction). The user can
        still switch to a paper-space sheet from the same combo.
        """
        super()._on_dxf_read(path, doc)
        # Populated combo + no selection == the shared dialog's multi-layout
        # "pick a sheet" state. (Don't gate on isVisible() — false when the
        # dialog isn't shown yet, e.g. under test.)
        combo = getattr(self, "_layout_combo", None)
        if combo is not None and combo.count() > 0 and combo.currentIndex() < 0:
            idx = combo.findText("Model")
            if idx >= 0:
                combo.setCurrentIndex(idx)   # fires _on_layout_changed -> extract

    # ------------------------------------------------------------------
    # Step navigation — neutralised (no rail, no stack navigation)
    # ------------------------------------------------------------------

    def _switch_step(self, key: str) -> None:  # type: ignore[override]
        """No-op: the flat layout shows all sections simultaneously."""
        return

    def _on_rail_clicked(self, key: str) -> None:  # type: ignore[override]
        """No-op: rail is detached."""
        return
