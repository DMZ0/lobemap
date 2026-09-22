"""Ingest meshes stored as vertex/face CSV tables.

Used for the FlyWire reference glomerulus surfaces, which ship as a vertex
table (PointNo, X, Y, Z) plus a face table already labelled per glomerulus
(id, name, v1, v2, v3). Vertex references are 1-based.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.meshfmt import MeshSet
from ..core.meshrepair import RepairReport, repair_meshset

COMPARTMENT_EXTENT_UM = {
    "glomeruli": (4.0, 45.0),
    "neuropil": (25.0, 150.0),
    "brain": (200.0, 1400.0),
}
UNIT_CANDIDATES = [(1e-3, "nm"), (1.0, "um"), (4e-3, "px4nm"), (8e-3, "px8nm")]


@dataclass
class CsvIngestResult:
    meshset: MeshSet
    skipped: list[str]
    scale_to_um: float
    source_units: str
    repair: RepairReport | None = None


def infer_scale(extents: np.ndarray, role: str) -> tuple[float, str]:
    lo, hi = COMPARTMENT_EXTENT_UM[role]
    typical = float(np.median(extents))
    hits = [(s, lab) for s, lab in UNIT_CANDIDATES if lo <= typical * s <= hi]
    detail = ", ".join(f"{lab}->{typical * s:.3g}um" for s, lab in UNIT_CANDIDATES)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(
            f"cannot identify units: median compartment extent {typical:g} is "
            f"not {lo}-{hi} um under any candidate ({detail})"
        )
    raise ValueError(f"ambiguous units: {[h[1] for h in hits]} ({detail})")


def ingest(
    vertices_csv: str | Path,
    faces_csv: str | Path,
    role: str = "glomeruli",
    repair: bool = True,
) -> CsvIngestResult:
    verts = pd.read_csv(vertices_csv)
    faces = pd.read_csv(faces_csv)

    # PointNo is 1-based and need not be contiguous; map it explicitly rather
    # than assuming row order matches the index.
    point_no = verts["PointNo"].to_numpy(dtype=np.int64)
    xyz = verts[["X", "Y", "Z"]].to_numpy(dtype=np.float64)
    lookup = {int(p): i for i, p in enumerate(point_no)}

    raw: list[tuple[str, np.ndarray, np.ndarray]] = []
    skipped: list[str] = []
    for name, group in faces.groupby("name", sort=True):
        tri = group[["v1", "v2", "v3"]].to_numpy(dtype=np.float64)
        if not np.isfinite(tri).all():
            skipped.append(f"{name}: non-finite vertex reference")
            continue
        tri = tri.astype(np.int64)
        try:
            idx = np.vectorize(lookup.__getitem__)(tri)
        except KeyError as exc:
            skipped.append(f"{name}: unknown PointNo {exc}")
            continue
        used, remapped = np.unique(idx, return_inverse=True)
        v = xyz[used]
        f = remapped.reshape(-1, 3)
        if not len(v) or not len(f):
            skipped.append(f"{name}: empty mesh")
            continue
        raw.append((str(name), v, f))

    if not raw:
        raise ValueError(f"no meshes assembled from {faces_csv}")

    extents = np.array(
        [float(np.max(v.max(axis=0) - v.min(axis=0))) for _, v, _ in raw]
    )
    scale, units = infer_scale(extents, role)

    ms = MeshSet.from_parts(
        [(n, v * scale, f) for n, v, f in raw],
        meta={
            "source": "csv-mesh-table",
            "source_file": Path(faces_csv).name,
            "source_units": units,
            "scale_to_um": scale,
            "units": "um",
            "role": role,
            "retrieved": datetime.now(UTC).date().isoformat(),
            "n_skipped": len(skipped),
        },
    )
    report = None
    if repair:
        ms, report = repair_meshset(ms)
    return CsvIngestResult(ms, skipped, scale, units, report)
