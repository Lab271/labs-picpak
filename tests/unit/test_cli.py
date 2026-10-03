from PIL import Image

from labs_picpak import cli, config


def test_name_and_frames_use_local_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    cli.main(["name", "ABCD-1234", "kitchen"])
    cli.main(["name", "EFGH-5678", "desk"])
    assert config.load() == {"kitchen": "ABCD-1234", "desk": "EFGH-5678"}
    assert config.resolve("desk") == "EFGH-5678"
    assert config.resolve("SOME-ADDRESS") == "SOME-ADDRESS"
    cli.main(["frames"])
    out = capsys.readouterr().out
    assert "kitchen" in out and "EFGH-5678" in out


def test_preview_needs_no_bluetooth(tmp_path):
    src = tmp_path / "photo.jpg"
    Image.new("RGB", (640, 480), (200, 30, 30)).save(src)
    out = tmp_path / "p.png"
    cli.main(["preview", str(src), "--out", str(out)])
    assert Image.open(out).size == (400, 300)


def test_parser_has_all_commands():
    names = set(cli.build_parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
    assert {"scan", "info", "list", "push", "delete", "pull", "identify", "preview", "dashboard",
            "export", "import", "name", "frames"} <= names


def test_export_import_and_dashboard_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    cli.main(["name", "ADDR", "kitchen"])
    z = tmp_path / "s.zip"
    cli.main(["export", str(z)])
    cli.main(["import", str(z)])
    cli.main(["dashboard", "--no-open"])
    out = capsys.readouterr().out
    assert "imported: " in out and "dashboard.html" in out
