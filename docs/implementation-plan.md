# lobemap — implementation plan

Companion to [design.md](design.md), which holds the architecture and the data model.
This file holds the build order, the acceptance criteria, and the decisions still open.

Guiding principle: **get one atlas end-to-end into napari before building the second
ingest.** The temptation with a catalogue of eight atlases is to write eight parsers
first. That defers every integration risk to the end, which is exactly backwards.

---

## Where the work runs

Everything in M0–M7 runs on a workstation. Mesh work is small: a glomerulus is a few
thousand vertices and an atlas ~60 of them, so bridging a whole atlas is a few hundred
thousand point transforms — seconds. Rasterizing for comparison metrics over an
AL-sized box is likewise trivial.

**Nothing here requires the HPC cluster.** Checked against this workstation — 32 GB
RAM, i5-12600K (10 cores / 16 threads), 3.3 TB free on `D:` — every job fits, including
the whole-brain stain. The H-series jobs are long-running *local* batch jobs, measured
in hours and dominated by synapse download rather than by arithmetic. The cluster stays
an escape hatch for one case only (see H1), not a dependency.

| job | cost | runs on |
| --- | --- | --- |
| Bridging atlas meshes | ~10⁵ points | local, seconds |
| Dice / Hausdorff per glomerulus | AL-sized grids | local, seconds |
| Marching cubes on the Grabe LM stack | one modest volume | local |
| Virtual stain, AL-bounded *(smoke test)* | ~4×10⁶ voxels ≈ 16 MB | local, instant |
| **Virtual stain, whole brain** | ≤ ~10 GB peak once cropped; see below | local, hours |
| Template warped into an EM space | chunked resample of ~2.6×10⁸ voxels | local, hours |

**The virtual stain covers the whole brain.** Not the antennal lobe region — the whole
brain, and for the male CNS the brain *excluding the ventral nerve cord*. Grid sizes,
from flybrains template bounding boxes at 0.5 µm (the resolution of the JRC2018
templates the method targets):

| space | extent (µm) | grid @ 0.5 µm | voxels | uint16 |
| --- | --- | --- | --- | --- |
| FAFB14 / FLYWIRE | 661 × 323 × 269 | 1323 × 646 × 539 | 4.6×10⁸ | 0.9 GB |
| JRCFIB2018F (hemibrain, partial brain) | 275 × 316 × 331 | 551 × 633 × 663 | 2.3×10⁸ | 0.5 GB |
| JRCFIB2022M (**whole CNS**, uncropped) | 753 × 627 × 1077 | 1506 × 1254 × 2154 | 4.1×10⁹ | 8.1 GB |

**Cropping the male CNS to brain is the single largest lever**: most of that 1077 µm
long axis is nerve cord, so excluding it takes ~8.1 GB down to roughly 2–3 GB. The
hierarchy gives a clean definition — `male-cns:v1.0` splits at the top into
`CentralBrain`, `Optic(L)`, `Optic(R)`, `VNC` and `CV`, so **brain = CentralBrain ∪
Optic(L) ∪ Optic(R)**, excluding `VNC` and the `CV` cervical connective. Filter
synapses by ROI membership rather than by a geometric box, then crop the grid to the
union bounding box of those ROIs.

**Memory, against 32 GB:** accumulate in float32 and write uint16. FAFB needs 1.8 GB
for the grid and roughly 4 GB peak through a separable blur; hemibrain about half that;
the male CNS *cropped to brain* around 5 GB, ~10 GB peak. All comfortable. Only the
**uncropped** male CNS is a problem — 4.1×10⁹ voxels is 16 GB in float32 and ~32 GB
peak, which is exactly the machine's total. That single case is the one reason to keep
the cluster in view, and cropping to brain removes it.

Arithmetic is not the bottleneck. A separable Gaussian at σ ≈ 900 nm on a 0.5 µm grid
has a radius of only a few voxels; three passes over 4.6×10⁸ elements is minutes.
Accumulation is a `bincount` over flattened voxel indices, streamed in synapse batches.
**The wall-clock cost is downloading 10⁸-odd synapses**, which no amount of cluster
allocation speeds up.

**Rule: long-running jobs are leaves.** Nothing in M0–M7 may block on one. That is
achievable because the M3 containment validator needs reference *meshes* — cheap and
instant — not reference *images*. The contract runs one way: an H-series job is a batch
script that writes a canonical asset plus its `Derivation` record, and the registry
consumes it like any other file. This also keeps the cluster option open at no cost: a
job that already runs headless from a script is portable by construction.

---

## M0 — De-risk the transform chain — **mostly done**

Bundles downloaded and the graph re-measured; results are in design §3. Summary:
10.3 GB, ~10 min, 112 registrations, and **every bridge the catalogue needs resolves**.
`FAFB14 → JRCFIB2018F` is pure Python (Affine/Alias/H5/H5/Affine).

Three findings that change downstream work, all now recorded in the design:

1. **FAFB14 is the FAFB-family hub**, not FLYWIRE — the FlyWire route to hemibrain
   drags in CMTK while the FAFB14 route does not. Affects M4 ingest targets.
2. **`resolve()` takes navis's route by default.** The registry weights warps at 1.0
   and affines/aliases at 0–0.1, so the shortest weighted path minimises *warps* and is
   therefore an accuracy heuristic. Override only where the binary-free alternative
   ties on warp count — which, measured, is the case for hemibrain↔maleCNS but not for
   FlyWire→hemibrain. Choosing FAFB14 as the ingest hub makes the latter moot.
   Affects M3.
3. **Mirroring never fails loudly**, including in hemibrain where the fallback
   reflection is not a midline mirror. Affects M3's harness.

**Still outstanding — the actual accuracy spike.** Take hemibrain `AL-DA1(R)` mesh
vertices → FAFB14 → back and measure displacement; then check the one-way result lands
inside Bates' `DA1`. This needs the M2 ingest to have produced a real mesh, so it runs
at the start of M3 rather than here.

**Acceptance (deferred to M3):** `AL-DA1(R)` round-trips with median vertex displacement
well under one glomerulus diameter (~10 µm), and the one-way transform overlaps Bates'
`DA1` rather than merely landing near it.

---

## M1 — Core model and registry

No real data yet. Small, fast, heavily tested.

```
src/lobemap/core/
  model.py       # the dataclasses from design.md §2
  registry.py    # TOML -> objects, with validation
  spaces.py      # adapter over flybrains: template lookup, bridge existence, mirror support
  meshfmt.py     # canonical mesh container: read/write
  names.py       # nomenclature + correspondence relations
registry/
  spaces.toml
  assets.toml
  atlases/*.toml
  nomenclature.csv
```

**Canonical mesh container** — one `.npz` per atlas, plus a sidecar CSV:

| array | dtype | meaning |
| --- | --- | --- |
| `vertices` | float32 (N,3) | **always µm**, in the atlas's native space |
| `faces` | int32 (M,3) | triangles, indices into `vertices` |
| `compartment_offsets` | int32 (K+1,) | slice bounds into both arrays per compartment |
| `meta` | JSON blob | space id, units-at-source, content hash, tool versions |

Chosen over glTF/PLY because it needs no dependency, memory-maps cleanly, and keeps one
atlas in one file. Per-compartment slicing is what the viewer's rebuild loop (M5) needs
on every selection change, so it must be O(1).

**Validation the registry must enforce**, since each corresponds to a bug that is
invisible at runtime:

- every `Asset.space` and `Atlas.native_space` names a known `Space`
- `Space.flybrains_template` is either `None` or actually registered in flybrains
- no `Compartment.canonical` entry is missing from `nomenclature.csv`
- `published_name` is unique within an atlas
- a `split`/`merge` relation has a matching entry on the other side

**Acceptance:** registry loads, all validators have a failing-case test, and
`spaces.py` correctly reports Grabe as an island and the male CNS as bridged.

---

## M2 — Walking skeleton: one atlas, one space, in napari

Deliberately the *easiest* ingest first — neuPrint serves hemibrain ROI meshes as OBJ
over an API, with no file-format archaeology.

```
src/lobemap/ingest/neuprint_rois.py
src/lobemap/viewer/{app.py,scene.py,layers.py}
```

1. Ingest `hemibrain:v1.2.1` AL glomeruli → canonical `.npz`. Handle the `AL-DC3` ROI
   that carries no side suffix; do not let it crash the parser or get silently dropped.
2. Minimal scene loader: one `Space`, one `Atlas`, no bridging, no mirroring.
3. One napari `Surface` layer for the atlas, `vertex_values` = compartment index, with a
   step-interpolated categorical colormap.
4. Crudest possible selection UI — a checkbox list. The real table is M5.

**Acceptance:** `lobemap --space hemibrain` opens napari showing right-side hemibrain
glomeruli in anatomically correct relative positions, and toggling a compartment rebuilds
the surface in under ~100 ms.

**Watch:** surface rebuild cost. If concatenating ~60 compartments per toggle is
visibly slow, switch to a persistent buffer with a visibility mask before going further,
not after five more ingests depend on the current shape.

---

## M3 — `resolve()`, caching, and the validation harness — **done**

The correctness core. Everything here is invisible when it works and produces
confident, wrong pictures when it doesn't.

```
src/lobemap/core/resolve.py
src/lobemap/validate/geometry.py
```

1. `resolve(asset_id, target_space, mirror=False)`. **Mirror is applied before
   bridging** — design §3, because hemibrain has no mirror registration.
2. Cache under `platformdirs.user_cache_dir("lobemap")`, keyed on source content
   hash + transform chain + navis/flybrains/lobemap versions. A version bump must
   miss the cache; add a test that asserts it.
3. Bring Bates (FAFB) into hemibrain space and display it alongside M2's hemibrain
   atlas. This is the first moment the space-centric design does something the
   atlas-centric one could not.

**The validation harness matters more than it looks.** A transform bug does not raise;
it draws a plausible antennal lobe in the wrong place. Automated checks:

- **Containment:** every bridged glomerulus centroid falls inside the target space's AL
  neuropil mesh.
- **Scale sanity:** whole-AL bounding box is ~60–80 µm across. Catches nm/µm errors,
  which are the most likely failure per design §3.
- **Correspondence:** for each `exact`-related pair across two atlases in one space,
  centroid separation is below a threshold. Flag outliers as either a bridging problem
  or a genuine disagreement — that distinction is a research finding, not a bug, and
  the harness should report rather than assert on it.
- **Round-trip:** A→B→A displacement stays below tolerance.

**Acceptance: met**, using male CNS rather than Bates as the bridged atlas, because
both neuPrint atlases were already ingested and Bates is an M4 parser. Measured:

- `JRCFIB2018F -> FAFB14 -> JRCFIB2018F` round-trip: median **0.07 um**, p95 0.11 um.
- Male CNS bridged into hemibrain space in 4.2 s, 0 non-finite vertices.
- 75 shared glomeruli, centroid separation median **7.4 um**, p90 11.6, max 18.0 (DM5).
  A glomerulus is ~25 um across, so this is ~0.3 diameters -- a mix of registration
  error and genuine inter-animal variation, reported rather than asserted on.
- Containment: hemibrain 77/77 inside their AL. Male CNS 115/116, the exception being
  `AL-VA1v(L)`, 9.7 um outside.

Two findings recorded in code:

- **The male CNS AL neuropil shells are not watertight** (~7k vertices vs hemibrain's
  ~27k), so point-in-mesh containment against them is not authoritative. The check now
  reports watertightness and downgrades to advisory rather than asserting against a
  shell with holes.
- **CMTK is not installed here**, so the default hemibrain<->maleCNS route fails.
  `choose_path` now detects binary availability and substitutes the binary-free route,
  which for this pair *ties on warp count* as measured -- so the substitution is free.
  Where it would not tie (FlyWire->hemibrain, +2 warps) the result is marked
  `degraded` and the layer name says so.

---

## M4 — Remaining ingests and nomenclature — **done**

Now that one path is proven end to end, parallelize the parsers. Rough effort:

| ingest | source format | size |
| --- | --- | --- |
| `male_cns` | neuPrint API (reuses M2) | S — pin `male-cns:v1.0` |
| `bates_plotly` | Plotly HTML, `mesh3d` traces | M — port lobemap's extractor |
| `benton_slicer` | 3D Slicer `.vtm`/`.vtp` + `.ctbl` | M — pyvista |
| `schlegel_supp` | eLife suppl. 11 and 12 | M — format unknown until opened |
| `flywire_ref` | FlyWire reference surfaces | S — fafbseg |
| `grabe_amira` | Amira `.am` labels + `.tif` | L — label volume, not meshes |

Grabe is last and hardest: it is a **label volume**, so it needs marching cubes to enter
the mesh-native pipeline, and it is an island with its own LM stack as its only
reference. Do not let its peculiarities shape the core.

**Nomenclature is re-derived, not ported.** lobemap's tables predate the male CNS and
Schlegel atlases and have no coverage for them — its `present_*` columns span only
Grabe, hemibrain, FlyWire, DoOR, Potter, Benton and Bates — so porting them would build
the catalogue's join key on a foundation that is incomplete for a third of the atlases.

Instead: enumerate `published_name` from each atlas's own compartment list, derive the
canonical set from that union, then **cross-check against lobemap's
`glomerulus_ground_truth.csv` and `glomerulus_name_reconciliation.csv` and require full
consistency**. Every disagreement gets resolved and recorded, not silently overwritten
— a name present in lobemap but in no atlas, or vice versa, is a finding about the
catalogue. The cross-check runs as a test, so later atlas additions cannot drift from
the curated tables. Benton's split is the first real exercise of the many-to-many
correspondence.

**Acceptance: met.** Eight atlases load and pass the validators (13/13 checks):
bates2020, benton2025, flywire_ref, grabe2015, neuprint_hemibrain, neuprint_cns,
schlegel2021_s11, schlegel2021_s12. 64 canonical names derived from their own
published names.

Findings worth carrying forward:

- **The deferred §9 question is answered: S11, S12 and the neuPrint hemibrain meshes
  are three distinct mesh sets**, not duplicates. S11 is built from receptor-neuron
  terminals and S12 from projection-neuron dendrites. Median centroid separation is
  1.10 um between S11 and S12, 1.76 and 2.36 um against neuPrint -- far below the
  6-8 um seen between animals, so they are three boundary definitions of one dataset.
  All three are kept.
- **S11 is the only atlas that realises the VM6 three-way split** into VM6l/VM6m/VM6v.
  Before it was ingested, those three names appeared in lobemap's curated table and in
  no atlas; after, the cross-check's reference-only list is empty.
- **The only remaining cross-check disagreement is VC3l/VC3m**, which exist solely in
  Bates -- the older names superseded by the VC3l/VC3m/VC5 -> VC3/VC5/VM6 rename chain
  that Benton and the FlyWire surfaces both carry.
- **FlyWire's reference surfaces are not an independent segmentation**: 0.50 um median
  from Bates, and the same rename chain.
- Benton reuses the Bates geometry almost verbatim (median 0.0 um); its revision is
  nomenclature, not boundaries.

---

## M5 — Viewer UX — **done**

```
src/lobemap/viewer/{panel.py,contours.py,presets.py}
```

1. **Compartment table** in the right dock: a view bound to the selected atlas layer,
   joined to the nomenclature table. Per-compartment visibility, filter by name or
   receptor, select-all/none. This is the bulk-selection interface, complementing
   click-to-identify rather than substituting for it.
2. **Click-to-identify works and should be wired up.** napari's `Surface._get_value_3d`
   does ray–triangle intersection and returns the barycentric-interpolated
   `vertex_values` plus the triangle index. Because compartments are disjoint meshes,
   all three vertices of any triangle share one compartment index, so the interpolated
   value is *exactly* that index — hovering or clicking identifies the glomerulus with
   no ambiguity. Wire it to the status bar and to table-row selection.
   The one gap is 2D: `Surface._get_value` returns `None`, so slice mode gets no
   picking from the surface itself. The `Shapes` contours below cover that case, since
   `Shapes._get_value` does return a shape index.
3. **Slice contours.** Mesh–plane intersection (`trimesh.Trimesh.section`) → napari
   `Shapes`, one colour per atlas. Per design §1, this is the only overlay mode in which
   two atlases are genuinely readable together, so it is not optional polish.
4. **Cross-atlas selection.** Visibility is per-compartment *across* atlases — the model
   must not assume one active atlas.
5. **Mirrored layers are marked** in the layer name and the table, since they are an
   approximation.
6. **Scene presets**, including one per atlas. These reproduce the atlas-centric design
   as a special case, which was the argument for the space-centric one.

**Acceptance: met**, in hemibrain space rather than FAFB, because three atlases are
native there (neuPrint, Schlegel S11, Schlegel S12) and the comparison needs no bridge.
Contours render one colour per atlas at a shared slice, so the three boundary
definitions of the same glomerulus are directly comparable.

Notes from building it:

- Contours are exact mesh-plane intersections via `trimesh.section`, not rasterised, so
  they stay crisp at any zoom and the pipeline never commits to a voxel grid. Each
  compartment's `Trimesh` is cached, and a bounding-box reject skips meshes the plane
  misses, which keeps a slider drag responsive.
- Contours are visible only in 2D and surfaces only carry 3D, switched on `ndisplay` --
  showing both at once double-draws every outline.
- The contour layer is also what restores **2D identification**: `Surface._get_value`
  returns `None` in 2D, but `Shapes._get_value` returns a shape index, which maps back
  to a compartment through the per-path owner list.
- Scene presets live in `registry/scenes.toml`. The five per-atlas presets are exactly
  the viewers an atlas-centric design would have shipped, which was the original
  argument for the space-centric one.

---

## M6 — Reference assets (all local)

1. **Neuropil and whole-brain meshes** per space: `fafbseg` or neuPrint `flywire-fafb`
   (`AL_L`/`AL_R`) for FAFB; neuPrint `AL(L)`/`AL(R)` for hemibrain and male CNS.
   These are needed earlier than M6 by the M3 containment check — build them there and
   formalize them here. Cheap, and the only reference assets anything else depends on.
2. **AL-bounded virtual stain — as a smoke test, not the deliverable.** Same recipe as
   H1 (design §5) restricted to `AL(L)`/`AL(R)`: synapses per ROI, 3D histogram at
   0.5 µm, Gaussian blur σ ≈ 900 nm. Its purpose is to validate the recipe, the
   `Derivation` record and the viewer's image-layer path cheaply, so that H1 is a
   parameter change rather than new code. The real whole-brain stain is H1.
3. JRC2018U nc82 as a `template_image` asset **in its own space only** — no warping.

**Acceptance:** the stain recipe runs end to end at AL scale in each EM space, a
glomerulus overlaid on it lines up with a visible neuropil boundary, and the same entry
point is ready to run unbounded on the cluster.

---

## M7 — Comparison tooling and distribution

1. ~~**Metrics** (`compare/metrics.py`): per-glomerulus Dice, IoU, Hausdorff.~~
   **Dropped.** This was never part of the design specification — it was added to
   this plan unprompted and removed once that was noticed. lobemap is for
   viewing and comparing atlases visually, not for scoring them.
2. Settle the deferred §9 question — whether Schlegel S11/S12 and the neuPrint hemibrain
   meshes are distinct. Consolidate registry entries if any pair collapses.
3. **Distribution.** Ship canonical meshes (small) in the wheel; fetch bridged caches
   and any warped templates (large) on demand with checksums. End users must never need
   CMTK, a neuPrint token, or network access to open a scene.

---

## H-series — long-running local jobs, deferred

Not scheduled against M0–M7, but **H1 is a real deliverable, not a contingency.** It
runs once the M6 smoke test proves the recipe. Both run locally, overnight; see
*Where the work runs* for why the cluster is not needed.

**H1 — whole-brain virtual stain.** Design §5, unbounded, per EM space. Grid sizes are
tabulated under *Where the work runs*.

- **Coverage is the whole brain.** For the male CNS that means the brain *excluding*
  the ventral nerve cord: filter synapses to `CentralBrain ∪ Optic(L) ∪ Optic(R)`,
  excluding `VNC` and the `CV` cervical connective, then crop the grid to the union
  bounding box of those ROIs. This is the difference between 8.1 GB and ~2–3 GB.
- Filter by **ROI membership**, not by a geometric box — neuPrint synapses carry ROI
  labels, and a box around the brain would still admit nerve-cord synapses.
- Accumulate as a chunked histogram: flatten voxel indices and reduce with `bincount`
  over synapse batches; never materialise the full float32 grid.
- Blur separably, axis by axis, over chunks.
- Output **multiscale OME-Zarr**, uint16. A 0.9 GB single-scale array is not something
  napari should be asked to open eagerly; the pyramid is what makes it viewable.
- Emit a `Derivation` (σ, voxel size, synapse source + version, ROI filter) and a
  checksum manifest.
- **Escalate to the cluster only for an uncropped male CNS grid**, the one case that
  does not fit in 32 GB. Cropping to brain is the intended path and avoids it.

**H2 — warped image templates.** Resample JRC2018U nc82 into each EM space through the
H5 deformation field (design §4). Still deferred: H1's native stain is cheaper and more
faithful, so H2 exists only if a genuine LM channel is needed for comparison against LM
data.

**Handoff requirements**, all of which should be verified before any cluster time is
requested:

- the flybrains transform bundles must be present on the cluster (M0 records the size)
- synapse source access from cluster nodes — token handling there is *not* the
  local-machine arrangement and must be worked out separately
- outputs land in the canonical asset format with a `Derivation` record and a checksum
  manifest, so the registry can consume them unchanged
- a scaled-down smoke run (one ROI) executes locally first, so the cluster job is a
  parameter change rather than new code

---

## Testing

- Unit tests run **offline**. Network tests marked and skipped by default; CI runs them
  only where credentials exist.
- Fixtures are small: two or three compartments, not whole atlases.
- Golden-value tests on transformed centroids, so a navis upgrade that silently changes
  results fails loudly.
- Every registry validator gets a failing case, not just a passing one.

## Open decisions

- ~~Ship or fetch bridged caches?~~ **Settled: fetch.** The transform bundles alone are
  10.3 GB (M0), and H1 outputs are 0.5-3 GB per space.
- **Nomenclature source of truth** — port lobemap's CSVs as-is, or re-derive from the
  atlases and treat the CSVs as one input? Affects how splits are represented.
- **Label-layer mode.** Rasterized `Labels` layers give click-to-identify, which
  `Surface` layers lack. Worth offering as an optional per-space rendering mode, or does
  the table make it unnecessary?
- **Repo licence** — still unset.

## Sequencing

M0 gates everything. M1→M2→M3 is a strict chain. M4's ingests parallelize once M3
lands. M5 needs M4 only for its second atlas. M6 and M7 are independent of each other,
and both are local. The H-series hangs off M6 and gates nothing.
