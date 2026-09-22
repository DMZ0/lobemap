"""Ingest AL glomerular ROI meshes from neuPrint.

Covers hemibrain and male CNS, which share the `AL-DA1(R)` naming convention.
Verified 2026-09-20 (see docs/probes/): male-cns:v1.0 has 58 glomeruli per side,
complete and symmetric; male-cns:v0.9 has none, so the version must be pinned.
hemibrain:v1.2.1 has 58 right / 19 left, plus one side-less `AL-DC3`.

Units are established by measurement, not assumption -- see `infer_scale`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from ..core.meshfmt import MeshSet
from ..core.meshrepair import RepairReport, repair_meshset

#: A glomerular ROI: "AL-DA1(R)", or side-less "AL-DC3".
GLOM_RE = re.compile(r"^AL-(?P<name>[^()]+?)(?:\((?P<side>[LR])\))?$")

#: Whole-AL ROIs, kept as neuropil reference assets rather than glomeruli.
NEUROPIL_RE = re.compile(r"^AL\((?P<side>[LR])\)$")

#: Plausible size of a SINGLE compartment, per role, in micrometres.
#: Sizing against one compartment rather than the whole set makes the unit
#: check independent of how many lobes or sides a dataset happens to contain --
#: the global extent of "all glomeruli" differs ~2x between a one-sided and a
#: bilateral atlas, but one glomerulus is one glomerulus.
COMPARTMENT_EXTENT_UM = {
    "glomeruli": (4.0, 45.0),
    # The neuropil role now covers every brain neuropil, not just the two
    # antennal lobes, so the ceiling has to admit the optic lobes.
    #
    # The FLOOR must stay well above 11 um, and that is not cosmetic: the
    # check is on the MEDIAN extent, and these ROIs arrive in 8 nm voxels
    # whose median reads 11,242. Dropping the floor to 10 made both readings
    # plausible -- nm gives 11.2 um, px8nm gives 89.9 -- and the ingest
    # refused as ambiguous rather than silently picking one. 25 rejects the
    # nm reading outright.
    "neuropil": (25.0, 400.0),
}

#: Subtrees of the ROI hierarchy that are not brain. The male CNS covers the
#: whole central nervous system, so its primary ROIs include the ventral
#: nerve cord and the cervical connective; the hemibrain has neither and is
#: unaffected.
NON_BRAIN_SUBTREES = ("VNC", "CV")

#: Catch-all ROIs for "in this region but not in any named neuropil". They
#: are primary, so they come back with the rest, but they have no mesh and
#: are not structures -- the male CNS has three.
UNSPECIFIED_SUFFIX = "-unspecified"


@dataclass
class IngestResult:
    meshset: MeshSet
    skipped: list[str]
    scale_to_um: float
    source_units: str
    repair: RepairReport | None = None


#: Source units neuPrint is known to serve meshes in.
UNIT_CANDIDATES = [(1e-3, "nm"), (1.0, "um"), (8e-3, "px8nm")]


def infer_scale(
    compartment_extents: np.ndarray, expect: tuple[float, float]
) -> tuple[float, str]:
    """Identify the source units from typical compartment size.

    neuPrint serves meshes in nm for some datasets and 8 nm voxels for others,
    and guessing wrong yields geometry that is confidently 1000x off. Rather
    than assume, test each candidate against a known anatomical size, using the
    MEDIAN compartment extent so one oddly-shaped ROI cannot swing the answer.

    Raises if no candidate fits, or if more than one does -- an ambiguous
    answer here is worse than no answer.
    """
    lo, hi = expect
    typical = float(np.median(compartment_extents))
    hits = [(s, lab) for s, lab in UNIT_CANDIDATES if lo <= typical * s <= hi]
    if len(hits) == 1:
        return hits[0]
    detail = ", ".join(f"{lab}->{typical * s:.3g}um" for s, lab in UNIT_CANDIDATES)
    if not hits:
        raise ValueError(
            f"cannot identify units: median compartment extent {typical:g} is "
            f"not {lo}-{hi} um under any candidate ({detail}). Check the source."
        )
    raise ValueError(
        f"ambiguous units: median compartment extent {typical:g} fits "
        f"{[h[1] for h in hits]} ({detail}). Narrow the expected range."
    )


def _parse_obj(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Minimal OBJ reader: vertices and triangular faces only."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for raw in data.decode("utf-8", "replace").splitlines():
        if raw.startswith("v "):
            x, y, z = raw.split()[1:4]
            verts.append((float(x), float(y), float(z)))
        elif raw.startswith("f "):
            idx = [int(tok.split("/")[0]) for tok in raw.split()[1:]]
            # OBJ is 1-based; negative indices count back from the end.
            idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
            for k in range(1, len(idx) - 1):  # fan-triangulate
                faces.append((idx[0], idx[k], idx[k + 1]))
    return (
        np.asarray(verts, dtype=np.float64).reshape(-1, 3),
        np.asarray(faces, dtype=np.int64).reshape(-1, 3),
    )


def fetch_rois(server: str, dataset: str, token: str | None = None):
    from neuprint import Client, fetch_all_rois

    client = Client(server, dataset=dataset, token=token)
    return client, sorted(fetch_all_rois(client=client))


def brain_neuropils(client) -> list[str]:
    """Every PRIMARY brain ROI in a dataset, which is its neuropil set.

    "Primary" is neuPrint's own term for the standard non-overlapping
    parcellation: the hemibrain marks 63 and the male CNS 144. The
    alternative, taking every ROI, gives 231 and 5,619 respectively and is
    full of sub-compartments and composites like `CRE(-ROB,-RUB)(R)` that
    overlap each other.

    The male CNS set is then cut to the brain. Its hierarchy divides into
    CentralBrain, Optic(L), Optic(R), VNC and CV, and the last two are not
    brain; the hemibrain has no such branches, so nothing is removed there.
    """
    import json

    from neuprint import fetch_roi_hierarchy

    meta = client.fetch_custom("MATCH (m:Meta) RETURN m.primaryRois AS p")
    raw = meta["p"][0]
    primary = set(json.loads(raw) if isinstance(raw, str) else (raw or []))

    text = fetch_roi_hierarchy(include_subprimary=False, mark_primary=False,
                               format="text", client=client)
    excluded: set[str] = set()
    depth_of_branch = None
    for line in text.splitlines():
        stripped = line.lstrip(" |+-")
        depth = len(line) - len(stripped)
        if depth_of_branch is not None and depth > depth_of_branch:
            excluded.add(stripped.rstrip("*"))
            continue
        depth_of_branch = None
        if stripped.rstrip("*") in NON_BRAIN_SUBTREES:
            depth_of_branch = depth
    return sorted(
        r for r in primary - excluded
        if UNSPECIFIED_SUFFIX not in r
    )


def ingest(
    server: str = "neuprint.janelia.org",
    dataset: str = "hemibrain:v1.2.1",
    token: str | None = None,
    role: str = "glomeruli",
    repair: bool = True,
) -> IngestResult:
    """Fetch AL ROI meshes and return a MeshSet in micrometres."""
    client, rois = fetch_rois(server, dataset, token)

    if role == "glomeruli":
        wanted = [r for r in rois if GLOM_RE.match(r)]
    else:
        # Every brain neuropil, for parity with the FAFB asset, which holds
        # all 78 that FlyWire serves rather than the antennal lobes alone.
        wanted = [r for r in brain_neuropils(client) if r in set(rois)]
    if not wanted:
        raise ValueError(
            f"no {role} ROIs matched in {dataset!r}. For male CNS make sure the "
            "version is v1.0 -- v0.9 has no glomerular subdivisions."
        )

    raw: list[tuple[str, np.ndarray, np.ndarray]] = []
    skipped: list[str] = []
    for roi in wanted:
        try:
            v, f = _parse_obj(client.fetch_roi_mesh(roi))
        except Exception as exc:  # noqa: BLE001 - one bad ROI must not kill the run
            skipped.append(f"{roi}: {type(exc).__name__}: {exc}")
            continue
        if not len(v) or not len(f):
            skipped.append(f"{roi}: empty mesh")
            continue
        raw.append((roi, v, f))

    if not raw:
        raise ValueError(f"every {role} mesh failed for {dataset!r}: {skipped}")

    # Largest dimension of each compartment's own bounding box.
    extents = np.array(
        [float(np.max(v.max(axis=0) - v.min(axis=0))) for _, v, _ in raw]
    )
    expect = COMPARTMENT_EXTENT_UM[role]
    scale, units = infer_scale(extents, expect)

    parts = [(name, v * scale, f) for name, v, f in raw]
    ms = MeshSet.from_parts(
        parts,
        meta={
            "source": "neuprint",
            "server": server,
            "dataset": dataset,
            "role": role,
            "source_units": units,
            "scale_to_um": scale,
            "units": "um",
            "retrieved": datetime.now(UTC).date().isoformat(),
            "n_skipped": len(skipped),
        },
    )
    report = None
    if repair:
        # Repair at ingest, not at use: a shell with holes cannot support the
        # inside/outside test the containment validator depends on.
        ms, report = repair_meshset(ms)
    return IngestResult(ms, skipped, scale, units, report)
