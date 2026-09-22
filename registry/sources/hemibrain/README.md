# hemibrain (natverse export)

Antennal-lobe glomerulus surfaces exported from `hemibrainr`:

Schlegel P, et al. `hemibrainr`: code for working with Janelia FlyEM hemibrain
data. https://github.com/natverse/hemibrainr

**Nothing in the registry reads this.** The hemibrain glomeruli are queried live
from neuPrint instead (`hemibrain:v1.2.1`), which carries the ROI hierarchy and
the whole-brain neuropil set as well. Kept because the export is a different
derivation of the same geometry, and the tables beside it are reference data
this viewer does not currently present.

## What is here

- `hemibrain_al_microns_vertices.csv.gz`, `hemibrain_al_microns_faces.csv.gz` —
  the exported surfaces, in microns.
- `hemibrain_al_microns_materials.csv` — glomerulus names per material id.
- `hemibrain_glomeruli_summary.csv` — per-glomerulus summary table.
- `vfb_glomerulus_terms.csv` — Virtual Fly Brain FBbt ids, definitions and
  synonyms.
- `odour_scenes.csv` — odour response groupings.
- `natverse_export_versions.txt` — the package versions the export was made
  with.
- `validation/coordinate_axes.csv`, `validation/label_extents.csv` — the axis
  convention of the export, and each glomerulus's voxel span. The export uses
  `Z, Y, X` as dorsal-ventral, antero-posterior and lateral-medial; the
  antero-posterior `Y` is documented by `hemibrainr` and the other two follow
  the hemibrain mesh convention.
- `scripts/` — how the surfaces and the VFB terms were obtained.
