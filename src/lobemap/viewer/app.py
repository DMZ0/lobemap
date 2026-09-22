"""Scene assembly and the napari application entry point."""

from __future__ import annotations

import contextlib

import numpy as np

from ..core.registry import Registry
from .axes import label_viewer_axes
from .contours import ContourOverlay
from .contours import install as install_contours
from .layers import AtlasSurface, canonical_colors, match_label_colors

#: Distinct flat colours for contour overlays, one per atlas, so two atlases
#: superimposed in slice view are told apart by colour rather than by shape.
ATLAS_CONTOUR_COLORS = [
    "#ff7f0e", "#1f77b4", "#2ca02c", "#d62728",
    "#9467bd", "#17becf", "#e377c2", "#bcbd22",
]

#: Reference geometry -- neuropil shells, whole brains -- gets a contour too,
#: muted and thin. Without one it has no representation in 2D at all: its
#: Surface is pulled from the layer list there, so an AL outline that was
#: perfectly visible in 3D simply vanished.
REFERENCE_CONTOUR_COLOR = "#9aa0a6"
REFERENCE_CONTOUR_WIDTH = 0.2


def _tag(meshset) -> str:
    """Mark bridged, degraded and mirrored layers in their name."""
    params = meshset.meta.get("derivation", {}).get("params", {})
    if not params:
        return ""
    bits = ["bridged"]
    if params.get("degraded"):
        bits.append("DEGRADED")
    if params.get("mirror"):
        bits.append("mirrored")
    return " [" + ", ".join(bits) + "]"


class MissingAssets(RuntimeError):
    """Nothing in this space is built yet, said usefully.

    This used to be a bare RuntimeError telling the reader to run
    `lobemap ingest ...`, with the ellipsis literal. `ingest` has subcommands
    for two pipelines only, so for most assets that was not a command anyone
    could run, and it arrived at the end of a twenty-line traceback. The
    first thing a new user saw was a crash whose advice did not work.
    """

    def __init__(self, space: str, registry) -> None:
        self.space = space
        self.assets = [
            a for a in registry.assets_in_space(space) if not a.path.exists()
        ]
        super().__init__(self._message(registry))

    def _message(self, registry) -> str:
        from ..build import load_recipes

        recipes = load_recipes(registry.root)
        lines = [
            (f"No data for space {self.space!r}: {len(self.assets)} of its "
             f"assets are not built yet."),
            "",
        ]
        for asset in self.assets:
            how = ("lobemap build " + asset.id) if asset.id in recipes                 else "lobemap stain  (see registry/data/README.md)"
            lines.append(f"  {asset.id:32s} {how}")
        have_recipe = [a.id for a in self.assets if a.id in recipes]
        lines += ["", "Build everything that has a recipe:", "",
                  "  lobemap build --all"]
        if len(have_recipe) < len(self.assets):
            lines += [
                "",
                "The virtual stains are not in that set: they need ~19 GB of",
                "synapse downloads, ~40 GB of scratch and hours of compute.",
            ]
        lines += ["", "Or fetch prebuilt data once a base_url is published:",
                  "", "  lobemap fetch"]
        return chr(10).join(lines)


def build_scene(
    viewer,
    registry: Registry,
    space: str,
    bridged: bool = False,
    align_biology: bool = False,
) -> tuple[dict[str, AtlasSurface], dict[str, ContourOverlay]]:
    """Add every atlas native to `space`, plus that space's reference meshes.

    With `bridged=True`, also bring in atlases whose native space is different
    -- the thing an atlas-centric design structurally cannot do.
    """
    if space not in registry.spaces:
        raise KeyError(f"unknown space {space!r}; known: {sorted(registry.spaces)}")

    surfaces: dict[str, AtlasSurface] = {}

    # Reference geometry first, so it sits underneath and starts hidden.
    for asset in registry.assets_in_space(space):
        if asset.role not in ("neuropil", "brain"):
            continue
        try:
            meshset = registry.mesh(asset.id)
        except (FileNotFoundError, KeyError):
            continue
        # Additive, not translucent: a translucent shell writes depth and so
        # hides the very glomeruli it is meant to give context to.
        surface = AtlasSurface(
            viewer, meshset, name=asset.id, opacity=0.35, blending="additive"
        )
        surface.layer.visible = False
        surface.layer.shading = "none"
        surfaces[asset.id] = surface

    _add_images(viewer, registry, space)

    for atlas in registry.atlases_in_space(space):
        try:
            meshset = registry.mesh(atlas.asset)
        except (FileNotFoundError, KeyError):
            continue
        surfaces[atlas.id] = AtlasSurface(
            viewer, meshset, name=atlas.title or atlas.id,
            colors=canonical_colors(atlas.compartments, registry.names.canonical),
        )

    if bridged:
        surfaces.update(
            _add_bridged(viewer, registry, space, align_biology=align_biology)
        )

    if not surfaces:
        raise MissingAssets(space, registry)

    # After the atlases, because the colours are read out of their Surface
    # layers rather than recomputed.
    for layer in viewer.layers:
        if layer.metadata.get("lobemap", {}).get("kind") == "labels":
            match_label_colors(layer, list(surfaces.values()))

    contours = _add_contours(viewer, registry, surfaces)

    # Anatomical names for the dimension sliders and napari's own axis
    # overlay. No layer of our own: see `viewer/axes.py`.
    label_viewer_axes(viewer, registry.spaces[space])

    return surfaces, contours


#: Per-role display defaults for image layers.
#:
#: Magenta for the stain because it reads as a fluorescence channel against
#: the grey template and the coloured surfaces, and because additive blending
#: composites it cleanly over them.
#:
#: `gamma` below 1 lifts the dim end, which a synapse-density map needs: the
#: distribution is long-tailed, so a linear ramp leaves most of the neuropil
#: near black while a few bright spots hold the top of the range.
#:
#: `attenuation` only does anything under `attenuated_mip`, where it fades
#: contributions by depth. Plain MIP through a whole brain is a flat wash of
#: whichever voxel happens to be brightest along each ray; attenuation
#: restores the sense of depth that makes the structure legible.
ROLE_DISPLAY = {
    "template_image": {"colormap": "gray"},
    "virtual_stain": {
        "colormap": "magenta",
        "gamma": 0.7,
        "rendering": "attenuated_mip",
        "attenuation": 0.1,
    },
}
DEFAULT_DISPLAY = {"colormap": "magma"}

#: Applied to every image layer unless a role overrides it.
BASE_DISPLAY = {
    "colormap": "magma",
    "blending": "additive",
    "rendering": "attenuated_mip",
}


def display_for(role: str, colormap: str | None = None,
                overrides=None) -> dict:
    """napari keyword arguments for an image layer of this role."""
    out = dict(BASE_DISPLAY)
    out.update(ROLE_DISPLAY.get(role, DEFAULT_DISPLAY))
    out.update(dict(overrides or {}))
    if colormap:
        out["colormap"] = colormap
    return out


ROLE_COLORMAP = {role: spec["colormap"] for role, spec in ROLE_DISPLAY.items()}
DEFAULT_COLORMAP = DEFAULT_DISPLAY["colormap"]

#: In 3D napari renders ONE multiscale level and, left to itself, picks the
#: coarsest -- 83x41x34 for the FAFB stain, which is unreadable. These bound
#: the level it is pinned to instead. 700 M voxels is just above the ~537 M of
#: a 2048x2048x128 confocal stack, which renders comfortably; 2048 is the 3D
#: texture limit a GPU is allowed to impose, and level 0 exceeds it at 2818.
VIEW3D_MAX_VOXELS = 700_000_000
VIEW3D_MAX_AXIS = 2048

#: Slice x-y and step through z, the way a confocal stack is read. Volume axes
#: are (x, y, z) to match the mesh columns, and napari would otherwise display
#: the last two -- y-z -- and put the slider on x.
#:
#: **2D only.** In 3D napari applies `dims.order` to an Image but NOT to a
#: Surface: `surface/_slice.py` returns `self.data[0]` unpermuted as soon as
#: nothing is non-displayed, while `_scalar_field/_slice.py` always does
#: `np.transpose(data, order)`. A non-identity order in 3D therefore transposes
#: the stain out from under the meshes, with no warning -- it just looks like a
#: registration failure. So 3D keeps the identity order, where the two agree.
DIMS_ORDER_XYZ = (2, 1, 0)


#: A face-on view is exactly axis-aligned, which is a gimbal-lock singularity
#: for the Euler angles napari stores its camera in. Its vispy round trip --
#: angles to quaternion and back -- cannot recover the third angle there and
#: zeroes it, which comes back as a NEGATED up vector: the brain renders
#: upside down. Turning the camera a fraction of a degree off axis makes the
#: decomposition unique and the roll survives. One degree across a 700 um
#: brain is about 12 um of depth difference edge to edge, invisible, and it
#: is a yaw about the dorsal axis so it reads as "very slightly turned"
#: rather than tilted. `tests/test_default_view.py` pins the napari behaviour
#: so this can be dropped if it is ever fixed upstream.
GIMBAL_NUDGE_DEG = 1.0


def orient_anterior(viewer, space, nudge_deg: float = GIMBAL_NUDGE_DEG) -> bool:
    """Face the anterior surface of the brain, dorsal up. True if applied.

    Needs BOTH axes. A view direction alone leaves the roll free, so a camera
    built from `anterior` without `dorsal` would face the right way at an
    arbitrary tilt -- worse than an obvious default, because it looks
    deliberate. Spaces declaring only one are left alone.
    """
    import numpy as np

    from ..core.model import axis_vector

    if viewer.dims.ndisplay != 3 or not (space.anterior and space.dorsal):
        return False
    anterior = axis_vector(space.anterior)
    dorsal = axis_vector(space.dorsal)

    # Yaw the camera slightly about the dorsal axis, off the singularity.
    view = -anterior
    if nudge_deg:
        # right-handed camera basis (right, up, -view): right = view x up.
        right = np.cross(view, dorsal)
        theta = np.radians(nudge_deg)
        view = view * np.cos(theta) + right * np.sin(theta)
        view /= np.linalg.norm(view)

    # napari 0.9 moved the camera; keep working on either.
    camera = getattr(viewer, "scene", viewer).camera
    camera.set_view_direction(
        view_direction=tuple(view), up_direction=tuple(dorsal)
    )
    # Up is what the round trip destroys, so that is what is checked.
    return bool(np.dot(np.asarray(camera.up_direction), dorsal) > 0.99)


def maximize(viewer) -> bool:
    """Open filling the screen. True if the request was made.

    napari exposes no public API for this, so it goes through the Qt window,
    and it is allowed to fail: headless runs and the tests have no window
    manager, and a viewer that cannot be maximised is still a usable viewer.

    Two quirks, both of which produce a window that *reports* itself
    maximised at 933x700:

    - Called before the event loop turns, `showMaximized` sets the window
      state without the window manager ever resizing anything. So it is also
      deferred with a zero-delay timer.
    - Once that state is set, a second `showMaximized` is a no-op, because Qt
      believes the window is already maximised. `showNormal` first clears the
      state so the next call actually takes effect.
    """
    window = getattr(getattr(viewer, "window", None), "_qt_window", None)
    if window is None:
        return False

    def _apply():
        window.showNormal()
        window.showMaximized()

    try:
        _apply()
        from qtpy.QtCore import QTimer

        QTimer.singleShot(0, _apply)
    except Exception:            # noqa: BLE001 - cosmetic, never fatal
        return False
    return True


def fit_view(viewer, margin: float = 0.02) -> None:
    """Fill the canvas with the data, without disturbing the orientation.

    `reset_view` resets the camera angles by default, which would undo
    `orient_anterior`.
    """
    try:
        viewer.reset_view(margin=margin, reset_camera_angle=False)
    except TypeError:                     # older napari: neither keyword
        viewer.reset_view()


def install_initial_fit(viewer, margin: float = 0.02) -> bool:
    """Keep refitting until the window settles, then stop at the first touch.

    Maximising is asynchronous, and the canvas can still report a zero width
    while the layout resolves, so *when* the usable size appears varies from
    run to run. A single fit, or a one-shot on the first resize, therefore
    lands on the right size only sometimes: measured across two spaces, Grabe
    refitted correctly and FAFB never refitted at all, keeping the zoom it
    had at 900x700.

    Refitting on every resize until the user does something removes the
    timing from the question. After the first click, scroll or keypress the
    view is theirs and this stops touching it.
    """
    canvas = getattr(getattr(viewer.window, "_qt_viewer", None), "canvas", None)
    events = getattr(canvas, "events", None)
    if events is None:
        fit_view(viewer, margin)
        return False

    state = {"touched": False, "size": None}

    def _size():
        # napari's OWN canvas size, not the Qt widget's. `fit_to_view` divides
        # by `viewer.canvas.size`, and that model value is updated after the
        # resize callbacks run -- so the widget can already read 987x944 while
        # a fit still computes against 900x700. Watching the widget is how
        # FAFB kept its startup zoom while Grabe happened to refit correctly.
        got = getattr(getattr(viewer, "canvas", None), "size", None)
        return tuple(got) if got is not None else None

    def _refit(event=None):
        # Driven by draws, not only by resize: the resize arrives while
        # napari's own canvas size is still stale, so a fit done there is
        # computed against the old size and no second resize comes to correct
        # it -- which is how FAFB kept the zoom it had at 900x700. Refitting
        # whenever the size CHANGES converges on the settled size and costs
        # nothing once it stops moving.
        if state["touched"]:
            return
        now = _size()
        if now is None or min(now) <= 0 or now == state["size"]:
            return
        state["size"] = now
        fit_view(viewer, margin)

    def _release(event=None):
        state["touched"] = True

    fit_view(viewer, margin)
    connected = False
    for name in ("resize", "draw"):
        with contextlib.suppress(Exception):
            getattr(events, name).connect(_refit)
            connected = True
    for name in ("mouse_press", "mouse_wheel", "key_press"):
        with contextlib.suppress(Exception):
            getattr(events, name).connect(_release)
    return connected


def level_for_3d(levels, max_voxels=VIEW3D_MAX_VOXELS, max_axis=VIEW3D_MAX_AXIS):
    """Finest pyramid level that will render as a single 3D texture."""
    import numpy as np

    for i, arr in enumerate(levels):
        shape = tuple(arr.shape)
        if np.prod(shape, dtype=np.int64) <= max_voxels and max(shape) <= max_axis:
            return i
    return len(levels) - 1


def default_colormap(role: str) -> str:
    return ROLE_COLORMAP.get(role, DEFAULT_COLORMAP)


def _add_images(viewer, registry: Registry, space: str) -> list:
    """Reference images: the LM template, and the virtual synapse stain.

    scale and translate come from the Volume itself, so the image sits in the
    same micrometre world as the meshes. Getting either wrong yields a
    plausible picture that is simply in the wrong place, which is why the
    stain has its own alignment validator.
    """
    layers = []
    for asset in registry.assets_in_space(space):
        if asset.kind not in ("image", "labels") or not asset.path.exists():
            continue
        volume = registry.volume(asset.id)

        if asset.kind == "labels":
            # A segmentation, not an intensity image: napari colours it by id
            # and picks values rather than interpolating them, so none of the
            # colormap/gamma/rendering defaults apply.
            layer = viewer.add_labels(
                np.asarray(volume.data),
                name=asset.id,
                visible=False,
                opacity=0.6,
                **volume.napari_kwargs(),
            )
            layer.metadata["lobemap"] = {
                "kind": "labels",
                "role": asset.role,
                # Written at ingest: voxel value -> the name the matching
                # mesh carries, which is what lets the two be coloured alike.
                "label_names": {
                    int(k): v
                    for k, v in (volume.meta.get("label_names") or {}).items()
                },
            }
            layers.append(layer)
            continue

        data = volume.napari_data()
        layer = viewer.add_image(
            data,
            multiscale=volume.is_multiscale,
            name=asset.id,
            visible=False,
            **display_for(asset.role, asset.colormap, asset.display),
            **volume.napari_kwargs(),
        )
        layer.metadata["lobemap"] = {
            "kind": "image",
            "role": asset.role,
            "level_3d": level_for_3d(data) if volume.is_multiscale else 0,
        }
        layers.append(layer)
    return layers


def install_display_mode(viewer, surfaces, contours, images=()) -> list[tuple]:
    """Show only what the current `ndisplay` can actually use.

    Returns (event, handler) pairs, so a scene switch can disconnect them;
    see `contours.install`.

    Three things switch together on 2D/3D:

    - **Meshes in 3D, contours in 2D.** Both are removed from the layer list
      rather than merely hidden, so the list holds only what is usable. The
      layer objects are kept, so contrast, colour and selection survive the
      round trip.
    - **Images pin a pyramid level in 3D.** napari's automatic choice there is
      the coarsest level; `level_for_3d` picks the finest one that fits in a
      texture. In 2D the lock is released so zoom-driven selection works.
    - **`dims.order` is permuted only in 2D**, to put the slider on z. In 3D
      it must stay the identity, because napari permutes an Image by it and a
      Surface not at all (see `DIMS_ORDER_XYZ`).
    """
    surf_layers = [s.layer for s in surfaces.values()]
    cont_layers = [c.layer for c in contours.values()]

    # Each contour mirrors its own surface, so 2D shows what 3D was showing
    # instead of a fixed set. Keyed by name, which both dicts share.
    paired = {
        contours[name].layer: surfaces[name].layer
        for name in contours
        if name in surfaces
    }
    was_visible: dict[int, bool] = {}

    def _apply(event=None) -> None:
        three_d = viewer.dims.ndisplay == 3
        ndim = viewer.dims.ndim
        # Identity in 3D, or the stain transposes away from the meshes.
        want_order = (
            tuple(range(ndim)) if three_d or ndim != 3 else DIMS_ORDER_XYZ
        )
        if tuple(viewer.dims.order) != want_order:
            viewer.dims.order = want_order
        for layer in images:
            info = layer.metadata.get("lobemap", {})
            if "level_3d" not in info:
                continue            # labels carry no pyramid to pin
            layer.locked_data_level = info["level_3d"] if three_d else None
        show = surf_layers if three_d else cont_layers
        hide = cont_layers if three_d else surf_layers
        for layer in hide:
            if layer in viewer.layers:
                was_visible[id(layer)] = layer.visible
                viewer.layers.remove(layer)
        for layer in show:
            if layer not in viewer.layers:
                viewer.layers.append(layer)
            # Outside the append guard on purpose. `_add_contours` has already
            # put the contour layers in the viewer, so on the first call they
            # need no adding -- and skipping the assignment left every one of
            # them hidden, which made slice contours silently never draw.
            twin = paired.get(layer)
            if twin is not None:
                # Inherit from the surface this contour stands in for, falling
                # back to what the contour itself last had.
                layer.visible = was_visible.get(
                    id(twin), was_visible.get(id(layer), twin.visible)
                )
            else:
                layer.visible = was_visible.get(id(layer), layer.visible)
        if not three_d:
            for overlay in contours.values():
                overlay.refresh()

    viewer.dims.events.ndisplay.connect(_apply)
    _apply()
    return [(viewer.dims.events.ndisplay, _apply)]


def _add_bridged(
    viewer, registry: Registry, space: str, align_biology: bool = False
) -> dict[str, AtlasSurface]:
    """Bring atlases from other spaces into this one, marked as bridged."""
    from ..core.resolve import resolve

    out: dict[str, AtlasSurface] = {}
    if registry.spaces[space].is_island:
        return out
    for atlas in registry.atlases.values():
        if atlas.native_space == space:
            continue
        source = registry.spaces.get(atlas.native_space)
        if source is None or source.is_island:
            continue
        try:
            meshset = resolve(
                registry, atlas.asset, space, align_biology=align_biology
            )
        except Exception as exc:  # noqa: BLE001 - a missing bridge is not fatal
            print(f"  skipping {atlas.id}: {type(exc).__name__}: {exc}")
            continue
        out[atlas.id] = AtlasSurface(
            viewer,
            meshset,
            name=f"{atlas.title or atlas.id}{_tag(meshset)}",
            opacity=0.6,
            # A bridged atlas is the case canonical colour exists for: the
            # point of bringing it in is to compare it against the native one.
            colors=canonical_colors(atlas.compartments, registry.names.canonical),
        )
    return out


def _add_contours(viewer, registry, surfaces) -> dict[str, ContourOverlay]:
    """One contour overlay per surface, including the reference geometry."""
    overlays: dict[str, ContourOverlay] = {}
    palette = iter(ATLAS_CONTOUR_COLORS * 4)
    for name, surface in surfaces.items():
        reference = name in registry.assets
        overlays[name] = ContourOverlay(
            viewer,
            surface.meshset,
            name=surface.name,
            color=REFERENCE_CONTOUR_COLOR if reference else next(palette),
            width=REFERENCE_CONTOUR_WIDTH if reference else 0.35,
            selection=set(surface.selection),
        )
    # The overlays carry their own event handlers, so a scene switch can
    # disconnect them without build_scene having to hand them back.
    handlers = install_contours(viewer, overlays)
    for overlay in overlays.values():
        overlay.handlers = handlers
    return overlays


def install_picking(viewer, surfaces, contours, panel=None) -> None:
    """Identify the glomerulus under the cursor, in 3D and in 2D.

    Surface._get_value_3d does ray-triangle intersection and returns the
    barycentric-interpolated vertex value; because compartments are disjoint
    meshes every triangle's vertices share one index, so that value IS the
    compartment index. In 2D Surface._get_value returns None, so the contour
    Shapes layer covers that case.
    """
    by_layer = {s.layer: (name, s) for name, s in surfaces.items()}
    contour_by_layer = {c.layer: (name, c) for name, c in contours.items()}

    def _on_move(layer, event):
        value = layer.get_value(
            event.position,
            view_direction=getattr(event, "view_direction", None),
            dims_displayed=getattr(event, "dims_displayed", None),
            world=True,
        )
        if isinstance(value, tuple):
            value = value[0]
        if value is None:
            return

        if layer in by_layer:
            name, surface = by_layer[layer]
            label = surface.name_at_value(value)
            index = round(float(value)) if label else None
        elif layer in contour_by_layer:
            name, overlay = contour_by_layer[layer]
            label = overlay.name_at_shape(int(value))
            index = (
                overlay.meshset.names.index(label) if label else None
            )
        else:
            return

        if label:
            viewer.status = f"{name}: {label}"
            if panel is not None and index is not None:
                panel.highlight(name, index)

    for surface in surfaces.values():
        surface.layer.mouse_move_callbacks.append(_on_move)
    for overlay in contours.values():
        overlay.layer.mouse_move_callbacks.append(_on_move)


def apply_scene(registry: Registry, scene_id: str, surfaces, contours,
                images=()) -> None:
    """Apply a named preset: which layers are visible, and which compartments.

    Image layers are included now. They are created hidden -- several are
    whole-brain volumes -- so a scene that means to show the stain has to say
    so, and previously had no way to.
    """
    scene = registry.scenes[scene_id]
    wanted = {layer.ref: layer for layer in scene.layers}
    for layer in images:
        spec = wanted.get(layer.name)
        if spec is not None:
            layer.visible = bool(spec.visible)
    for name, surface in surfaces.items():
        spec = wanted.get(name)
        surface.layer.visible = bool(spec and spec.visible)
        only = (spec.style or {}).get("compartments") if spec else None
        if only:
            keep = {
                i for i, n in enumerate(surface.meshset.names)
                if any(tok.lower() in n.lower() for tok in only)
            }
            surface.set_selection(keep)
            if name in contours:
                contours[name].set_selection(keep)
        if name in contours:
            contours[name].layer.visible = bool(spec and spec.visible)


class SceneSession:
    """One loaded space, and everything needed to unload it again.

    Switching space inside a live viewer is not just `layers.clear()`. The
    display-mode and contour hooks are bound to `viewer.dims.events`, which
    outlives any scene: left connected, they keep firing against surfaces
    whose layers have been removed, so the second scene ends up driven partly
    by the first. The compartment panel is a dock widget and has to be taken
    out of the window rather than dropped on the floor.

    So a session records exactly what it created, and `teardown` undoes it in
    reverse. Rebuilding in place is what makes the switch cheap: the process,
    the Qt window and the GPU context all survive, and only the data is
    swapped.
    """

    def __init__(self, viewer, registry, space, scene=None):
        self.viewer = viewer
        self.registry = registry
        self.space = space
        self.scene = scene
        self.surfaces: dict = {}
        self.contours: dict = {}
        self.images: list = []
        self.panel = None
        self.dock = None
        self.handlers: list[tuple] = []

    def teardown(self) -> None:
        for event, handler in self.handlers:
            with contextlib.suppress(Exception):
                event.disconnect(handler)
        self.handlers = []
        for overlay in self.contours.values():
            for event, handler in getattr(overlay, "handlers", ()) or ():
                with contextlib.suppress(Exception):
                    event.disconnect(handler)
        if self.dock is not None:
            with contextlib.suppress(Exception):
                self.viewer.window.remove_dock_widget(self.dock)
        self.dock = self.panel = None
        # Contour and mesh layers may be out of the viewer entirely -- the
        # display mode removes whichever mode cannot draw them -- so clearing
        # the layer list is what drops them either way.
        with contextlib.suppress(Exception):
            self.viewer.layers.clear()
        self.surfaces, self.contours, self.images = {}, {}, []


def load_space(
    viewer,
    registry: Registry,
    space: str,
    scene: str | None = None,
    bridged: bool = False,
    align_biology: bool = False,
    show: tuple[str, ...] = (),
    fit: bool = True,
) -> SceneSession:
    """Build a scene into a viewer that may already hold one.

    The ordering here is load-bearing and is the same as the original
    `run`: the scene preset is applied AFTER the display mode, because that
    hook adds and removes layers and restores remembered visibility, so
    running it first lets it overwrite what the preset just set.
    """
    session = SceneSession(viewer, registry, space, scene)
    surfaces, contours = build_scene(
        viewer, registry, space, bridged=bridged, align_biology=align_biology
    )
    session.surfaces, session.contours = surfaces, contours

    from .panel import CompartmentPanel

    panel = CompartmentPanel(viewer, surfaces, registry=registry,
                             contours=contours)
    session.panel = panel
    session.dock = viewer.window.add_dock_widget(
        panel, area="right", name="Compartments"
    )
    install_picking(viewer, surfaces, contours, panel=panel)

    session.images = [
        layer for layer in viewer.layers
        if layer.metadata.get("lobemap", {}).get("kind") in ("image", "labels")
    ]
    session.handlers = install_display_mode(
        viewer, surfaces, contours, session.images
    ) or []

    if scene is None:
        scene = registry.spaces[space].default_scene
    session.scene = scene
    if scene:
        apply_scene(registry, scene, surfaces, contours, session.images)
    if show:
        _show_layers(viewer, show)

    orient_anterior(viewer, registry.spaces[space])
    if fit:
        install_initial_fit(viewer)
    return session


def run(
    registry_root,
    space: str | None = None,
    ndisplay: int = 3,
    bridged: bool = False,
    align_biology: bool = False,
    scene: str | None = None,
    show: tuple[str, ...] = (),
) -> None:
    import napari

    registry = Registry.load(registry_root)
    if scene:
        if scene not in registry.scenes:
            raise KeyError(
                f"unknown scene {scene!r}; known: {sorted(registry.scenes)}"
            )
        space = registry.scenes[scene].space
    if space is None:
        raise ValueError("need a space or a scene")

    viewer = napari.Viewer(title=f"lobemap - {scene or space}", ndisplay=ndisplay)

    def _load(target: str, use_scene: str | None = None):
        session = load_space(
            viewer, registry, target,
            scene=use_scene,
            bridged=bridged,
            align_biology=align_biology,
            show=show,
        )
        viewer.title = f"lobemap - {session.scene or session.space}"
        return session

    # The first scene may be named on the command line; later ones come from
    # whatever the switcher picks, so they take their space's own default.
    session = _load(space, scene)

    from .switcher import SpaceSwitcher

    switcher = SpaceSwitcher(viewer, registry, session, _load)
    # Added ONCE and never torn down, unlike the compartment panel: it is the
    # control that does the switching, so it cannot be owned by the scene it
    # replaces.
    viewer.window.add_dock_widget(switcher, area="left", name="Scene")

    maximize(viewer)
    # Maximising is asynchronous, so the fit follows the canvas rather than
    # running once and hoping. `load_space` already installed one; this is
    # after the dock widgets, which change the canvas size.
    install_initial_fit(viewer)
    napari.run()


def _show_layers(viewer, wanted) -> None:
    """Turn on layers named on the command line, by id or by role.

    Image layers start hidden because several of them are whole-brain volumes;
    asking for one by name is the way to see it without waiting for all of
    them.
    """
    names = {layer.name for layer in viewer.layers}
    for want in wanted:
        hits = [
            layer for layer in viewer.layers
            if layer.name == want
            or layer.metadata.get("lobemap", {}).get("role") == want
        ]
        if not hits:
            raise KeyError(
                f"nothing called {want!r} in this scene; layers: {sorted(names)}"
            )
        for layer in hits:
            layer.visible = True


__all__ = [
    "BASE_DISPLAY",
    "GIMBAL_NUDGE_DEG",
    "ROLE_DISPLAY",
    "MissingAssets",
    "SceneSession",
    "apply_scene",
    "build_scene",
    "display_for",
    "fit_view",
    "install_display_mode",
    "install_initial_fit",
    "install_picking",
    "level_for_3d",
    "load_space",
    "maximize",
    "orient_anterior",
    "run",
]
