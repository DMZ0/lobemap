# Changelog

## Unreleased

### Changed

- Replaced the viewer with a ground-up rewrite, developed separately and
  merged here. It is organised around coordinate SPACES rather than atlases:
  atlases are bridged into a space via navis-flybrains, so several can be
  compared in one scene. Ships a napari GUI (`lobemap view <space>`), OME-Zarr
  multiscale volumes, exact slice contours, per-glomerulus selection and
  labelling, virtual neuropil stains built from presynapse density, and a
  registry of atlases with canonical nomenclature anchored to Benton 2025.
- The console script is `lobemap`; the package is `src/lobemap`. The rewrite
  was called `glomviewer` while it lived in its own repository.
- Removed the previous `lobemap.py` entry point, the `lobemap` shell wrapper
  and `scripts/`, which the rewrite supersedes. They remain on the `legacy`
  branch, as do `docs/usage.md` and the demo media that documented them.
- The published source data the ingested assets are built from is unchanged.
  It moved from `datasets/` to `registry/sources/` later in this same
  unreleased window; see below.
- Version set to 0.2.0.dev0: the two declarations in `pyproject.toml` and
  `__init__.py` disagreed (0.0.0 and 0.1.0.dev0) and both sat below the
  released 0.1.4 on the same PyPI name.

### Added

- Grabe's `VP1` maps to `VP1` rather than to `VP1d;VP1l;VP1m`. GRABE has one atlas, so its vocabulary is that atlas and there is nothing to reconcile against; the merge was a survivor of the global Benton-anchored vocabulary that per-space vocabularies replaced, and it put three names into GRABE that its own geometry cannot tell apart. Its vocabulary is now 54 names, matching the atlas exactly, as the other two single-atlas spaces already did. The correspondence it recorded is cross-space and belongs to `lobemap reconcile`.
- The `canonical` column appears only on atlases that disagree with their space's vocabulary somewhere, and a disagreeing entry is red. Three of the six atlases carry it: the Schlegel rename chain in hemibrain, the VM6 split in S11, Grabe's VP1 merge. Compared on the bare glomerulus, so `AL-DA1(R)` against `DA1` is agreement rather than 77 red rows.
- The filter searches every text column, annotation included, and the placeholder says so — it named only name, canonical and side while already searching the rest.
- The panel buttons sit in two aligned rows — `Filtered`, `Show all`, `Label all`, `Fill all` above `Invert`, `Show none`, `Label none`, `Fill none` — so each column pairs an action with its opposite. `All` and `None` are renamed `Show all` and `Show none`: they were named before `Label` and `Fill` had pairs of their own, and no longer said which of the three they acted on.
- `Fill all` and `Fill none` buttons, beside `Label all` / `Label none`. `Fill all` fills whatever is currently visible, matching how `Label all` behaves.
- The home button ("Reset view to original state") restores the anatomical view: looking down A-P in the posterior direction, dorsal up. `reset_view` sets the camera angles to (0, 0, 0), which is a view down the ARRAY axes — and those are not the anatomical ones, antero-posterior being z in FAFB and y in the hemibrain — so it left the brain at an arbitrary attitude that could only be undone by reopening the scene.
- Axis indicator labels name the single pole each arrow points at — FAFB reads `R, V, P`, the hemibrain `L, A, V` — instead of a direction of travel like `A->P`. The old form was accurate but read like the name of an axis, leaving which end is which to be worked out from the arrow. A pole cannot be read as an axis name, and is derived from where its own arrow goes, so it cannot contradict it.
- A neuropil layer's tab drops the columns that only describe a glomerulus and names its column `neuropil`. It has no compartments behind it, so canonical, side and the five annotation columns were blank while the header claimed the table was about glomeruli. `label` and `fill` stay and still work.
- Table columns size to their widest cell rather than a fixed width, which was truncating the long receptor lists and padding the short ones.
- The glomerulus table sorts. Clicking a header sorts by that column, and it opens sorted by glomerulus name — naturally, so `DA10` follows `DA9` rather than `DA1`.
- A `fill` checkbox per glomerulus, beside `label`, drawing its 2D contour filled rather than as an outline. A napari `path` cannot be filled, so a filled glomerulus is added as a `polygon`; mesh–plane intersections are closed loops, so that is geometrically honest.
- Five annotation columns — `receptor(s)`, `sensillum`, `ALRN`, `organ`, `co-receptor(s)` — from `registry/reference/glomerulus_ground_truth.csv`, joined on the canonical name. Every compartment of every atlas finds a row; receptors are populated for 98% of them.
- `registry/reference/glomerulus_ground_truth.csv`, retained from the upstream `datasets/reference-tables/`.
- `lobemap pack` writes the upload-ready copies of the data artifacts. `manifest` and `fetch --check` zipped a Zarr store to hash it and then deleted the archive, so the bytes a downloader receives could not be obtained; `pack` keeps them, under the names `fetch` requests, and re-hashes each against the manifest.
- `lobemap fetch --nostains`, to skip the virtual stains.

### Changed

- The data is published as release assets and no longer ships in the repository. All fourteen artifacts (2.51 GB) are on the [`data-v1` release](https://github.com/DMZ0/lobemap/releases/tag/data-v1), and `base_url` in the committed manifest points at them. The eleven small assets used to be tracked; splitting the rule by size left two answers to where the data lives, for the 76 MB it saved.
- `lobemap fetch` gets every artifact, including the three virtual stains. `--nostains` skips them, which is 76 MB instead of 2.5 GB; every space still opens, the three EM spaces just without their reference image. Holding them back by default made the obvious command the one that left three of the four spaces looking incomplete for no stated reason.
- `lobemap view` fetches missing required artifacts before opening a scene. Nothing runs on `uv sync`, so this is the first opportunity a fresh clone has to get its data.
- The "no data for this space" report leads with `lobemap fetch` rather than `lobemap build`.
- Reference images are visible whenever they are on disk. They were created hidden and turned back on by each default scene preset, so the default only governed a scene that did not name its own image — `hemibrain_three_ways` opened with the stain off, which nobody had chosen. A preset can still turn one off. The Grabe label volume stays off: it is a segmentation of the glomeruli the meshes already draw.

- Removed the scene concept. `registry/scenes.toml`, `Scene`, `LayerSpec`, `lobemap scenes` and `lobemap view --scene` are gone; a space is the unit the viewer opens. A scene was never a different view of the data — `build_scene` takes a space and loads every atlas native to it, and the preset was applied afterwards and set nothing but `.visible`, so two scenes on one space held identical layers. `spaces.toml` gains `primary_atlas`, replacing `default_scene`, and the rest follows from an asset's role. `lobemap spaces` now reports what each space opens with. The one preset not reproduced is `hemibrain_three_ways`, which is two clicks in the compartment panel.

- `lobemap` with no arguments opens the viewer on FAFB, rather than exiting with a usage message. `lobemap view` also takes the default.
- Removed the JRC2018U space. It held no atlas, so there was nothing to open in it, and it appeared in `lobemap spaces` as though there were.
- Removed ten unused folders from `datasets/`: banc, comparative-atlases, door, edmond-fibsem, flywire, flywire-codex, laissue-1999, potter-task-2022, reference-tables and vfb. No recipe or module read any of them. `docs/data-sources.md` is rewritten around the six atlases the viewer actually opens, and covers only those; source folders kept without being used are described in `registry/sources/`, beside the files.
- `datasets/` is gone. The five remaining folders are `registry/sources/<dataset>/`, with the redundant `data/source/` level flattened away, and the registry is now self-contained: a recipe's `source` and its path-valued params resolve against the registry root rather than the repository root, so `--registry` can point anywhere. The per-dataset napari modules and the 256-cube label caches were not carried over — they belong to the viewer this one replaced and are on the `legacy` branch, which still holds the whole original tree.
- Removed the `hemibrain/` source folder. Its `hemibrainr` surface export covers the same 58 glomeruli as the live neuPrint query, which resolves two of them further (`VC3l`/`VC3m` where the export had `VC3`). Three annotation tables went with it — receptor, ligand and valence per glomerulus, and Virtual Fly Brain FBbt terms — which were not redundant, only unused. All of it is on the `legacy` branch.
- `--data-root` is honoured by `validate`, `check`, `reconcile`, `bridge` and `build`, which all built a registry without it. It mattered most in `build`, which resolved its target against the default root, so building into a scratch data root overwrote the real asset.

### Fixes

- Showing a glomerulus in 2D no longer switches its mesh on underneath the slice. `AtlasSurface.refresh` turns its layer on whenever something is selected — right in 3D — and the display-mode hook only fires on an `ndisplay` change, so nothing put the mesh back. Showing now draws whichever layer the current mode can read: contours in 2D, meshes in 3D. This also fixes the other half, that showing in 2D left the contours off.
- Filling a neuropil contour no longer raises `could not convert string to float`. A layer's colour is not always a sequence of numbers — the neuropil shells are the hex string `#9aa0a6`, and indexing that yields `#`. Colour specs now go through napari's own parser, so names, hex and arrays all work.
- `lobemap view` no longer prints a `crash log: ...` line on every launch, and no longer leaves an empty log behind. faulthandler is still armed — a native vispy/Qt/driver fault would otherwise kill python with no trace — but it now reports only when something was written, deletes its file on a clean exit, and sweeps empties left by runs that were killed rather than exited. Measured before the change: 54 empty files out of 55 launches, against one real report. A log still held open by a live viewer cannot be unlinked, so those are skipped.
- The anatomical axis indicator is drawn as a canvas overlay rather than a scene one, so it is visible in the default view of every space. A scene overlay sits at the world origin, which is not inside the data: FAFB spans x 192-853 um, so its indicator was ~190 um off-screen, and the male CNS showed part of one.
- Removed three `*_stain.progress.log` files committed by accident.
- A data release no longer starts a PyPI workflow run. It fired on every published release and failed at the tag check, mailing a failure for a release that was never meant to build a package.

### Notes

- Data under `registry/data/` is gitignored and fetched; `registry/manifest.toml` records what belongs there and each file's sha256. See `registry/data/README.md` for how each asset is rebuilt from source.

## 0.1.4 - 2026-08-20

### Fixes

- Corrected GH146-GAL4 status for V, VM5v, VP2, and VP3 from the Grabe source tables.

### Changes

- Moved all dataset files under `datasets/` and kept installed atlas data available without downloads or cache generation.

## 0.1.3 - 2026-05-16

### Changes

- Added driver-line glomerulus presets, including `Orco-GAL4 & GH146-GAL4`, to atlas glomerulus tables.
- Added a `lobemap --version` option for package install checks.

## 0.1.2 - 2026-05-11

### Changes

- Increased Grabe 2015 slice label size to make glomerulus labels easier to read.

## 0.1.1 - 2026-05-10

### Changes

- Switched README demo images to absolute raw GitHub URLs so they render on the PyPI project page.
- Added repeatable PyPI release documentation and GitHub Actions Trusted Publishing workflow.

## 0.1.0 - 2026-05-10

Initial PyPI release.

### Features

- Installable Python package with the `lobemap` command-line entrypoint.
- Napari viewer for Drosophila antennal lobe atlas datasets.
- Atlas selector for Grabe 2015, Bates Schlegel 2020, hemibrain, FlyWire, Benton 2025, JRC2018Unisex, DoOR, Potter Task 2022, Virtual Fly Brain, and BANC resources.
- Tracked runtime source tables, volumes, and derived caches needed by installed viewers.
- Reference table for glomerulus names, receptors, sensilla, ligands, valence, driver lines, VFB IDs, and atlas coverage.
