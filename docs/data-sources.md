# Data Sources

Every atlas and reference volume the viewer can open, and where it came from.
`registry/assets.toml` carries the same provenance per asset, machine-readable,
and is the authority if the two ever disagree.

Nothing here is redistributed under a licence of lobemap's own. Each dataset
keeps the licence and citation requirements of its own publication. **If you use
an atlas, cite the paper it came from.**

Paper PDFs are not tracked. Their links are in
[`paper-pdf-sources.csv`](../registry/sources/paper-pdf-sources.csv).

## What the viewer opens

Four coordinate spaces, six atlases. A space also carries its brain neuropils
and one reference image.

| space | atlas | compartments | source |
|---|---|---|---|
| FAFB14 | Benton 2025 | 58 | Dataset EV2, ships in `registry/sources/` |
| JRCFIB2018F | neuPrint hemibrain | 77 | neuPrint `hemibrain:v1.2.1` |
| | Schlegel 2021 S11 | 59 | eLife supplementary file 11 |
| | Schlegel 2021 S12 | 58 | eLife supplementary file 12 |
| JRCFIB2022M | neuPrint male CNS | 116 | neuPrint `male-cns:v1.0` |
| GRABE | Grabe 2015 | 108 | Amira label volume, ships in `registry/sources/` |

## Benton 2025 — FAFB14

Folder: [`benton-2025/`](../registry/sources/benton-2025/)

Glomerular segmentation of FAFB, read from the published Slicer scene
(`DatasetEV2.seg.vtm`). The names are FAFB's vocabulary; the nomenclature table
records how the other atlases map onto them.

- Benton R, et al. *EMBO Reports*, 2025. doi:10.1038/s44319-025-00476-8

## Schlegel 2021 — JRCFIB2018F

Downloaded from the eLife CDN at build time (CC BY 4.0), not tracked:

```
https://cdn.elifesciences.org/articles/66018/elife-66018-supp11-v2.zip
https://cdn.elifesciences.org/articles/66018/elife-66018-supp12-v2.zip
```

Two independent parcellations of the same volume — S11 traced from receptor
neurons, S12 from projection neurons — which is why both are kept. Supplementary
file 11 ships 59 meshes rather than the 60 its caption states; VM2 is absent.
Verified against a fresh download, and recorded in `docs/findings.md`.

- Schlegel P, Bates AS, et al. *eLife*, 2021. doi:10.7554/eLife.66018

## neuPrint — JRCFIB2018F and JRCFIB2022M

Queried live through `neuprint-python`, so nothing is tracked. Needs
`NEUPRINT_APPLICATION_CREDENTIALS`. Both the glomeruli and the whole-brain
neuropil set come from the ROI hierarchy; see `registry/data/README.md` for the
exact commands.

- hemibrain: https://neuprint.janelia.org — Scheffer LK, et al. *eLife*, 2020.
  doi:10.7554/eLife.57443 (CC BY 4.0)
- male CNS: https://neuprint-cns.janelia.org — `male-cns:v1.0`

## Grabe 2015 — GRABE

Folder: [`grabe-2015/`](../registry/sources/grabe-2015/)

A light-microscopy template rather than EM, and an island: no bridging
registration connects it to any other space. Three assets come from it — the
glomerular meshes, the label volume they were surfaced from, and the confocal
stack that serves as its reference image. The meshes are surfaced from the Amira
label volume rather than the published OBJ export; `registry/assets.toml` says
why.

- Grabe V, Strutz A, Baschwitz A, Hansson BS, Sachse S. *Journal of Comparative
  Neurology*, 2015. doi:10.1002/cne.23697
- Grabe V, et al. *Cell Reports*, 2016. doi:10.1016/j.celrep.2016.08.063

## FAFB neuropils

Whole-brain neuropil meshes from the FlyWire segmentation, via
[`fafbseg-py`](https://github.com/navis-org/fafbseg-py).

These are coarse — about 394 vertices and 7 µm facets — and visibly so beside
the neuPrint sets. Warped male CNS meshes were tried as a replacement and
reverted: smoother, but a measurably worse fit to FAFB. `docs/findings.md` has
the measurement.

## Virtual neuropil stains

Not an atlas: a synthetic reference image, one per EM space. Presynapse density
binned at 0.25 µm and blurred with a 450 nm Gaussian, which reads like an nc82
antibody stain while being computed natively in each volume rather than warped
in from light microscopy. Built from the published synapse releases, about 20 GB
of input that is not kept:

| space | source |
|---|---|
| JRCFIB2018F | `gs://neuroglancer-janelia-flyem-hemibrain/v1.2/synapses/by_id/` |
| JRCFIB2022M | `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/syn-points-male-cns-v1.0-minconf-0.5.feather` |
| FAFB14 | FAFB v783 Princeton synapse table — Dorkenwald S, et al. *Nature*, 2024. doi:10.1038/s41586-024-07558-y |
