"""Right-dock compartment table.

A view bound to one atlas layer, joined to the canonical nomenclature, never a
union across atlases -- that is what keeps it usable as atlases accumulate
(design section 7).

Visibility is per-compartment ACROSS atlases (design section 1), so each atlas
gets its own tab driving its own layer, and nothing assumes a single active
atlas.

The table is for bulk selection. It complements click-to-identify rather than
replacing it: picking in the canvas selects the row here, and vice versa.
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

#: Column 0 toggles the mesh, the last toggles the slice label. Labels are
#: per glomerulus because several atlases in one scene would otherwise write
#: each name once per atlas.
COLUMNS = ("", "glomerulus", "canonical", "side", "label")
VISIBLE_COL = 0
LABEL_COL = len(COLUMNS) - 1


class AtlasTab(QWidget):
    def __init__(self, surface, compartments=None, contour=None) -> None:
        super().__init__()
        self.surface = surface
        self.contour = contour
        self.compartments = list(compartments or [])
        self._updating = False

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter by name, canonical or side")
        self.filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter)

        buttons = QHBoxLayout()
        for label, slot in (
            ("All", self._all),
            ("None", self._none),
            ("Filtered", self._filtered_only),
            ("Invert", self._invert),
            ("Label all", self._labels_for_shown),
            ("Label none", self._no_labels),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.table = QTableWidget(surface.meshset.n_compartments, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(VISIBLE_COL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(LABEL_COL, QHeaderView.ResizeToContents)
        for col in range(1, LABEL_COL):
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        by_index = {c.local_id: c for c in self.compartments}
        for row, name in enumerate(surface.meshset.names):
            comp = by_index.get(row)
            check = QTableWidgetItem()
            check.setFlags(check.flags() | Qt.ItemIsUserCheckable)
            check.setCheckState(
                Qt.Checked if row in surface.selection else Qt.Unchecked
            )
            check.setData(Qt.UserRole, row)
            self.table.setItem(row, 0, check)

            label = QTableWidgetItem(name)
            rgba = surface.colors[row]
            label.setForeground(
                QColor.fromRgbF(float(rgba[0]), float(rgba[1]), float(rgba[2]))
            )
            self.table.setItem(row, 1, label)
            self.table.setItem(
                row, 2, QTableWidgetItem(", ".join(comp.canonical) if comp else "")
            )
            self.table.setItem(row, 3, QTableWidgetItem((comp.side or "") if comp else ""))

            label_check = QTableWidgetItem()
            label_check.setFlags(label_check.flags() | Qt.ItemIsUserCheckable)
            label_check.setCheckState(Qt.Unchecked)
            label_check.setData(Qt.UserRole, row)
            label_check.setToolTip("write this glomerulus's name on the slice (2D)")
            self.table.setItem(row, LABEL_COL, label_check)

        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, stretch=1)

        self.count = QLabel()
        layout.addWidget(self.count)
        self.setLayout(layout)
        self._update_count()

    # -- helpers ---------------------------------------------------------

    def _row_text(self, row: int) -> str:
        return " ".join(
            (self.table.item(row, c).text() if self.table.item(row, c) else "")
            for c in range(1, len(COLUMNS))
        ).lower()

    def _push(self, selection: set[int]) -> None:
        self.surface.set_selection(selection)
        if self.contour is not None:
            self.contour.set_selection(selection)
        self._update_count()

    def _update_count(self) -> None:
        self.count.setText(
            f"{len(self.surface.selection)} / {self.table.rowCount()} shown"
        )

    # -- handlers --------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        if item.column() == LABEL_COL:
            if self.contour is not None:
                self.contour.set_label(
                    int(item.data(Qt.UserRole)),
                    item.checkState() == Qt.Checked,
                )
            return
        if item.column() != VISIBLE_COL:
            return
        index = int(item.data(Qt.UserRole))
        visible = item.checkState() == Qt.Checked
        self.surface.set_visible(index, visible)
        if self.contour is not None:
            self.contour.set_selection(self.surface.selection)
        self._update_count()

    def _set_labels(self, indices) -> None:
        wanted = set(indices)
        self._updating = True
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, LABEL_COL)
                if item is not None:
                    item.setCheckState(
                        Qt.Checked if row in wanted else Qt.Unchecked
                    )
        finally:
            self._updating = False
        if self.contour is not None:
            self.contour.set_labels(wanted)

    def _labels_for_shown(self) -> None:
        """Label whatever is currently visible -- the useful bulk action."""
        self._set_labels(set(self.surface.selection))

    def _no_labels(self) -> None:
        self._set_labels(set())

    def _set_rows(self, rows) -> None:
        self._updating = True
        selection = set()
        for row in range(self.table.rowCount()):
            on = row in rows
            self.table.item(row, 0).setCheckState(
                Qt.Checked if on else Qt.Unchecked
            )
            if on:
                selection.add(row)
        self._updating = False
        self._push(selection)

    def _all(self) -> None:
        self._set_rows(set(range(self.table.rowCount())))

    def _none(self) -> None:
        self._set_rows(set())

    def _filtered_only(self) -> None:
        """Check exactly the rows currently passing the filter."""
        self._set_rows(
            {r for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)}
        )

    def _invert(self) -> None:
        current = set(self.surface.selection)
        self._set_rows(set(range(self.table.rowCount())) - current)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, bool(needle) and needle not in self._row_text(row))

    # -- picking ---------------------------------------------------------

    def highlight(self, index: int) -> None:
        """Select and scroll to the row for a compartment picked in the canvas."""
        if 0 <= index < self.table.rowCount():
            self.table.selectRow(index)
            self.table.scrollToItem(self.table.item(index, 1))


class CompartmentPanel(QTabWidget):
    def __init__(self, viewer, surfaces: dict, registry=None, contours=None) -> None:
        super().__init__()
        self.viewer = viewer
        self.tabs: dict[str, AtlasTab] = {}
        contours = contours or {}
        for name, surface in surfaces.items():
            atlas = registry.atlases.get(name) if registry else None
            tab = AtlasTab(
                surface,
                compartments=atlas.compartments if atlas else None,
                contour=contours.get(name),
            )
            self.tabs[name] = tab
            self.addTab(tab, name[:20])

    def highlight(self, layer_name: str, index: int) -> None:
        tab = self.tabs.get(layer_name)
        if tab is None:
            return
        self.setCurrentWidget(tab)
        tab.highlight(index)
