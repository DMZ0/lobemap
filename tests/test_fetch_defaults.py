"""What `fetch` downloads when you do not tell it.

The data is published as one release, but it is not one size: the three
virtual stains are 2.44 GB of the 2.51 GB total, and they are reference
imagery that starts hidden, so every scene opens without them. A plain
`fetch` therefore gets the 76 MB that a scene cannot open without, and the
stains have to be asked for -- the same rule `build --all` uses at the
other end of the pipeline, for the same reason.

Driven over `file://` URLs, so the real download path runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lobemap.cli import _autofetch, _optional_assets, main
from lobemap.core import manifest as mf


class _Asset:
    def __init__(self, aid, path):
        self.id, self.path = aid, path


@pytest.fixture
def published(tmp_path):
    """A registry whose two artifacts are published, one of them expensive."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "mesh.npz").write_bytes(b"meshes" * 100)
    (source / "stain.npz").write_bytes(b"a much bigger thing" * 100)
    assets = [_Asset("mesh", source / "mesh.npz"),
              _Asset("stain", source / "stain.npz")]

    served = tmp_path / "served"
    served.mkdir()
    arts = mf.build(source, assets)
    for art in arts:
        (served / art.transfer_name).write_bytes(
            (source / art.path).read_bytes())

    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "recipes.toml").write_text(
        '[mesh]\npipeline = "obj_archive"\n\n'
        '[stain]\npipeline = "virtual_stain"\nexpensive = true\n',
        encoding="utf-8")
    url = served.resolve().as_uri()
    (registry / "manifest.toml").write_text(mf.dump(arts, url), encoding="utf-8")

    data = tmp_path / "data"
    return registry, data


def _fetch(registry, data, *extra):
    return main(["--registry", str(registry), "--data-root", str(data),
                 "fetch", *extra])


def test_a_plain_fetch_leaves_the_expensive_one_alone(published, capsys):
    registry, data = published
    assert _fetch(registry, data) == 0
    assert (data / "mesh.npz").exists()
    assert not (data / "stain.npz").exists()
    assert "holding back" in capsys.readouterr().out


def test_all_includes_it(published):
    registry, data = published
    assert _fetch(registry, data, "--all") == 0
    assert (data / "mesh.npz").exists()
    assert (data / "stain.npz").exists()


def test_naming_it_is_enough(published):
    """Asking for it by name must not be overruled by the default."""
    registry, data = published
    assert _fetch(registry, data, "--asset", "stain") == 0
    assert (data / "stain.npz").exists()
    assert not (data / "mesh.npz").exists()


def test_check_does_not_re_zip_the_expensive_one(published, capsys):
    """`--check` verifies a store by zipping it, which for the real stains
    is 2.4 GB of work. The default selection keeps that off the fast path."""
    registry, data = published
    _fetch(registry, data, "--all")
    assert _fetch(registry, data, "--check") == 0
    assert "1 selected" in capsys.readouterr().out


def test_autofetch_gets_the_required_ones(published):
    registry, data = published
    _autofetch(registry, data)
    assert (data / "mesh.npz").exists()
    assert not (data / "stain.npz").exists()


def test_autofetch_is_silent_when_there_is_nothing_to_do(published, capsys):
    registry, data = published
    _autofetch(registry, data)
    capsys.readouterr()
    _autofetch(registry, data)
    assert capsys.readouterr().out == ""


def test_autofetch_does_nothing_without_a_base_url(published, tmp_path):
    """Opening the viewer must not depend on a published release."""
    registry, data = published
    arts, _ = mf.load(registry / "manifest.toml")
    (registry / "manifest.toml").write_text(mf.dump(arts), encoding="utf-8")
    _autofetch(registry, data)
    assert not data.exists() or not list(data.iterdir())


def test_autofetch_survives_an_unreachable_host(published, tmp_path):
    """A failed fetch must still let the viewer start and say what is
    missing in its own terms."""
    registry, data = published
    arts, _ = mf.load(registry / "manifest.toml")
    (registry / "manifest.toml").write_text(
        mf.dump(arts, "file:///nowhere-at-all"), encoding="utf-8")
    _autofetch(registry, data)          # must not raise
    assert not (data / "mesh.npz").exists()


def test_the_real_registry_holds_back_exactly_the_stains():
    root = Path(__file__).resolve().parents[1] / "registry"
    assert _optional_assets(root) == {
        "fafb_stain", "hemibrain_stain", "malecns_stain"}


def test_the_shipped_manifest_points_at_the_release():
    """If this is ever cleared, a fresh clone silently has no data path."""
    root = Path(__file__).resolve().parents[1] / "registry"
    arts, base_url = mf.load(root / "manifest.toml")
    assert base_url, "no base_url: a fresh clone cannot fetch anything"
    assert len(arts) == 14
    # `fetch` builds f"{base}/{transfer_name}", so the URL must be a flat
    # namespace with no path of its own left to append.
    assert not base_url.endswith("/")
