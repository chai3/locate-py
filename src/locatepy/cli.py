import argparse
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict, cast

BATCH_SIZE = 100_000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000

SORT_COLUMNS = {
    "path": "path",
    "name": "name",
    "size": "size",
    "local_size": "local_size",
    "modified_time": "mtime_ns",
    "created_time": "birthtime_ns",
    "accessed_time": "atime_ns",
}

DIR_SORT_COLUMNS = {
    "path": "path",
    "name": "name",
    "size": "size",
    "local_size": "local_size",
    "modified_time": "mtime_ns",
    "created_time": "birthtime_ns",
    "accessed_time": "atime_ns",
    "files": "files",
    "total_size": "total_size",
    "total_local_size": "total_local_size",
    "total_files": "total_files",
}

CSV_HEADER = [
    "path",
    "name",
    "size",
    "local_size",
    "created_time",
    "accessed_time",
    "modified_time",
    "attributes",
]

CSV_HEADER_DIR = [
    "path",
    "name",
    "files",
    "size",
    "local_size",
    "total_files",
    "total_size",
    "total_local_size",
    "created_time",
    "accessed_time",
    "modified_time",
    "attributes",
]

VALID_FILE_FIELDS: list[str] = CSV_HEADER
VALID_DIR_FIELDS: list[str] = CSV_HEADER_DIR
DEFAULT_FILE_OUTPUT_FIELDS = ["path", "size", "modified_time"]
DEFAULT_DIR_OUTPUT_FIELDS = ["path", "total_size", "total_files", "modified_time"]


class FileResult(TypedDict):
    path: str
    name: str
    size: int | None
    local_size: int
    created_time: str
    accessed_time: str
    modified_time: str
    attributes: int | None


class DirResult(TypedDict):
    path: str
    name: str
    files: int
    size: int
    local_size: int
    total_files: int
    total_size: int
    total_local_size: int
    created_time: str
    accessed_time: str
    modified_time: str
    attributes: int | None


class Config(TypedDict, total=False):
    database_path: str
    target_paths: list[str]
    ignore_paths: list[str]
    ignore_names: list[str]


class FileEntry(NamedTuple):
    path: str
    name: str
    size: int | None
    birthtime_ns: int | None
    atime_ns: int | None
    mtime_ns: int | None
    file_attributes: int | None
    local_size: int


class DbFileRow(NamedTuple):
    id: int
    path: str
    name: str
    size: int | None
    birthtime_ns: int | None
    atime_ns: int | None
    mtime_ns: int | None
    file_attributes: int | None
    local_size: int


class DbDirRow(NamedTuple):
    id: int
    path: str
    name: str
    birthtime_ns: int | None
    atime_ns: int | None
    mtime_ns: int | None
    file_attributes: int | None
    files: int
    size: int
    local_size: int
    total_files: int
    total_size: int
    total_local_size: int


class LocateArgs(argparse.Namespace):
    config: str
    update: bool
    regex: str | None
    pattern: str | None
    name: str | None
    sort: str | None
    sort_order: str | None
    min_size: str | None
    max_size: str | None
    min_total_size: str | None
    max_total_size: str | None
    type: str
    modified_time_after: str | None
    modified_time_before: str | None
    created_time_after: str | None
    created_time_before: str | None
    accessed_time_after: str | None
    accessed_time_before: str | None
    target_dir: str | None
    limit: int | None
    ignore_case: bool
    format: str
    init: bool
    mcp: bool
    output_fields: list[str] | None


class _DirAccum:
    __slots__ = (
        "atime_ns",
        "birthtime_ns",
        "file_attributes",
        "files",
        "local_size",
        "mtime_ns",
        "name",
        "size",
        "total_files",
        "total_local_size",
        "total_size",
    )

    def __init__(self) -> None:
        self.name: str = ""
        self.birthtime_ns: int | None = None
        self.atime_ns: int | None = None
        self.mtime_ns: int | None = None
        self.file_attributes: int | None = None
        self.files: int = 0
        self.size: int = 0
        self.local_size: int = 0
        self.total_files: int = 0
        self.total_size: int = 0
        self.total_local_size: int = 0


def _calc_local_size(_path: str, size: int | None, file_attributes: int | None) -> int:
    if file_attributes is not None and (
        file_attributes & FILE_ATTRIBUTE_RECALL_ON_OPEN
    ):
        return 0
    return size if size is not None else 0


def _file_batch_rows(batch: list[FileEntry]) -> list[tuple]:
    return [
        (
            e.path,
            e.name,
            e.size,
            e.birthtime_ns,
            e.atime_ns,
            e.mtime_ns,
            e.file_attributes,
            e.local_size,
        )
        for e in batch
    ]


def interactive_init(config_path: Path) -> None:
    """npm init スタイルの対話的な設定ファイル作成"""
    print("This utility will walk you through creating a locate-py config file.")
    print("Press ^C at any time to quit.\n")

    default_db = "locate-py.db"
    db_input = input(f"database path: ({default_db}) ").strip()
    database_path = db_input or default_db

    default_target = str(Path.cwd())
    targets_input = input(f"target paths(comma-separated): ({default_target}) ").strip()
    target_paths = (
        [p.strip() for p in targets_input.split(",")]
        if targets_input
        else [default_target]
    )

    ignores_input = input("ignore paths(comma-separated): ").strip()
    ignore_paths: list[str] = []
    if ignores_input:
        ignore_paths = [p.strip() for p in ignores_input.split(",")]

    ignore_names_input = input("ignore names(comma-separated) : ").strip()
    ignore_names: list[str] = []
    if ignore_names_input:
        ignore_names = [n.strip() for n in ignore_names_input.split(",")]

    config: Config = {
        "database_path": database_path,
        "target_paths": target_paths,
        "ignore_paths": ignore_paths,
        "ignore_names": ignore_names,
    }

    print(f"\nAbout to write to {config_path}:")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    print()
    answer = input("Is this OK? ([Y]es / [N]o): ").strip().lower()
    if answer not in ("y", "yes", ""):
        print("Aborted.")
        sys.exit(1)

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\nConfig file created: {config_path}")

    db_answer = input("\nBuild database now? ([Y]es / [N]o): ").strip().lower()
    if db_answer in ("y", "yes", ""):
        app = LocatePy(config, LocateArgs())
        for msg in app.update_db():
            print(msg)
        print("Database built successfully.")


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise SystemExit("Error: config file not found. Run locatepy --init first.")
    with config_path.open(encoding="utf-8") as f:
        return json.load(f)


def _scan_files_and_collect_dirs(
    path: str,
    ignore_names: set[str],
    ignore_paths: set[str],
    dir_accums: dict[str, "_DirAccum"],
) -> Iterator[FileEntry]:
    """Yield files while accumulating directory stats into dir_accums."""
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
                            accum.name = entry.name
                            try:
                                st = entry.stat(follow_symlinks=False)
                                accum.birthtime_ns = getattr(
                                    st, "st_birthtime_ns", None
                                )
                                accum.atime_ns = st.st_atime_ns
                                accum.mtime_ns = st.st_mtime_ns
                                accum.file_attributes = getattr(
                                    st, "st_file_attributes", None
                                )
                            except OSError:
                                pass
                            dir_accums[norm] = accum
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        path_norm = os.path.normpath(entry.path)
                        size = st.st_size
                        file_attributes = getattr(st, "st_file_attributes", None)
                        yield FileEntry(
                            path=path_norm,
                            name=entry.name,
                            size=size,
                            birthtime_ns=getattr(st, "st_birthtime_ns", None),
                            atime_ns=st.st_atime_ns,
                            mtime_ns=st.st_mtime_ns,
                            file_attributes=file_attributes,
                            local_size=_calc_local_size(
                                path_norm, size, file_attributes
                            ),
                        )
        except PermissionError:
            pass
        except OSError:
            pass


def _propagate_totals(dir_accums: dict[str, "_DirAccum"]) -> None:
    """Propagate total_* bottom-up from direct-child aggregates."""
    for acc in dir_accums.values():
        acc.total_files = acc.files
        acc.total_size = acc.size
        acc.total_local_size = acc.local_size
    for d in sorted(dir_accums, key=lambda p: p.count(os.sep), reverse=True):
        parent = os.path.dirname(d)
        if parent != d and parent in dir_accums:
            p = dir_accums[parent]
            c = dir_accums[d]
            p.total_files += c.total_files
            p.total_size += c.total_size
            p.total_local_size += c.total_local_size


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
            return int(datetime.strptime(s.strip(), fmt).timestamp() * 1e9)  # noqa: DTZ007 treat user input as local time
        except ValueError:
            continue
    raise SystemExit(
        f"Error: invalid date format: {s!r}\n"
        "  Use one of: YYYY-MM-DD / YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM:SS"
    )


def _add_size_filter(
    where: list[str], params: list, col_expr: str, val: str, option_name: str
) -> None:
    try:
        where.append(f"{col_expr} ?")
        params.append(_parse_size(val))
    except ValueError:
        raise SystemExit(f"Error: invalid value for {option_name}: {val!r}") from None


def _build_order_clause(
    args: LocateArgs, sort_columns: dict[str, str], *, is_dir: bool
) -> str:
    if args.sort is None and args.sort_order is None:
        return ""
    sort_key = args.sort or "path"
    if sort_key not in sort_columns:
        valid = ", ".join(sort_columns)
        raise SystemExit(
            f"Error: --sort {sort_key!r} is not available for"
            f" --type {'dir' if is_dir else 'file'}."
            f" Valid keys: {valid}"
        )
    if args.sort_order:
        order = args.sort_order.upper()
    elif sort_key == "path":
        order = "ASC"
    else:
        order = "DESC"
    return f" ORDER BY {sort_columns[sort_key]} {order}"


def _apply_filters_and_sort(  # noqa: C901
    where: list[str],
    params: list,
    args: LocateArgs,
    sort_columns: dict[str, str] = SORT_COLUMNS,
    *,
    is_dir: bool = False,
) -> str:
    if args.target_dir:
        norm = os.path.normpath(args.target_dir)
        where.append("path LIKE ?")
        params.append(norm + os.sep + "%")
    if args.min_size is not None:
        _add_size_filter(where, params, "size >=", args.min_size, "--min-size")
    if args.max_size is not None:
        _add_size_filter(where, params, "size <=", args.max_size, "--max-size")
    if is_dir:
        min_total = getattr(args, "min_total_size", None)
        max_total = getattr(args, "max_total_size", None)
        if min_total is not None:
            _add_size_filter(
                where, params, "total_size >=", min_total, "--min-total-size"
            )
        if max_total is not None:
            _add_size_filter(
                where, params, "total_size <=", max_total, "--max-total-size"
            )
    for col, after_attr, before_attr in [
        ("mtime_ns", "modified_time_after", "modified_time_before"),
        ("birthtime_ns", "created_time_after", "created_time_before"),
        ("atime_ns", "accessed_time_after", "accessed_time_before"),
    ]:
        after_val = getattr(args, after_attr)
        before_val = getattr(args, before_attr)
        if after_val is not None:
            where.append(f"{col} >= ?")
            params.append(_parse_date_ns(after_val))
        if before_val is not None:
            where.append(f"{col} <= ?")
            params.append(_parse_date_ns(before_val))
    name_val = getattr(args, "name", None)
    if name_val is not None:
        where.append("name LIKE ?")
        params.append(f"%{name_val}%")
    return _build_order_clause(args, sort_columns, is_dir=is_dir)


def _format_size(size: int) -> str:
    size: float | int
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:  # noqa: PLR2004
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _ns_to_str(ns: int | None) -> str:
    if ns is None:
        return ""
    return datetime.fromtimestamp(ns / 1e9).strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ006 display in local time


def _row_to_dict(row: tuple, *, is_dir: bool) -> FileResult | DirResult:
    if is_dir:
        r = DbDirRow(*row)
        return {
            "path": r.path,
            "name": r.name,
            "files": r.files,
            "size": r.size,
            "local_size": r.local_size,
            "total_files": r.total_files,
            "total_size": r.total_size,
            "total_local_size": r.total_local_size,
            "created_time": _ns_to_str(r.birthtime_ns),
            "accessed_time": _ns_to_str(r.atime_ns),
            "modified_time": _ns_to_str(r.mtime_ns),
            "attributes": r.file_attributes,
        }
    r = DbFileRow(*row)
    return {
        "path": r.path,
        "name": r.name,
        "size": r.size,
        "local_size": r.local_size,
        "created_time": _ns_to_str(r.birthtime_ns),
        "accessed_time": _ns_to_str(r.atime_ns),
        "modified_time": _ns_to_str(r.mtime_ns),
        "attributes": r.file_attributes,
    }


def _format_csv_fields(
    d: FileResult | DirResult,
    path: str,
    *,
    is_dir: bool,
    output_fields: list[str],
) -> list[str]:
    if is_dir:
        dr = cast("DirResult", d)
        field_map: dict[str, str] = {
            "path": path,
            "name": dr["name"],
            "files": str(dr["files"]),
            "size": str(dr["size"]),
            "local_size": str(dr["local_size"]),
            "total_files": str(dr["total_files"]),
            "total_size": str(dr["total_size"]),
            "total_local_size": str(dr["total_local_size"]),
            "created_time": dr["created_time"],
            "accessed_time": dr["accessed_time"],
            "modified_time": dr["modified_time"],
            "attributes": str(dr["attributes"]) if dr["attributes"] is not None else "",
        }
    else:
        fr = cast("FileResult", d)
        field_map = {
            "path": path,
            "name": fr["name"],
            "size": str(fr["size"]) if fr["size"] is not None else "",
            "local_size": str(fr["local_size"]),
            "created_time": fr["created_time"],
            "accessed_time": fr["accessed_time"],
            "modified_time": fr["modified_time"],
            "attributes": str(fr["attributes"]) if fr["attributes"] is not None else "",
        }
    return [field_map[f] for f in output_fields]


def _get_entry_size(d: FileResult | DirResult, *, is_dir: bool) -> int:
    if is_dir:
        return cast("DirResult", d)["total_size"]
    return cast("FileResult", d)["size"] or 0


def _print_summary(
    count: int, total_size: int, args: LocateArgs, *, is_dir: bool
) -> None:
    if args.format != "human":
        return
    entity = "directory" if is_dir else "file"
    if count == 0:
        print(f"No matching {entity} found.")
    elif is_dir:
        print(f"Search complete: {count:,} entries")
    else:
        print(f"Search complete: {count:,} entries / {_format_size(total_size)}")


def _print_results(
    results: Iterator[FileResult | DirResult],
    args: LocateArgs,
    *,
    is_dir: bool,
) -> None:
    delimiter = "\t" if args.format == "tsv" else ","

    output_fields: list[str] = (
        args.output_fields
        if args.output_fields is not None
        else (DEFAULT_DIR_OUTPUT_FIELDS if is_dir else DEFAULT_FILE_OUTPUT_FIELDS)
    )

    count = 0
    total_size = 0
    header_written = False
    json_results: list[dict[str, object]] = []

    for d in results:
        if not header_written:
            if args.format == "human":
                print(delimiter.join(output_fields))
            header_written = True

        if args.format == "path":
            print(d["path"])
        elif args.format == "jsonl":
            d_dict = cast("dict[str, object]", d)
            print(json.dumps({k: d_dict[k] for k in output_fields}, ensure_ascii=False))
        elif args.format == "json":
            d_dict = cast("dict[str, object]", d)
            json_results.append({k: d_dict[k] for k in output_fields})
        else:
            # tsv / csv
            path = f'"{d["path"]}"' if args.format == "csv" else d["path"]
            fields = _format_csv_fields(
                d, path, is_dir=is_dir, output_fields=output_fields
            )
            print(delimiter.join(fields))

        total_size += _get_entry_size(d, is_dir=is_dir)
        count += 1

    if args.format == "json":
        print(json.dumps(json_results, ensure_ascii=False, indent=2))

    _print_summary(count, total_size, args, is_dir=is_dir)


_SEARCH_OPTION_ATTRS = (
    "name",
    "sort",
    "sort_order",
    "limit",
    "min_size",
    "max_size",
    "min_total_size",
    "max_total_size",
    "modified_time_after",
    "modified_time_before",
    "created_time_after",
    "created_time_before",
    "accessed_time_after",
    "accessed_time_before",
    "ignore_case",
    "type",
    "target_dir",
)


def _has_search_options(args: LocateArgs) -> bool:
    # if type is "dir", treat it as an explicit search
    if getattr(args, "type", "file") == "dir":
        return True
    return any(getattr(args, attr, None) for attr in _SEARCH_OPTION_ATTRS)


class LocatePy:
    def __init__(self, config: Config, args: LocateArgs) -> None:
        self.config = config
        self.args = args
        db_path_str = config.get("database_path")
        self.db_path: Path = Path(db_path_str) if db_path_str else Path("locate-py.db")

    def _check_db(self) -> None:
        if not self.db_path.exists():
            raise SystemExit("Error: database not found. Run locatepy -u first.")

    def _get_table(self) -> Literal["files", "dirs"]:
        return "dirs" if self.args.type == "dir" else "files"

    def _run_search(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params: list,
        table: Literal["files", "dirs"] = "files",
    ) -> Iterator[FileResult | DirResult]:
        pragma_value = "OFF" if self.args.ignore_case else "ON"
        conn.execute(f"PRAGMA case_sensitive_like = {pragma_value}")
        is_dir = table == "dirs"
        sort_columns = DIR_SORT_COLUMNS if is_dir else SORT_COLUMNS
        where = [sql]
        order_clause = _apply_filters_and_sort(
            where, params, self.args, sort_columns, is_dir=is_dir
        )
        limit_clause = (
            f" LIMIT {self.args.limit}" if self.args.limit is not None else ""
        )
        conditions = " AND ".join(where)
        full_sql = (
            f"SELECT * FROM {table} WHERE {conditions}{order_clause}{limit_clause}"  # noqa: S608
        )
        for row in conn.execute(full_sql, params):
            yield _row_to_dict(row, is_dir=is_dir)

    def _setup_database(self, conn: sqlite3.Connection) -> None:
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
                name                TEXT NOT NULL DEFAULT '',
                size                INTEGER,
                birthtime_ns        INTEGER,
                atime_ns            INTEGER,
                mtime_ns            INTEGER,
                file_attributes     INTEGER,
                local_size          INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE dirs (
                id                  INTEGER PRIMARY KEY,
                path                TEXT NOT NULL UNIQUE,
                name                TEXT NOT NULL DEFAULT '',
                birthtime_ns        INTEGER,
                atime_ns            INTEGER,
                mtime_ns            INTEGER,
                file_attributes     INTEGER,
                files               INTEGER NOT NULL DEFAULT 0,
                size                INTEGER NOT NULL DEFAULT 0,
                local_size          INTEGER NOT NULL DEFAULT 0,
                total_files         INTEGER NOT NULL DEFAULT 0,
                total_size          INTEGER NOT NULL DEFAULT 0,
                total_local_size    INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()

    def _insert_directories(
        self, conn: sqlite3.Connection, dir_accums: dict[str, _DirAccum]
    ) -> int:
        dir_insert_sql = (
            "INSERT OR REPLACE INTO dirs "
            "(path, name, birthtime_ns, atime_ns, mtime_ns, file_attributes, "
            " files, size, local_size, total_files, total_size, total_local_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        dir_batch = [
            (
                path,
                acc.name,
                acc.birthtime_ns,
                acc.atime_ns,
                acc.mtime_ns,
                acc.file_attributes,
                acc.files,
                acc.size,
                acc.local_size,
                acc.total_files,
                acc.total_size,
                acc.total_local_size,
            )
            for path, acc in dir_accums.items()
        ]
        for i in range(0, len(dir_batch), BATCH_SIZE):
            conn.executemany(dir_insert_sql, dir_batch[i : i + BATCH_SIZE])
            conn.commit()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dirs_path ON dirs(path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dirs_name ON dirs(name)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dirs_total_size ON dirs(total_size)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dirs_total_files ON dirs(total_files)"
        )
        conn.commit()
        return len(dir_batch)

    def update_db(self) -> Iterator[str]:
        yield "Starting database creation."

        ignore_names = set(self.config.get("ignore_names", []))
        ignore_paths = {
            os.path.normpath(p) for p in self.config.get("ignore_paths", [])
        }

        # Get stat for base directory itself (use os.stat() since there is no DirEntry)
        dir_accums: dict[str, _DirAccum] = {}
        for base in self.config.get("target_paths", []):
            norm_base = os.path.normpath(base)
            accum = _DirAccum()
            accum.name = os.path.basename(norm_base)
            try:
                st = os.stat(norm_base)
                accum.birthtime_ns = getattr(st, "st_birthtime_ns", None)
                accum.atime_ns = st.st_atime_ns
                accum.mtime_ns = st.st_mtime_ns
                accum.file_attributes = getattr(st, "st_file_attributes", None)
            except OSError:
                pass
            dir_accums[norm_base] = accum

        with sqlite3.connect(self.db_path) as conn:
            self._setup_database(conn)

            total = 0
            batch: list[FileEntry] = []
            insert_sql = (
                "INSERT OR REPLACE INTO files "
                "(path, name, size, birthtime_ns, atime_ns, "
                "mtime_ns, file_attributes, local_size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for base in self.config.get("target_paths", []):
                for fe in _scan_files_and_collect_dirs(
                    base, ignore_names, ignore_paths, dir_accums
                ):
                    parent = os.path.dirname(fe.path)
                    if parent in dir_accums:
                        acc = dir_accums[parent]
                        acc.files += 1
                        acc.size += fe.size or 0
                        acc.local_size += fe.local_size
                    batch.append(fe)
                    if len(batch) >= BATCH_SIZE:
                        total += len(batch)
                        yield f"  Processing entry {total:,}... ({fe.path})"
                        conn.executemany(insert_sql, _file_batch_rows(batch))
                        conn.commit()
                        batch.clear()

            if batch:
                conn.executemany(insert_sql, _file_batch_rows(batch))
                conn.commit()
                total += len(batch)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON files(path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON files(name)")
            conn.commit()

            _propagate_totals(dir_accums)
            dir_count = self._insert_directories(conn, dir_accums)

        yield f"Indexed {total:,} files."
        yield f"Indexed {dir_count:,} directories."

    def search_pattern(self, pattern: str) -> Iterator[FileResult | DirResult]:
        self._check_db()
        table = self._get_table()
        with sqlite3.connect(self.db_path) as conn:
            yield from self._run_search(conn, "path LIKE ?", [f"%{pattern}%"], table)

    def search_regex(self, pattern: str) -> Iterator[FileResult | DirResult]:
        self._check_db()
        table = self._get_table()
        flags = re.IGNORECASE if self.args.ignore_case else 0
        try:
            re.compile(pattern, flags)
        except re.error as e:
            raise SystemExit(f"Error: invalid regular expression: {e}") from e
        with sqlite3.connect(self.db_path) as conn:
            conn.create_function(
                "REGEXP", 2, lambda pat, val: bool(re.search(pat, val or "", flags))
            )
            yield from self._run_search(conn, "path REGEXP ?", [pattern], table)

    def search_all(self) -> Iterator[FileResult | DirResult]:
        self._check_db()
        table = self._get_table()
        with sqlite3.connect(self.db_path) as conn:
            yield from self._run_search(conn, "1=1", [], table)


def _parse_output_fields(
    raw: str, *, is_dir: bool, parser: argparse.ArgumentParser
) -> list[str]:
    valid_fields = VALID_DIR_FIELDS if is_dir else VALID_FILE_FIELDS
    parsed = [f.strip() for f in raw.split(",") if f.strip()]
    if not parsed:
        parser.error("--output-fields: at least one field must be specified")
    invalid = [f for f in parsed if f not in valid_fields]
    if invalid:
        parser.error(
            f"--output-fields: invalid field(s): {', '.join(invalid)}. "
            f"Valid fields: {', '.join(valid_fields)}"
        )
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple locate command")
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        default="locate-py.json",
        help="Path to config file (default: locate-py.json)",
    )
    parser.add_argument(
        "-u", "--update", action="store_true", help="Update the database"
    )
    parser.add_argument(
        "-r", "--regex", metavar="PATTERN", help="Search with regex pattern"
    )
    parser.add_argument("pattern", nargs="?", help="Search by pattern (partial match)")
    parser.add_argument(
        "--name",
        metavar="PATTERN",
        help="Search by file/directory name only (basename, not parent dirs)",
    )

    all_sort_keys = sorted(set(SORT_COLUMNS) | set(DIR_SORT_COLUMNS))
    parser.add_argument(
        "--sort",
        choices=all_sort_keys,
        metavar="KEY",
        help=(
            "Sort key (--type file): "
            + ", ".join(SORT_COLUMNS)
            + " / (--type dir): "
            + ", ".join(DIR_SORT_COLUMNS)
        ),
    )
    parser.add_argument(
        "--sort-order",
        choices=["asc", "desc"],
        dest="sort_order",
        metavar="ORDER",
        help="Sort order: asc / desc (default: path→asc, others→desc)",
    )
    parser.add_argument(
        "--min-size",
        dest="min_size",
        metavar="SIZE",
        help="Minimum size (e.g. 1K, 10M)",
    )
    parser.add_argument(
        "--max-size",
        dest="max_size",
        metavar="SIZE",
        help="Maximum size (e.g. 100M, 1G)",
    )
    parser.add_argument(
        "--min-total-size",
        dest="min_total_size",
        metavar="SIZE",
        help="(--type dir only) Minimum total size under directory (e.g. 1G)",
    )
    parser.add_argument(
        "--max-total-size",
        dest="max_total_size",
        metavar="SIZE",
        help="(--type dir only) Maximum total size under directory",
    )
    parser.add_argument(
        "--type",
        choices=["file", "dir"],
        default="file",
        dest="type",
        help="Type to search: file (default), dir",
    )
    parser.add_argument(
        "--modified-time-after",
        dest="modified_time_after",
        metavar="DATE",
        help="Modified time lower bound",
    )
    parser.add_argument(
        "--modified-time-before",
        dest="modified_time_before",
        metavar="DATE",
        help="Modified time upper bound",
    )
    parser.add_argument(
        "--created-time-after",
        dest="created_time_after",
        metavar="DATE",
        help="Creation time lower bound",
    )
    parser.add_argument(
        "--created-time-before",
        dest="created_time_before",
        metavar="DATE",
        help="Creation time upper bound",
    )
    parser.add_argument(
        "--accessed-time-after",
        dest="accessed_time_after",
        metavar="DATE",
        help="Access time lower bound",
    )
    parser.add_argument(
        "--accessed-time-before",
        dest="accessed_time_before",
        metavar="DATE",
        help="Access time upper bound",
    )
    parser.add_argument(
        "--target-dir",
        dest="target_dir",
        metavar="DIR",
        help="Restrict search to the specified directory",
    )

    parser.add_argument(
        "-l", "--limit", type=int, metavar="N", help="Maximum number of matches"
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        dest="ignore_case",
        help="Case-insensitive search",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["human", "tsv", "csv", "path", "json", "jsonl"],
        default="human",
        dest="format",
        help="Output format: human (default), tsv, csv, path, json, jsonl",
    )
    parser.add_argument(
        "--output-fields",
        dest="output_fields",
        metavar="FIELDS",
        default=None,
        help=(
            "Comma-separated fields to output (e.g. path,size,modified_time). "
            "Default for --type file: path,size,modified_time. "
            "Default for --type dir: path,total_size,modified_time. "
            "File fields: path,size,local_size,created_time,accessed_time,"
            "modified_time,attributes. "
            "Dir fields: path,files,size,local_size,total_files,total_size,"
            "total_local_size,created_time,accessed_time,modified_time,attributes."
        ),
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Interactively create config file and optionally build database",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP server (stdio transport)",
    )

    args = parser.parse_args(namespace=LocateArgs())

    if args.output_fields is not None:
        args.output_fields = _parse_output_fields(
            cast("str", args.output_fields), is_dir=args.type == "dir", parser=parser
        )

    if args.mcp:
        from locatepy import mcp as mcp_module  # noqa: PLC0415

        mcp_module.main(["--config", args.config])
        return

    if args.init:
        interactive_init(Path(args.config))
        return

    config = load_config(Path(args.config))

    app = LocatePy(config, args)

    is_dir = args.type == "dir"
    if args.update:
        for msg in app.update_db():
            print(msg)
    elif args.regex:
        _print_results(app.search_regex(args.regex), args, is_dir=is_dir)
    elif args.pattern:
        _print_results(app.search_pattern(args.pattern), args, is_dir=is_dir)
    elif _has_search_options(args):
        _print_results(app.search_all(), args, is_dir=is_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
