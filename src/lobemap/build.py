"""Derive a built asset from its source, per `registry/recipes.toml`.

Every asset under `registry/data/` is derived, which is the justification for
keeping the large ones out of git. That justification was only half true: the
pipelines all existed, but which one to run for which asset, and with what
arguments, lived as prose in `registry/data/README.md`. Nine of the fifteen
assets had no runnable path at all, so "rebuildable" meant "rebuildable by
someone who reads the source and retypes the snippets".

This turns the recipes into data and runs them.

**A rebuild is not byte-identical to the original, and cannot be.** Every
pipeline stamps `retrieved` with the current date, so the file's sha256
differs from the day it was first built. `manifest.toml` therefore verifies
TRANSFER integrity -- that a download arrived intact -- and not
reproducibility. What is reproducible is the `content_hash` each container
computes over its actual content: vertices, faces and names for a MeshSet,
voxels and geometry for a Volume. That is what `--expect` checks, and what
the build reports so it can be recorded.
"""

from __future__ import annotations

import shutil
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RECIPES = "recipes.toml"

#: Downloaded sources are cached here, under the data root, so a second
#: build of the same asset does not re-fetch.
CACHE_DIR = ".build"

_PIPELINES: dict[str, object] = {}


def pipeline(name: str):
    def register(fn):
        _PIPELINES[name] = fn
        return fn
    return register


@dataclass
class Recipe:
    asset: str
    pipeline: str
    source: str | None = None
    url: str | None = None
    params: dict = field(default_factory=dict)


@dataclass
class BuildResult:
    asset: str
    path: Path
    content_hash: str
    notes: list[str] = field(default_factory=list)


def load_recipes(registry_root) -> dict[str, Recipe]:
    path = Path(registry_root) / DEFAULT_RECIPES
    if not path.exists():
        return {}
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    out = {}
    for asset, body in spec.items():
        out[asset] = Recipe(
            asset=asset,
            pipeline=body["pipeline"],
            source=body.get("source"),
            url=body.get("url"),
            params=dict(body.get("params", {})),
        )
    return out


def resolve_source(recipe: Recipe, repo_root: Path, cache: Path,
                   progress=None) -> Path | None:
    """The local file a recipe reads, downloading it first if it is a URL."""
    if recipe.source:
        path = repo_root / recipe.source
        if not path.exists():
            raise FileNotFoundError(
                f"{recipe.asset}: source {recipe.source} is missing. It is "
                f"expected to ship in the repository."
            )
        return path
    if not recipe.url:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / Path(recipe.url).name
    if target.exists():
        return target
    if progress:
        progress(f"downloading {recipe.url}")
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(recipe.url) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh, 1 << 20)
    tmp.replace(target)
    return target


# -- pipelines ------------------------------------------------------------
#
# Each takes the resolved source and the recipe's params and returns an
# object with `.save(path)` and `.content_hash()`.


@pipeline("label_volume")
def _label_volume(src, params, **_):
    from .ingest.label_volume import ingest, materials_from_amira

    materials = materials_from_amira(params["materials"])
    return ingest(
        src, materials,
        voxel_um_zyx=tuple(params["voxel_um_zyx"]),
        transpose=tuple(params.get("transpose", (2, 1, 0))),
        mask_sigma_um=params.get("mask_sigma_um", 1.0),
        level=params.get("level", 0.44),
        smooth=params.get("smooth", 0),
    ).meshset


@pipeline("label_masks")
def _label_masks(src, params, **_):
    """The publication's own voxel masks, unmodified.

    Deliberately not a pyramid: averaging neighbouring voxels of a label
    volume gives the mean of two ids, which is a third label.
    """
    from .ingest.label_volume import masks_volume, materials_from_amira

    return masks_volume(
        src, materials_from_amira(params["materials"]),
        voxel_um_zyx=tuple(params["voxel_um_zyx"]),
        transpose=tuple(params.get("transpose", (2, 1, 0))),
    )


@pipeline("image_stack")
def _image_stack(src, params, **_):
    from .ingest.image_stack import ingest

    return ingest(
        src, space=params["space"],
        voxel_um_zyx=tuple(params["voxel_um_zyx"]),
        transpose=tuple(params.get("transpose", (2, 1, 0))),
        role=params.get("role", "template_image"),
    ).volume


@pipeline("bates_plotly")
def _bates(src, params, **_):
    from .ingest.bates_plotly import ingest

    return ingest(src, role=params.get("role", "glomeruli")).meshset


@pipeline("slicer_vtm")
def _slicer(src, params, **_):
    from .ingest.slicer_vtm import ingest

    return ingest(src, ras_to_lps=params.get("ras_to_lps", True)).meshset


@pipeline("obj_archive")
def _obj_archive(src, params, **_):
    from .ingest.obj_archive import ingest

    return ingest(src, include_side=params.get("include_side", True)).meshset


@pipeline("neuprint_rois")
def _neuprint(src, params, **_):
    from .ingest.neuprint_rois import ingest

    return ingest(
        server=params["server"], dataset=params["dataset"],
        role=params.get("role", "glomeruli"),
    ).meshset


@pipeline("flywire_neuropils")
def _flywire(src, params, progress=None, **_):
    from .ingest.flywire_neuropils import bridge_to_fafb14, ingest

    # This pipeline's callback is (i, total, name, n_vertices), not the
    # single message string every other caller here uses. Adapt rather than
    # forward: passing ours straight through raised
    # "lambda() takes 1 positional argument but 4 were given" after the
    # meshes had already been fetched.
    relay = None
    if progress is not None:
        def relay(i, total, name, n_verts):
            progress(f"[{i}/{total}] {name} ({n_verts} vertices)")

    meshset = ingest(progress=relay).meshset
    if params.get("bridge_to") == "FAFB14":
        if progress:
            progress("bridging FLYWIRE -> FAFB14")
        meshset = bridge_to_fafb14(meshset)
    return meshset


# -- driver ---------------------------------------------------------------


def build_asset(registry, asset_id: str, recipes=None, progress=None,
                overwrite: bool = False) -> BuildResult:
    """Derive one asset and write it where the registry expects it."""
    registry_root = Path(registry.root)
    repo_root = registry_root.parent
    recipes = recipes if recipes is not None else load_recipes(registry_root)

    if asset_id not in recipes:
        raise KeyError(
            f"no recipe for {asset_id!r}. Recipes are in "
            f"{registry_root / DEFAULT_RECIPES}; the virtual stains are built "
            f"with `lobemap stain` instead."
        )
    if asset_id not in registry.assets:
        raise KeyError(f"{asset_id!r} is not an asset in this registry")

    recipe = recipes[asset_id]
    target = registry.assets[asset_id].path
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"{target} already exists; pass overwrite to replace it"
        )

    fn = _PIPELINES.get(recipe.pipeline)
    if fn is None:
        raise KeyError(
            f"{asset_id}: unknown pipeline {recipe.pipeline!r}; known: "
            f"{sorted(_PIPELINES)}"
        )

    cache = registry.data_root / CACHE_DIR
    src = resolve_source(recipe, repo_root, cache, progress=progress)
    if progress:
        progress(f"{asset_id}: {recipe.pipeline}")
    obj = fn(src, recipe.params, progress=progress)

    target.parent.mkdir(parents=True, exist_ok=True)
    # `Volume.save` dispatches on the suffix, so a registry path ending in
    # .zarr writes an OME-Zarr pyramid and anything else writes npz. The
    # recipe does not need to say which.
    obj.save(target)
    return BuildResult(asset_id, target, obj.content_hash())


def buildable(registry, recipes=None) -> list[str]:
    """Assets this can derive, in registry order."""
    recipes = recipes if recipes is not None else load_recipes(registry.root)
    return [a for a in registry.assets if a in recipes]


def missing(registry) -> list[str]:
    """Declared assets whose file is not on disk."""
    return [a for a, asset in registry.assets.items() if not asset.path.exists()]


__all__ = [
    "BuildResult",
    "Recipe",
    "build_asset",
    "buildable",
    "load_recipes",
    "missing",
    "resolve_source",
]
