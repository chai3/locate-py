import argparse
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict


BATCH_SIZE = 100_000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000

SORT_COLUMNS = {
    "path": "path",
    "size": "st_size",
    "lsize": "lsize",
    "mtime": "st_mtime_ns",
    "ctime": "st_birthtime_ns",
    "atime": "st_atime_ns",
}

DIR_SORT_COLUMNS = {
    "path":        "path",
    "size":        "size",
    "lsize":       "lsize",
    "mtime":       "st_mtime_ns",
    "ctime":       "st_birthtime_ns",
    "atime":       "st_atime_ns",
    "files":       "files",
    "total_size":  "total_size",
    "total_lsize": "total_lsize",
    "total_files": "total_files",
}

CSV_HEADER = [
    "path",
    "size",
    "lsize",
    "ctime",
    "atime",
    "mtime",
    "attributes",
]

CSV_HEADER_DIR = [
    "path",
    "files",
    "size",
    "lsize",
    "total_files",
    "total_size",
    "total_lsize",
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
    lsize: int


class DbFileRow(NamedTuple):
    id: int
    path: str
    st_size: int | None
    st_birthtime_ns: int | None
    st_atime_ns: int | None
    st_mtime_ns: int | None
    st_file_attributes: int | None
    lsize: int


class DbDirRow(NamedTuple):
    id: int
    path: str
    st_birthtime_ns: int | None
    st_atime_ns: int | None
    st_mtime_ns: int | None
    st_file_attributes: int | None
    files: int
    size: int
    lsize: int
    total_files: int
    total_size: int
    total_lsize: int


class _DirAccum:
    __slots__ = (
        "st_birthtime_ns", "st_atime_ns", "st_mtime_ns", "st_file_attributes",
        "files", "size", "lsize", "total_files", "total_size", "total_lsize",
    )

    def __init__(self) -> None:
        self.st_birthtime_ns: int | None = None
        self.st_atime_ns: int | None = None
        self.st_mtime_ns: int | None = None
        self.st_file_attributes: int | None = None
        self.files: int = 0
        self.size: int = 0
        self.lsize: int = 0
        self.total_files: int = 0
        self.total_size: int = 0
        self.total_lsize: int = 0


def _calc_lsize(path: str, st_size: int | None, st_file_attributes: int | None) -> int:
    if st_file_attributes is not None and (st_file_attributes & FILE_ATTRIBUTE_RECALL_ON_OPEN):
        return 0
    return st_size if st_size is not None else 0


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


def _scan_files_and_collect_dirs(
    path: str,
    ignore_names: set[str],
    ignore_paths: set[str],
    dir_accums: dict[str, "_DirAccum"],
) -> Iterator[FileEntry]:
    """ファイルをyieldしながら、ディレクトリのstatをdir_accumsに蓄積する。"""
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        norm = os.path.normpath(entry.path)
                        if norm not in ignore_paths and entry.name not in ignore_names:
                            accum = _DirAccum()
                            try:
                                st = entry.stat(follow_symlinks=False)
                                accum.st_birthtime_ns = getattr(st, "st_birthtime_ns", None)
                                accum.st_atime_ns = st.st_atime_ns
                                accum.st_mtime_ns = st.st_mtime_ns
                                accum.st_file_attributes = getattr(st, "st_file_attributes", None)
                            except OSError:
                                pass
                            dir_accums[norm] = accum
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        path_norm = os.path.normpath(entry.path)
                        st_size = st.st_size
                        st_file_attributes = getattr(st, "st_file_attributes", None)
                        yield FileEntry(
                            path=path_norm,
                            st_size=st_size,
                            st_birthtime_ns=getattr(st, "st_birthtime_ns", None),
                            st_atime_ns=st.st_atime_ns,
                            st_mtime_ns=st.st_mtime_ns,
                            st_file_attributes=st_file_attributes,
                            lsize=_calc_lsize(path_norm, st_size, st_file_attributes),
                        )
        except PermissionError:
            pass
        except OSError:
            pass


def _propagate_totals(dir_accums: dict[str, "_DirAccum"]) -> None:
    """直下集計からボトムアップで total_* を伝播する。"""
    for acc in dir_accums.values():
        acc.total_files = acc.files
        acc.total_size = acc.size
        acc.total_lsize = acc.lsize
    for d in sorted(dir_accums, key=lambda p: p.count(os.sep), reverse=True):
        parent = os.path.dirname(d)
        if parent != d and parent in dir_accums:
            p = dir_accums[parent]
            c = dir_accums[d]
            p.total_files += c.total_files
            p.total_size += c.total_size
            p.total_lsize += c.total_lsize


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
    where: list[str],
    params: list,
    args: argparse.Namespace,
    sort_columns: dict[str, str] = SORT_COLUMNS,
    is_dir: bool = False,
) -> str:
    size_col = "size" if is_dir else "st_size"
    if getattr(args, "target_dir", None):
        norm = os.path.normpath(args.target_dir)
        where.append("path LIKE ?")
        params.append(norm + os.sep + "%")
    if args.min_size is not None:
        try:
            where.append(f"{size_col} >= ?")
            params.append(_parse_size(args.min_size))
        except ValueError:
            raise SystemExit(f"エラー: --min-size の値が不正です: {args.min_size!r}")
    if args.max_size is not None:
        try:
            where.append(f"{size_col} <= ?")
            params.append(_parse_size(args.max_size))
        except ValueError:
            raise SystemExit(f"エラー: --max-size の値が不正です: {args.max_size!r}")

    if is_dir:
        min_total = getattr(args, "min_total_size", None)
        max_total = getattr(args, "max_total_size", None)
        if min_total is not None:
            try:
                where.append("total_size >= ?")
                params.append(_parse_size(min_total))
            except ValueError:
                raise SystemExit(f"エラー: --min-total-size の値が不正です: {min_total!r}")
        if max_total is not None:
            try:
                where.append("total_size <= ?")
                params.append(_parse_size(max_total))
            except ValueError:
                raise SystemExit(f"エラー: --max-total-size の値が不正です: {max_total!r}")

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
    if sort_key not in sort_columns:
        valid = ", ".join(sort_columns)
        raise SystemExit(
            f"エラー: --sort {sort_key!r} は --type {'dir' if is_dir else 'file'} では使用できません。"
            f" 使用可能: {valid}"
        )
    if args.sort_order:
        order = args.sort_order.upper()
    elif sort_key == "path":
        order = "ASC"
    else:
        order = "DESC"
    return f" ORDER BY {sort_columns[sort_key]} {order}"


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
        str(row.lsize),
        _ns_to_str(row.st_birthtime_ns),
        _ns_to_str(row.st_atime_ns),
        _ns_to_str(row.st_mtime_ns),
        str(row.st_file_attributes) if row.st_file_attributes is not None else "",
    ]
    print(delimiter.join(fields))


def _print_dir_row(row: DbDirRow, delimiter: str, quote_path: bool = False) -> None:
    path = f'"{row.path}"' if quote_path else row.path
    fields = [
        path,
        str(row.files),
        str(row.size),
        str(row.lsize),
        str(row.total_files),
        str(row.total_size),
        str(row.total_lsize),
        _ns_to_str(row.st_birthtime_ns),
        _ns_to_str(row.st_atime_ns),
        _ns_to_str(row.st_mtime_ns),
        str(row.st_file_attributes) if row.st_file_attributes is not None else "",
    ]
    print(delimiter.join(fields))


_SEARCH_OPTION_ATTRS = (
    "sort",
    "sort_order",
    "limit",
    "min_size",
    "max_size",
    "min_total_size",
    "max_total_size",
    "mtime_after",
    "mtime_before",
    "ctime_after",
    "ctime_before",
    "atime_after",
    "atime_before",
    "ignore_case",
    "type",
    "target_dir",
)


def _has_search_options(args: argparse.Namespace) -> bool:
    # type が "dir" の場合は明示的な検索指定とみなす
    if getattr(args, "type", "file") == "dir":
        return True
    return any(getattr(args, attr, None) for attr in _SEARCH_OPTION_ATTRS)


class LocatePyApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        db_path_str = config.get("database_path")
        self.db_path: Path = Path(db_path_str) if db_path_str else Path("locate-py.db")

    def _check_db(self) -> None:
        if not self.db_path.exists():
            raise SystemExit(
                "エラー: データベースが見つかりません。先に locate -u を実行してください。"
            )

    def _get_table(self, args: argparse.Namespace) -> Literal["files", "dirs"]:
        return "dirs" if getattr(args, "type", "file") == "dir" else "files"

    def _run_search(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params: list,
        args: argparse.Namespace,
        table: Literal["files", "dirs"] = "files",
    ) -> None:
        is_dir = table == "dirs"
        sort_columns = DIR_SORT_COLUMNS if is_dir else SORT_COLUMNS
        where = [sql]
        order_clause = _apply_filters_and_sort(where, params, args, sort_columns, is_dir)
        limit_clause = f" LIMIT {args.limit}" if args.limit is not None else ""
        full_sql = (
            f"SELECT * FROM {table} WHERE {' AND '.join(where)}{order_clause}{limit_clause}"
        )

        delimiter = "\t" if args.format == "tsv" else ","
        quote_path = args.format == "csv"
        header = CSV_HEADER_DIR if is_dir else CSV_HEADER
        entity = "ディレクトリ" if is_dir else "ファイル"

        count = 0
        total_size = 0
        header_written = False

        for row in conn.execute(full_sql, params):
            if not header_written:
                if not args.no_header and args.format != "path":
                    print(delimiter.join(header))
                header_written = True
            if is_dir:
                db_row = DbDirRow(*row)
                if args.format == "path":
                    print(db_row.path)
                else:
                    _print_dir_row(db_row, delimiter, quote_path=quote_path)
                total_size += db_row.total_size
            else:
                db_row = DbFileRow(*row)
                if args.format == "path":
                    print(db_row.path)
                else:
                    _print_row(db_row, delimiter, quote_path=quote_path)
                if db_row.st_size is not None:
                    total_size += db_row.st_size
            count += 1

        if count == 0:
            if not args.no_summary:
                print(f"マッチする{entity}が見つかりませんでした。")
        elif not args.no_summary:
            if is_dir:
                print(f"検索完了 {count:,} 件")
            else:
                print(f"検索完了 {count:,} 件 / {_format_size(total_size)}")

    def update_db(self) -> None:
        print("データベースの作成を開始します。")

        ignore_names = set(self.config.get("ignore_names", []))
        ignore_paths = {os.path.normpath(p) for p in self.config.get("ignore_paths", [])}

        # ベースディレクトリ自体のstatを取得（DirEntryがないため os.stat()）
        dir_accums: dict[str, _DirAccum] = {}
        for base in self.config.get("target_paths", []):
            norm_base = os.path.normpath(base)
            accum = _DirAccum()
            try:
                st = os.stat(norm_base)
                accum.st_birthtime_ns = getattr(st, "st_birthtime_ns", None)
                accum.st_atime_ns = st.st_atime_ns
                accum.st_mtime_ns = st.st_mtime_ns
                accum.st_file_attributes = getattr(st, "st_file_attributes", None)
            except OSError:
                pass
            dir_accums[norm_base] = accum

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -65536")  # 64MByte
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("DROP TABLE IF EXISTS files")
            conn.execute("DROP TABLE IF EXISTS dirs")
            conn.execute("""
                CREATE TABLE files (
                    id                  INTEGER PRIMARY KEY,
                    path                TEXT NOT NULL UNIQUE,
                    st_size             INTEGER,
                    st_birthtime_ns     INTEGER,
                    st_atime_ns         INTEGER,
                    st_mtime_ns         INTEGER,
                    st_file_attributes  INTEGER,
                    lsize               INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE dirs (
                    id                  INTEGER PRIMARY KEY,
                    path                TEXT NOT NULL UNIQUE,
                    st_birthtime_ns     INTEGER,
                    st_atime_ns         INTEGER,
                    st_mtime_ns         INTEGER,
                    st_file_attributes  INTEGER,
                    files               INTEGER NOT NULL DEFAULT 0,
                    size                INTEGER NOT NULL DEFAULT 0,
                    lsize               INTEGER NOT NULL DEFAULT 0,
                    total_files         INTEGER NOT NULL DEFAULT 0,
                    total_size          INTEGER NOT NULL DEFAULT 0,
                    total_lsize         INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()

            total = 0
            batch: list[FileEntry] = []
            insert_sql = (
                "INSERT OR REPLACE INTO files "
                "(path, st_size, st_birthtime_ns, st_atime_ns, st_mtime_ns, st_file_attributes, lsize) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
            for base in self.config.get("target_paths", []):
                for fe in _scan_files_and_collect_dirs(base, ignore_names, ignore_paths, dir_accums):
                    parent = os.path.dirname(fe.path)
                    if parent in dir_accums:
                        acc = dir_accums[parent]
                        acc.files += 1
                        acc.size += fe.st_size or 0
                        acc.lsize += fe.lsize

                    batch.append(fe)
                    if len(batch) >= BATCH_SIZE:
                        total += len(batch)
                        print(f"  {total:,} 件目を処理中... ({fe.path})")
                        conn.executemany(insert_sql, batch)
                        conn.commit()
                        batch.clear()

            if batch:
                conn.executemany(insert_sql, batch)
                conn.commit()
                total += len(batch)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON files(path)")
            conn.commit()

            # ボトムアップ伝播
            _propagate_totals(dir_accums)

            # dirs テーブルへバッチ INSERT
            dir_insert_sql = (
                "INSERT OR REPLACE INTO dirs "
                "(path, st_birthtime_ns, st_atime_ns, st_mtime_ns, st_file_attributes, "
                " files, size, lsize, total_files, total_size, total_lsize) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            dir_batch = [
                (
                    path,
                    acc.st_birthtime_ns, acc.st_atime_ns, acc.st_mtime_ns, acc.st_file_attributes,
                    acc.files, acc.size, acc.lsize,
                    acc.total_files, acc.total_size, acc.total_lsize,
                )
                for path, acc in dir_accums.items()
            ]
            for i in range(0, len(dir_batch), BATCH_SIZE):
                conn.executemany(dir_insert_sql, dir_batch[i : i + BATCH_SIZE])
                conn.commit()

            conn.execute("CREATE INDEX IF NOT EXISTS idx_dirs_path ON dirs(path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dirs_total_size ON dirs(total_size)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dirs_total_files ON dirs(total_files)")
            conn.commit()

        print(f"{total:,} 件のファイルをインデックスしました。")
        print(f"{len(dir_batch):,} 件のディレクトリをインデックスしました。")

    def search_pattern(self, pattern: str, args: argparse.Namespace) -> None:
        self._check_db()
        table = self._get_table(args)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"PRAGMA case_sensitive_like = {'OFF' if args.ignore_case else 'ON'}"
            )
            self._run_search(conn, "path LIKE ?", [f"%{pattern}%"], args, table)

    def search_regex(self, pattern: str, args: argparse.Namespace) -> None:
        self._check_db()
        table = self._get_table(args)
        flags = re.IGNORECASE if args.ignore_case else 0
        try:
            re.compile(pattern, flags)
        except re.error as e:
            raise SystemExit(f"エラー: 正規表現が不正です: {e}")
        with sqlite3.connect(self.db_path) as conn:
            conn.create_function(
                "REGEXP", 2, lambda pat, val: bool(re.search(pat, val or "", flags))
            )
            self._run_search(conn, "path REGEXP ?", [pattern], args, table)

    def search_all(self, args: argparse.Namespace) -> None:
        self._check_db()
        table = self._get_table(args)
        with sqlite3.connect(self.db_path) as conn:
            self._run_search(conn, "1=1", [], args, table)


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

    all_sort_keys = sorted(set(SORT_COLUMNS) | set(DIR_SORT_COLUMNS))
    parser.add_argument(
        "--sort",
        choices=all_sort_keys,
        metavar="KEY",
        help=(
            "ソートキー (--type file): " + ", ".join(SORT_COLUMNS)
            + " / (--type dir): " + ", ".join(DIR_SORT_COLUMNS)
        ),
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
        "--min-total-size",
        dest="min_total_size",
        metavar="SIZE",
        help="(--type dir 専用) 配下全サイズの下限 (例: 1G)",
    )
    parser.add_argument(
        "--max-total-size",
        dest="max_total_size",
        metavar="SIZE",
        help="(--type dir 専用) 配下全サイズの上限",
    )
    parser.add_argument(
        "--type",
        choices=["file", "dir"],
        default="file",
        dest="type",
        help="検索対象の種類: file（デフォルト）, dir",
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
    parser.add_argument(
        "--target-dir",
        dest="target_dir",
        metavar="DIR",
        help="指定したディレクトリ配下のみを検索対象とする",
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

    if args.create_config:
        return

    app = LocatePyApp(config)

    if args.update:
        app.update_db()
    elif args.regex:
        app.search_regex(args.regex, args)
    elif args.pattern:
        app.search_pattern(args.pattern, args)
    elif _has_search_options(args):
        app.search_all(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
