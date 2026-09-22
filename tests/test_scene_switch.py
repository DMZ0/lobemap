"""Switching space in a live viewer must leave nothing of the old scene.

The failure this guards against is not a crash on the switch but a viewer
that afterwards is driven by two scenes at once: the display-mode and contour
hooks live on `viewer.dims.events`, which outlives any one scene, so a
handler left connected keeps firing against layers that have been removed.
"""

from __future__ import annotations

import pytest

from lobemap.core.registry import Registry
from lobemap.viewer.app import load_space


@pytest.fixture(scope="module")
def registry():
    return Registry.load("registry")


def _handler_count(viewer):
    return len(viewer.dims.events.ndisplay.callbacks)


def test_switching_replaces_the_scene(registry):
    napari = pytest.importorskip("napari")
    viewer = napari.Viewer(show=False)
    try:
        first = load_space(viewer, registry, "GRABE", fit=False)
        assert any("grabe" in n.lower() for n in
                   (layer.name for layer in viewer.layers))
        before = _handler_count(viewer)

        first.teardown()
        assert len(viewer.layers) == 0, "teardown left layers behind"

        second = load_space(viewer, registry, "JRCFIB2018F", fit=False)
        names = [layer.name for layer in viewer.layers]
        assert not any("grabe" in n.lower() for n in names), (
            f"the old scene survived the switch: {names}"
        )
        assert second.space == "JRCFIB2018F"

        # The point of the test: hooks must not accumulate.
        assert _handler_count(viewer) == before, (
            f"dims.ndisplay handlers grew {before} -> {_handler_count(viewer)};"
            " the old scene is still being driven"
        )
    finally:
        viewer.close()


def test_repeated_switching_is_stable(registry):
    """Four switches must behave like one -- no growth, no leftovers."""
    napari = pytest.importorskip("napari")
    viewer = napari.Viewer(show=False)
    try:
        session = load_space(viewer, registry, "GRABE", fit=False)
        counts, layer_counts = [], []
        for space in ("JRCFIB2018F", "GRABE", "JRCFIB2022M", "GRABE"):
            session.teardown()
            session = load_space(viewer, registry, space, fit=False)
            counts.append(_handler_count(viewer))
            layer_counts.append(len(viewer.layers))
        assert len(set(counts)) == 1, f"handlers drifted across switches: {counts}"
        # GRABE appears twice and must rebuild identically both times.
        assert layer_counts[1] == layer_counts[3], (
            f"the same space gave different layer counts: {layer_counts}"
        )
    finally:
        viewer.close()


def test_switching_still_switches_display_mode(registry):
    """After a switch, 2D/3D must drive the NEW scene's layers."""
    napari = pytest.importorskip("napari")
    viewer = napari.Viewer(ndisplay=3, show=False)
    try:
        session = load_space(viewer, registry, "GRABE", fit=False)
        session.teardown()
        session = load_space(viewer, registry, "JRCFIB2018F", fit=False)

        surface = next(iter(session.surfaces.values())).layer
        contour = next(iter(session.contours.values())).layer
        viewer.dims.ndisplay = 2
        assert contour in viewer.layers, "contours missing in 2D after a switch"
        assert surface not in viewer.layers, "meshes still present in 2D"
        viewer.dims.ndisplay = 3
        assert surface in viewer.layers, "meshes missing in 3D after a switch"
        assert contour not in viewer.layers, "contours still present in 3D"
    finally:
        viewer.close()
