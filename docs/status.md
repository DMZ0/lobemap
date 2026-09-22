# lobemap — build status

Where the implementation stands against
[implementation-plan.md](implementation-plan.md). Measured results live in
[findings.md](findings.md); architecture in [design.md](design.md).

Last updated 2026-09-21.

---

## Summary

| milestone | state |
| --- | --- |
| M0 — de-risk the transform chain | **done** |
| M1 — core model and registry | **done** |
| M2 — walking skeleton in napari | **done** |
| M3 — `resolve()`, caching, validation harness | **done** |
| M4 — remaining ingests and nomenclature | **done** |
| M5 — viewer UX | **done** |
| M6 — reference assets and virtual stain | **done** |
| M7 — distribution | **done** (metrics dropped, see below) |

**26/26 validation checks pass. 231 tests. Lint clean.**

Registry: 7 atlases, 5 spaces, 16 assets, 8 scene presets, 58 canonical names
(Benton 2025's published names, enforced by `Registry.validate`).
All three whole-brain virtual stains are built (findings §7).

---

## What exists

```
src/lobemap/
  core/
    model.py        Space, Asset, Atlas, Compartment, Derivation, Scene,
                    lateral_convention + apparent/biological side conversion
    registry.py     TOML -> objects, validation, mesh/volume accessors
    meshfmt.py      MeshSet: concatenated meshes + per-compartment offsets, um
    imagefmt.py     Volume: data + voxel_um + origin_um, napari scale/translate
    zarrfmt.py      OME-Zarr (NGFF 0.4) store with a multiscale pyramid
    meshrepair.py   per-component watertight repair (trimesh -> pymeshfix)
    names.py        nomenclature, correspondence relations, ROI name parsing
    spaces.py       flybrains adapter: routing policy, mirror, tool versions
    resolve.py      bridge + cache (content hash + route + tool versions)
    manifest.py     fetchable artifacts: checksums, verify, download
  ingest/
    neuprint_rois.py   hemibrain / male CNS ROI meshes
    bates_plotly.py    Bates 2020 Plotly HTML
    slicer_vtm.py      Benton 2025 3D Slicer .vtm/.vtp
    obj_archive.py     Schlegel S11/S12 STL zips (also .obj/.7z)
    label_volume.py    Grabe masks -> marching cubes
    image_stack.py     TIFF/NRRD -> Volume, + verify_against_labels
    csv_meshes.py      vertex/face CSV tables
    virtual_stain.py   binned-KDE accumulator, blur, Volume assembly
    stain_slabs.py     slab-partitioned build for grids too big for RAM
    synapse_buckets.py hemibrain shards / male CNS feather / FAFB CSV
    synapse_sources.py neuPrint slab streaming  [being replaced, see below]
  validate/
    geometry.py     scale, containment, roundtrip, correspondence
    images.py       covers-mesh, brightness-at-mesh, inside-shell
    reconcile.py    geometric name reconciliation with ambiguity test
  viewer/
    app.py          scene assembly, bridged layers, image layers, picking
    layers.py       AtlasSurface: alpha repaint + debounced compaction
    contours.py     exact mesh-plane intersections as Shapes (2D)
    panel.py        compartment table joined to nomenclature
  cli.py            view, scenes, validate, spaces, check, reconcile,
                    nomenclature, bridge, repair, stain, tozarr,
                    manifest, fetch, ingest {neuprint,bates}
registry/
  spaces.toml assets.toml atlases/*.toml scenes.toml nomenclature.csv
  data/           ingested .npz (meshes) and .zarr (volumes),
                  gitignored and rebuildable
tests/            231 tests, offline except where marked
```

---

## M6 — what is done and what is not

### Done

- **`Volume` container and image assets** end to end: registry support,
  napari layers with `scale`/`translate` from the Volume itself.
- **Three image validators** — covers-mesh, brightness-at-mesh,
  inside-shell — and they run for images in a space with **no native atlas**
  by bridging one in, which previously left JRC2018U entirely unchecked.
- **Grabe confocal stack** (`grabe2015_stack`), 5.70× brightness at
  glomerulus centroids.
- **JRC2018U nc82** (`jrc2018u_nc82`), 3.81× against bridged Bates.
- **FAFB neuropils** (`fafb_neuropil`): all 78 that
  `fafbseg.flywire.get_neuropil_volumes` serves, bridged FLYWIRE → FAFB14
  (0 warps; 10 vertices outside the offset field keep their input
  coordinates). `get_neuropil_volumes` has no whole-brain entry, so the brain
  outline is their union — which is why the Bates Plotly brain mesh was
  dropped rather than kept as a separate layer.
- **Virtual stain machinery**: accumulator, separable blur, uint8 output with
  recorded intensity scale, full `Derivation`. Proven by the AL preflight
  (§7 of findings): 286× inside/outside contrast.

### The whole-brain stains — done

Built from the published bulk releases via
`ingest/synapse_buckets.py` (one loader per source). Presynapses only;
σ = 450 nm; 0.25 µm grid; uint8; male CNS cropped to brain. Numbers, the
verification behind each coordinate convention, and why 0.25 µm does not
raise the resolution are in findings §7.

Grids past ~0.4 G voxels are built slab by slab through disk
(`ingest/stain_slabs.py`); peak RAM is independent of grid size.

Volumes are stored as **OME-Zarr** (NGFF 0.4) with a 5–6 level pyramid: the
three stains total 2.44 GB, down from 21.9 GB as uint16 `.npy`. The npz path
remains for small volumes and for reading what already exists. Meshes stay
`.npz` and no longer require `allow_pickle` (findings §7).

`ingest/synapse_sources.py` keeps the neuPrint slab-streaming path as a
fallback and for ROI-scoped queries; it is marked superseded for stain
building.

### Viewer defaults

Every space with an atlas names a `default_scene`, which `lobemap view
<space>` applies: **one** atlas plus that space's reference image, rather
than every atlas stacked on top of each other. FAFB opens on Benton,
hemibrain on neuPrint hemibrain, male CNS on neuPrint male CNS, Grabe on
Grabe with its confocal channel in place of a stain.

Image display is per role (`viewer.app.ROLE_DISPLAY`), with `colormap`
overridable per asset in `assets.toml`. A virtual stain gets magenta,
gamma 0.7 and `attenuated_mip` at attenuation 0.1 — gamma below 1 because a
synapse-density distribution is long-tailed, and attenuation because plain
MIP through a whole brain is a flat wash.

**Glomeruli are coloured by canonical name**, so the same glomerulus is the
same colour in every atlas. Previously colour came from a compartment's
position in its own file, which made DA1 orange in Bates and red-brown in
Benton.

**Slice labels are per glomerulus.** Each contour layer can write compartment
names onto the slice, chosen by a `label` checkbox in the panel — off by
default, because several atlases in one scene would otherwise write every
name two or three times over. A compartment crossing the plane as several
contours is labelled once, on the longest. napari's own layer controls carry
a global text toggle on top of this.

**The window opens maximised**, through Qt since napari exposes no API for
it, and failing silently where there is no window manager. It takes
`showNormal()` then `showMaximized()`, deferred onto the event loop: called
earlier, or without clearing the state first, Qt reports the window
maximised while leaving it at 933x700. The view is refitted on the first
canvas resize for the same reason: fitting immediately after the maximise
call uses the old canvas and leaves the brain filling 27% of a full-screen
window, against 81% once it waits.

**Grabe keeps its original voxel masks** as a hidden Labels layer beside the
meshes surfaced from them, so the smoothing can always be checked against
its input. Stored as npz, not zarr: a pyramid would average label ids.

**The camera faces anterior with dorsal up in 3D**, from per-space
`anterior`/`dorsal` axes in `spaces.toml`. All four spaces holding an atlas
declare both, determined twice over and agreeing: from positional glomerulus
nomenclature (D/V first letter, A/P second, averaged over ~58 centroids,
0.92–0.99 dominance) and from handedness — the animal's left falls on the
viewer's right, inverted in FAFB because its image data is. The axes differ
between spaces: hemibrain's antero-posterior axis is y where FAFB's and the
male CNS's is z.

The camera is turned 1° off axis on purpose (`GIMBAL_NUDGE_DEG`). A face-on
view is an exact gimbal-lock singularity for the Euler angles napari stores
its camera in, and its vispy round trip returns a **negated** up vector
there — the brain renders upside down, silently. A test pins that napari
behaviour so the nudge can be removed if it is ever fixed.

---

## M7 — distribution done; metrics dropped

**Comparison metrics were removed at the user's request.** They were never in
the original specification — I put them in the plan unprompted, and they are
not part of what lobemap is for. `compare/` and `lobemap compare` are
gone, along with the `manifold3d` dependency they needed.

1. **Distribution**. `lobemap manifest` and `lobemap fetch`, with
   sha256 over the transferred bytes and a deterministic zip for `.zarr`
   directories. The registry now separates metadata (ships) from data
   (fetched, defaulting to the user cache directory when there is no
   `registry/data`, which is the installed-from-a-wheel case).

### Still open in M7

- **`base_url` is unset**: nothing is published. The mechanism is complete and
  tested over `file://`; it needs a host (Zenodo is the obvious one).
- **The wheel does not yet carry the registry metadata.** `DEFAULT_REGISTRY`
  resolves relative to the source tree, so an installed wheel finds nothing
  unless `--registry` or `LOBEMAP_REGISTRY` is set. Packaging it means
  moving `registry/*.toml` under `src/lobemap/`.

---

## Known gaps and deliberate omissions

- **CMTK is installed but non-functional on Windows** (findings §2). Costs
  nothing: the two CMTK routes are a tie or avoidable.
- **The `flywire_ref` atlas was removed** at the user's request — it was taken
  from lobemap, not the requested catalogue, and measured as Bates geometry in
  FlyWire coordinates (0.50 µm). `FLYWIRE` is no longer a registered space;
  navis still routes through it internally.
- **VM6 is absent from Grabe** (no voxels in the "only sure ones" label
  volume) and only Schlegel S11 realises its three-way split.
- **Grabe left/right provenance** is an open question for the authors
  (findings §3).
- **Schlegel's unpublished FAFB meshes** exist but are not available; S11/S12
  are the hemibrain ones.
- **`grabe2015` sits outside the VC3/VC5/VM6 rename classification**
  (findings §7). It predates the VC3l/VC3m split, so its `VC3` is unsplit and
  its `VC5` is probably old-VC5 (= new VM6) — but GRABE is an island space
  with no bridge, so unlike the other atlases this cannot be settled
  geometrically. Its three entries are unchanged pending the authors.
- **Two atlases resolve glomeruli at a different grain than the vocabulary**,
  and both are kept rather than flattened: Schlegel S11 splits `VM6` into
  VM6l/VM6m/VM6v (`split`), and Grabe does not resolve `VP1` into
  VP1d/VP1l/VP1m (`merge`). Flattening S11 was considered and rejected —
  Grabe's cannot be flattened the other way, so doing one and not the other
  would be inconsistent.
- The repo has **no licence** yet.

---

## Rebuilding from scratch

`registry/data/*.npz` and `*.zarr` are gitignored and rebuildable; see
`registry/data/README.md` for the ingest commands. Needs
`NEUPRINT_APPLICATION_CREDENTIALS` and, for FAFB neuropils, the CAVE secret.
The flybrains bundles must be downloaded once
(`flybrains.download_jrc_transforms()` + `download_jefferislab_transforms()`).
