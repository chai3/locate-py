"""main() に対する integration テスト。"""

import json
import sys
from pathlib import Path

import pytest

from locatepy.cli import main


@pytest.fixture
def file_tree(tmp_path: Path) -> Path:
    """テスト用ファイルツリーを事前作成。"""
    (tmp_path / "report.txt").write_bytes(b"x" * 1024)  # 1 KB
    (tmp_path / "README.md").write_bytes(b"readme")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "data.csv").write_bytes(b"a,b,c")
    (sub / "big_file.bin").write_bytes(b"x" * 1024 * 1024)  # 1 MB
    return tmp_path


@pytest.fixture
def env(
    file_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    """設定ファイル生成 → -u でDB構築。"""
    db_path = file_tree / "test.db"
    config: dict = {
        "database_path": str(db_path),
        "target_paths": [str(file_tree)],
        "ignore_paths": [],
        "ignore_names": [],
    }
    config_path = file_tree / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["locatepy", "-c", str(config_path), "-u"])
    main()

    return file_tree, config_path


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_update_creates_db(
    file_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """-u でDBファイルが生成されることを確認。"""
    db_path = file_tree / "test.db"
    config: dict = {
        "database_path": str(db_path),
        "target_paths": [str(file_tree)],
        "ignore_paths": [],
        "ignore_names": [],
    }
    config_path = file_tree / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["locatepy", "-c", str(config_path), "-u"])
    main()

    assert db_path.exists()


def test_search_pattern(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """パターン検索でマッチするファイルが出力される。"""
    _tmp, config_path = env
    capsys.readouterr()  # fixture の出力をクリア

    monkeypatch.setattr(sys, "argv", ["locatepy", "-c", str(config_path), "report"])
    main()

    out = capsys.readouterr().out
    assert "report.txt" in out


def test_search_no_match(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """マッチなし時に 'No matching file found.' が出力される。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys, "argv", ["locatepy", "-c", str(config_path), "zzz_no_such_file"]
    )
    main()

    out = capsys.readouterr().out
    assert "No matching file found." in out


def test_search_regex(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """-r でregex検索が動作する。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys, "argv", ["locatepy", "-c", str(config_path), "-r", r"\.csv$"]
    )
    main()

    out = capsys.readouterr().out
    assert "data.csv" in out
    assert "report.txt" not in out


def test_format_json(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--format json でJSON配列が出力される。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["locatepy", "-c", str(config_path), "--format", "json", "report"],
    )
    main()

    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "path" in data[0]
    assert "report.txt" in data[0]["path"]


def test_format_path(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--format path でパスのみ出力される(ヘッダー・サマリーなし)。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["locatepy", "-c", str(config_path), "--format", "path", "report"],
    )
    main()

    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].endswith("report.txt")


def test_type_dir(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--type dir でディレクトリが出力される。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["locatepy", "-c", str(config_path), "--type", "dir", "subdir"],
    )
    main()

    out = capsys.readouterr().out
    assert "subdir" in out


def test_min_size(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--min-size 500K でサイズフィルタが動作する(big_file.bin のみヒット)。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys, "argv", ["locatepy", "-c", str(config_path), "--min-size", "500K"]
    )
    main()

    out = capsys.readouterr().out
    assert "big_file.bin" in out
    assert "report.txt" not in out


def test_output_fields_default_file(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--output-fields 未指定時(file)のデフォルトヘッダーが path,size,modified_time。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["locatepy", "-c", str(config_path), "report"])
    main()

    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert header == "path\tsize\tmodified_time"


def test_output_fields_default_dir(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--output-fields 未指定時(dir)のデフォルトヘッダーが path,total_size,modified_time。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys, "argv", ["locatepy", "-c", str(config_path), "--type", "dir", "subdir"]
    )
    main()

    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert header == "path\ttotal_size\ttotal_files\tmodified_time"


def test_output_fields_tsv(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--output-fields path,size でヘッダーが2列のみ、modified_time が含まれない。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        ["locatepy", "-c", str(config_path), "--output-fields", "path,size", "report"],
    )
    main()

    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert header == "path\tsize"
    assert "modified_time" not in header


def test_output_fields_json(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--output-fields path,modified_time --format json でキーが2つのみ。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "locatepy",
            "-c",
            str(config_path),
            "--format",
            "json",
            "--output-fields",
            "path,modified_time",
            "report",
        ],
    )
    main()

    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) == 1
    assert set(data[0].keys()) == {"path", "modified_time"}


def test_output_fields_dir(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """--type dir --output-fields path,total_size でdir用フィールドが正しく出力される。"""
    _tmp, config_path = env
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "locatepy",
            "-c",
            str(config_path),
            "--type",
            "dir",
            "--output-fields",
            "path,total_size",
            "subdir",
        ],
    )
    main()

    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert header == "path\ttotal_size"
    assert "subdir" in out


def test_output_fields_invalid(
    env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """無効なフィールド名指定で SystemExit が発生する。"""
    _tmp, config_path = env

    monkeypatch.setattr(
        sys,
        "argv",
        ["locatepy", "-c", str(config_path), "--output-fields", "path,invalid_field"],
    )
    with pytest.raises(SystemExit):
        main()
