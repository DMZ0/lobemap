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
- `datasets/` is unchanged and still holds the published source data the
  ingested assets are built from.
- Version set to 0.2.0.dev0: the two declarations in `pyproject.toml` and
  `__init__.py` disagreed (0.0.0 and 0.1.0.dev0) and both sat below the
  released 0.1.4 on the same PyPI name.

### Notes

- Built assets under `registry/data/` are gitignored and rebuildable; see
  `registry/data/README.md`. `lobemap manifest` records their hashes.

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
