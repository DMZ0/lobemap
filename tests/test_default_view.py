"""The camera the GUI opens with, and the atlas it opens with.

Anatomical axes differ between spaces -- hemibrain's antero-posterior axis is
y where FAFB's is z -- so they are declared per space and measured, never
assumed. A camera pointed down the wrong axis still renders something, which
is why this is tested rather than eyeballed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lobemap.core.model import Space, axis_vector
from lobemap.core.registry import Registry

REGISTRY = Path(__file__).resolve().parents[1] / "registry"


@pytest.mark.parametrize(
    ("spec", "expect"),
    [("-z", (0, 0, -1)), ("+y", (0, 1, 0)), ("y", (0, 1, 0)), ("-X", (-1, 0, 0))],
)
def test_axis_vector(spec, expect):
    assert np.allclose(axis_vector(spec), expect)


def test_axis_vector_rejects_nonsense():
    for bad in ("", "-w", "up", "zz"):
        with pytest.raises(ValueError, match="axis reference"):
            axis_vector(bad)


#: Determined twice over, from positional nomenclature and from handedness.
EXPECTED_AXES = {
    "FAFB14": ("-z", "-y"),
    "JRCFIB2018F": ("+y", "-z"),
    "JRCFIB2022M": ("-z", "-y"),
    "GRABE": ("-y", "-z"),
}


def test_declared_axes_match_what_was_measured():
    reg = Registry.load(REGISTRY)
    for space_id, (anterior, dorsal) in EXPECTED_AXES.items():
        space = reg.spaces[space_id]
        assert (space.anterior, space.dorsal) == (anterior, dorsal), space_id
    assert reg.spaces["FAFB14"].primary_atlas == "benton2025"


def test_axes_agree_with_positional_nomenclature():
    """AL names encode position: D/V first letter, A/P second.

    This is the independent check on the declared axes. It caught a dorsal
    sign that was backwards in all four spaces.
    """
    from lobemap.core.names import parse_roi

    reg = Registry.load(REGISTRY)
    for atlas_id, space_id in (("benton2025", "FAFB14"),
                               ("neuprint_hemibrain", "JRCFIB2018F"),
                               ("neuprint_cns", "JRCFIB2022M"),
                               ("grabe2015", "GRABE")):
        ms = reg.mesh(reg.atlases[atlas_id].asset)
        sides = {s for _, s in (parse_roi(n) for n in ms.names) if s}
        side = "R" if "R" in sides else (min(sides) if sides else None)
        cents = {}
        for i, raw in enumerate(ms.names):
            name, s = parse_roi(raw)
            if side and s and s != side:
                continue
            a, b = int(ms.vertex_offsets[i]), int(ms.vertex_offsets[i + 1])
            cents.setdefault(name, []).append(ms.vertices[a:b].mean(0))
        cents = {k: np.mean(v, axis=0) for k, v in cents.items()}

        def direction(pos, neg, cents=cents):
            p = [v for k, v in cents.items() if pos(k)]
            q = [v for k, v in cents.items() if neg(k)]
            return np.mean(p, axis=0) - np.mean(q, axis=0)

        space = reg.spaces[space_id]
        dorsal = direction(lambda n: n[:1] == "D", lambda n: n[:1] == "V")
        anterior = direction(lambda n: n[1:2] == "A", lambda n: n[1:2] == "P")
        assert np.dot(dorsal, axis_vector(space.dorsal)) > 0, f"{space_id} dorsal"
        assert np.dot(anterior, axis_vector(space.anterior)) > 0, f"{space_id} anterior"


def test_left_al_lands_on_the_viewers_right_except_in_fafb():
    """The handedness convention, which fixes the sign of dorsal.

    Screen right is view x up. Getting that cross product backwards inverts
    dorsal, which renders the brain upside down and looks like a camera bug.
    """
    reg = Registry.load(REGISTRY)
    cases = {
        "FAFB14": ("fafb_neuropil", "AL_L", "AL_R", -1),
        "JRCFIB2018F": ("neuprint_hemibrain_neuropil", "AL(L)", "AL(R)", +1),
        "JRCFIB2022M": ("neuprint_cns_neuropil", "AL(L)", "AL(R)", +1),
        "GRABE": ("grabe2015_glomeruli", "DA1(L)", "DA1(R)", +1),
    }
    for space_id, (asset, left, right_name, want) in cases.items():
        space = reg.spaces[space_id]
        ms = reg.mesh(asset)

        def centroid(name, ms=ms):
            i = ms.names.index(name)
            a, b = int(ms.vertex_offsets[i]), int(ms.vertex_offsets[i + 1])
            return ms.vertices[a:b].mean(0)

        view = -axis_vector(space.anterior)
        up = axis_vector(space.dorsal)
        screen_right = np.cross(view, up)
        offset = float(np.dot(centroid(left) - centroid(right_name), screen_right))
        assert (offset > 0) == (want > 0), (space_id, offset)


def test_the_antennal_lobes_lie_anterior_in_fafb():
    """A third, independent check on the anterior axis alone.

    The landmark is the union of all 78 neuropils, which is what stands in
    for a brain outline now that the Bates Plotly brain mesh is gone.
    """
    reg = Registry.load(REGISTRY)
    brain = reg.mesh("fafb_neuropil").vertices
    mid = (brain.min(0) + brain.max(0)) / 2
    al = reg.mesh("benton2025_glomeruli").vertices.mean(0)
    anterior = axis_vector(reg.spaces["FAFB14"].anterior)
    assert np.dot(al - mid, anterior) > 0, "ALs must be on the anterior side"


def test_spaces_disagree_about_which_axis_is_anterior():
    """The reason this is per-space data and not a constant."""
    reg = Registry.load(REGISTRY)
    assert reg.spaces["JRCFIB2018F"].anterior == "+y"
    assert reg.spaces["JRCFIB2022M"].anterior == "-z"
    assert reg.spaces["FAFB14"].anterior == "-z"


def test_every_space_opens_with_exactly_one_atlas_and_its_image():
    """Two atlases stacked at startup is unreadable; that is the whole point.

    This used to read the answer out of a scene preset. There is no preset
    now: the space names its primary atlas, and the image comes along
    because an image is shown whenever it is on disk.
    """
    reg = Registry.load(REGISTRY)
    expected = {
        "FAFB14": ("benton2025", "fafb_stain"),
        "JRCFIB2018F": ("neuprint_hemibrain", "hemibrain_stain"),
        "JRCFIB2022M": ("neuprint_cns", "malecns_stain"),
        "GRABE": ("grabe2015", "grabe2015_stack"),
    }
    for space_id, (atlas, image) in expected.items():
        primary = reg.primary_atlas(space_id)
        assert primary is not None and primary.id == atlas, space_id
        images = [a.id for a in reg.assets_in_space(space_id)
                  if a.kind == "image"]
        assert images == [image], (space_id, images)


def test_every_space_with_an_atlas_declares_both_axes():
    """One axis alone leaves the roll free, so the camera is skipped."""
    reg = Registry.load(REGISTRY)
    for space_id, space in reg.spaces.items():
        if not reg.atlases_in_space(space_id):
            continue
        assert space.anterior and space.dorsal, space_id


def test_spaces_with_an_atlas_all_declare_a_default():
    reg = Registry.load(REGISTRY)
    for space_id, space in reg.spaces.items():
        if reg.atlases_in_space(space_id):
            assert space.primary_atlas, f"{space_id} has atlases but no primary"


def test_the_other_atlases_of_a_space_are_still_loaded():
    """Not shown is not the same as not there.

    JRCFIB2018F is the case the whole design exists for: three
    parcellations of one volume, superposable because they share a space.
    Opening on one of them must not mean the other two are absent.
    """
    reg = Registry.load(REGISTRY)
    here = {a.id for a in reg.atlases_in_space("JRCFIB2018F")}
    assert here == {"neuprint_hemibrain", "schlegel2021_s11",
                    "schlegel2021_s12"}
    assert reg.primary_atlas("JRCFIB2018F").id == "neuprint_hemibrain"


def test_registry_rejects_a_bad_axis_or_primary_atlas():
    from lobemap.core.registry import RegistryError

    reg = Registry.load(REGISTRY, validate=False)
    reg.spaces["FAFB14"] = Space(id="FAFB14", title="x", units="um",
                                 anterior="sideways")
    with pytest.raises(RegistryError, match="signed axis"):
        reg.validate()

    reg = Registry.load(REGISTRY, validate=False)
    reg.spaces["FAFB14"] = Space(id="FAFB14", title="x", units="um",
                                 primary_atlas="no_such_atlas")
    with pytest.raises(RegistryError, match="no_such_atlas"):
        reg.validate()


def test_several_atlases_and_no_primary_is_a_registry_error():
    """Otherwise the viewer picks one and the choice is invisible."""
    from dataclasses import replace

    from lobemap.core.registry import RegistryError

    reg = Registry.load(REGISTRY, validate=False)
    reg.spaces["JRCFIB2018F"] = replace(reg.spaces["JRCFIB2018F"],
                                        primary_atlas=None)
    with pytest.raises(RegistryError, match="no primary_atlas"):
        reg.validate()


# -- the camera itself ---------------------------------------------------


@pytest.fixture
def viewer():
    napari = pytest.importorskip("napari")
    v = napari.Viewer(ndisplay=3, show=False)
    yield v
    v.close()


def test_orient_anterior_points_the_camera_down_the_declared_axis(viewer):
    from lobemap.viewer.app import GIMBAL_NUDGE_DEG, orient_anterior

    space = Space(id="S", title="s", units="um", anterior="-z", dorsal="+y")
    assert orient_anterior(viewer, space) is True
    cam = getattr(viewer, "scene", viewer).camera
    # Camera sits anterior and looks posteriorly, i.e. along +z, less the
    # small yaw that keeps it off the gimbal singularity.
    off = np.degrees(np.arccos(np.clip(
        np.dot(np.asarray(cam.view_direction), (0, 0, 1)), -1, 1)))
    assert off == pytest.approx(GIMBAL_NUDGE_DEG, abs=0.01)
    assert np.dot(np.asarray(cam.up_direction), (0, 1, 0)) > 0.99


def test_an_exactly_axis_aligned_camera_is_flipped_by_napari(viewer):
    """Why `GIMBAL_NUDGE_DEG` exists. Pins the napari behaviour.

    At exact gimbal lock napari's vispy round trip -- angles to quaternion and
    back -- cannot recover the third Euler angle and zeroes it, which returns
    a NEGATED up vector. The brain renders upside down with no error. If this
    test starts failing, napari has fixed it and the nudge can go.
    """
    from napari._vispy.camera import (
        napari_angles_to_vispy_quat as forward,
    )
    from napari._vispy.camera import (
        vispy_quat_to_napari_angles as backward,
    )
    from napari.components.camera import Camera

    def round_trip(view, up):
        cam = Camera()
        cam.set_view_direction(view_direction=view, up_direction=up)
        angles = backward(forward(np.array(cam.angles), (False,) * 3),
                          (False,) * 3)
        out = Camera()
        out.angles = tuple(angles)
        return np.asarray(out.up_direction)

    assert np.dot(round_trip((0, 0, 1), (0, 1, 0)), (0, 1, 0)) < -0.99, (
        "napari no longer inverts an axis-aligned camera; drop the nudge"
    )
    eps = np.tan(np.radians(1.0))
    nudged = np.array([eps, 0.0, 1.0])
    nudged /= np.linalg.norm(nudged)
    assert np.dot(round_trip(tuple(nudged), (0, 1, 0)), (0, 1, 0)) > 0.99


def test_the_nudge_survives_the_round_trip_for_every_space():
    from napari._vispy.camera import (
        napari_angles_to_vispy_quat as forward,
    )
    from napari._vispy.camera import (
        vispy_quat_to_napari_angles as backward,
    )
    from napari.components.camera import Camera

    from lobemap.viewer.app import orient_anterior

    napari = pytest.importorskip("napari")
    reg = Registry.load(REGISTRY)
    viewer = napari.Viewer(ndisplay=3, show=False)
    try:
        for space_id, (_anterior, dorsal) in EXPECTED_AXES.items():
            assert orient_anterior(viewer, reg.spaces[space_id]) is True
            cam = getattr(viewer, "scene", viewer).camera
            angles = backward(forward(np.array(cam.angles), (False,) * 3),
                              (False,) * 3)
            after = Camera()
            after.angles = tuple(angles)
            assert np.dot(np.asarray(after.up_direction),
                          axis_vector(dorsal)) > 0.99, space_id
    finally:
        viewer.close()


def test_a_space_missing_dorsal_is_left_alone(viewer):
    """Facing the right way at an arbitrary roll is worse than not trying."""
    from lobemap.viewer.app import orient_anterior

    before = tuple(getattr(viewer, "scene", viewer).camera.view_direction)
    space = Space(id="S", title="s", units="um", anterior="-z")
    assert orient_anterior(viewer, space) is False
    after = tuple(getattr(viewer, "scene", viewer).camera.view_direction)
    assert before == after


def test_orientation_is_skipped_in_2d(viewer):
    from lobemap.viewer.app import orient_anterior

    viewer.dims.ndisplay = 2
    space = Space(id="S", title="s", units="um", anterior="-z", dorsal="+y")
    assert orient_anterior(viewer, space) is False


def test_fit_view_keeps_the_orientation(viewer):
    """reset_view resets camera angles by default, which would undo it."""
    from lobemap.viewer.app import fit_view, orient_anterior

    viewer.add_image(np.zeros((40, 30, 20), np.uint8))
    space = Space(id="S", title="s", units="um", anterior="-z", dorsal="+y")
    orient_anterior(viewer, space)
    fit_view(viewer)
    cam = getattr(viewer, "scene", viewer).camera
    assert np.dot(np.asarray(cam.view_direction), (0, 0, 1)) > 0.999
    assert np.dot(np.asarray(cam.up_direction), (0, 1, 0)) > 0.99
    assert cam.zoom > 0


def test_a_space_with_no_atlases_has_no_primary():
    """Nothing to open means nothing to open ON, rather than a crash."""
    reg = Registry.load(REGISTRY, validate=False)
    reg.spaces["EMPTY"] = Space(id="EMPTY", title="empty", units="um")
    assert reg.primary_atlas("EMPTY") is None


def test_the_initial_fit_follows_the_canvas(viewer):
    """Maximising is asynchronous, so a fit done once lands on the wrong size.

    Measured through the real startup, before and after: FAFB 42% -> 81% of
    the canvas, Grabe 50% -> 96%, hemibrain 57% -> 96%, male CNS -> 97%.
    """
    from lobemap.viewer.app import install_initial_fit

    viewer.add_image(np.zeros((40, 30, 20), np.uint8))
    assert install_initial_fit(viewer) is True
    cam = getattr(viewer, "scene", viewer).camera
    assert cam.zoom > 0


def test_the_initial_fit_watches_napari_canvas_not_the_widget(viewer):
    """`fit_to_view` divides by `viewer.canvas.size`, which lags the widget.

    Watching the Qt widget instead is why FAFB kept its 900x700 zoom while
    other spaces happened to refit correctly.
    """
    import inspect

    from lobemap.viewer.app import install_initial_fit

    source = inspect.getsource(install_initial_fit)
    assert 'getattr(viewer, "canvas", None)' in source
    assert "native" not in source


def test_the_initial_fit_survives_a_viewer_without_a_canvas():
    """Headless runs have no Qt viewer to hang the callback on."""
    from lobemap.viewer.app import install_initial_fit

    class _Dummy:
        class window:
            pass

        def reset_view(self, **_kw):
            self.reset = True

    dummy = _Dummy()
    assert install_initial_fit(dummy) is False
    assert getattr(dummy, "reset", False) is True
