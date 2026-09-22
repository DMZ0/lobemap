"""Every asset must have a runnable path to existence.

The gap this guards was not a bug in any pipeline -- they all worked. It was
that knowing WHICH pipeline to run, with which arguments, existed only as
prose in registry/data/README.md, so nine of the fifteen assets could not be
rebuilt by anyone who had not read the source.
"""

from __future__ import annotations

import pytest

from lobemap.build import buildable, load_recipes, missing
from lobemap.core.registry import Registry

#: Built by `lobemap stain` instead: ~19 GB of downloads, ~40 GB of scratch
#: and hours of compute make them a deliberate act, not a recipe.
STAINS = {"fafb_stain", "hemibrain_stain", "malecns_stain"}


@pytest.fixture(scope="module")
def registry():
    return Registry.load("registry", validate=False)


def test_every_asset_is_either_buildable_or_a_stain(registry):
    recipes = load_recipes(registry.root)
    orphans = [a for a in registry.assets if a not in recipes and a not in STAINS]
    assert not orphans, (
        f"no way to rebuild: {orphans}. Add a recipe to registry/recipes.toml "
        f"or the asset cannot be reproduced by anyone."
    )


def test_recipes_only_name_real_assets(registry):
    unknown = [a for a in load_recipes(registry.root) if a not in registry.assets]
    assert not unknown, f"recipes for assets that do not exist: {unknown}"


def test_local_sources_actually_ship(registry):
    """A recipe pointing at a file that is not in the repo is not runnable."""
    root = registry.root.parent
    for name, recipe in load_recipes(registry.root).items():
        if not recipe.source:
            continue
        assert (root / recipe.source).exists(), (
            f"{name}: source {recipe.source} does not ship in the repository"
        )
        for key in ("materials",):
            if key in recipe.params:
                assert (root / recipe.params[key]).exists(), (
                    f"{name}: {key} {recipe.params[key]} does not ship"
                )


def test_every_recipe_names_a_known_pipeline(registry):
    from lobemap.build import _PIPELINES

    for name, recipe in load_recipes(registry.root).items():
        assert recipe.pipeline in _PIPELINES, (
            f"{name}: unknown pipeline {recipe.pipeline!r}"
        )


def test_buildable_excludes_the_stains(registry):
    assert STAINS.isdisjoint(buildable(registry))


def test_missing_reports_what_is_absent(registry):
    absent = set(missing(registry))
    assert absent <= set(registry.assets)
    # The stains are the ones this repository does not ship.
    assert absent == STAINS, (
        f"expected only the stains to be absent, got {sorted(absent)}"
    )


def test_the_no_data_error_names_a_runnable_command(registry):
    """The old message said `lobemap ingest ...`, ellipsis and all."""
    from lobemap.viewer.app import MissingAssets

    text = str(MissingAssets("JRCFIB2018F", registry))
    assert "..." not in text, "the advice still contains a literal ellipsis"
    assert "lobemap build --all" in text
    assert "lobemap fetch" in text
    # It must name the specific assets, not just gesture at the space.
    assert "hemibrain_stain" in text
