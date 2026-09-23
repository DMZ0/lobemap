"""Anatomical names for napari's own axis indicator.

Every space in this project uses different array axes for the same anatomy --
the antero-posterior axis is z in FAFB and the male CNS but y in the
hemibrain -- and each may run either way along them. So "which way is
anterior" is not something a reader can carry between scenes, and without
this the only thing that knew it was the camera.

napari already draws an axis indicator, so the job here is only to name it:
`dims.axis_labels` becomes the anatomy and the overlay is switched on.

Each label is the single pole its own arrow POINTS AT. The indicator draws
one arrow per array axis, always along INCREASING index, and which pole
that reaches differs per space -- FAFB's third axis runs posterior while
the hemibrain's second runs anterior -- so the labels differ too: FAFB
reads R, V, P and the hemibrain L, A, V.

They used to read as a direction of travel, "A->P". That was accurate and
still misread: it looks like the NAME of an axis, and naming the axis
leaves which end is which to be worked out from the arrow. A label that
names one pole cannot be read as an axis name, and cannot contradict the
arrow it sits on, because it is derived from where that arrow goes.

Labelling every arrow `A`, `D`, `L` regardless was considered and is not
possible here: `CanvasAxesOverlay` has no way to reverse an arrow, so on
FAFB's third axis the label would point opposite to the arrow under it --
the same disagreement that got the old Vectors layer removed, below.

napari 0.9 offers two: a SCENE overlay drawn at the world origin, and a
CANVAS overlay anchored in a corner. This uses the canvas one, because the
world origin is not inside the data. Spaces are in the coordinates their
volume was published in, and only some of them start at zero: FAFB's stain
spans x 192-853 um, so an indicator at the origin sits ~190 um outside
everything on screen and the default view simply does not contain it. The
male CNS starts at 37 um and showed part of one. Anchoring to the canvas
makes it independent of where the data happens to sit, and of pan and
zoom.

There used to be a second, world-space `anatomical axes` Vectors layer here
as well, coloured per anatomical axis and pointing at each positive pole.
Two indicators for one thing was already redundant, and worse, they
disagreed: because its arrows pointed at the anatomical pole rather than up
the array axis, they ran OPPOSITE to the overlay's in 8 of the 12
space/axis combinations -- in FAFB the overlay's z arrow points posterior
while the layer's A-P arrow pointed anterior. It was removed rather than
reconciled, since the overlay's direction is fixed by construction.

The poles come from `core.model.anatomical_axes`, which documents how the
lateral direction was measured.
"""

from __future__ import annotations

import contextlib

import numpy as np

from ..core.model import AXIS_POLES, anatomical_axes


def axis_labels_for(space) -> tuple[str, ...] | None:
    """Anatomical names for the three ARRAY axes, in array order.

    Each array axis carries exactly one anatomical axis here -- the spaces
    declare anterior and dorsal as signed array axes, so the frame is
    axis-aligned by construction -- which is what makes this possible at all.

    Each label is the pole that axis's arrow points at, so it describes
    the arrow rather than the axis: an arrow running toward posterior is
    labelled `P`, not `A-P` or `A->P`.
    """
    frame = anatomical_axes(space)
    if frame is None:
        return None
    names = ["?", "?", "?"]
    for positive, negative, _label in AXIS_POLES:
        vector = frame[positive]
        axis = int(np.argmax(np.abs(vector)))
        # The arrow runs along INCREASING index, so it reaches `positive`
        # when this axis points that way and `negative` when it does not.
        names[axis] = positive if vector[axis] > 0 else negative
    return tuple(names)


def label_viewer_axes(viewer, space) -> bool:
    """Name the sliders anatomically and show napari's axis overlay.

    The labels are the part that matters and they work in 2D as well as 3D,
    because they are the slider names rather than geometry. They are also
    independent of the overlay: turning the overlay off would not cost them.
    """
    labels = axis_labels_for(space)
    if labels is None:
        return False
    # napari TRUNCATES a label tuple longer than `ndim`, keeping the tail, so
    # on a viewer that is still 2D three labels silently become two and land
    # on the wrong axes -- D->V onto x and A->P onto y. Refuse instead: this
    # runs at the end of `build_scene`, by which point the layers have made
    # the viewer 3D, and a viewer that is not is not one these labels
    # describe.
    if getattr(viewer.dims, "ndim", 3) != len(labels):
        return False
    try:
        viewer.dims.axis_labels = labels
    except Exception:            # noqa: BLE001 - cosmetic, never fatal
        return False
    # The canvas overlay, not the scene one: see the module docstring. Both
    # exist in napari 0.9 under `canvas.overlays` and `scene.overlays`;
    # older napari has only `viewer.axes`, which is the canvas-anchored one.
    overlay = None
    for holder in ("canvas", "scene"):
        container = getattr(getattr(viewer, holder, None), "overlays", None)
        if container is not None:
            with contextlib.suppress(Exception):
                overlay = container["axes"]
            if overlay is not None:
                break
    if overlay is None:
        with contextlib.suppress(Exception):
            overlay = viewer.axes
    if overlay is None:
        return True             # labels landed; the indicator is cosmetic
    with contextlib.suppress(Exception):
        overlay.visible = True
        overlay.labels = True
    return True


__all__ = [
    "axis_labels_for",
    "label_viewer_axes",
]
