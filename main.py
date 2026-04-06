import argparse
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, TypedDict


DB_PATH = Path("locate-py.db")
BATCH_SIZE = 100_000

SORT_COLUMNS = {
    "path": "path",
    "size": "st_size",
    "mtime": "st_mtime_ns",
    "ctime": "st_birthtime_ns",
    "atime": "st_atime_ns",
}

CSV_HEADER = [
    "path",
    "size",
    "ctime",
    "atime",
    "mtime",
    "attributes",
]


class Config(TypedDict, total=False):
    database_path: str
    target_paths: list[str]
    ignore_paths: list[str]
    ignore_names: list[str]


class FileEntry(NamedTuple):
    path: str
    st_size: int | None
    st_birthtime_ns: int | None
    st_atime_ns: int | None
    st_mtime_ns: int | None
    st_file_attributes: int | None


class DbFileRow(NamedTuple):
    id: int
    path: str
    st_size: int | None
    st_birthtime_ns: int | None
    st_atime_ns: int | None
    st_mtime_ns: int | None
    st_file_attributes: int | None


def _default_config() -> Config:
    cwd = str(Path.cwd())
    if sys.platform == "win32":
        return {
            "database_path": "locate-py.db",
            "target_paths": [cwd],
            "ignore_paths": [],
            "ignore_names": [],
        }
    else:
        return {
            "database_path": "locate-py.db",
            "target_paths": [cwd],
            "ignore_paths": ["/dev", "/proc", "/sys"],
            "ignore_names": [""],
        }


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        config = _default_config()
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os_name = "Windows" if sys.platform == "win32" else sys.platform
        print(f"{config_path} が見つからなかったため、自動作成しました。(OS: {os_name})")
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return config
    with config_path.open(encoding="utf-8") as f:
        return json.load(f)


def scan_dir(path: str, ignore_names: set[str], ignore_paths: set[str]) -> Iterator[os.DirEntry[str]]:
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        norm = os.path.normpath(entry.path)
                        if norm not in ignore_paths and entry.name not in ignore_names:
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry
        except PermissionError:
            pass
        except OSError:
            pass


def _iter_rows(config: Config) -> Iterator[FileEntry]:
    ignore_names = set(config.get("ignore_names", []))
    ignore_paths = {os.path.normpath(p) for p in config.get("ignore_paths", [])}
    for base in config.get("target_paths", []):
        for entry in scan_dir(base, ignore_names, ignore_paths):
            st = entry.stat(follow_symlinks=False)
            yield FileEntry(
                path=os.path.normpath(entry.path),
                st_size=st.st_size,
                st_birthtime_ns=getattr(st, "st_birthtime_ns", None),
                st_atime_ns=st.st_atime_ns,
                st_mtime_ns=st.st_mtime_ns,
                st_file_attributes=getattr(st, "st_file_attributes", None),
            )


def update_db(config: Config) -> None:
    print("データベースの作成を開始します。")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -65536")  # 64MByte
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
        batch: list[FileEntry] = []
        insert_sql = (
            "INSERT OR REPLACE INTO files "
            "(path, st_size, st_birthtime_ns, st_atime_ns, st_mtime_ns, st_file_attributes) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        for row in _iter_rows(config):
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                total += len(batch)
                print(f"  {total:,} 件目を処理中... ({row.path})")
                conn.executemany(insert_sql, batch)
                conn.commit()
                batch.clear()

        if batch:
            conn.executemany(insert_sql, batch)
            conn.commit()
            total += len(batch)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON files(path)")
        conn.commit()

    print(f"{total:,} 件のファイルをインデックスしました。")


def _parse_size(s: str) -> int:
    s = s.strip()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if s and s[-1].upper() in units:
        return int(s[:-1]) * units[s[-1].upper()]
    return int(s)


_DATE_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]


def _parse_date_ns(s: str) -> int:
    for fmt in _DATE_FORMATS:
        try:
            return int(datetime.strptime(s.strip(), fmt).timestamp() * 1e9)
        except ValueError:
            continue
    raise SystemExit(
        f"エラー: 日付フォーマットが不正です: {s!r}\n"
        "  YYYY-MM-DD / YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM:SS のいずれかで指定してください。"
    )


def _apply_filters_and_sort(
    where: list[str], params: list, args: argparse.Namespace
) -> str:
    if args.min_size is not None:
        try:
            where.append("st_size >= ?")
            params.append(_parse_size(args.min_size))
        except ValueError:
            raise SystemExit(f"エラー: --min-size の値が不正です: {args.min_size!r}")
    if args.max_size is not None:
        try:
            where.append("st_size <= ?")
            params.append(_parse_size(args.max_size))
        except ValueError:
            raise SystemExit(f"エラー: --max-size の値が不正です: {args.max_size!r}")

    for col, after_attr, before_attr in [
        ("st_mtime_ns", "mtime_after", "mtime_before"),
        ("st_birthtime_ns", "ctime_after", "ctime_before"),
        ("st_atime_ns", "atime_after", "atime_before"),
    ]:
        after_val = getattr(args, after_attr)
        before_val = getattr(args, before_attr)
        if after_val is not None:
            where.append(f"{col} >= ?")
            params.append(_parse_date_ns(after_val))
        if before_val is not None:
            where.append(f"{col} <= ?")
            params.append(_parse_date_ns(before_val))

    if args.sort is None and args.sort_order is None:
        return ""
    sort_key = args.sort or "path"
    if args.sort_order:
        order = args.sort_order.upper()
    elif sort_key == "path":
        order = "ASC"
    else:
        order = "DESC"
    return f" ORDER BY {SORT_COLUMNS[sort_key]} {order}"


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _ns_to_str(ns: int | None) -> str:
    if ns is None:
        return ""
    return datetime.fromtimestamp(ns / 1e9).strftime("%Y-%m-%d %H:%M:%S")


def _print_row(row: DbFileRow, delimiter: str, quote_path: bool = False) -> None:
    path = f'"{row.path}"' if quote_path else row.path
    fields = [
        path,
        str(row.st_size) if row.st_size is not None else "",
        _ns_to_str(row.st_birthtime_ns),
        _ns_to_str(row.st_atime_ns),
        _ns_to_str(row.st_mtime_ns),
        str(row.st_file_attributes) if row.st_file_attributes is not None else "",
    ]
    print(delimiter.join(fields))


def _check_db() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            "エラー: データベースが見つかりません。先に locate -u を実行してください。"
        )


def _run_search(
    conn: sqlite3.Connection, sql: str, params: list, args: argparse.Namespace
) -> None:
    where = [sql]
    order_clause = _apply_filters_and_sort(where, params, args)
    limit_clause = f" LIMIT {args.limit}" if args.limit is not None else ""
    full_sql = (
        f"SELECT * FROM files WHERE {' AND '.join(where)}{order_clause}{limit_clause}"
    )

    delimiter = "\t" if args.format == "tsv" else ","
    quote_path = args.format == "csv"

    count = 0
    total_size = 0
    header_written = False

    for row in conn.execute(full_sql, params):
        db_row = DbFileRow(*row)
        if not header_written:
            if not args.no_header and args.format != "path":
                print(delimiter.join(CSV_HEADER))
            header_written = True
        if args.format == "path":
            print(db_row.path)
        else:
            _print_row(db_row, delimiter, quote_path=quote_path)
        count += 1
        if db_row.st_size is not None:
            total_size += db_row.st_size

    if count == 0:
        if not args.no_summary:
            print("マッチするファイルが見つかりませんでした。")
    elif not args.no_summary:
        print(f"検索完了 {count:,} 件 / {_format_size(total_size)}")


def search_pattern(pattern: str, args: argparse.Namespace) -> None:
    _check_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"PRAGMA case_sensitive_like = {'OFF' if args.ignore_case else 'ON'}"
        )
        _run_search(conn, "path LIKE ?", [f"%{pattern}%"], args)


def search_regex(pattern: str, args: argparse.Namespace) -> None:
    _check_db()
    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        re.compile(pattern, flags)
    except re.error as e:
        raise SystemExit(f"エラー: 正規表現が不正です: {e}")
    with sqlite3.connect(DB_PATH) as conn:
        conn.create_function(
            "REGEXP", 2, lambda pat, val: bool(re.search(pat, val or "", flags))
        )
        _run_search(conn, "path REGEXP ?", [pattern], args)


def search_all(args: argparse.Namespace) -> None:
    _check_db()
    with sqlite3.connect(DB_PATH) as conn:
        _run_search(conn, "1=1", [], args)


_SEARCH_OPTION_ATTRS = (
    "sort",
    "limit",
    "min_size",
    "max_size",
    "mtime_after",
    "mtime_before",
    "ctime_after",
    "ctime_before",
    "atime_after",
    "atime_before",
    "ignore_case",
)


def _has_search_options(args: argparse.Namespace) -> bool:
    return any(getattr(args, attr) for attr in _SEARCH_OPTION_ATTRS)


def main() -> None:
    parser = argparse.ArgumentParser(description="シンプルな locate コマンド")
    parser.add_argument(
        "-c", "--config",
        metavar="PATH",
        default="locate-py.json",
        help="設定ファイルのパス（デフォルト: locate-py.json）",
    )
    parser.add_argument(
        "-u", "--update", action="store_true", help="データベースを更新する"
    )
    parser.add_argument("-r", "--regex", metavar="PATTERN", help="正規表現で検索する")
    parser.add_argument("pattern", nargs="?", help="パターンで検索する（部分一致）")

    parser.add_argument(
        "--sort",
        choices=list(SORT_COLUMNS),
        metavar="KEY",
        help="ソートキー: " + ", ".join(SORT_COLUMNS),
    )
    parser.add_argument(
        "--sort-order",
        choices=["asc", "desc"],
        dest="sort_order",
        metavar="ORDER",
        help="ソート順: asc / desc（省略時: path→asc、その他→desc）",
    )
    parser.add_argument(
        "--min-size", dest="min_size", metavar="SIZE", help="最小サイズ (例: 1K, 10M)"
    )
    parser.add_argument(
        "--max-size", dest="max_size", metavar="SIZE", help="最大サイズ (例: 100M, 1G)"
    )
    parser.add_argument(
        "--mtime-after", dest="mtime_after", metavar="DATE", help="更新日時の下限"
    )
    parser.add_argument(
        "--mtime-before", dest="mtime_before", metavar="DATE", help="更新日時の上限"
    )
    parser.add_argument(
        "--ctime-after", dest="ctime_after", metavar="DATE", help="作成日時の下限"
    )
    parser.add_argument(
        "--ctime-before", dest="ctime_before", metavar="DATE", help="作成日時の上限"
    )
    parser.add_argument(
        "--atime-after", dest="atime_after", metavar="DATE", help="アクセス日時の下限"
    )
    parser.add_argument(
        "--atime-before", dest="atime_before", metavar="DATE", help="アクセス日時の上限"
    )

    parser.add_argument("-l", "--limit", type=int, metavar="N", help="最大マッチ数")
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        dest="ignore_case",
        help="大文字小文字を区別しない",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["tsv", "csv", "path"],
        default="tsv",
        dest="format",
        help="出力フォーマット: tsv（デフォルト）, csv, path",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        dest="no_header",
        help="ヘッダ行を出力しない",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        dest="no_summary",
        help="合計ファイル数・サイズを出力しない",
    )
    parser.add_argument(
        "--create-config",
        action="store_true",
        dest="create_config",
        help="設定ファイルを作成して終了する",
    )

    args = parser.parse_args()

    config = load_config(Path(args.config))

    global DB_PATH
    db_path_str = config.get("database_path")
    if db_path_str:
        DB_PATH = Path(db_path_str)

    if args.create_config:
        return
    elif args.update:
        update_db(config)
    elif args.regex:
        search_regex(args.regex, args)
    elif args.pattern:
        search_pattern(args.pattern, args)
    elif _has_search_options(args):
        search_all(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
