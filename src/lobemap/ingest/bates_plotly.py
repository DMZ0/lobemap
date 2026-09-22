"""Ingest the Bates et al. 2020 AL atlas from its Plotly HTML.

Data S1 of Bates, Schlegel et al. (2020) Curr Biol 30(16):3183-3199.e6 ships as
a self-contained interactive HTML page: the glomerulus meshes are embedded as
Plotly `mesh3d` traces. Left antennal lobe, FAFB space.

The trace array is located with json.JSONDecoder.raw_decode rather than a
hand-written brace scanner, so string escapes inside the payload cannot
desynchronise the parse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..core.meshfmt import MeshSet
from ..core.meshrepair import RepairReport, repair_meshset

MARKER = "Plotly.newPlot("

RGBA_RE = re.compile(
    r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?\)"
)

#: The atlas HTML carries one non-glomerular trace: a whole-brain `neuropil`
#: mesh (627 um across). It is a valuable FAFB-space reference asset, but it is
#: emphatically not a glomerulus, so roles are separated at ingest.
NON_GLOMERULUS_NAMES = {"neuropil", "brain", "outline"}

#: Plausible size of one compartment per role, in micrometres. Same tripwire as
#: the neuPrint ingest: identify units by measurement, never by assumption.
COMPARTMENT_EXTENT_UM = {
    "glomeruli": (4.0, 45.0),
    "brain": (200.0, 1400.0),
}
UNIT_CANDIDATES = [(1e-3, "nm"), (1.0, "um"), (4e-3, "px4nm"), (8e-3, "px8nm")]


@dataclass
class BatesIngestResult:
    meshset: MeshSet
    skipped: list[str]
    scale_to_um: float
    source_units: str
    repair: RepairReport | None = None


def extract_traces(html: str) -> list[dict]:
    """Return the Plotly trace list embedded in the page."""
    start = html.index(MARKER)
    array_start = html.index("[", start)
    data, _end = json.JSONDecoder().raw_decode(html, array_start)
    if not isinstance(data, list):
        raise TypeError("Plotly payload is not a trace array")
    return data


def parse_color(value) -> tuple[float, float, float, float] | None:
    if not isinstance(value, str):
        return None
    m = RGBA_RE.fullmatch(value.strip())
    if not m:
        return None
    r, g, b, a = m.groups()
    return (
        float(r) / 255.0,
        float(g) / 255.0,
        float(b) / 255.0,
        float(a) if a is not None else 1.0,
    )


def _trace_name(trace: dict, index: int) -> str:
    for key in ("name", "legendgroup", "hovertext", "text"):
        value = trace.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0].strip()
    return f"trace{index}"


def infer_scale(extents: np.ndarray, role: str = "glomeruli") -> tuple[float, str]:
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
    path: str | Path, role: str = "glomeruli", repair: bool = True
) -> BatesIngestResult:
    path = Path(path)
    traces = extract_traces(path.read_text(encoding="utf-8", errors="replace"))

    raw: list[tuple[str, np.ndarray, np.ndarray]] = []
    colors: dict[str, tuple[float, float, float, float]] = {}
    skipped: list[str] = []
    for idx, tr in enumerate(traces):
        if tr.get("type") != "mesh3d":
            continue
        name = _trace_name(tr, idx)
        is_glom = name.lower() not in NON_GLOMERULUS_NAMES
        if is_glom != (role == "glomeruli"):
            continue
        try:
            # Keep the published axis order: navis expects template-native XYZ,
            # and reordering here would silently rotate the atlas.
            v = np.column_stack(
                [
                    np.asarray(tr["x"], dtype=np.float64),
                    np.asarray(tr["y"], dtype=np.float64),
                    np.asarray(tr["z"], dtype=np.float64),
                ]
            )
            f = np.column_stack(
                [
                    np.asarray(tr["i"], dtype=np.int64),
                    np.asarray(tr["j"], dtype=np.int64),
                    np.asarray(tr["k"], dtype=np.int64),
                ]
            )
        except (KeyError, ValueError) as exc:
            skipped.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if not len(v) or not len(f):
            skipped.append(f"{name}: empty mesh")
            continue
        col = parse_color(tr.get("color"))
        if col:
            colors[name] = col
        raw.append((name, v, f))

    if not raw:
        raise ValueError(f"no mesh3d traces for role {role!r} in {path}")

    extents = np.array(
        [float(np.max(v.max(axis=0) - v.min(axis=0))) for _, v, _ in raw]
    )
    scale, units = infer_scale(extents, role)

    ms = MeshSet.from_parts(
        [(n, v * scale, f) for n, v, f in raw],
        meta={
            "source": "bates2020-plotly",
            "source_file": path.name,
            "source_units": units,
            "scale_to_um": scale,
            "units": "um",
            "role": role,
            "retrieved": datetime.now(UTC).date().isoformat(),
            "colors": {k: list(v) for k, v in colors.items()},
            "n_skipped": len(skipped),
        },
    )
    report = None
    if repair:
        ms, report = repair_meshset(ms)
    return BatesIngestResult(ms, skipped, scale, units, report)
