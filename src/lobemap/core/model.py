"""Core data model. See docs/design.md section 2.

Reference geometry is not a separate class -- it is an Asset with a different
`role`. That is what keeps this small.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

Units = Literal["nm", "um", "px"]

Role = Literal[
    "glomeruli",
    "neuropil",
    "brain",
    "template_image",
    "virtual_stain",
    "map_2d",
]

Kind = Literal["meshset", "mesh", "image", "labels"]

Side = Literal["L", "R"]

#: How a space's image laterality relates to the animal's.
#:
#: "biological": image left is the fly's right, the normal frontal-view
#: convention. Hemibrain, male CNS and the JRC2018 templates.
#:
#: "mirrored": the image data is left-right inverted, so image left is the
#: fly's LEFT. FAFB and FlyWire. Verified by measurement: FlyWire's AL_L --
#: whose annotation is the modern, post-correction one -- bridges onto
#: hemibrain AL(R) at 4.6 um versus 94.3 um to AL(L). The bridging
#: registrations therefore preserve APPARENT side, not biological side.
LateralConvention = Literal["biological", "mirrored"]

#: Signed axis references, as used by `Space.anterior` and `Space.dorsal`:
#: "-z" means the negative z direction points anterior.
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def axis_vector(spec: str):
    """Turn a signed axis reference like "-z" into a unit vector."""
    import numpy as np

    text = spec.strip().lower()
    sign = -1.0 if text.startswith("-") else 1.0
    letter = text.lstrip("+-")
    if letter not in _AXIS_INDEX:
        raise ValueError(f"not an axis reference: {spec!r}")
    out = np.zeros(3)
    out[_AXIS_INDEX[letter]] = sign
    return out


def anatomical_axes(space):
    """Pole name -> unit vector, for a space that declares its axes.

    Returns A/P, D/V and R/L, or None when the space declares no axes -- the
    same rule the camera follows, since a frame built from one axis alone
    would put lateral in an arbitrary place.

    R always points at the BIOLOGICAL right hemisphere. For a biological
    space that is `cross(anterior, dorsal)`, measured against the declared
    sides of every atlas carrying both: dot +0.98 (hemibrain), +0.99 (male
    CNS), +0.99 (Grabe).

    **A mirrored space negates it**, and getting this wrong is silent. FAFB's
    image data is left-right inverted, so apparent and biological sides come
    apart there, and the two kinds of label in that space disagree about
    which they use:

    - FlyWire's neuropil annotations are the modern, post-correction ones and
      are BIOLOGICAL: `AL_L` really is the left lobe.
    - Bates's and Benton's glomerulus sides are APPARENT, which is why they
      declare side R while sitting inside `AL_L`.

    `cross(anterior, dorsal)` runs from `AL_R` toward `AL_L` in FAFB, so
    unnegated it would point at the biological LEFT -- the arrow would be
    exactly reversed in the one space where nobody could check it against a
    second lobe, because FAFB's atlases cover only one.
    """
    import numpy as np

    if not (space.anterior and space.dorsal):
        return None
    anterior = axis_vector(space.anterior)
    dorsal = axis_vector(space.dorsal)
    right = np.cross(anterior, dorsal)
    if space.is_mirrored:
        right = -right
    return {
        "A": anterior, "P": -anterior,
        "D": dorsal, "V": -dorsal,
        "R": right, "L": -right,
    }


#: The three axes, as (positive pole, negative pole, label).
AXIS_POLES = (("A", "P", "A-P"), ("D", "V", "D-V"), ("R", "L", "L-R"))


def flip_side(side):
    """Swap L and R. Anything else -- None, "both" -- passes through."""
    if side == "L":
        return "R"
    if side == "R":
        return "L"
    return side

#: How a compartment corresponds to a canonical name.
#: How an atlas's compartment relates to the canonical vocabulary, which is
#: Benton 2025's published names. Read from the atlas's point of view:
#:
#:   exact    one compartment, one canonical name, same name
#:   renamed  one compartment, one canonical name, different name
#:            (Bates VC3l is canonical VC3 -- Schlegel et al. 2021)
#:   split    several compartments share ONE canonical name, because this
#:            atlas resolves a structure the vocabulary does not
#:            (Schlegel S11's VM6l, VM6m, VM6v are all canonical VM6)
#:   merge    ONE compartment carries several canonical names, because this
#:            atlas does not resolve a structure the vocabulary does
#:            (Grabe's VP1 covers canonical VP1d, VP1l and VP1m)
#:   absent   no correspondence
Relation = Literal["exact", "split", "merge", "renamed", "absent"]

#: Conversion into the internal working unit (micrometres).
TO_UM: Mapping[str, float] = {"nm": 1e-3, "um": 1.0}


@dataclass(frozen=True)
class Space:
    """A coordinate frame, with units.

    `flybrains_template` is None for an island -- a space with no bridging
    registrations to anything else (Grabe).
    """

    id: str
    title: str
    units: Units
    flybrains_template: str | None = None
    lateral_convention: LateralConvention = "biological"
    #: Which signed array axis points anterior, and which dorsal, as "-z" /
    #: "+y". These differ BETWEEN spaces -- hemibrain's antero-posterior axis
    #: is y where FAFB's and the male CNS's is z -- so they are declared per
    #: space rather than assumed. Both are needed to orient a camera; with
    #: only one the roll would be a guess, so the viewer leaves the camera
    #: alone instead.
    anterior: str | None = None
    dorsal: str | None = None
    #: Which of this space's atlases is shown when it opens. The others
    #: are loaded and listed, just switched off: a space holds every atlas
    #: native to it, and two glomerular parcellations drawn on top of each
    #: other are unreadable. Optional when the space has only one.
    primary_atlas: str | None = None
    notes: str = ""

    @property
    def is_island(self) -> bool:
        return self.flybrains_template is None

    @property
    def is_mirrored(self) -> bool:
        """True if image laterality is inverted relative to the animal."""
        return self.lateral_convention == "mirrored"

    def apparent_side(self, biological: Side | None) -> Side | None:
        """Which side of the IMAGE a biologically-`biological` structure sits on."""
        return flip_side(biological) if self.is_mirrored else biological

    def biological_side(self, apparent: Side | None) -> Side | None:
        """Which side of the ANIMAL an image-`apparent` structure belongs to."""
        return flip_side(apparent) if self.is_mirrored else apparent


@dataclass(frozen=True)
class Derivation:
    """How a computed asset was produced.

    Without this, a stale cache is undetectable after a dependency upgrade.
    `params` carries the resolved transform path for bridged assets -- not a
    hand-specified one, since navis chooses the route.
    """

    recipe: str
    inputs: tuple[str, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    tool_versions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Provenance:
    doi: str | None = None
    url: str | None = None
    retrieved: date | None = None
    license: str | None = None
    checksum: str | None = None
    derivation: Derivation | None = None


@dataclass(frozen=True)
class Asset:
    """Any geometry or image, atlas or reference alike."""

    id: str
    role: Role
    space: str
    kind: Kind
    path: Path
    side: Side | Literal["both"] | None = None
    #: Display colormap. None takes the role's default; see
    #: `lobemap.viewer.app.default_colormap`.
    colormap: str | None = None
    #: Any other napari image-layer keywords, overriding the role's defaults.
    #: Grabe's confocal channel is a `template_image` -- it is real microscopy,
    #: not a synthesised stain, and relabelling its role to get the look would
    #: be a lie about provenance -- but it should still be displayed like the
    #: stains, so it carries the override rather than the wrong role.
    display: Mapping[str, Any] = field(default_factory=dict)
    source: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True)
class Compartment:
    """One glomerulus within one atlas.

    `published_name` is immutable and authoritative; `canonical` may hold zero,
    one or several names, because correspondence is not one-to-one -- Grabe's
    single VP1 carries three canonical names. See `Relation`.
    """

    local_id: int
    published_name: str
    side: Side | None = None
    canonical: tuple[str, ...] = ()
    relation: Relation = "exact"
    color: tuple[float, float, float, float] | None = None

    @property
    def label(self) -> str:
        return self.published_name


@dataclass(frozen=True)
class Atlas:
    id: str
    title: str
    native_space: str
    asset: str
    citation: str = ""
    doi: str = ""
    parent: str | None = None
    compartments: tuple[Compartment, ...] = ()

    def by_name(self, name: str) -> Compartment | None:
        for c in self.compartments:
            if c.published_name == name:
                return c
        return None


# `Scene` and `LayerSpec` used to live here: a named set of layers, each
# with its own `visible`, `mirror` and `style`. They were removed because a
# scene was never a different view of the data. `build_scene` takes a SPACE
# and loads every atlas native to it; the scene was applied afterwards and
# set nothing but `.visible`, so two scenes on one space held identical
# layers and differed only in which boxes started ticked. `mirror` and
# `style` were never used by any scene in the registry.
#
# What remains of the idea is `Space.primary_atlas` plus visibility keyed on
# an asset's ROLE, which reproduced every scene the registry had except
# `hemibrain_three_ways` -- two clicks in the compartment panel.
