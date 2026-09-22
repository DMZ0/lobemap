# lobemap

A [napari](https://napari.org) viewer for *Drosophila* antennal lobe
glomerular atlases.

Several groups have published glomerular parcellations of the antennal lobe,
each from a different volume and each using its own names. lobemap puts them
in one viewer so they can be looked at side by side: as 3D meshes, or as
exact cross-sections on a slice through the underlying image.

Scenes are organised by **coordinate space** rather than by atlas. A scene is
a space — FAFB, the hemibrain, the male CNS, the Grabe light-microscopy
template — and it holds every atlas native to that space at once, together
with that space's neuropil geometry and reference images.

## Installing

Python 3.11 or 3.12, and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/DMZ0/lobemap
```

```bash
cd lobemap && uv sync
```

## Quick start

```bash
uv run lobemap view GRABE
```

That opens the Grabe 2015 scene, which needs no extra data. To list what else
is available:

```bash
uv run lobemap scenes
```

```bash
uv run lobemap view JRCFIB2018F
```

`lobemap` is installed into the project's virtual environment, so `uv run`
is the simplest way to reach it. Activating the environment
(`.venv/Scripts/Activate.ps1` on Windows, `source .venv/bin/activate`
elsewhere) lets you drop the prefix. The registry is found relative to the
installed package, so the commands work from any directory.

## What is included

| space | atlas | compartments |
|---|---|---|
| FAFB14 | Benton 2025 (Dataset EV2) | 58 |
| JRCFIB2018F (hemibrain) | neuPrint hemibrain | 77 |
| | Schlegel 2021 S11, from receptor neurons | 59 |
| | Schlegel 2021 S12, from projection neurons | 58 |
| JRCFIB2022M (male CNS) | neuPrint male CNS | 116 |
| GRABE | Grabe 2015 | 108 |

Each space also carries its brain neuropils, and most carry a reference
image: the Grabe confocal stack, or a **virtual neuropil stain** — the
density of predicted presynapses, binned and blurred to something that looks
like an nc82 antibody stain, computed natively in each EM volume rather than
warped in from light microscopy.

Glomerulus names are scoped to a space. Two atlases can only be superimposed
if they share one, so that is the only place their names have to agree, and
each space keeps its own vocabulary rather than deferring to a single
authority. Switching scenes may therefore change both the list of glomeruli
and their colours.

## Data

The atlas and neuropil meshes ship with the repository — about 72 MB, so a
fresh clone opens every scene. The three virtual stains do not: they are
2.3 GB, and each is regenerated often enough that committing them would add
a permanent copy to the history every time.

Build them when you want them:

```bash
uv run lobemap build --list
```

```bash
uv run lobemap build hemibrain_stain
```

Each stain needs several gigabytes downloaded from the published synapse
releases, about 40 GB of scratch space, and a long run, so `build --all`
skips them and they have to be asked for by name. Everything else is
derived from sources that either ship in `datasets/` or are downloaded
automatically; `registry/recipes.toml` records exactly how.

A rebuilt asset is not byte-identical to the original — every pipeline
stamps the date it ran — but its *content* hash is, and the build prints it.

## In the viewer

- **3D** draws the meshes. **2D** draws exact mesh–plane contours, computed
  by intersection rather than rasterised, so they stay sharp at any zoom.
- Each glomerulus keeps one colour across the atlases of its space, in 3D,
  in 2D and on its slice label.
- The right-hand panel has a tab per atlas: a checkbox to show each
  glomerulus, and a second to write its name on the slice.
- The control at the bottom right switches between scenes without
  restarting.
- Reference images start hidden. `--show` reveals one by asset id or by
  role, for example `--show virtual_stain`.

Both the mesh and contour layers stay in the layer list in either mode; the
one the current mode cannot draw is simply switched off.

## Checking the data

```bash
uv run lobemap check
```

This is a geometric harness, not a schema check: it confirms every
glomerulus centroid lies inside its own antennal lobe, that each reference
image is brighter at glomerulus centroids than at background, and that
images and meshes occupy the same box in micrometres. An asset can be
present, well-formed and in the wrong place, and only a measurement catches
that.

`lobemap --help` lists the rest, including tools for comparing atlases by
geometry (`reconcile`) and moving geometry between spaces (`bridge`).

## Documentation

- [docs/design.md](docs/design.md) — why scenes are spaces, and the data model
- [docs/findings.md](docs/findings.md) — measurements, including the ones that
  overturned an assumption
- [docs/data-sources.md](docs/data-sources.md) — where each dataset came from

## Lineage

This is a fork of [lobemap](https://github.com/gumadeiras/lobemap) by
Gustavo Madeira Santana. The viewer has been rewritten around coordinate
spaces, and the ingest, registry and validation are new, but the curated
nomenclature tables and the source datasets under `datasets/` come from the
original and remain its work.

## License

MIT, inherited from the original — see [LICENSE](LICENSE).

The datasets are not covered by it. Each retains the license and citation
requirements of its own publication, recorded per asset in
`registry/assets.toml` and in
[docs/data-sources.md](docs/data-sources.md). If you use an atlas, cite the
paper it came from.
