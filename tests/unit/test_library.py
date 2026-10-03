import pytest
from PIL import Image

from labs_picpak import config, dashboard, library
from labs_picpak.library import Entry


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    def use(name):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / name / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / name / "data"))

    use("mac-a")
    return use


def entry(slot, md5="aa", source="/photos/a.jpg"):
    return Entry(slot=slot, source=source, md5=md5, fit="cover", pushed_at="2026-10-03T10:00:00+02:00")


def test_record_forget_and_preview(xdg):
    config.save({"kitchen": "ADDR-1"})
    library.record("kitchen", "ADDR-1", entry(2), Image.new("RGB", (400, 300)))
    assert library.load()["kitchen"].slots[2].source == "/photos/a.jpg"
    assert library.preview_path("kitchen", 2).exists()
    library.forget("kitchen", 2)
    assert 2 not in library.load()["kitchen"].slots
    assert not library.preview_path("kitchen", 2).exists()


def test_frame_key_maps_address_to_name(xdg):
    config.save({"kitchen": "ADDR-1"})
    assert library.frame_key("kitchen") == "kitchen"
    assert library.frame_key("ADDR-1") == "kitchen"
    assert library.frame_key("OTHER") == "OTHER"


def test_reconcile_statuses(xdg):
    library.record("k", "A", entry(2, md5="m2"), None)
    library.record("k", "A", entry(3, md5="m3"), None)
    library.record("k", "A", entry(9, md5="m9"), None)
    fs = library.reconcile("k", "A", used=[1, 2, 3], md5s={1: "x", 2: "m2", 3: "different"})
    assert fs.status == {1: "unknown", 2: "ok", 3: "changed", 9: "gone"}
    assert library.load()["k"].on_frame == [1, 2, 3]


def test_export_import_to_another_machine(xdg, tmp_path):
    config.save({"kitchen": "ADDR-A"})
    library.record("kitchen", "ADDR-A", entry(2), Image.new("RGB", (400, 300), "red"))
    z = library.export(tmp_path / "state.zip")

    xdg("mac-b")  # a second machine with its own state
    config.save({"desk": "ADDR-B"})
    library.record("desk", "ADDR-B", entry(5), None)
    frames, slots = library.import_(z)
    assert (frames, slots) == (2, 2)
    assert config.load() == {"desk": "ADDR-B", "kitchen": "ADDR-A"}
    assert library.preview_path("kitchen", 2).exists()

    frames, slots = library.import_(z, replace=True)
    assert (frames, slots) == (1, 1)
    assert config.load() == {"kitchen": "ADDR-A"}


def test_import_rejects_other_zips(xdg, tmp_path):
    import zipfile

    bad = tmp_path / "x.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ValueError):
        library.import_(bad)


def test_dashboard_lists_frames_slots_and_status(xdg):
    library.record("kitchen", "ADDR-1", entry(2, source="/p/dokyo.png"), Image.new("RGB", (400, 300)))
    library.reconcile("kitchen", "ADDR-1", used=[1, 2], md5s={1: "?", 2: "aa"})
    html = dashboard.render().read_text()
    assert "kitchen" in html and "dokyo.png" in html
    assert "previews/kitchen/2.png" in html
    assert "not recorded" in html  # slot 1


def test_rename_moves_name_records_and_previews(xdg):
    config.save({"frame-1": "ADDR-1"})
    library.record("frame-1", "ADDR-1", entry(2), Image.new("RGB", (400, 300)))
    library.record("ADDR-2", "ADDR-2", entry(3), Image.new("RGB", (400, 300)))  # pushed before naming
    library.rename("frame-1", "kitchen")
    library.rename("ADDR-2", "desk")
    assert config.load() == {"kitchen": "ADDR-1", "desk": "ADDR-2"}
    assert set(library.load()) == {"kitchen", "desk"}
    assert library.preview_path("kitchen", 2).exists() and library.preview_path("desk", 3).exists()
    with pytest.raises(ValueError):
        library.rename("kitchen", "desk")
