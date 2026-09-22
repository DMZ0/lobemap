"""The anatomical frame, checked against the anatomy rather than asserted.

Which array axis points anterior differs between spaces, and the sign differs
too, so these are facts about data that have to be measured. A sign error
here is invisible -- the triad looks just as convincing pointing the wrong
way -- which is why this file measures instead of restating the constants.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from lobemap.core.model import anatomical_axes
from lobemap.core.registry import Registry
from lobemap.viewer.axes import axis_labels_for, label_viewer_axes


@pytest.fixture(scope="module")
def registry():
    return Registry.load("registry")


def _strip(name: str) -> str:
    return re.sub(r"^AL-", "", re.sub(r"\(.\)$", "", name))


def _group_centroid(meshset, keep):
    picked = [
        meshset.compartment(i)[0].mean(0)
        for i, name in enumerate(meshset.names)
        if keep(_strip(name))
    ]
    return np.mean(picked, axis=0) if picked else None


@pytest.mark.parametrize(
    "space,atlas",
    [
        ("FAFB14", "benton2025"),
        ("JRCFIB2018F", "neuprint_hemibrain"),
        ("JRCFIB2022M", "neuprint_cns"),
        ("GRABE", "grabe2015"),
    ],
)
def test_frame_agrees_with_positional_nomenclature(registry, space, atlas):
    """D* must sit dorsal of V*, and *A anterior of *P, in every space.

    Glomerulus names encode position -- first letter D/V, second A/P or M/L --
    so the names are an independent witness to the geometry.
    """
    frame = anatomical_axes(registry.spaces[space])
    assert frame is not None, f"{space} declares no axes"
    entry = next(a for a in registry.atlases_in_space(space) if a.id == atlas)
    meshset = registry.mesh(entry.asset)

    dorsal_group = _group_centroid(meshset, lambda n: n.startswith("D"))
    ventral_group = _group_centroid(meshset, lambda n: n.startswith("V"))
    anterior_group = _group_centroid(meshset, lambda n: len(n) > 1 and n[1] == "A")
    posterior_group = _group_centroid(meshset, lambda n: len(n) > 1 and n[1] == "P")

    for a, b, pole, what in (
        (dorsal_group, ventral_group, "D", "D* vs V*"),
        (anterior_group, posterior_group, "A", "*A vs *P"),
    ):
        assert a is not None and b is not None, f"{atlas}: no {what} groups"
        direction = a - b
        direction = direction / np.linalg.norm(direction)
        agreement = float(np.dot(direction, frame[pole]))
        assert agreement > 0.5, (
            f"{space}/{atlas}: {what} points {agreement:+.2f} along {pole}; "
            f"the {pole} axis looks inverted"
        )


def test_lateral_points_at_the_biological_right_in_fafb(registry):
    """A mirrored space MUST flip the lateral axis.

    FAFB is the one space where apparent and biological sides come apart,
    and the two kinds of label in it disagree about which they use: FlyWire's
    neuropil annotations are post-correction and biological, so `AL_L` really
    is the left lobe, while Bates's and Benton's glomerulus sides are
    apparent -- they declare R while sitting inside `AL_L`.

    So the R arrow has to run from `AL_L` toward `AL_R`. Unnegated,
    cross(anterior, dorsal) runs the other way, and FAFB is precisely where
    that could not be caught by comparing two lobes of one atlas, because
    its atlases cover only one.
    """
    frame = anatomical_axes(registry.spaces["FAFB14"])
    assert registry.spaces["FAFB14"].is_mirrored, "fixture assumption changed"
    meshset = registry.mesh("fafb_neuropil")
    centroid = {}
    for name in ("AL_L", "AL_R"):
        verts, _faces = meshset.compartment(meshset.names.index(name))
        centroid[name] = verts.mean(0)
    biological_right = centroid["AL_R"] - centroid["AL_L"]
    biological_right /= np.linalg.norm(biological_right)
    assert float(np.dot(biological_right, frame["R"])) > 0.9


@pytest.mark.parametrize(
    "space,atlas",
    [
        ("JRCFIB2018F", "neuprint_hemibrain"),
        ("JRCFIB2022M", "neuprint_cns"),
        ("GRABE", "grabe2015"),
    ],
)
def test_lateral_points_at_declared_right_where_sides_are_biological(
    registry, space, atlas
):
    """In an unmirrored space the declared sides ARE the biological ones."""
    assert not registry.spaces[space].is_mirrored
    frame = anatomical_axes(registry.spaces[space])
    entry = next(a for a in registry.atlases_in_space(space) if a.id == atlas)
    meshset = registry.mesh(entry.asset)
    sides: dict[str, list] = {"L": [], "R": []}
    for i, compartment in enumerate(entry.compartments):
        if compartment.side in sides:
            sides[compartment.side].append(meshset.compartment(i)[0].mean(0))
    assert sides["L"] and sides["R"], f"{atlas} has no L/R pair"
    direction = np.mean(sides["R"], axis=0) - np.mean(sides["L"], axis=0)
    direction /= np.linalg.norm(direction)
    assert float(np.dot(direction, frame["R"])) > 0.9


def test_a_space_without_axes_gets_no_frame(registry):
    space = registry.spaces["JRC2018U"]
    assert not (space.anterior and space.dorsal), "fixture assumption changed"
    assert anatomical_axes(space) is None
    assert axis_labels_for(space) is None


def test_axis_labels_name_every_array_axis(registry):
    """Each array axis carries exactly one anatomical axis, with its sign.

    A label is the direction of travel alone -- "P->A" -- so the pair of
    poles is what identifies the axis.
    """
    for space_id in ("FAFB14", "JRCFIB2018F", "JRCFIB2022M", "GRABE"):
        labels = axis_labels_for(registry.spaces[space_id])
        assert labels is not None and len(labels) == 3
        assert "?" not in "".join(labels), f"{space_id}: unnamed axis in {labels}"
        for label in labels:
            assert "(" not in label, (
                f"{space_id}: {label!r} still repeats the axis name"
            )
        # A set, not a sorted list: `<` on frozensets is subset, not an
        # ordering, so sorting them compares nothing useful.
        pairs = {frozenset(label.split("->")) for label in labels}
        assert pairs == {
            frozenset("AP"), frozenset("DV"), frozenset("LR")
        }, f"{space_id}: {labels} does not cover all three axes once each"


def test_axis_labels_read_along_increasing_index(registry):
    """"P->A" must mean that walking the slider up goes P then A."""
    for space_id in ("FAFB14", "JRCFIB2018F", "JRCFIB2022M", "GRABE"):
        space = registry.spaces[space_id]
        frame = anatomical_axes(space)
        for axis, label in enumerate(axis_labels_for(space)):
            _from, to = label.split("->")
            assert frame[to][axis] > 0, (
                f"{space_id} axis {axis} is labelled {label!r}, but {to} "
                f"points down the axis, not up it"
            )


def test_no_axes_layer_is_created(registry):
    """The anatomy is named on napari's own overlay, not drawn as a layer.

    A second, world-space triad used to be added here. It duplicated the
    overlay, and because its arrows pointed at the anatomical pole rather
    than up the array axis they ran OPPOSITE to the overlay's in 8 of the 12
    space/axis combinations -- in FAFB the overlay's z arrow points posterior
    while the layer's A-P arrow pointed anterior.
    """
    napari = pytest.importorskip("napari")
    from lobemap.viewer.app import build_scene

    viewer = napari.Viewer(show=False)
    try:
        build_scene(viewer, registry, "GRABE")
        stray = [
            layer.name for layer in viewer.layers
            if layer.metadata.get("lobemap", {}).get("kind") == "axes"
            or "anatomical axes" in layer.name
        ]
        assert not stray, f"an axes layer came back: {stray}"
    finally:
        viewer.close()


def test_the_overlay_is_turned_on_and_named(registry):
    napari = pytest.importorskip("napari")
    from lobemap.viewer.app import build_scene

    viewer = napari.Viewer(show=False)
    try:
        build_scene(viewer, registry, "FAFB14")
        assert tuple(viewer.dims.axis_labels) == axis_labels_for(
            registry.spaces["FAFB14"]
        )
        overlay = viewer.scene.overlays.axes
        assert overlay.visible is True
        assert overlay.labels is True
    finally:
        viewer.close()


def test_a_space_without_axes_leaves_the_labels_alone(registry):
    """No axes declared means no claim about orientation, not a wrong one."""
    napari = pytest.importorskip("napari")

    viewer = napari.Viewer(ndisplay=3, show=False)
    try:
        before = tuple(viewer.dims.axis_labels)
        assert label_viewer_axes(viewer, registry.spaces["JRC2018U"]) is False
        assert tuple(viewer.dims.axis_labels) == before
    finally:
        viewer.close()


def test_labels_are_refused_rather_than_truncated(registry):
    """Three labels onto a 2D viewer must not silently become two.

    napari keeps the TAIL of an over-long label tuple, so D->V would land on
    x and A->P on y -- a confident, wrong answer in place of no answer.
    """
    napari = pytest.importorskip("napari")

    viewer = napari.Viewer(show=False)      # no layers: dims.ndim == 2
    try:
        assert viewer.dims.ndim == 2, "fixture assumption changed"
        before = tuple(viewer.dims.axis_labels)
        assert label_viewer_axes(viewer, registry.spaces["FAFB14"]) is False
        assert tuple(viewer.dims.axis_labels) == before
    finally:
        viewer.close()
