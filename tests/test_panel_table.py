"""The glomerulus table: sorting, the fill toggle, and the annotation join.

Sorting is the risky one. Every handler used to treat the visual row as
the compartment id -- `_set_rows`, the filter, `highlight` -- which is
true only while the table is in insertion order. Once a header click can
reorder it, a row number means nothing, so these check behaviour AFTER a
sort rather than before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REGISTRY = Path(__file__).resolve().parents[1] / "registry"
pytest.importorskip("napari")


@pytest.fixture(scope="module")
def registry():
    from lobemap.core.registry import Registry

    if not (REGISTRY / "data").is_dir():
        pytest.skip("no ingested data")
    return Registry.load(REGISTRY)


@pytest.fixture
def tab(registry):
    import napari

    from lobemap.viewer.app import build_scene
    from lobemap.viewer.panel import CompartmentPanel

    try:
        viewer = napari.Viewer(show=False, ndisplay=3)
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"no Qt display: {exc}")
    try:
        surfaces, contours = build_scene(viewer, registry, "JRCFIB2018F")
        panel = CompartmentPanel(viewer, surfaces, registry=registry,
                                 contours=contours)
        yield panel.tabs["neuprint_hemibrain"]
    finally:
        viewer.close()


def _col(tab, name):
    from lobemap.viewer.panel import COLUMNS

    return COLUMNS.index(name)


def test_it_opens_sorted_by_glomerulus(tab):
    from lobemap.viewer.panel import NAME_COL, _natural_key

    names = [tab.table.item(r, NAME_COL).text()
             for r in range(tab.table.rowCount())]
    assert names == sorted(names, key=_natural_key)
    assert tab.table.isSortingEnabled()


def test_numbers_sort_naturally(tab):
    """DA10 after DA9, which plain string order gets wrong."""
    from lobemap.viewer.panel import _natural_key

    assert _natural_key("DA9") < _natural_key("DA10")
    assert sorted(["VC10", "VC2", "VC1"], key=_natural_key) == \
        ["VC1", "VC2", "VC10"]


def test_a_row_no_longer_means_a_compartment_index(tab):
    """The premise of the whole refactor.

    hemibrain's names happen to arrive alphabetical, so the DEFAULT sort
    is a no-op there and proves nothing. Reverse it to force the case
    every handler now has to survive.
    """
    from qtpy.QtCore import Qt

    from lobemap.viewer.panel import NAME_COL

    tab.table.sortItems(NAME_COL, Qt.DescendingOrder)
    pairs = {r: tab._index_of(r) for r in range(tab.table.rowCount())}
    assert any(r != i for r, i in pairs.items()), "sorting changed nothing"
    # Still a bijection: every compartment present exactly once.
    assert sorted(pairs.values()) == list(range(tab.table.rowCount()))
    # And picking still lands on the right glomerulus.
    tab.highlight(0)
    assert tab._index_of(tab.table.currentRow()) == 0
    tab.table.sortItems(NAME_COL, Qt.AscendingOrder)


def test_highlight_finds_the_row_for_an_index(tab):
    from lobemap.viewer.panel import NAME_COL

    index = 7
    tab.highlight(index)
    row = tab.table.currentRow()
    assert tab._index_of(row) == index, (
        "highlight jumped to a row number, not to the compartment"
    )
    assert tab.table.item(row, NAME_COL).text() == \
        tab.surface.meshset.names[index]


def test_show_none_then_all_round_trips(tab):
    n = tab.table.rowCount()
    tab._none()
    assert tab.surface.selection == set()
    tab._all()
    assert tab.surface.selection == set(range(n))


def test_filtered_only_selects_the_right_compartments(tab):
    """The filter hides rows; the selection must be in index space."""
    tab._apply_filter("DA1")
    tab._filtered_only()
    chosen = {tab.surface.meshset.names[i] for i in tab.surface.selection}
    assert chosen, "nothing matched DA1"
    assert all("da1" in n.lower() for n in chosen), chosen
    tab._apply_filter("")


def test_the_fill_column_drives_the_contour_overlay(tab):
    from qtpy.QtCore import Qt

    from lobemap.viewer.panel import FILL_COL

    assert tab.contour is not None
    row = 3
    index = tab._index_of(row)
    assert index not in tab.contour.filled
    tab.table.item(row, FILL_COL).setCheckState(Qt.Checked)
    assert index in tab.contour.filled, "ticking fill did not reach the layer"
    tab.table.item(row, FILL_COL).setCheckState(Qt.Unchecked)
    assert index not in tab.contour.filled


def test_fill_and_label_are_independent(tab):
    from qtpy.QtCore import Qt

    from lobemap.viewer.panel import FILL_COL, LABEL_COL

    row = 5
    index = tab._index_of(row)
    tab.table.item(row, FILL_COL).setCheckState(Qt.Checked)
    assert index in tab.contour.filled
    assert index not in tab.contour.labels
    tab.table.item(row, LABEL_COL).setCheckState(Qt.Checked)
    assert index in tab.contour.filled and index in tab.contour.labels
    tab.table.item(row, FILL_COL).setCheckState(Qt.Unchecked)


def test_annotation_columns_are_populated(tab):
    from lobemap.viewer.panel import NAME_COL

    rec = _col(tab, "receptor(s)")
    got = {}
    for r in range(tab.table.rowCount()):
        name = tab.table.item(r, NAME_COL).text()
        got[name] = tab.table.item(r, rec).text()
    hits = [v for v in got.values() if v]
    assert len(hits) > 30, f"only {len(hits)} rows carry a receptor"
    # Joined on the CANONICAL name: the published one here is `AL-DA1(R)`.
    da1 = next(v for k, v in got.items() if "DA1(" in k.upper())
    assert da1 == "Or67d", da1


@pytest.fixture
def fafb_tabs(registry):
    """FAFB has both kinds of layer: one atlas and one neuropil set."""
    import napari

    from lobemap.viewer.app import build_scene
    from lobemap.viewer.panel import CompartmentPanel

    try:
        viewer = napari.Viewer(show=False, ndisplay=3)
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"no Qt display: {exc}")
    try:
        surfaces, contours = build_scene(viewer, registry, "FAFB14")
        # Bound to a name: an inline `CompartmentPanel(...).tabs` lets the
        # panel be collected, and Qt then deletes the widgets underneath.
        panel = CompartmentPanel(viewer, surfaces, registry=registry,
                                 contours=contours)
        yield panel.tabs
    finally:
        viewer.close()


def _visible_headers(tab):
    from lobemap.viewer.panel import COLUMNS

    return [
        tab.table.horizontalHeaderItem(i).text()
        for i in range(len(COLUMNS))
        if not tab.table.isColumnHidden(i)
    ]


def test_a_neuropil_layer_is_not_described_as_glomeruli(fafb_tabs):
    """It has no compartments, so seven columns were blank and the header
    claimed the table was about glomeruli while listing whole neuropils."""
    tab = fafb_tabs["fafb_neuropil"]
    assert tab.is_atlas is False
    assert _visible_headers(tab) == ["", "neuropil", "label", "fill"]


def test_an_atlas_layer_keeps_every_column(fafb_tabs):
    tab = fafb_tabs["benton2025"]
    assert tab.is_atlas is True
    headers = _visible_headers(tab)
    assert headers[1] == "glomerulus"
    for expected in ("canonical", "side", "receptor(s)", "co-receptor(s)"):
        assert expected in headers


def test_fill_and_label_still_work_on_a_neuropil_tab(fafb_tabs):
    """The two columns that are kept must still drive the layer."""
    from qtpy.QtCore import Qt

    from lobemap.viewer.panel import FILL_COL, LABEL_COL

    tab = fafb_tabs["fafb_neuropil"]
    if tab.contour is None:
        pytest.skip("no contour overlay for the neuropil layer")
    index = tab._index_of(2)
    tab.table.item(2, FILL_COL).setCheckState(Qt.Checked)
    assert index in tab.contour.filled
    tab.table.item(2, LABEL_COL).setCheckState(Qt.Checked)
    assert index in tab.contour.labels


def test_columns_are_sized_to_their_contents(fafb_tabs):
    """Not a fixed width: the receptor lists vary by a factor of three."""
    from qtpy.QtWidgets import QHeaderView

    from lobemap.viewer.panel import COLUMNS

    tab = fafb_tabs["benton2025"]
    header = tab.table.horizontalHeader()
    for col in range(len(COLUMNS)):
        assert header.sectionResizeMode(col) == QHeaderView.ResizeToContents
    widths = {
        tab.table.horizontalHeaderItem(c).text(): tab.table.columnWidth(c)
        for c in range(len(COLUMNS))
    }
    # A column holding long strings must be wider than one holding "L"/"R".
    assert widths["receptor(s)"] > widths["side"], widths
    assert len(set(widths.values())) > 3, "columns look uniformly sized"


def test_a_hex_colour_spec_does_not_break_filling():
    """The bug: neuropil shells are the string "#9aa0a6", and indexing a
    string gives "#", so filling one raised `could not convert string to
    float`. Only the atlases carry per-compartment arrays."""
    from lobemap.viewer.contours import ContourOverlay

    for spec in ("#9aa0a6", "#ff7f0e", "white", (0.1, 0.2, 0.3, 1.0)):
        r, g, b, a = ContourOverlay._as_rgba(spec)
        assert all(0.0 <= v <= 1.0 for v in (r, g, b, a)), spec


def test_fill_all_works_on_a_neuropil_layer(fafb_tabs):
    """End to end, in 2D, where the contours actually draw."""
    import numpy as np

    tab = fafb_tabs["fafb_neuropil"]
    if tab.contour is None:
        pytest.skip("no contour overlay")
    tab.contour.layer.visible = True
    tab.contour.refresh()

    tab._fill_for_shown()
    assert tab.contour.filled == set(tab.surface.selection)
    if len(tab.contour.layer.data):
        kinds = {getattr(s, "name", str(s)).lower()
                 for s in tab.contour.layer.shape_type}
        assert kinds == {"polygon"}, kinds
        faces = np.asarray(tab.contour.layer.face_color)
        assert np.allclose(faces[:, 3], tab.contour.FILL_ALPHA)

    tab._no_fill()
    assert tab.contour.filled == set()


def test_fill_buttons_track_the_checkboxes(fafb_tabs):
    from qtpy.QtCore import Qt

    from lobemap.viewer.panel import FILL_COL

    tab = fafb_tabs["benton2025"]
    tab._fill_for_shown()
    states = {tab.table.item(r, FILL_COL).checkState()
              for r in range(tab.table.rowCount())}
    assert states == {Qt.Checked}, "Fill all left boxes unticked"
    tab._no_fill()
    states = {tab.table.item(r, FILL_COL).checkState()
              for r in range(tab.table.rowCount())}
    assert states == {Qt.Unchecked}, "Fill none left boxes ticked"
