import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any


CONFIG_PATH = Path("locate-py.json")
DB_PATH = Path("locate-py.db")
BATCH_SIZE = 100_000

CSV_HEADER = [
    "path",
    "st_size",
    "st_birthtime_ns",
    "st_atime_ns",
    "st_mtime_ns",
    "st_file_attributes",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"エラー: {CONFIG_PATH} が見つかりません。")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def scan_dir(path: str, ignore_names: set[str]) -> Iterator[os.DirEntry[str]]:
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in ignore_names:
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry
        except PermissionError:
            pass
        except OSError:
            pass


def _iter_rows(
    config: dict[str, Any],
) -> Iterator[tuple[str, int | None, int | None, int | None, int | None, int | None]]:
    ignore_names = set(config.get("ignore_names", []))
    for base in config.get("target_paths", []):
        for entry in scan_dir(base, ignore_names):
            st = entry.stat(follow_symlinks=False)
            yield (
                os.path.normpath(entry.path),
                st.st_size,
                getattr(st, "st_birthtime_ns", None),
                st.st_atime_ns,
                st.st_mtime_ns,
                getattr(st, "st_file_attributes", None),
            )


def update_db(config: dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -65536")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("DROP TABLE IF EXISTS files")
        conn.execute("""
            CREATE TABLE files (
                id                  INTEGER PRIMARY KEY,
                path                TEXT NOT NULL UNIQUE,
                st_size             INTEGER,
                st_birthtime_ns     INTEGER,
                st_atime_ns         INTEGER,
                st_mtime_ns         INTEGER,
                st_file_attributes  INTEGER
            )
        """)
        conn.commit()

        total = 0
        batch = []
        insert_sql = (
            "INSERT OR REPLACE INTO files "
            "(path, st_size, st_birthtime_ns, st_atime_ns, st_mtime_ns, st_file_attributes) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        for row in _iter_rows(config):
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                conn.commit()
                total += len(batch)
                print(f"  {total:,} 件処理済み...", end="\r", flush=True)
                batch.clear()

        if batch:
            conn.executemany(insert_sql, batch)
            conn.commit()
            total += len(batch)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON files(path)")
        conn.commit()

    print(f"{total:,} 件のファイルをインデックスしました。")


def _ns_to_str(ns: int | None) -> str:
    if ns is None:
        return ""
    return datetime.fromtimestamp(ns / 1e9).strftime("%Y-%m-%d %H:%M:%S")


def _print_row(writer: Any, row: tuple[Any, ...]) -> None:
    _, path, st_size, birthtime_ns, atime_ns, mtime_ns, file_attrs = row
    writer.writerow(
        [
            path,
            st_size if st_size is not None else "",
            _ns_to_str(birthtime_ns),
            _ns_to_str(atime_ns),
            _ns_to_str(mtime_ns),
            file_attrs if file_attrs is not None else "",
        ]
    )


def search_pattern(pattern: str) -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            "エラー: データベースが見つかりません。先に locate -u を実行してください。"
        )
    writer = csv.writer(sys.stdout)
    found = False
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA case_sensitive_like = OFF")
        for row in conn.execute(
            "SELECT * FROM files WHERE path LIKE ?", (f"%{pattern}%",)
        ):
            if not found:
                writer.writerow(CSV_HEADER)
                found = True
            _print_row(writer, row)
    if not found:
        print("マッチするファイルが見つかりませんでした。")


def search_regex(pattern: str) -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            "エラー: データベースが見つかりません。先に locate -u を実行してください。"
        )
    try:
        re.compile(pattern)
    except re.error as e:
        raise SystemExit(f"エラー: 正規表現が不正です: {e}")

    writer = csv.writer(sys.stdout)
    found = False
    with sqlite3.connect(DB_PATH) as conn:
        conn.create_function(
            "REGEXP", 2, lambda pat, val: bool(re.search(pat, val or ""))
        )
        for row in conn.execute("SELECT * FROM files WHERE path REGEXP ?", (pattern,)):
            if not found:
                writer.writerow(CSV_HEADER)
                found = True
            _print_row(writer, row)
    if not found:
        print("マッチするファイルが見つかりませんでした。")


def main() -> None:
    parser = argparse.ArgumentParser(description="シンプルな locate コマンド")
    parser.add_argument(
        "-u", "--update", action="store_true", help="データベースを更新する"
    )
    parser.add_argument("-r", "--regex", metavar="PATTERN", help="正規表現で検索する")
    parser.add_argument("pattern", nargs="?", help="パターンで検索する（部分一致）")
    args = parser.parse_args()

    if args.update:
        config = load_config()
        update_db(config)
    elif args.regex:
        search_regex(args.regex)
    elif args.pattern:
        search_pattern(args.pattern)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
