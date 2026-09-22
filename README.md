# lobemap

A [napari](https://napari.org) viewer for *Drosophila* antennal lobe
glomerular atlases.

Several groups have published glomerular parcellations of the antennal lobe,
each from a different volume and each using its own names. lobemap puts them
in one viewer so they can be looked at side by side: as 3D meshes, or as
exact cross-sections on a slice through the underlying image.

The unit the viewer opens is a **coordinate space** — FAFB, the hemibrain,
the male CNS, the Grabe light-microscopy template — not an atlas. A space
holds every atlas native to it at once, together with that space's neuropil
geometry and reference image. That is what lets two parcellations of the
same volume be superposed: sharing a space is exactly the condition under
which comparing them means anything.

## Installing

Python 3.11 or 3.12, and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/DMZ0/lobemap
```

```bash
cd lobemap && uv sync
```

Then fetch the data, which is published separately rather than committed:

```bash
uv run lobemap fetch
```

That is 76 MB: every atlas, every neuropil set and the Grabe confocal
stack, which is enough to open all four spaces. It leaves out the virtual
stains, described under [Data](#data) below, because they are 2.4 GB.

## Quick start

```bash
uv run lobemap
```

That opens FAFB. To list the spaces and what each will put on screen:

```bash
uv run lobemap spaces
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

Each space also carries its brain neuropils and one reference image. For
Grabe, which is light microscopy, that is its own confocal stack. For the
three EM spaces it is a **virtual neuropil stain**: the density of
predicted presynapses, binned and blurred into something that reads like an
nc82 antibody stain, computed natively in each volume rather than warped in
from light microscopy.

Glomerulus names are scoped to a space. Two atlases can only be superimposed
if they share one, so that is the only place their names have to agree, and
each space keeps its own vocabulary rather than deferring to a single
authority. Switching space may therefore change both the list of glomeruli
and their colours.

## Data

None of the data is committed. All fourteen artifacts are published as
assets on the [`data-v1`
release](https://github.com/DMZ0/lobemap/releases/tag/data-v1) — 2.51 GB,
of which the three virtual stains are 2.44 GB, which is why a plain `fetch`
leaves them out. `registry/manifest.toml` records the sha256 of every one,
and `lobemap fetch` checks each download against it; a file that does not
match is discarded rather than kept.

```bash
uv run lobemap fetch --all
```

gets the stains as well, or name one to fetch it on its own.

`lobemap view` fetches anything a scene needs and cannot find, so in
practice the explicit `fetch` above is a way to get it over with rather
than a requirement. The stains are never fetched implicitly, because
every scene opens without one — but a stain that *is* on disk is shown,
so fetching one changes what you see the next time that scene opens.

You can also rebuild from source instead of downloading:

```bash
uv run lobemap build --list
```

```bash
uv run lobemap build hemibrain_stain
```

Each stain needs several gigabytes downloaded from the published synapse
releases, about 40 GB of scratch space, and a long run, so `build --all`
skips them and they have to be asked for by name. Everything else is
derived from sources that either ship in `registry/sources/` or are downloaded
automatically; `registry/recipes.toml` records exactly how.

A rebuilt asset is not byte-identical to the original — every pipeline
stamps the date it ran — but its *content* hash is, and the build prints it.
`lobemap pack` writes the upload-ready copies if you are republishing.

## In the viewer

- **3D** draws the meshes. **2D** draws exact mesh–plane contours, computed
  by intersection rather than rasterised, so they stay sharp at any zoom.
- Each glomerulus keeps one colour across the atlases of its space, in 3D,
  in 2D and on its slice label.
- The right-hand panel has a tab per atlas: a checkbox to show each
  glomerulus, and a second to write its name on the slice.
- The control at the bottom right switches between spaces without
  restarting.
- A space with several atlases opens on one of them — `primary_atlas` in
  `registry/spaces.toml` — with the rest loaded and switched off, since two
  glomerular parcellations drawn on top of each other are unreadable. The
  panel's tabs turn the others on.
- A space's reference image — the virtual stain, or the Grabe confocal
  channel — is shown whenever it has been fetched. `--show` turns on a
  layer that is off, by asset id or by role, for example `--show
  neuropil`.
- The axis indicator in the bottom-left corner is labelled anatomically,
  as a direction of travel: `P->A` on the axis that runs posterior to
  anterior. Which array axis that is differs between spaces, so the labels
  change when you switch.

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

- [docs/design.md](docs/design.md) — why the viewer is organised around
  spaces, and the data model
- [docs/findings.md](docs/findings.md) — measurements, including the ones that
  overturned an assumption
- [docs/data-sources.md](docs/data-sources.md) — where each dataset came from

## Lineage

This is a fork of [lobemap](https://github.com/gumadeiras/lobemap) by
Gustavo Madeira Santana. The viewer has been rewritten around coordinate
spaces, and the ingest, registry and validation are new, but the curated
nomenclature tables and the published source data under `registry/sources/`
come from the original and remain its work.

## License

MIT, inherited from the original — see [LICENSE](LICENSE).

The datasets are not covered by it. Each retains the license and citation
requirements of its own publication, recorded per asset in
`registry/assets.toml` and in
[docs/data-sources.md](docs/data-sources.md). If you use an atlas, cite the
paper it came from.
