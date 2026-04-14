"""mcp.search の output_fields 対応テスト。"""

import json
import sys
from pathlib import Path

import pytest

from locatepy.cli import main as cli_main
from locatepy.mcp import _state, search

pytestmark = pytest.mark.usefixtures("db_config")


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
def db_config(
    file_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """設定ファイル生成 → -u でDB構築し、_state を設定して config_path を返す。"""
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
    cli_main()
    _state["config_path"] = str(config_path)

    return config_path


def test_search_default_output_fields() -> None:
    """output_fields 未指定時、file のデフォルト fields のみ返る。"""
    results = search("report")
    assert len(results) == 1
    assert set(results[0].keys()) == {"path", "size", "modified_time"}


def test_search_default_output_fields_dir() -> None:
    """output_fields 未指定時、dir のデフォルト fields が返る。"""
    results = search("subdir", type="dir")
    assert len(results) >= 1
    assert set(results[0].keys()) == {
        "path",
        "total_size",
        "total_files",
        "modified_time",
    }


def test_search_custom_output_fields() -> None:
    """output_fields 指定時、指定したキーのみ含む辞書が返る。"""
    results = search("report", output_fields=["path", "name"])
    assert len(results) == 1
    assert set(results[0].keys()) == {"path", "name"}


def test_search_output_fields_single() -> None:
    """output_fields に1フィールドのみ指定できる。"""
    results = search("report", output_fields=["path"])
    assert len(results) == 1
    assert list(results[0].keys()) == ["path"]


def test_search_output_fields_invalid() -> None:
    """無効なフィールド指定で ValueError が発生する。"""
    with pytest.raises(ValueError, match="Invalid output_fields"):
        search("report", output_fields=["path", "invalid_field"])


def test_search_output_fields_dir_invalid() -> None:
    """dir type で存在しないフィールドを指定すると ValueError が発生する。"""
    with pytest.raises(ValueError, match="Invalid output_fields"):
        search("subdir", type="dir", output_fields=["path", "no_such_field"])


def test_search_all_file_fields() -> None:
    """全 file フィールド指定で全キーが揃う。"""
    all_fields = [
        "path",
        "name",
        "size",
        "local_size",
        "created_time",
        "accessed_time",
        "modified_time",
        "attributes",
    ]
    results = search("report", output_fields=all_fields)
    assert len(results) == 1
    assert set(results[0].keys()) == set(all_fields)
