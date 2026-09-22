"""Slice contours: exact mesh-plane intersections drawn as napari Shapes.

Per docs/design.md section 1 this is the only overlay mode in which two atlases
are genuinely readable together. Nested semi-transparent surfaces are
unreadable past two; outlines are not.

Contours are computed exactly, by intersecting the mesh with the current slice
plane, rather than by rasterising. That keeps them crisp at any zoom and avoids
committing the pipeline to a voxel grid.

They also restore identification in 2D: napari's Surface._get_value returns
None in 2D, but Shapes._get_value returns a shape index, so the contour layer
is what makes a sliced glomerulus clickable.
"""

from __future__ import annotations

import warnings

import numpy as np

from ..core.meshfmt import MeshSet


class ContourOverlay:
    """One Shapes layer per atlas, recomputed as the slice slider moves."""

    def __init__(
        self,
        viewer,
        meshset: MeshSet,
        name: str,
        color,
        selection: set[int] | None = None,
        axis: int | None = None,
        width: float = 0.35,
        colors=None,
        fill_opacity: float = 0.85,
    ) -> None:
        self.viewer = viewer
        self.meshset = meshset
        self.name = name
        #: Compartments whose name is drawn on the slice. Empty by default:
        #: with several atlases loaded every glomerulus would be written two
        #: or three times over, so labels are opt-in per glomerulus.
        self.labels: set[int] = set()
        self.color = color
        #: Per-compartment RGBA, taken from the Surface layer so a filled
        #: cross-section is the same colour as its mesh. None falls back to
        #: the single per-atlas `color`.
        self.colors = None if colors is None else np.asarray(colors, float)
        self.fill_opacity = fill_opacity
        self._axis = axis
        self.width = width
        self.selection = set(
            range(meshset.n_compartments) if selection is None else selection
        )
        self._cache: dict[int, object] = {}
        self._shape_index: list[int] = []

        self.layer = viewer.add_shapes(
            data=[],
            name=f"{name} [contours]",
            shape_type="polygon",
            edge_color=color,
            edge_width=width,
            face_color="transparent",
            ndim=3,
            visible=False,
        )
        self.layer.metadata["lobemap"] = {"kind": "contours", "atlas": name}

    # -- geometry --------------------------------------------------------

    @property
    def axis(self) -> int:
        """The axis being sliced: whatever napari's slider is on.

        `viewer.dims.order[0]` is the first non-displayed axis. Reading it
        live means rolling the dims, or displaying x-y instead of y-z, moves
        the contours with the slider instead of silently leaving them cutting
        the wrong plane.
        """
        if self._axis is not None:
            return self._axis
        order = tuple(self.viewer.dims.order)
        return int(order[0]) if order else 0

    def _mesh(self, index: int):
        """Trimesh for one compartment, built once and reused per slice."""
        if index not in self._cache:
            import trimesh

            v, f = self.meshset.compartment(index)
            self._cache[index] = trimesh.Trimesh(
                vertices=v, faces=f, process=False
            )
        return self._cache[index]

    def slice_position(self) -> float:
        """World coordinate of the current slice along the sliced axis."""
        dims = self.viewer.dims
        point = getattr(dims, "point", None)
        if point is not None and len(point) > self.axis:
            return float(point[self.axis])
        # Older napari: derive from the step index and the axis range.
        step = dims.current_step[self.axis]
        lo, _hi, span = dims.range[self.axis]
        return float(lo + step * span)

    def contours_at(self, position: float) -> tuple[list[np.ndarray], list[int]]:
        """Polylines crossing the plane, plus the compartment each came from."""
        origin = np.zeros(3)
        origin[self.axis] = position
        normal = np.zeros(3)
        normal[self.axis] = 1.0

        paths: list[np.ndarray] = []
        owners: list[int] = []
        for index in sorted(self.selection):
            mesh = self._mesh(index)
            lo, hi = mesh.bounds[0][self.axis], mesh.bounds[1][self.axis]
            if not (lo <= position <= hi):
                continue  # cheap reject before the intersection
            try:
                section = mesh.section(plane_origin=origin, plane_normal=normal)
            except Exception:  # noqa: BLE001, S112 - a tangent plane degenerates
                continue
            if section is None:
                continue
            for poly in section.discrete:
                if len(poly) < 2:
                    continue
                pts = np.asarray(poly, dtype=float)
                # Pin exactly to the plane so napari shows it on this slice.
                pts[:, self.axis] = position
                paths.append(pts)
                owners.append(index)
        return paths, owners

    def _rgba(self, index: int):
        if self.colors is None or not (0 <= index < len(self.colors)):
            return None
        return self.colors[index]

    def _face_colors(self, owners):
        """One fill per shape, matching the mesh of the same compartment."""
        out = []
        for index in owners:
            rgba = self._rgba(index)
            if rgba is None:
                out.append(self.color)
            else:
                rgba = np.array(rgba, dtype=float)
                rgba[3] = self.fill_opacity
                out.append(rgba)
        return out

    def _edge_colors(self, owners):
        """A full-opacity outline of the same hue, so touching neighbours
        stay separable where their fills meet."""
        out = []
        for index in owners:
            rgba = self._rgba(index)
            out.append(self.color if rgba is None else np.array(rgba, float))
        return out

    # -- updates ---------------------------------------------------------

    def refresh(self) -> None:
        if not self.layer.visible:
            return
        paths, owners = self.contours_at(self.slice_position())
        self._shape_index = owners
        # Clear, then add with the shape type given explicitly. Assigning
        # `data` and then `shape_type` looks equivalent and is not: the
        # setter re-adds every shape onto a shape list that already holds the
        # previous ones, and once the layer has been displayed in 2D those
        # carry 2D mesh vertices. Stacking them against 3D ones raised
        # "array at index 0 has size 2 and the array at index 1 has size 3"
        # on the second switch back into 2D.
        self.layer.data = []
        if paths:
            # POLYGONS, not paths. A Surface sliced by napari is the set of
            # triangles straddling the plane, so what you see is their
            # projected footprint: wide where the surface runs tangent to the
            # slice, vanishing where it runs perpendicular. That reads as a
            # shell of wandering thickness rather than a cross-section.
            #
            # These loops are the exact mesh-plane intersection and are
            # closed -- 45/45 on a mid-AL slice of Grabe -- so filling them
            # gives the actual cross-section of the solid.
            self.layer.add(
                paths,
                shape_type="polygon",
                edge_color=self._edge_colors(owners),
                edge_width=self.width,
                face_color=self._face_colors(owners),
            )
        # Text after data: napari requires one string per shape, so setting it
        # first would leave the counts disagreeing.
        self._apply_text(owners, paths)

    def _apply_text(self, owners: list[int], paths) -> None:
        strings = self._label_strings(owners, paths) if paths else []
        try:
            self.layer.text = {
                "string": strings,
                "size": 7,
                "color": self.color,
                "anchor": "center",
            }
        except Exception as exc:      # noqa: BLE001 - never worth a crash
            # Reported once rather than swallowed: if napari changes its text
            # API this is the only thing that tells us.
            if not getattr(self, "_text_warned", False):
                self._text_warned = True
                warnings.warn(f"slice labels unavailable: {exc!r}",
                              RuntimeWarning, stacklevel=2)

    def set_selection(self, indices) -> None:
        self.selection = set(indices)
        self.refresh()

    def set_labels(self, indices) -> None:
        """Choose which compartments write their name on the slice."""
        self.labels = set(indices)
        self.refresh()

    def set_label(self, index: int, on: bool) -> None:
        self.labels.add(index) if on else self.labels.discard(index)
        self.refresh()

    def _label_strings(self, owners: list[int], paths) -> list[str]:
        """One string per shape; blank except on each compartment's longest.

        A glomerulus can cross the plane as several separate polylines -- a
        concave one, or a compartment made of disconnected bodies -- and
        writing its name on all of them stacks the same text on itself. The
        longest contour is the one a reader would point at.
        """
        best: dict[int, int] = {}
        for i, (owner, path) in enumerate(zip(owners, paths)):
            if owner not in self.labels:
                continue
            if owner not in best or len(path) > len(paths[best[owner]]):
                best[owner] = i
        chosen = set(best.values())
        return [
            self.meshset.names[owner] if i in chosen else ""
            for i, owner in enumerate(owners)
        ]

    def name_at_shape(self, shape_index: int | None) -> str | None:
        """Map a picked Shapes index back to a compartment name."""
        if shape_index is None or not (0 <= shape_index < len(self._shape_index)):
            return None
        return self.meshset.names[self._shape_index[shape_index]]


def install(viewer, overlays: dict[str, ContourOverlay]) -> list[tuple]:
    """Keep contours in step with the slider.

    Returns (event, handler) pairs. Switching scenes replaces the overlays,
    and a handler left connected would go on refreshing layers belonging to
    a torn-down scene, so the caller needs to be able to disconnect them.

    Visibility is deliberately NOT set here. `viewer.app.install_display_mode`
    owns it, because it also adds and removes the layers and has to mirror each
    contour against its own surface -- two handlers on the same event, each
    with its own idea of what should be visible, is how a layer ends up
    visible in a mode that cannot draw it.
    """

    def _on_display_change(event=None) -> None:
        if viewer.dims.ndisplay == 2:
            for overlay in overlays.values():
                overlay.refresh()

    def _on_step(event=None) -> None:
        if viewer.dims.ndisplay != 2:
            return
        for overlay in overlays.values():
            overlay.refresh()

    pairs = [
        (viewer.dims.events.ndisplay, _on_display_change),
        (viewer.dims.events.current_step, _on_step),
        (viewer.dims.events.order, _on_step),
    ]
    for event, handler in pairs:
        event.connect(handler)
    _on_display_change()
    return pairs
