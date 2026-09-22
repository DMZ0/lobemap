# lobemap — design

A napari application for viewing and comparing *Drosophila* antennal lobe glomerular
atlases in their native and bridged coordinate spaces.

Status: design document, implemented. Two decisions below have since been
revised; see the amendment.

---

## Amendment: one space per atlas, and nomenclature per space

Two things this document argues for are no longer true of the code.

**An atlas is now shown only in its native space.** Section 1 allows atlas
layers "native to that space, or bridged into it", and the viewer had a
`--bridged` flag and a cross-space scene. Both are gone. Bridging survives
where it concerns DATA rather than display: ingest still transforms an asset
into the space it is declared in (the FlyWire neuropils are bridged
FLYWIRE to FAFB14), and `lobemap bridge` and `lobemap reconcile` still
compare across spaces from the command line. The argument in section 1
against the ATLAS-centric design stands -- scenes are still organised by
space, and the reference geometry, images and several atlases of one space
still share a scene.

**Nomenclature is per space, not global.** There is no longer a single
canonical vocabulary anchored to one atlas. Each space's vocabulary is the
union of the names its own atlases resolve to, because a space is the only
place two atlases can be superimposed. A global vocabulary had to nominate
one atlas as the authority and restate every other in its terms, which is
awkward exactly where the communities disagree -- the Schlegel 2021 rename
chain meant the hemibrain atlases were described in FAFB's names. The cost
is that a glomerulus may take a different colour in different scenes, since
colour is assigned by position in the space's vocabulary.

In practice only the hemibrain now has several atlases to reconcile. Every
other space has one, and its vocabulary is that atlas's own names.

The Bates 2020 atlas was also removed: Benton 2025 revises the same meshes.

Lineage: this is a from-scratch successor to [lobemap](https://github.com/gumadeiras/lobemap)
(Gustavo Madeira Santana). It reuses that project's ideas and some of its curated
tables and ingest logic, but not its architecture.

---

## 1. The central decision: spaces, not atlases, are the organizing unit

Two designs were considered.

**Atlas-centric.** One viewer per mesh set. Each viewer loads its atlas plus a fixed
set of companion layers (AL(L), AL(R), whole brain, a reference stain) bridged into
that atlas's native space.

**Space-centric.** One scene per *coordinate space*. Within a scene, any number of
atlas layers may be loaded — native to that space, or bridged into it — alongside the
reference geometry and images that belong to the space.

**We adopt the space-centric design.** Reasons:

1. *Atlas-centric is a strict subset.* A "Bates viewer" is just a FAFB scene with one
   atlas enabled. Shipping named scene presets reproduces the atlas-centric experience
   exactly. The converse does not hold.

2. *Atlas-centric does not avoid the bridging work.* Under that design, the FAFB viewer
   still needs a reference stain warped into FAFB and the hemibrain viewer needs one
   warped into hemibrain. The full bridging graph is required either way; atlas-centric
   merely runs it more times and stores more copies of every reference asset.

3. *The scientifically interesting questions are cross-atlas.* Do Bates' and Schlegel's
   VA1v agree? How far do Benton's revised boundaries move from their Bates parents? How
   much of an apparent FAFB/hemibrain disagreement is real biological variation versus
   error in the bridging registration itself? An atlas-centric application cannot pose
   any of these.

### Accepted cost

Superimposing many glomeruli from multiple atlases — in 3D or in slice view — looks
bad. This is not treated as a problem to solve. The application permits arbitrary
combinations and relies on the user to choose sparse, legible ones; an over-ambitious
selection renders poorly and the user scales back. No sparsity constraint is enforced,
and no "only one atlas visible at a time" mode is imposed.

The design consequence is that **the unit of visibility is the compartment, not the
layer.** The selection model must address individual glomeruli across atlases
simultaneously, which rules out leaning on napari's per-layer visibility toggles as the
primary control (see §7).

---

## 2. Core model

Seven types. Reference geometry is not a separate class — it is an `Asset` with a
different `role`, which is what keeps the model small.

```python
Units = Literal["nm", "um", "px"]
Role  = Literal["glomeruli", "neuropil", "brain", "template_image",
                "virtual_stain", "map_2d"]

@dataclass(frozen=True)
class Space:
    id: str                          # FAFB14 | FLYWIRE | JRCFIB2018F | JRC2018U | CNS | GRABE
    title: str
    units: Units                     # authoritative
    flybrains_template: str | None   # navis-flybrains registry name; None => island
    mirror_supported: bool
    notes: str                       # e.g. FAFB14 / FAFB14.1 / FlyWire-nm differences

@dataclass(frozen=True)
class Derivation:
    recipe: str                      # "synapse_density" | "bridge" | "mirror" | ...
    inputs: tuple[str, ...]          # Asset ids
    params: Mapping[str, object]     # sigma_nm, voxel_um, transform chain
    tool_versions: Mapping[str, str] # navis, flybrains, lobemap

@dataclass(frozen=True)
class Provenance:
    doi: str | None
    url: str | None
    retrieved: date | None
    license: str | None
    checksum: str | None
    derivation: Derivation | None    # set when this asset was computed, not downloaded

@dataclass(frozen=True)
class Asset:
    id: str
    role: Role
    space: str                       # Space.id
    kind: Literal["meshset", "mesh", "image", "labels"]
    side: Literal["L", "R", "both"] | None
    path: Path
    source: Provenance

@dataclass(frozen=True)
class Compartment:                   # one glomerulus within one atlas
    local_id: int                    # index into the parent meshset
    published_name: str              # exactly as published — never rewritten
    canonical: tuple[str, ...]       # 0, 1, or many canonical names — see below
    side: Literal["L", "R"]
    color: RGBA | None

@dataclass(frozen=True)
class Atlas:
    id: str
    title: str
    citation: str
    doi: str
    native_space: str
    asset: str                       # the glomeruli meshset Asset
    compartments: tuple[Compartment, ...]
    parent: str | None               # set when this atlas revises another (Benton -> Bates)

```

There is deliberately no `Scene`. One existed: a named set of layers, each
with its own `visible`, `mirror` and `style`, which `lobemap view --scene`
selected. It was removed because a scene was never a different view of the
data. `build_scene` takes a SPACE and loads every atlas native to it; the
preset was applied afterwards and set nothing but `.visible`, so two
scenes on one space held identical layers and differed only in which boxes
started ticked. `mirror` and `style` were never used by any scene in the
registry, and the in-viewer switcher enumerated spaces, so the one scene
that justified the concept -- three hemibrain atlases at once -- was
unreachable from the UI meant to expose it.

What survives is `Space.primary_atlas` plus visibility keyed on an asset's
role: primary atlas on, other atlases loaded and off, neuropil off, image
on when it is on disk, label volume off. That reproduces every preset the
registry had.

Resolution is a single cached function:

```python
def resolve(asset_id: str, target_space: str, *, mirror: bool = False) -> Geometry
```

Six properties of this model worth stating explicitly:

- **`published_name` and `canonical` are both required, and `published_name` is
  immutable.** Cross-atlas superposition is meaningless without an assertion that this
  VA1v is that VA1v, and the atlases genuinely disagree on nomenclature. The
  reconciliation table is the load-bearing component of the whole design, not a
  convenience. Provenance dies if the published name is overwritten in place.

- **One atlas defines the canonical vocabulary: Benton 2025.** Its 58 published names
  *are* the canonical set, and every other atlas maps onto them. Naming the source
  matters more than which source is named: left implicit, the set drifts into a union of
  whatever each atlas happens to call things, which is how `VC3l` and `VM6v` became
  canonical names that no current nomenclature uses. `Registry.validate` now fails if a
  canonical name is not one of Benton's.

- **Compartment-to-canonical correspondence is not one-to-one**, and both directions
  occur. Schlegel S11 resolves VM6 into VM6l/VM6m/VM6v, so three compartments share one
  canonical name (`split`); Grabe does not resolve VP1 at all, so one compartment
  carries three canonical names (`merge`). Renames are one-to-one under a different name
  (`renamed`): Bates `VC3l` is canonical `VC3`. `canonical` is therefore a tuple and
  each correspondence carries a relation — `exact`, `split`, `merge`, `renamed`,
  `absent`. A single nullable foreign key would have silently mangled exactly the cases
  that are scientifically interesting.

  Both discrepancies are kept rather than flattened. Merging S11's three VM6 parts into
  one would have made it match the vocabulary, but Grabe's unresolved VP1 cannot be
  split to match, so flattening one and not the other would be inconsistent — and it
  would discard the finer segmentation that is S11's distinguishing feature.

- **Mirroring is a transform, not a property of an object.** Bates ships left-only;
  hemibrain is right-complete. Comparing them at all requires mirroring one, so
  `mirror=True` is needed from day one. Mirrored layers must be visibly marked in the UI
  as approximations.

- **Islands are a normal state, not an error.** `flybrains_template = None` (Grabe)
  simply yields a space whose scene has one atlas and no bridges. Grabe is the only
  island in the catalogue: the male CNS was a candidate but bridges cleanly (§3).

- **Derived assets carry their recipe.** The virtual stain (§5) and every bridged or
  mirrored cache entry are computed, not downloaded, and must record σ, voxel size,
  input asset ids, and the versions of navis/flybrains used. Without this, stale caches
  are undetectable.

- **No `Specimen` / `Dataset` entity.** For these purposes it would be 1:1 with `Space`.
  Unit variants (hemibrain 8 nm voxels vs µm) are cleaner as two `Space` records than as
  one specimen carrying a unit flag.

---

## 3. Coordinate spaces and transforms

**Internal working unit is µm**, matching napari world coordinates. Every `Asset`
declares its units and every transform records input and output units explicitly. Silent
nm/µm/voxel mixing is the most likely source of wrong-but-plausible output in this
application.

**Most navis-flybrains bridges are non-affine** — H5 deformation fields and CMTK warps.
A napari layer `affine` cannot represent them. Therefore:

> Transformation applies to vertices at ingest/cache time. It is never a render-time
> layer transform.

Cache keys must combine the source asset's content hash, the full transform chain, and
the navis / flybrains / lobemap versions. Anything less produces silently stale
geometry after a dependency upgrade.

**Dependency risk.** Several flybrains registrations require external CMTK binaries, and
the transform bundles are large downloads (`flybrains.download_jrc_transforms()`,
`download_jefferislab_transforms()`). End users must not need CMTK: transformed geometry
is precomputed and distributed or fetched as a cache, and live transformation is a
developer-time path. The space graph is validated at startup, and a space whose bridges
are unavailable degrades to an island rather than raising.

**FAFB is not one space.** FAFB14, FAFB14.1, FlyWire nm, and raw 4 nm voxels are
distinct, and the differences are not all rigid. Each gets its own `Space` record with
the distinction spelled out in `notes`; nothing is treated as a synonym without a
recorded transform.

### Measured transform availability

flybrains 0.6.3 / navis 1.12.0. Before downloading the bundles: 36 templates, 49
registrations, and no path from FAFB to hemibrain or to JRC2018U at all. After
`download_jrc_transforms()` + `download_jefferislab_transforms()`: **112 registrations,
10.3 GB on disk, ~10 minutes**. Every bridge the catalogue needs then resolves.

`navis.xform_brain(source=, target=)` finds the route itself via a weighted shortest
path (`registry.find_bridging_path`), so nothing here should ever name intermediate
spaces. Resolved chains, and what each costs:

| bridge | resolved chain | external binary? |
| --- | --- | --- |
| FAFB14 → JRCFIB2018F | Affine, Alias, H5, H5, Affine | **no — pure Python** |
| FAFB14 → JRC2018U | Affine, Alias, H5, H5 | **no** |
| JRCFIB2018F → JRC2018U | Affine, H5, H5 | **no** |
| JRCFIB2022M → JRC2018U | Affine, H5, H5 | **no** |
| FLYWIRE → JRCFIB2018F | Affine, **CMTK**, H5, Affine | yes |
| JRCFIB2018F → JRCFIB2022M | Affine, H5, **CMTK**, Affine, TPS | yes |

Three consequences:

- **FAFB14, not FLYWIRE, is the FAFB-family hub.** The FAFB14 route to hemibrain is
  pure Python; the FlyWire route goes through CMTK. Ingest should land FAFB-family
  assets in FAFB14 and let the FlyWire↔FAFB14 affine handle the rest.
- **Trust navis's routing; do not constrain it by default.** The registry weights warps
  (H5, CMTK, Elastix, thin-plate) at 1.0 and affines and aliases at 0–0.1, so the
  shortest weighted path is the one with the *fewest warps* — an accuracy heuristic,
  not merely a shortest-path one. Every chained warp compounds interpolation error, so
  overriding the router to dodge a binary can make the result worse.

  `find_bridging_path` does take an `avoid` argument, and the honest test is warp count,
  not step count. Measured on the two catalogue bridges that pull in CMTK:

  | bridge | default route | avoiding CMTK | verdict |
  | --- | --- | --- | --- |
  | JRCFIB2018F → JRCFIB2022M | 3 warps (h5, **cmtk**, tps) | 3 warps (h5, h5, tps) | **tie** — the CMTK route wins only on an arbitrary tie-break, so avoiding it is free |
  | FLYWIRE → JRCFIB2018F | 2 warps (**cmtk**, h5) | 4 warps | avoiding it is genuinely worse |

  So the rule is: take navis's route; override only when the binary-free alternative
  has an *equal* warp count. And note the FlyWire case does not arise in practice —
  landing FAFB-family assets in FAFB14 at ingest reaches hemibrain in 2 warps with no
  CMTK at all, which is why FAFB14 is the hub. Record the resolved path in
  `Derivation` either way.
- The downloads settle the distribution question: **10.3 GB is fetched, never shipped.**

**The male CNS template is `JRCFIB2022M`** — nanometres, 8 nm voxels, dims
94088 × 78317 × 134576.

### Laterality: image side is not the animal's side

**FAFB and FlyWire image data is left-right inverted**, and the bridging
registrations do not correct it. Established by two measurements:

1. Hemibrain's labels are biologically correct. The asymmetric body is known to be
   larger on the fly's right; in hemibrain AB(R) is 1431 um3 against AB(L)'s 390 um3.
2. FlyWire's `AL_L` -- the modern post-correction annotation, so biologically left --
   bridges onto hemibrain `AL(R)` at 4.6 um versus 94.3 um to `AL(L)`.

So a bridge preserves **apparent** side, not biological side. `Space` therefore carries
`lateral_convention` ("biological" or "mirrored"), `Asset.side` records the
**biological** side, and `Space.apparent_side()` converts. `resolve(...,
align_biology=True)` inserts a mirror when the two spaces disagree.

Consequences for the catalogue:

- **Bates 2020 is the fly's LEFT AL.** The paper calls it right, but predates the
  discovery of the inversion. It sits on FAFB's image-right, which is why it bridges
  onto hemibrain's AL(R). Benton inherits this.
- **Schlegel S11/S12 are unaffected.** They ship in JRCFIB2018Fraw -- hemibrain
  coordinates, not inverted -- and align with the neuPrint AL(R) meshes at 1.76 and
  2.36 um, so they are biologically right.
- Comparing Bates against hemibrain without `align_biology` compares a left AL to a
  right one. That is legitimate for morphology, since the lobes are near mirror
  symmetric, but it must be stated rather than implied.

### Mirroring

`navis.mirror_brain()` **succeeds on every template tested** — FAFB14, JRCFIB2018F,
JRCFIB2022M and JRC2018U — so a mirror never fails loudly. But explicit mirror
registrations exist only for some (FAFB14, FLYWIRE, BANC, FANC, JRCFIB2022M and others;
*not* JRCFIB2018F, JRC2018F or JRC2018U), and where none exists navis falls back to a
reflection derived from the template's own bounding box.

That fallback is fine for a symmetric whole-brain template and **wrong for hemibrain**,
which is a half-brain: reflecting about its own bounding-box centre is not a midline
mirror. The danger is that it returns confident, plausible, wrong geometry rather than
an error.

So the rule stands — `resolve()` applies **mirror before bridge** — but for a sounder
reason than "hemibrain cannot mirror". It can, and that is the problem. Mirror in a
space with a real registration or genuine symmetry, then bridge in. The M3 validation
harness should assert this ordering rather than trusting it.

---

## 4. Warped image templates

Precomputing warped image stacks per target space does largely remove the *performance*
objection to pushing templates into EM spaces — the cost is paid once, offline.

Two objections survive precomputation:

- **Fidelity.** Resampling through a deformation field blurs, and the registration's own
  error (locally several µm) is baked into the result. Precomputation does not improve
  either; it stops you paying for them repeatedly.
- **Distribution.** One warped whole-brain stack per (template × target space) pair is
  hundreds of MB. These cannot ship in the package and require a cache-download
  mechanism with integrity checking.

Both are acceptable if warped templates are wanted, and the design keeps them as
ordinary derived `Asset`s so they can be added per space without special-casing. But §5
is the better default.

---

## 5. Virtual neuropil stain

Following the synapse-density method: downsample and Gaussian-blur predicted synapse
locations (σ ≈ 900 nm) to produce a density map at approximately the resolution of the
LM data used in the standard templates.

**This is preferred over warping JRC2018U into each EM space**, for three reasons:

1. It is computed *natively* in each EM space. No bridging transform is involved, so
   neither registration error nor resampling blur enters the reference channel — which
   matters especially because the reference channel is what users will visually trust
   when judging alignment.
2. It is cheap: a 3D histogram of synapse coordinates at ~0.5 µm voxels followed by a
   Gaussian filter. The only real cost is obtaining the synapse table.
3. It is arguably the *more* faithful analogue of nc82, not merely a substitute. nc82
   labels Bruchpilot at presynaptic active zones, so a predicted-presynapse density map
   is close to the same underlying signal rather than an approximation of it.

Per space: hemibrain synapses via neuprint; FAFB/FlyWire via the published synapse
prediction tables; male CNS via neuprint if that dataset exposes them.

In the model this is an `Asset(role="virtual_stain", kind="image")` whose `Derivation`
records the synapse source and version, σ, voxel size, and blur implementation.
JRC2018U's real nc82 channel remains available as a `template_image` asset in its own
space, which is where it is cheapest and most honest.

---

## 6. Atlas catalogue

Each row becomes one `Atlas` record. Entries marked *verify* are assumptions to test
before building around them, not established facts.

| id | source | native space | side | notes |
| --- | --- | --- | --- | --- |
| `grabe2015` | Grabe et al. 2015 | LM template (island) | — | No bridge to any EM space. Ships its own stack as the only reference layer. |
| `bates2020` | Bates et al. 2020, Curr Biol, Data S1 | FAFB | L | Delivered as self-contained Plotly HTML; meshes embedded as `mesh3d` traces. |
| `benton2025` | Benton et al. 2025, EMBO Rep, Dataset EV2 | FAFB | L | Manual revision of the Bates meshes, including splitting one glomerulus into two, so `parent = "bates2020"` and the correspondence to `bates2020` is not one-to-one. 3D Slicer `.vtm` / `.vtp` with a `.ctbl` colour table. |
| `flywire_ref` | FlyWire reference glomerulus surfaces | FlyWire/FAFB | *verify* | A distinct resource from the Bates Plotly atlas despite shared nomenclature and a closely related space. |
| `schlegel2021_s11` | Schlegel et al. 2021, eLife, Suppl. file 11 | hemibrain (*verify*) | *verify* | Two mesh sets in one paper; modelled as two atlases. |
| `schlegel2021_s12` | Schlegel et al. 2021, eLife, Suppl. file 12 | hemibrain (*verify*) | *verify* | |
| `neuprint_hemibrain` | neuPrint ROI meshes, hemibrain v1.2.1 | JRCFIB2018F | R complete, L partial | Likely marching-cubes from the ROI label volume. |
| `neuprint_cns` | neuPrint `male-cns:v1.0` ROI meshes | JRCFIB2022M | L + R | **Confirmed.** 59 glomerular ROIs per side, complete and symmetric, named `AL-DA1(L)` exactly as in hemibrain. Meshes are served. Pin **v1.0**: `male-cns:v0.9` exposes only `AL(L)`/`AL(R)` with no subdivisions. |

Two further findings from the neuPrint survey (2026-09-20):

- **The same token works on both `neuprint.janelia.org` and
  `neuprint-cns.janelia.org`**, and both carry `male-cns`. They carry *different*
  hemibrain point releases, though — v1.2.1 and v1.2.2 — so the server is part of an
  asset's identity, not an interchangeable mirror.
- **`flywire-fafb:v783b`** (on the CNS server) exposes `AL_L` / `AL_R` at neuropil
  level only, with no glomerular subdivisions among its 78 ROIs. It is therefore a
  source for the FAFB-space `neuropil` reference assets — an alternative to `fafbseg`
  — and not a glomerular atlas. Note the underscore naming, which differs from
  hemibrain's parenthesised convention.

**These three hemibrain-space entries are assumed distinct** until shown otherwise.
Assuming distinctness is the safe direction: duplicates can be consolidated later
without data loss, whereas collapsing genuinely different segmentations into one record
destroys information silently. The comparison tooling that would settle it is deferred,
not abandoned (§9).

---

## 7. Rendering and UI

**Geometry is stored as meshes.** lobemap rasterized every atlas into a private 256³
label volume normalized to its own bounding box, which is precisely what makes a
space-centric design impossible: physical coordinates are discarded. Storage here is a
concatenated vertex/face array per atlas plus compartment offsets and a names table.

**One napari `Surface` layer per atlas**, whose `data` is rebuilt from the currently
selected compartments. One layer per glomerulus would be simpler but yields an unusable
layer list at ~60 glomeruli × several atlases. Per-compartment colour comes from
`vertex_values` against a step-interpolated categorical colormap.

**Slice view uses explicit contours.** Mesh–plane intersection produces exact polylines,
drawn into a `Shapes` layer, one colour per atlas. This gives crisp, styleable outlines
and is the only overlay mode in which two atlases are genuinely readable together. It is
preferred to relying on napari's built-in surface slicing.

**Rasterization is never the storage format.** Meshes stay meshes; the only
voxel grids here are the reference images and the virtual stains, which are
voxel data to begin with.

**The right-hand panel is the primary selection interface.** napari `Surface` layers do
not support click-to-identify well, so identification and toggling happen in a table.
The table is a *view bound to the selected atlas layer*, joined to the canonical
nomenclature table by `canonical` — never a union across all loaded atlases. That is
what keeps it usable as atlases accumulate.

**Registry over code.** Per-dataset logic splits into (a) declarative TOML registry
records and (b) offline ingest scripts that parse each source format into the canonical
mesh format. The viewer itself is generic and dataset-agnostic. lobemap's 300–700-line
Qt module per dataset is the pattern being avoided.

---

## 8. Tooling and data access

The Python stack is preferred throughout; it is taken to be functionally equivalent to
the R-based counterparts (`hemibrainr`, `natverse`), which are not dependencies.

| package | used for |
| --- | --- |
| [navis-flybrains](https://github.com/navis-org/navis-flybrains) | template registry, bridging registrations between FAFB / FlyWire / hemibrain / JRC2018 / VNC spaces, and mirror registrations. The authority for what `Space.flybrains_template` may contain and for which bridges exist. |
| [fafbseg](https://fafbseg-py.readthedocs.io/en/latest/) | FAFB/FlyWire-side data: neuropil and whole-brain meshes, coordinate-space handling within the FAFB family, and the FlyWire synapse tables feeding the virtual stain (§5). |
| [neuprint-python](https://connectome-neuprint.github.io/neuprint-python/docs/) | hemibrain and male CNS: `fetch_roi_hierarchy` / `fetch_all_rois` for the compartment inventory, `Client.fetch_roi_mesh` for ROI geometry, and synapse queries for the virtual stain. |
| [navis](https://navis.readthedocs.io/) | the transform engine underneath flybrains (`xform_brain`, `mirror_brain`) and mesh I/O. |

All four are **ingest-time and developer-time dependencies**. None should be required to
open a scene: the viewer reads the canonical mesh format and the registry, and network
access or a neuPrint token is needed only to rebuild caches. This also keeps the runtime
free of CMTK (§3).

Note that lobemap sourced its hemibrain surfaces through `hemibrainr`; the equivalent
path here is `neuprint-python`, which also removes an R dependency from the rebuild
pipeline.

---

## 9. Open questions

**Does the male CNS expose glomerulus-level ROIs?** *Answered, 2026-09-20: yes.*
`male-cns:v1.0` carries 59 glomerular ROIs per side — complete and symmetric, unlike
hemibrain's 58 right / 19 left — under hemibrain's `AL-DA1(L)` naming, and
`fetch_roi_mesh()` returns real geometry for them. `male-cns:v0.9` does **not**, so the
version must be pinned. The male CNS is also a genuine space, not an island: its
template is `JRCFIB2022M` and it bridges directly to FAFB14 and FLYWIRE by thin-plate
spline with no downloads required. Grabe remains the only island.

**Are the Schlegel S11/S12 and neuPrint hemibrain mesh sets distinct?** *Assumed
distinct, on measurement.* S11 is receptor-neuron based and S12 projection-neuron
based; their median centroid separation is 1.10 µm against 1.76 and 2.36 µm to
neuPrint, all far below the 6–8 µm seen between animals. Three boundary definitions
of one dataset, not duplicates. All three entries stay.

---

## 10. Out of scope for v1

- Neuron skeletons, synapse-level data, connectivity.
- Editing or authoring atlas geometry.
- Anything requiring CMTK at user runtime.
- Warped whole-brain image templates in EM spaces (§4), deferred in favour of the
  virtual stain (§5).
