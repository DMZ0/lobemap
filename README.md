# lobemap

A napari application for viewing and comparing *Drosophila* antennal lobe glomerular
atlases in their native and bridged coordinate spaces.

**Status: M0-M7 complete.** Seven atlases across five coordinate spaces, plus
whole-brain virtual neuropil stains for all three EM volumes, stored as
multiscale OME-Zarr; see
[docs/status.md](docs/status.md).

Scenes are organized by *coordinate space* (FAFB, hemibrain, JRC2018U, male CNS,
Grabe), not by atlas. Within a scene, any number of glomerular atlases — native to that
space or bridged into it with navis-flybrains — can be shown together alongside the
neuropil, whole-brain, and reference-image layers belonging to that space.

- [docs/design.md](docs/design.md) — architecture, data model, atlas catalogue, open questions
- [docs/implementation-plan.md](docs/implementation-plan.md) — build order and acceptance criteria
- [docs/status.md](docs/status.md) — what is built, what remains
- [docs/findings.md](docs/findings.md) — measured results, with the numbers behind them

## Running it

The `lobemap` command lives in the project's virtual environment, so it is
not on `PATH` until that environment is active. Any of these work:

```powershell
# from the repo, without activating anything
uv run lobemap view FAFB14 --show virtual_stain

# or activate once, then use the short form for the rest of the session
.\.venv\Scripts\Activate.ps1
lobemap view FAFB14 --show virtual_stain

# or call it by full path, from anywhere
C:/Users/<you>/Documents/GitHub/lobemap/.venv/Scripts/lobemap.exe scenes
```

The registry is located relative to the installed package, so the commands
work from any working directory. `lobemap --help` lists the rest;
`lobemap scenes` lists the named presets.

In the viewer: **2D** shows the slice contours and steps through z; **3D**
shows the meshes. The layer list holds only what the current mode uses.
Image layers start hidden, which is what `--show` overrides -- it takes an
asset id or a role such as `virtual_stain`.

## Relationship to lobemap

lobemap is a from-scratch successor to
[lobemap](https://github.com/gumadeiras/lobemap) by Gustavo Madeira Santana. It reuses
that project's ideas, curated nomenclature tables, and some source-format ingest logic,
but replaces its per-atlas viewer architecture and its rasterized label-volume storage.

## License

Not yet chosen. Data files retain the rights and citation requirements of their
original sources.
