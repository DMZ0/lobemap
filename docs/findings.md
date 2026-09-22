# lobemap — measured findings

Empirical results established while building this, with the numbers that back
them. Anything here was measured on this machine unless marked otherwise.
Companion to [design.md](design.md) (architecture) and
[implementation-plan.md](implementation-plan.md) (build order and status).

---

## 1. Laterality: FAFB image space is mirrored

**FAFB and FlyWire image data is left-right inverted, and the bridging
registrations do not correct it.** Three independent measurements:

1. **Hemibrain's own labels are biologically correct.** The asymmetric body is
   known to be larger on the fly's right; in hemibrain `AB(R)` is 1431 µm³
   against `AB(L)`'s 390 µm³ — 3.7×.
2. **FlyWire's `AL_L`** — the modern post-correction annotation, so
   biologically left — **bridges onto hemibrain `AL(R)`** at 4.6 µm versus
   94.3 µm to `AL(L)`; `AL_R` lands on `AL(L)`.
3. **All 58 Bates centroids fall inside the fafbseg `AL_L` shell**, none
   inside `AL_R`.

So a bridge preserves **apparent** side, not biological side.

**Consequence: Bates 2020 is the fly's LEFT antennal lobe.** The paper
describes it as the right AL, but predates the discovery that FAFB is
inverted; the authors have confirmed this. Benton inherits it. Schlegel
S11/S12 are unaffected — they ship in hemibrain coordinates, which are not
inverted.

Modelled as `Space.lateral_convention` ∈ {biological, mirrored};
`Asset.side` records the **biological** side; `Space.apparent_side()`
converts; `resolve(..., align_biology=True)` inserts a mirror when the two
spaces disagree.

| | pairs | median separation |
| --- | --- | --- |
| Bates → hemibrain, apparent (default) | 58 vs hemibrain-R | 6.3 µm |
| Bates → hemibrain, `align_biology=True` | 19 vs hemibrain-L | 9.6 µm |

Both are legitimate; the first compares a left AL against a right one, which
is fine for morphology but must be *stated*.

---

## 2. Transforms

After `download_jrc_transforms()` + `download_jefferislab_transforms()`:
**10.3 GB on disk, ~10 min, 112 registrations** (49 before). Every bridge the
catalogue needs then resolves.

| bridge | resolved chain | external binary? |
| --- | --- | --- |
| FAFB14 → JRCFIB2018F | Affine, Alias, H5, H5, Affine | **no** |
| FAFB14 → JRC2018U | Affine, Alias, H5, H5 | no |
| JRCFIB2018F → JRC2018U | Affine, H5, H5 | no |
| JRCFIB2022M → JRC2018U | Affine, H5, H5 | no |
| FLYWIRE → JRCFIB2018F | Affine, **CMTK**, H5, Affine | yes |
| JRCFIB2018F → JRCFIB2022M | Affine, H5, **CMTK**, Affine, TPS | yes |

- **Trust navis's routing.** The registry weights warps at 1.0 and
  affines/aliases at 0–0.1, so the shortest weighted path minimises *warps* —
  an accuracy heuristic, not merely shortest-path. Overriding it to dodge a
  binary can make results worse.
- **FAFB14, not FLYWIRE, is the FAFB-family hub**: the FAFB14 route to
  hemibrain is pure Python, the FlyWire route drags in CMTK.
- Avoiding CMTK **ties on warp count** for hemibrain↔maleCNS (3 warps either
  way) and is **strictly worse** for FlyWire→hemibrain (2 → 4 warps).
- Round-trip `JRCFIB2018F → FAFB14 → JRCFIB2018F`: **median 0.07 µm**, p95
  0.11 µm. So cross-atlas disagreement is not bridging noise.
- **The male CNS template is `JRCFIB2022M`** — nm, 8 nm voxels, dims
  94088 × 78317 × 134576. Grabe is the only island.

### CMTK on Windows does not work, and cannot be made to

Installed CMTK 3.3.1 (NITRC) at `C:\Users\clark\tools\CMTK-3.3.1`, added to
User PATH, plus an **extensionless copy of `streamxform`** because navis globs
for the name without `.exe` and would otherwise never find it. navis then
reports CMTK 3.3.1 and the binaries run.

But **no CMTK tool in this Windows build can open a `.list` directory
archive** — `describe.exe` reports "File does not exist" for every one, even
uncompressed, even at a trivial path. Pointing at the inner `registration.gz`
gets further ("Did not find 'registration' section in affine xform archive"),
which proves gzip and TypedStream parsing both work: it is specifically
directory archives. Conversion by CMTK is circular, since `xform2dfield` would
have to read the `.list` first. A fix needs WSL (not installed here) or a
hand-written B-spline FFD reader. **Not worth it** — the two CMTK routes in
the catalogue are either a tie or avoidable via the FAFB14 hub.

### Mirroring never fails loudly

`navis.mirror_brain()` **succeeds on every template tested**, falling back to
a bounding-box reflection where no registration exists. For a half-brain like
hemibrain that is not a midline mirror — it returns plausible, confident,
wrong geometry. Hence `resolve()` applies **mirror before bridge**.

### Importing fafbseg changes the transform graph

It registers the dedicated FlyWire↔FAFB offset field, so navis routes
`FLYWIRE → FLYWIREraw → FAFB14raw → FAFB14` rather than the thin-plate route a
process without fafbseg picks. That field covers only the imaged volume and
returns **NaN outside it** (10 of 1184 neuropil shell vertices), which
destroys a mesh. Those points now keep their input coordinates, with the count
recorded; defensible only because the skipped correction is sub-micron.

---

## 3. The catalogue

Seven atlases, five spaces. **64 canonical names.**

| atlas | space | compartments | notes |
| --- | --- | --- | --- |
| bates2020 | FAFB14 | 58 | biologically **left**; Plotly HTML, nm |
| benton2025 | FAFB14 | 58 | 3D Slicer RAS; reuses Bates geometry |
| grabe2015 | GRABE (island) | 108 | 54 L + 54 R, surfaced from voxel masks |
| neuprint_hemibrain | JRCFIB2018F | 77 | 58 R + 19 L |
| neuprint_cns | JRCFIB2022M | 116 | 58/side, complete and symmetric |
| schlegel2021_s11 | JRCFIB2018F | 59 | RN-based |
| schlegel2021_s12 | JRCFIB2018F | 58 | PN-based |

### Male CNS has glomerular ROIs — in v1.0 only

`male-cns:v1.0` carries **58 glomerular ROIs per side**, complete and
symmetric (unlike hemibrain's 58 R / 19 L), under hemibrain's `AL-DA1(L)`
naming, and `fetch_roi_mesh()` returns real geometry. **`male-cns:v0.9` has
none** — pin v1.0. The same token works on `neuprint.janelia.org` and
`neuprint-cns.janelia.org`, but they carry *different* hemibrain point
releases (v1.2.1 vs v1.2.2), so the server is part of an asset's identity.

### Schlegel S11, S12 and neuPrint are three distinct mesh sets

S11 is built from **receptor-neuron terminals**, S12 from **projection-neuron
dendrites**. Median centroid separations: **S11↔S12 1.10 µm**, vs neuPrint
**1.76** and **2.36 µm** — far below the 6–8 µm seen between animals. Three
boundary definitions of one dataset, not duplicates. All three kept.

**S11 is the only atlas realising the VM6 three-way split** into
VM6l/VM6m/VM6v. Before it was ingested those names appeared in lobemap's
curated table and in no atlas; afterwards the cross-check's reference-only
list is empty.

### The VC3/VC5/VM6 rename chain is Schlegel's, not Benton's

58 geometric matches against Bates at **median 0.0 µm**. The actual change is
a rename chain, so a name-based join pairs the wrong structures:

| Bates | Benton | separation |
| --- | --- | --- |
| `VC3l` | `VC3` | 0.07 µm |
| `VC3m` | `VC5` | 0.09 µm |
| `VC5` | `VM6` | 0.23 µm |

Hence the `reconcile` command, which pairs by geometry and compares names
after. It needs an **ambiguity test**: without one it invented 10 renames
between hemibrain and male CNS, which share one nomenclature — neighbouring
glomeruli are ~10 µm apart while corresponding ones are 6–8 µm apart after
bridging. It now requires a clear margin over the runner-up and declines
rather than guessing.

### Nomenclature cross-check against lobemap

64 canonical names derived from the atlases' own published names. The single
remaining disagreement is **`VC3l`/`VC3m`**, present only in Bates as the
older names superseded by that rename chain.

### Grabe: the masks are primary, not the OBJ export

The paper (Grabe et al. 2015, doi 10.1002/cne.23697) states segmentation was
done in **AMIRA 5.5.0**, then *"Reconstructed surfaces from AMIRA were
imported to FIJI"* and converted to `.obj`. So the OBJs are three steps
downstream of the voxel label field.

| | OBJ export | surfaced from masks |
| --- | --- | --- |
| mean offset vs the stack | 0.376 µm in x (~1.1 voxels) | **0.0001 µm** |
| rms | 0.406 µm | **0.0020 µm** |
| glomeruli | 55 (left only) | **108** (54 L + 54 R) |
| watertight before repair | 55/55 | 108/108 |

Alignment is now exact by construction, because meshes and the confocal stack
come from one array in one orientation. The paper's stated count of **54
glomeruli** matches the masks; the OBJ export's 55th is **VM6**, which has
**zero voxels** in the label volume — whose filename is literally
`..._labels_only_sure_ones_...`, so it was evidently dropped as uncertain.
That is notable because VM6 is exactly the glomerulus lobemap's table splits
three ways and that only Schlegel S11 realises.

Left and right are **independently segmented, not mirrored**: paired volumes
differ by a median of 13.9%, up to 54%, none identical. Open question: the
paper describes selecting *one* representative AL, yet the published file
(named `Merged_2-...`) contains both.

---

## 4. Units and source formats

Units are **never assumed** — every ingest identifies them by measuring median
compartment size against a known anatomical range, and an unrecognised or
ambiguous scale is an error.

| source | units found | gotcha |
| --- | --- | --- |
| neuPrint ROI meshes | 8 nm voxels | — |
| Bates Plotly HTML | nm | contains a whole-brain `neuropil` trace (627 µm) that is not a glomerulus |
| Benton 3D Slicer | nm, **RAS** | negate x and y → 0.0 µm offset from Bates |
| Schlegel STL | 8 nm voxels (`JRCFIB2018Fraw`) | — |
| Grabe TIFF | 0.34 × 0.34 × 0.96 µm | read from ImageJ metadata |
| JRC2018U NRRD (VFB) | 0.519 × 0.519 × 1.0 µm | diagonal `space directions` → **no transpose** |

Other format traps:

- **Benton `Segment_ID` carries 3D Slicer's uniquifying suffixes** — `VP1m`
  arrives as `VP1m_1`, which would fabricate a glomerulus the dataset's own
  colour table calls plain `VP1m`. Use the `Segment_Name` prefix instead.
- **Slicer VTPs duplicate every triangle vertex.** Unmerged, `split()` saw
  1602 one-triangle components and discarded all of them. Merge vertices
  *before* splitting.
- **hemibrain's `AL-DC3`** (the side-less ROI) has an **empty mesh**.
- lobemap's curated table annotates names in prose — `VM6v (VM6)`,
  `VM6l*(new)` — so a cross-check must strip annotations while keeping
  `(L)`/`(R)`.

---

## 5. Mesh repair

- **MeshFix's default `remove_smallest_components=True` discards real
  anatomy.** Several neuPrint glomeruli arrive as multiple disconnected
  bodies — male CNS VP1l is 11 pieces on the left, 5 on the right — and the
  discarded pieces sit 0.9–4.3 µm from the main mass, visibly the same
  structure split by a segmentation break. That silently deleted **35% of
  VP1l(L)**. `joincomp` makes no difference.
- **Fix: repair each connected component and keep them all.** A union of
  closed components is still watertight, so containment is unaffected. Max
  volume change across all CNS glomeruli fell from **35% to 0.06%**.
- **Merge vertices before splitting** (see Slicer VTPs above).
- The volume-change metric **must not be gated on `trimesh.is_volume`**, which
  is False for exactly the open meshes being repaired — that made every repair
  report 0.0% and hid the VP1l case entirely.

---

## 6. napari behaviour

- **Surface picking works in 3D.** `Surface._get_value_3d` does ray–triangle
  intersection and returns the barycentric-interpolated `vertex_values`.
  Because compartments are disjoint meshes, all three vertices of a triangle
  share one index, so that value is *exactly* the compartment index.
- **In 2D, `Surface._get_value` returns `None`.** The contour `Shapes` layer
  restores identification there, since `Shapes._get_value` returns a shape
  index.
- **napari does not short-circuit a no-op write to `layer.visible`** —
  assigning `True` to an already-visible layer costs **~70 ms**.
- Cost of a selection change, 77 compartments / 158k vertices:

  | operation | cost |
  | --- | --- |
  | `layer.data = ...` | 77 ms |
  | `layer.visible = True` (no-op) | 70 ms |
  | `meshset.select()` (numpy) | 3.6 ms |
  | `layer.colormap = ...` | 0.9 ms |

  So a toggle repaints via colormap alpha and compacts geometry on a debounce:
  **148 ms → 0.92 ms**. Hidden geometry still absorbs the 3D pick ray until
  compaction, so picking filters to the current selection.
- **Translucent reference shells write depth and occlude the glomeruli they
  exist to contextualise.** Use `blending="additive"`.
- A `Colormap` with `interpolation="zero"` needs `len(controls) == len(colors)
  + 1`; contrast limits of `(-0.5, n-0.5)` put value *i* at the centre of bin
  *i*.

---

## 7. Virtual neuropil stain

The method is a **binned 3D Gaussian KDE**: histogram presynapse locations
onto a 0.5 µm grid, convolve with σ = 900 nm. Binning makes the effective
kernel Gaussian ⊛ box, so the bandwidth is √(σ² + h²/12) = **912 nm**, a 1.3%
inflation — measured and reported by the pipeline.

σ is an **instrument constant, not a fitted bandwidth**. A data-driven rule
goes as n^(−1/7) in 3D, far smaller at 10⁷ points; the method is deliberately
over-smoothed because the goal is to forge a point-spread function.

**Presynapses only** (user decision, 2026-09-21): nc82 labels Bruchpilot at
presynaptic active zones, so presynapse density is the same physical signal.
Counting connections would weight each T-bar by its partner count.

### AL preflight (hemibrain) — passed

669,019 presynapses at confidence ≥ 0.5, none outside the grid. Alignment
validators emphatic: **286× mean intensity inside the AL shell versus
outside**; 6.6× at glomerulus centroids. The rendered stain reproduces the
glomerular pattern — bright cores, dark septa — from synapse positions alone,
with the neuPrint outlines falling on its septa
(`docs/images/m6-virtual-stain-AL.png`).

### Synapse sources: the buckets, not neuPrint

**~60% of detected synapses are not assigned to proofread neurons**, mostly
postsynapses on fine twigs (user, from the dataset authors). Starting from
proofread-linked connections would make the stain *biased*, not merely
sparser: brightest where tracing was most complete rather than where synapses
are.

| dataset | source | contents |
| --- | --- | --- |
| hemibrain | `gs://neuroglancer-janelia-flyem-hemibrain/v1.2/synapses/by_id/` | 8 shards, ~4.4 GB; **7,925,760 annotations in shard 0** → ~63 M total |
| male CNS | `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/syn-points-male-cns-v1.0-minconf-0.5.feather` | 13.1 GB, **357,489,383 rows**: 45,656,140 PreSyn + 311,833,243 PostSyn |
| FAFB | `fafb_v783_princeton_synapse_table.csv.gz` (local, 2.7 GB) | `pre_x/y/z`, `ctr_*`, `post_*`, `size`, root ids, neuropil |

Hemibrain's store is `neuroglancer_annotations_v1`, `annotation_type: LINE`,
8 nm dimensions, with `pre_synaptic_confidence`/`post_synaptic_confidence`.
Decode with cloudvolume's `ShardingSpecification.from_dict` +
`ShardReader.disassemble_shard` (60 s per shard) rather than implementing the
sharded format. Single-annotation encoding is 6 × float32 geometry (point A
xyz, point B xyz) then the two float32 properties.

**Which endpoint is presynaptic was verified, not assumed.** A T-bar serves
many PSDs, so its endpoint should repeat. In shard 0, endpoint **A is 66%
unique** (5,228,268 / 7,925,760) and **B is 100% unique** → **A is
presynaptic**.

Only `by_id` is the full detected set; `pre_synaptic_cell/` and
`post_synaptic_cell/` are indexes over *assigned* synapses only.

**Nuance worth remembering:** hemibrain's ~63 M annotations imply ~9.5 M
unique T-bars, and neuPrint returned **9,496,606** presynapses — so for
hemibrain *presynapses specifically*, a bare
`MATCH (s:Synapse {type:'pre'})` was already the complete set. The 60%
incompleteness bites on the postsynaptic side and on queries that start from
neuron criteria. The bucket is still right: ~50× faster, and the only
practical route for male CNS and FAFB.

### The three whole-brain stains — built

| dataset | presynapses | source rows | read | build | grid | file |
| --- | --- | --- | --- | --- | --- | --- |
| hemibrain | **9,496,607** | ~63 M annotations | 265 s | 128 s | 1142x1306x1366 | 0.38 GB |
| FAFB | **79,935,406** | 219,060,529 pairs | 62 s | 184 s | 2686x1332x1118 | 0.84 GB |
| male CNS (brain) | **35,237,247** | 45,656,140 PreSyn | 26 s | 211 s | 2818x1578x1102 | 1.07 GB |

0.25 um bins, sigma 900 nm, presynapses only, uint8, stored as OME-Zarr with
a multiscale pyramid. 10.9 G voxels and **2.30 GB** in total; 876 s of compute
from cached sources.

Brightness at glomerulus centroids: 7.10× (hemibrain), 3.62× (FAFB), 5.52×
(male CNS); inside/outside 5.66×, 2.38×, 3.75×. All 26 registry checks pass.

**Hemibrain's dedup total is 9,496,607 against neuPrint's 9,496,606** — a
difference of one. That settles the earlier inference: for hemibrain
presynapses specifically, a bare `MATCH (s:Synapse {type:'pre'})` already
returned the complete detected T-bar set. The bucket is still the right
source: 297 s against ~50 min, and the only practical route for the others.

The inside/outside ratios are much lower than the AL-only preflight's 286×,
and that is correct rather than a regression: in a whole-brain stain
"outside the AL" is other neuropil, which is also synapse-dense. The preflight
had nothing outside the AL at all.

**FAFB's 219 M pairs collapse to 79.9 M unique T-bars** — about 2.7
postsynaptic partners each. Skipping that deduplication would have weighted
every T-bar by its partner count, which is precisely what counting connections
does and what nc82 does not.

### The rename is a literature fact, and it splits the catalogue by date

Measured first, from the meshes -- each is the other's best match in both
directions, at an overlap of 0.996-0.999 by volume:

| Benton | Bates | overlap | centroid |
| --- | --- | --- | --- |
| VC3 | VC3l | 0.9980 | 0.01 um |
| VC5 | VC3m | 0.9990 | 0.01 um |
| VM6 | VC5 | 0.9959 | 0.10 um |

Then confirmed in the literature, which also corrects the attribution: the
rename is **Schlegel et al. 2021** (eLife 66018), landing in hemibrain from
**v1.3** and coordinated with other groups. `VC5 -> VM6`, `VC3m -> VC5`,
`VC3l -> VC3`. Benton 2025 adopts it rather than originating it -- its own
text cites Schlegel for "updated glomerular naming" and does not discuss the
chain. The rationale was VM6's three ALRN subpopulations (VM6v, VM6m, VM6l),
which had caused the earlier discrepancies.

**So the catalogue splits by date, not by atlas:**

| convention | atlases |
| --- | --- |
| old (`VC3l`, `VC3m`, `VC5`) | bates2020 (2020), neuprint_hemibrain (**v1.2.1**) |
| new (`VC3`, `VC5`, `VM6`) | benton2025, neuprint_cns, schlegel2021_s11, schlegel2021_s12 |

hemibrain being on the old side is the subtle part: the rename shipped in
v1.3 and the registry pins v1.2.1, so hemibrain and the male CNS -- both
neuPrint, both nominally the same naming -- disagree. **The new names reuse
old ones for different structures**, which is what makes a name-based join
silently wrong rather than merely incomplete.

**The canonical vocabulary is now Benton 2025's 58 published names**, by
decision, with every other atlas mapping onto them and `Registry.validate`
failing if a canonical name is not one of Benton's. The two old-convention
atlases carry `renamed` correspondences:

Before the fix, a name-based join of Bates against Benton paired `VC5` with
`VC5` -- two structures 12.78 um apart with **no overlap at all** -- while
leaving `VC3`, `VC3l`, `VC3m` and `VM6` unmatched. All six now resolve.

`grabe2015` is **not** classified. It predates the VC3l/VC3m split entirely,
carrying an unsplit `VC3` and a `VC5` that is probably old-VC5 (= new VM6) --
but GRABE is an island space with no bridge, so this cannot be settled
geometrically the way the others were. Left as-is and flagged.

### Distribution: fetch, never ship

Measured: the flybrains bundles are 10.3 GB, the stains 2.4 GB. So the wheel
carries only registry metadata and everything with voxels or vertices is
fetched once, after which scenes open offline. `lobemap manifest` records
sha256 and size for all 16 artifacts (2.53 GB transferred); `lobemap fetch`
downloads and verifies, and `--check` verifies what is already present.

A `.zarr` store is a directory, so it travels as a zip and **the checksum is
of the transferred bytes**. Zipping is made deterministic -- sorted entries,
normalised timestamps -- or a rebuild would look like changed data. A download
whose checksum does not match is discarded rather than kept, and one bad
artifact does not block the others.

`base_url` is deliberately unset in the committed manifest: nothing is
published yet, and a plausible URL that 404s would fail later and less
clearly than no URL at all.

### Smoothing a label volume: three constraints, kept independent

Marching cubes on a *binary* mask is a staircase. Grabe's glomeruli had
**42% of faces on an exactly axis-aligned normal** against 3% for Bates, and
31% pointing along z alone -- the z sampling is 0.96 um where x and y are
0.34. They read as voxel masks rather than glomeruli, which is what they are
surfaced from.

Smoothing the mesh afterwards is the obvious move and the weak one: Taubin
reached 17% and no further, because by then the steps are vertices. Blurring
the mask and taking the isosurface of the smooth field removes them at the
source, **42% -> 3.9%**, in line with the other atlases.

That introduces two new problems, and the point is that each gets its own
mechanism rather than being traded against smoothing:

| problem | wrong fix | what is done |
| --- | --- | --- |
| neighbours collide | shrink sigma until they stop | each surface sits where its field overtakes its strongest rival |
| blurring shrinks volume | lower the isolevel everywhere | lower it against *background* only |

**Collisions.** Thresholding each blurred mask independently expands every
region outward, so touching glomeruli interpenetrate: at sigma 0.8 and level
0.46, **158 voxels ended up inside two glomeruli at once** -- VC3/VP2,
VA1d/VA1v, DM1/DM4 and a dozen more. Choosing sigma small enough to avoid
that undersmooths for a reason that has nothing to do with smoothing. Placing
each surface at the midpoint between neighbouring blurred fields makes
overlap impossible instead -- `g_i > g_j` and `g_j > g_i` cannot both hold --
and leaves sigma free. Verified at every sigma tried, and the ingest counts
claims per voxel and refuses to write an overlap.

**Shrinkage.** Blurring pulls a convex surface in by roughly sigma^2/R, so it
falls hardest on the small glomeruli: 7.2% of the volume at level 0.5. Level
0.44 restores it to -0.4%, and cannot cause collisions, because a shared
boundary is set by the midpoint rule and never by the level.

Two bugs found in the same pass, both silent:

- **Every one of the 108 meshes had inverted face winding**, which breaks 3D
  lighting. The label array is transposed by `(2, 1, 0)` before marching
  cubes, an odd permutation, so skimage's winding described inward normals.
  Now checked per mesh against the signed volume and flipped.
- An Amira materials parser I added took the `Id` fields at face value, but
  Amira numbers from 1 with `Exterior` as Id 1 while its TIFF export writes
  background as 0. That shifted **every glomerulus onto its neighbour's
  label**, surfacing four that should be empty and losing VM6's known
  absence. The background voxel value (0, 92% of the volume) and positional
  nomenclature coherence (0.81 against 0.74) both identified it. The ingest
  now refuses to run if the modal voxel value is claimed by a glomerulus.

### Sigma halved to 450 nm

Rebuilt on request. Unlike halving the bin size, this one **does** raise the
resolution, and it puts the 0.25 um grid in exactly the relationship 0.5 um
had to sigma 900 nm: Nyquist at 0.25 um bins is 2 cycles/um and the Gaussian
passes 1.1e-7 there. Effective bandwidth 903 nm -> 456 nm.

| | inside/outside | at centroids | store |
| --- | --- | --- | --- |
| hemibrain | 5.66x -> **5.83x** | 7.10x -> **6.69x** | 0.38 -> 0.42 GB |
| FAFB | 2.38x -> **2.44x** | 3.62x -> **3.73x** | 0.84 -> 0.91 GB |
| male CNS | 3.75x -> **3.73x** | 5.52x -> **5.34x** | 1.07 -> 1.11 GB |

The contrast measures move in **both directions**, which is the signature of
less smoothing rather than of better or worse data: a point sample of a
less-smoothed field has higher variance, so centroid brightness gets noisier
while the region-averaged inside/outside ratio barely moves. These numbers are
not comparable with the sigma 900 series and should not be read as an
improvement. The stores grow slightly because less smoothing leaves more
entropy to compress.

**This departs from the nc82-matching rationale**, which fixed sigma as an
instrument constant. It is a deliberate choice for visible detail, recorded in
each Derivation as `sigma_um`.

The banding visible in the hemibrain MIP is **not** a slab seam from the
disk-backed blur: plane-to-plane variation at seam positions is 1.11x that
elsewhere (hemibrain) and 1.06x (FAFB), and the largest jump in each volume is
nowhere near a seam. It is hemibrain's own FIB-SEM slab structure.

### Halving the bin size does not raise the resolution

Rebuilt at 0.25 um on request, and the measurements are the argument for why
the grid is not what limits these:

| bin | effective sigma | centroid brightness (hemibrain) | inside/outside |
| --- | --- | --- | --- |
| 0.5 um | 911.5 nm | 6.97× | 5.65× |
| 0.25 um | 902.9 nm | 7.05× | 5.64× |

**Sigma sets the resolution; the bin size only samples it.** Effective
bandwidth sqrt(sigma^2 + h^2/12) moves 0.9%, and a 900 nm Gaussian's transfer
at the *old* Nyquist frequency of 1 cycle/um is already **1.1e-7** of DC. So
0.5 um sampled the field well above Nyquist and the extra voxels are
interpolation, not detail -- which is why every contrast measure is unchanged.

Finer bins are still worth something: `Volume.sample` is nearest-neighbour, so
0.5 um voxels carry up to 0.43 um of positional error when reading the stain
at mesh vertices, halved to 0.22 um. Genuinely finer structure would need
sigma reduced too, which departs from the nc82-matching rationale.

### Grids past ~0.4 G voxels need a different algorithm

The in-RAM builder cannot run at 0.25 um, and not by a small margin:
`np.bincount(flat, minlength=n_voxels)` alone allocates 8 bytes per voxel --
**39 GB** for the male CNS grid against 22 GB free -- and the whole-array
`gaussian_filter` needs two float32 copies on top.

The way out is that **the point cloud is far smaller than the grid it fills**:
35 M presynapses are 420 MB as int32 indices against 19.6 GB for the grid. So
`ingest/stain_slabs.py` partitions points by slab, spills them to disk, and
bins and blurs one slab at a time inside a 1.2 GB budget. Peak RAM is then
independent of grid size.

The blur stays exact rather than approximate. A Gaussian is separable, so a
slab spanning all of y and z is already exact in those axes; along the
partition axis it carries a halo of the kernel's true reach (scipy's
`truncate * sigma` = 14 voxels at 0.25 um), and `mode="nearest"` at a block
edge only touches voxels inside the halo, which are cropped. Slabs are forced
wider than the halo so three consecutive point files always cover one block.
`tests/test_stain_slabs.py` compares against the whole-array builder over 5-,
3-, 2- and 1-slab layouts: **max deviation 1 count** of uint16 quantisation.

Two bugs that only a test could have found, both of which would have produced
plausible output rather than an error:

- `slab_width` bound `SLAB_BUDGET_BYTES` as a **default argument**, evaluated
  at import, so the budget constant could never be lowered at runtime -- the
  machine's RAM would have been ignored on any smaller machine.
- The first set of test budgets all clamped to the `2*halo` floor, so a
  parametrised equivalence check ran one layout three times while appearing to
  cover three.

### Storage: OME-Zarr, because compression and random access are not exclusive

The npz/npy pair forced a choice neither format escapes. A compressed `.npz`
must be inflated whole into RAM, so a 4.9 GB stain cost 4.9 GB just to open;
an uncompressed `.npy` memory-maps but gives up compression entirely. **Zarr
is chunked, compressed and randomly accessible at once**, so the choice
disappears.

| | uint16 npy | uint8 npy | uint8 OME-Zarr |
| --- | --- | --- | --- |
| hemibrain | 4.07 GB | 2.04 GB | **0.38 GB** |
| FAFB | 8.00 GB | 4.00 GB | **0.84 GB** |
| male CNS | 9.80 GB | 4.90 GB | **1.07 GB** |
| total | 21.9 GB | 10.9 GB | **2.30 GB** |

21% of the uint8 arrays *including* the pyramid, and 10.5% of where this
started. 64^3 chunks with zstd over bit-shuffled bytes; bit shuffling matters
because these are smooth 8-bit maps with a large near-zero background, which
byte shuffling cannot expose at one byte per sample.

Counter-intuitively **Zarr is slightly larger for small volumes** --
`grabe2015_stack` 124%, `jrc2018u_nc82` 116% -- because chunk-local
compression does worse than whole-array deflate at that scale and the pyramid
adds about 14%. Irrelevant at 15-37 MB, and the pyramid is worth it.

### The pyramid is what makes these viewable at all

napari cannot render a 5 G-voxel array: it has to page the whole thing in.
Given a pyramid it draws the coarsest level covering the view and refines on
zoom. The stains carry 5-6 levels; the coarsest are 71x81x85 to 88x49x34.

Two details that would have produced plausible-looking errors:

- **Levels are block means, not subsamples.** Averaging preserves the
  integral, so coarse levels keep level 0's intensity scale. A subsampled
  pyramid would be noisier *and* dimmer, which in a density map reads as less
  signal.
- **Factors are per axis.** An axis halves only while it has room. A uniform
  2^L factor crashed on a thin axis -- `pyramid_shapes` kept a size-1 axis at
  1 while the reducer assumed 2 everywhere -- and would have thinned the z of
  a confocal stack that cannot spare it. Each level records its own scale
  *and* translation, because level L's first voxel centre sits `(f - 1) / 2`
  original voxels in; omitting that shifts coarse levels by up to half a voxel
  against the meshes, which looks like bad registration.

**Axis order is kept as (x, y, z)**, matching the mesh vertex columns, and the
NGFF `axes` metadata declares it rather than transposing. NGFF 0.4 requires
only that space axes come last, so this is spec-legal -- but a reader that
hardcodes z, y, x instead of reading the metadata will show these transposed.
Geometry is read back from the NGFF `coordinateTransformations`, not from our
own attributes, so a store stays correct if another tool rewrites it.

### 8-bit costs 0.35% of the contrast

Both LM references were already uint8 (`grabe2015_stack`, `jrc2018u_nc82`), so
8-bit matches the confocal data the stain emulates rather than degrading it.

| | inside/outside | at centroids |
| --- | --- | --- |
| hemibrain uint16 -> uint8 | 5.64× -> **5.66×** | 7.05× -> **7.10×** |
| FAFB | 2.38× -> **2.38×** | 3.61× -> **3.62×** |
| male CNS | 3.74× -> **3.75×** | 5.49× -> **5.52×** |

What 8-bit discards is the faint outer skirt of the blur: the 9-15% of
non-zero voxels it rounds to zero all sit below 0.2% of peak. On synthetic
blobs the ratio rises about 4%, because there the background is *nothing but*
that skirt -- a fixture artefact, not a format one, and the reason
`test_uint8_preserves_the_contrast_that_matters` uses a diffuse component.

### Mesh containers no longer need pickle

`MeshSet.load` used `allow_pickle=True`, because `names` was stored as a numpy
object array and numpy can only read those by unpickling. Unpickling runs code
the file chooses, so under M7's fetch-never-ship plan a downloaded mesh could
execute anything. Names are now JSON and the default read path uses
`allow_pickle=False`; legacy containers still load, but only via an explicit
second pass. All 11 were migrated in place with **content hashes unchanged**,
so no cached bridge invalidated.

Meshes stay `.npz` rather than becoming Zarr. They are 80 MB across 13 files,
ragged rather than gridded, read whole, and have no meaningful pyramid -- none
of Zarr's advantages apply, and no tool reads meshes from Zarr, so it would
reduce interoperability rather than raise it.

### Male CNS: the brain/VNC boundary is unambiguous

Classifying sampled presynapses by the `primary` ROI column against the VNC
subtree of the neuPrint hierarchy (61 ROIs under VNC + CV):

- brain-labelled presynapses span **z 101.3–328.4 µm**
- VNC-labelled presynapses span **z 538.7–1049.2 µm**
- a **210 µm gap** between them, the cervical connective

So the crop is applied as grid bounds rather than a label filter, which keeps
synapses whose ROI is unspecified but whose position is in the brain. It drops
10,418,893 of 45,656,140 presynapses (22.8%).

### Coordinate conventions, verified not assumed

- **male CNS feather**: columns stored `z, y, x`; read by name into `(x, y, z)`.
  With that order **93.2%** of in-bbox presynapses fall inside the AL neuropil
  mesh, against a 30.4% bbox fill fraction and 11.9% for the next-best
  permutation. Units are 8 nm voxels.
- The feather is **spatially ordered**, so its first 400k rows span only
  ~210 µm of a ~1077 µm volume and unit inference from the head fails
  outright. Sample across the table.

### neuPrint query lessons

- **Never ask neo4j for `min`/`max` over the synapse table.** The unfiltered
  aggregate scans ~10⁷ rows and hits the server transaction timeout. Bounds
  come from geometry already held.
- **~40 s of fixed overhead per query**, regardless of result size; transfer
  then runs at ~5,000–7,000 rows/s. A whole-brain hemibrain run over 28 slabs
  was ~50 min, roughly a third of it spent querying empty bounding-box space.
- Counting male CNS presynapses globally returns **HTTP 504**.

---

## 8. Environment

- **neuPrint token**: `NEUPRINT_APPLICATION_CREDENTIALS`, User scope. One
  token serves both servers. Tokens issued before neuPrint's auth change are
  rejected with "invalid or expired token"; a current one is 64 chars, not a
  JWT.
- **FlyWire/CAVE token**: `~/.cloudvolume/secrets/cave-secret.json` (written
  via `fafbseg.flywire.set_chunkedgraph_secret`). `fafbseg` does **not** read
  `FLYWIRE_APPLICATION_CREDENTIALS`.
- **CMTK**: `C:\Users\clark\tools\CMTK-3.3.1\CMTK\lib\cmtk\bin`, on User PATH,
  with an extensionless `streamxform` alias. Non-functional, see §2.
- **flybrains transform bundles**: `C:\Users\clark\flybrain-data`, 10.3 GB.
- `run_with_token.ps1` / `run_stain.ps1` bridge User-scope env vars and PATH
  into a child process, so a session started before those were set still sees
  them. Both run `python -u`: **stdout block-buffering through a wrapper shell
  made a healthy job look hung and cost a needlessly killed run.** Long jobs
  also append progress to `registry/data/<asset>.progress.log`.
- Machine: 32 GB RAM, i5-12600K (10c/16t), 3.3 TB free on `D:`. Nothing in
  this project needs the HPC cluster.
