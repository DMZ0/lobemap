"""Benton 2025's published names ARE the canonical vocabulary.

A flat canonical set only works if exactly one atlas defines it. Left
implicit, the set drifts into a union of whatever every atlas happens to call
things -- which is how `VC3l` and `VM6v` became canonical names that no
current nomenclature uses, and how Bates `VC5` and Benton `VC5` came to share
one canonical name while being different structures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lobemap.core.names import Nomenclature, normalise, parse_roi
from lobemap.core.registry import CANONICAL_SOURCE_ATLAS, Registry

REGISTRY = Path(__file__).resolve().parents[1] / "registry"


@pytest.fixture(scope="module")
def reg():
    return Registry.load(REGISTRY, validate=False)


def test_canonical_set_is_exactly_the_source_atlas(reg):
    source = reg.atlases[CANONICAL_SOURCE_ATLAS]
    expected = {normalise(parse_roi(c.published_name)[0]) for c in source.compartments}
    actual = {normalise(c) for c in reg.names.canonical}
    assert actual == expected, {
        "not published by the source": sorted(actual - expected),
        "published but unmapped": sorted(expected - actual),
    }


def test_the_registry_validates_clean(reg):
    assert reg.validate() == []


def test_validation_rejects_a_canonical_outside_the_source(reg):
    """The guard, not just the current state. This one is fatal, not a warning."""
    from lobemap.core.names import Correspondence
    from lobemap.core.registry import RegistryError

    victim = Registry.load(REGISTRY, validate=False)
    victim.names = Nomenclature(
        canonical=[*reg.names.canonical, "NotAGlomerulus"],
        correspondences=[Correspondence("bates2020", "DA1", ("NotAGlomerulus",))],
    )
    with pytest.raises(RegistryError, match="NotAGlomerulus") as exc:
        victim.validate()
    assert CANONICAL_SOURCE_ATLAS in str(exc.value)


def test_legacy_names_are_published_not_canonical(reg):
    """VC3l/VC3m are Bates's and hemibrain's names, not vocabulary."""
    for legacy in ("VC3l", "VC3m", "VM6l", "VM6m", "VM6v", "VP1"):
        assert not reg.names.is_canonical(legacy), legacy


@pytest.mark.parametrize(
    ("atlas", "published", "canonical", "relation"),
    [
        ("bates2020", "VC3l", ("VC3",), "renamed"),
        ("bates2020", "VC3m", ("VC5",), "renamed"),
        ("bates2020", "VC5", ("VM6",), "renamed"),
        ("neuprint_hemibrain", "AL-VC3l(R)", ("VC3",), "renamed"),
        ("schlegel2021_s11", "VM6l", ("VM6",), "split"),
        ("schlegel2021_s11", "VM6v", ("VM6",), "split"),
        ("grabe2015", "VP1(L)", ("VP1d", "VP1l", "VP1m"), "merge"),
    ],
)
def test_the_awkward_correspondences(reg, atlas, published, canonical, relation):
    corr = reg.names.resolve(atlas, published)
    assert corr is not None, f"{atlas}/{published} unresolved"
    assert corr.canonical == canonical
    assert corr.relation == relation


def test_split_and_merge_point_opposite_ways(reg):
    """A split has many compartments per name; a merge many names per one."""
    s11 = reg.atlases["schlegel2021_s11"]
    vm6 = [c for c in s11.compartments if c.canonical == ("VM6",)]
    assert len(vm6) == 3 and all(c.relation == "split" for c in vm6)

    grabe = reg.atlases["grabe2015"]
    vp1 = [c for c in grabe.compartments if c.relation == "merge"]
    assert vp1, "expected Grabe's unresolved VP1"
    assert all(len(c.canonical) == 3 for c in vp1)


def test_every_compartment_resolves_to_something(reg):
    orphans = [
        (at.id, c.published_name)
        for at in reg.atlases.values()
        for c in at.compartments
        if not c.canonical
    ]
    assert orphans == [], orphans
