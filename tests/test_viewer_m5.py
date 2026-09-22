"""M5: slice contours, the compartment table, and scene presets."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REGISTRY = Path(__file__).resolve().parents[1] / "registry"

pytest.importorskip("napari")
pytest.importorskip("trimesh")


@pytest.fixture(scope="module")
def registry():
    from lobemap.core.registry import Registry

    if not (REGISTRY / "data").is_dir():
        pytest.skip("no ingested data")
    return Registry.load(REGISTRY)


@pytest.fixture(scope="module")
def viewer():
    import napari

    try:
        v = napari.Viewer(show=False, ndisplay=2)
    except Exception as exc:  # pragma: no cover - no display
        pytest.skip(f"no Qt display: {exc}")
    yield v
    v.close()


@pytest.fixture(scope="module")
def scene(registry, viewer):
    from lobemap.viewer.app import build_scene

    return build_scene(viewer, registry, "JRCFIB2018F")


# -- contours -----------------------------------------------------------


def test_every_surface_has_a_contour_including_reference_shells(scene):
    """Reference geometry needs one too, or it has no 2D representation.

    Mesh layers are removed from the layer list in 2D, so a neuropil shell
    without a contour did not merely lose its outline -- it vanished.
    """
    from lobemap.viewer.app import REFERENCE_CONTOUR_COLOR

    surfaces, contours = scene
    assert set(contours) == set(surfaces)
    assert "neuprint_hemibrain" in contours
    assert "neuprint_hemibrain_neuropil" in contours
    # Muted, so context does not compete with the data.
    assert contours["neuprint_hemibrain_neuropil"].color == REFERENCE_CONTOUR_COLOR
    assert contours["neuprint_hemibrain"].color != REFERENCE_CONTOUR_COLOR


def test_contour_lies_exactly_on_the_slice_plane(scene):
    _surfaces, contours = scene
    overlay = contours["neuprint_hemibrain"]
    centroid = overlay.meshset.centroid(0)
    paths, owners = overlay.contours_at(float(centroid[overlay.axis]))
    assert paths, "a plane through a centroid should intersect the mesh"
    for path in paths:
        assert np.allclose(path[:, overlay.axis], centroid[overlay.axis])
    assert all(0 <= o < overlay.meshset.n_compartments for o in owners)


def test_plane_outside_the_mesh_yields_nothing(scene):
    _surfaces, contours = scene
    overlay = contours["neuprint_hemibrain"]
    far = float(overlay.meshset.vertices[:, overlay.axis].max() + 500.0)
    paths, owners = overlay.contours_at(far)
    assert paths == [] and owners == []


def test_contours_follow_the_selection(scene):
    _surfaces, contours = scene
    overlay = contours["neuprint_hemibrain"]
    overlay.set_selection([0])
    centroid = overlay.meshset.centroid(0)
    _paths, owners = overlay.contours_at(float(centroid[overlay.axis]))
    assert set(owners) <= {0}
    overlay.set_selection(range(overlay.meshset.n_compartments))


def test_picked_shape_maps_back_to_a_name(scene):
    """2D identification: Surface._get_value returns None, Shapes does not."""
    _surfaces, contours = scene
    overlay = contours["neuprint_hemibrain"]
    overlay.set_selection(range(overlay.meshset.n_compartments))
    overlay.layer.visible = True
    overlay.refresh()
    if not overlay._shape_index:
        pytest.skip("current slice cuts nothing")
    assert overlay.name_at_shape(0) in overlay.meshset.names
    assert overlay.name_at_shape(None) is None
    assert overlay.name_at_shape(10_000) is None


# -- table --------------------------------------------------------------


def test_table_joins_canonical_names(registry, scene):
    from lobemap.viewer.panel import CompartmentPanel

    surfaces, contours = scene
    panel = CompartmentPanel(None, surfaces, registry=registry, contours=contours)
    tab = panel.tabs["neuprint_hemibrain"]
    assert tab.table.rowCount() == surfaces["neuprint_hemibrain"].meshset.n_compartments
    canonicals = [
        tab.table.item(r, 2).text() for r in range(tab.table.rowCount())
    ]
    assert any(c for c in canonicals), "no canonical names joined into the table"
    sides = {tab.table.item(r, 3).text() for r in range(tab.table.rowCount())}
    assert sides & {"L", "R"}


def test_table_filter_hides_rows(registry, scene):
    from lobemap.viewer.panel import CompartmentPanel

    surfaces, contours = scene
    panel = CompartmentPanel(None, surfaces, registry=registry, contours=contours)
    tab = panel.tabs["neuprint_hemibrain"]
    tab.filter.setText("DA1")
    visible = [r for r in range(tab.table.rowCount()) if not tab.table.isRowHidden(r)]
    assert visible and len(visible) < tab.table.rowCount()
    for r in visible:
        assert "da1" in tab._row_text(r)
    tab.filter.setText("")


# -- scenes -------------------------------------------------------------


def test_scene_presets_reference_known_layers(registry):
    """Every preset names real atlases/assets -- validated at load time too."""
    assert registry.scenes, "no scenes defined"
    for scene_def in registry.scenes.values():
        assert scene_def.space in registry.spaces
        for layer in scene_def.layers:
            assert layer.ref in registry.atlases or layer.ref in registry.assets


def test_apply_scene_restricts_compartments(registry, viewer):
    from lobemap.viewer.app import apply_scene, build_scene

    surfaces, contours = build_scene(viewer, registry, "JRCFIB2018F")
    apply_scene(registry, "da1_across_atlases", surfaces, contours)
    surface = surfaces["neuprint_hemibrain"]
    assert surface.layer.visible
    names = [surface.meshset.names[i] for i in surface.selection]
    assert names and all("DA1" in n.upper() for n in names)
    # A layer absent from the preset is hidden.
    assert not surfaces["neuprint_hemibrain_neuropil"].layer.visible


def test_contours_and_labels_take_their_mesh_colour(registry):
    """A glomerulus is one colour, in 3D and in 2D and on its label.

    Colouring per atlas meant every outline in a scene shared one hue, so a
    slice said which atlas a shape came from but not which glomerulus --
    while the mesh of that same glomerulus was already colour-coded by
    canonical name.
    """
    import numpy as np

    napari = pytest.importorskip("napari")
    from lobemap.viewer.app import build_scene, install_display_mode

    viewer = napari.Viewer(show=False, ndisplay=3)
    try:
        surfaces, contours = build_scene(viewer, registry, "GRABE")
        images = [
            layer for layer in viewer.layers
            if layer.metadata.get("lobemap", {}).get("kind")
            in ("image", "labels")
        ]
        install_display_mode(viewer, surfaces, contours, images)
        viewer.dims.ndisplay = 2

        overlay, surface = contours["grabe2015"], surfaces["grabe2015"]
        axis = overlay.axis
        mid = float(np.percentile(overlay.meshset.vertices[:, axis], 50))
        viewer.dims.set_point(axis, mid)
        overlay.set_labels(set(overlay.selection))
        overlay.refresh()

        owners = overlay._shape_index
        assert len(owners) > 10, "no cross-sections to check"

        edges = np.asarray(overlay.layer.edge_color)
        for shape, owner in enumerate(owners):
            np.testing.assert_allclose(
                edges[shape][:3], surface.colors[owner][:3], atol=1e-2,
                err_msg=f"{overlay.meshset.names[owner]} outline is not its "
                        f"mesh colour",
            )

        # A bare list of colours is indistinguishable from one colour given
        # component-wise, and napari collapses it to a constant. The
        # encoding must survive as a per-shape array.
        encoding = overlay.layer.text.color
        array = np.asarray(getattr(encoding, "array", encoding))
        assert array.shape == (len(owners), 4), (
            f"label colours collapsed to {array.shape}; they are not per-shape"
        )
        for shape, owner in enumerate(owners):
            np.testing.assert_allclose(
                array[shape][:3], surface.colors[owner][:3], atol=1e-2,
                err_msg=f"{overlay.meshset.names[owner]} label is not its "
                        f"mesh colour",
            )
    finally:
        viewer.close()


def test_reference_shells_keep_one_colour(registry):
    """Context geometry stays grey; colouring it would compete."""
    napari = pytest.importorskip("napari")
    from lobemap.viewer.app import REFERENCE_CONTOUR_COLOR, build_scene

    # FAFB14, not GRABE: GRABE is an island space carrying only its own
    # atlas, so it has no reference shell to check.
    viewer = napari.Viewer(show=False, ndisplay=2)
    try:
        _surfaces, contours = build_scene(viewer, registry, "FAFB14")
        shells = [c for name, c in contours.items() if name in registry.assets]
        assert shells, "no reference geometry in this scene"
        for shell in shells:
            assert shell.colors is None
            assert shell.color == REFERENCE_CONTOUR_COLOR
    finally:
        viewer.close()
