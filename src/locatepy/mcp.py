"""MCP server for locatepy."""
import re
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from locatepy.cli import (
    DirResult,
    FileResult,
    LocateArgs,
    LocatePy,
    load_config,
)

mcp = FastMCP(
    name="locatepy",
    instructions=(
        "Search files and directories indexed by locatepy. "
        "Use 'search' for pattern (substring) searches, "
        "'search_regex' for regular expression searches, "
        "and 'update_index' to rebuild the index."
    ),
)


def _make_locate_args(
    *,
    type: str = "file",
    sort: str | None = None,
    sort_order: str | None = None,
    limit: int | None = None,
    min_size: str | None = None,
    max_size: str | None = None,
    min_total_size: str | None = None,
    max_total_size: str | None = None,
    mtime_after: str | None = None,
    mtime_before: str | None = None,
    ctime_after: str | None = None,
    ctime_before: str | None = None,
    atime_after: str | None = None,
    atime_before: str | None = None,
    target_dir: str | None = None,
    ignore_case: bool = False,
) -> LocateArgs:
    args = LocateArgs()
    args.type = type
    args.sort = sort
    args.sort_order = sort_order
    args.limit = limit
    args.min_size = min_size
    args.max_size = max_size
    args.min_total_size = min_total_size
    args.max_total_size = max_total_size
    args.mtime_after = mtime_after
    args.mtime_before = mtime_before
    args.ctime_after = ctime_after
    args.ctime_before = ctime_before
    args.atime_after = atime_after
    args.atime_before = atime_before
    args.target_dir = target_dir
    args.ignore_case = ignore_case
    args.format = "json"
    args.no_header = True
    args.no_summary = True
    return args


def _make_app(config_path: str | None, **kwargs) -> LocatePy:
    path = Path(config_path) if config_path else Path("locate-py.json")
    config = load_config(path)
    return LocatePy(config, _make_locate_args(**kwargs))


@mcp.tool()
def search(
    pattern: Annotated[str, "Substring to search for in file/directory paths"],
    type: Annotated[str, "Entry type: 'file' or 'dir'"] = "file",
    sort: Annotated[str | None, "Sort key (path, size, mtime, ctime, atime, lsize, ...)"] = None,
    sort_order: Annotated[str | None, "Sort order: 'asc' or 'desc'"] = None,
    limit: Annotated[int | None, "Maximum number of results"] = None,
    min_size: Annotated[str | None, "Minimum file size (e.g. '1M', '500K')"] = None,
    max_size: Annotated[str | None, "Maximum file size (e.g. '100M', '1G')"] = None,
    min_total_size: Annotated[str | None, "Minimum total dir size (dir type only)"] = None,
    max_total_size: Annotated[str | None, "Maximum total dir size (dir type only)"] = None,
    mtime_after: Annotated[str | None, "Modified after (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"] = None,
    mtime_before: Annotated[str | None, "Modified before"] = None,
    ctime_after: Annotated[str | None, "Created after"] = None,
    ctime_before: Annotated[str | None, "Created before"] = None,
    atime_after: Annotated[str | None, "Accessed after"] = None,
    atime_before: Annotated[str | None, "Accessed before"] = None,
    target_dir: Annotated[str | None, "Restrict search to this directory"] = None,
    ignore_case: Annotated[bool, "Case-insensitive search"] = False,
    config_path: Annotated[str | None, "Path to locate-py.json config file"] = None,
) -> list[FileResult | DirResult]:
    """Search for files or directories matching a substring pattern."""
    app = _make_app(
        config_path,
        type=type,
        sort=sort,
        sort_order=sort_order,
        limit=limit,
        min_size=min_size,
        max_size=max_size,
        min_total_size=min_total_size,
        max_total_size=max_total_size,
        mtime_after=mtime_after,
        mtime_before=mtime_before,
        ctime_after=ctime_after,
        ctime_before=ctime_before,
        atime_after=atime_after,
        atime_before=atime_before,
        target_dir=target_dir,
        ignore_case=ignore_case,
    )
    try:
        return list(app.search_pattern(pattern))
    except SystemExit as e:
        raise ValueError(str(e)) from e


@mcp.tool()
def search_regex(
    pattern: Annotated[str, "Regular expression to search for in file/directory paths"],
    type: Annotated[str, "Entry type: 'file' or 'dir'"] = "file",
    sort: Annotated[str | None, "Sort key"] = None,
    sort_order: Annotated[str | None, "Sort order: 'asc' or 'desc'"] = None,
    limit: Annotated[int | None, "Maximum number of results"] = None,
    min_size: Annotated[str | None, "Minimum file size"] = None,
    max_size: Annotated[str | None, "Maximum file size"] = None,
    target_dir: Annotated[str | None, "Restrict search to this directory"] = None,
    ignore_case: Annotated[bool, "Case-insensitive search"] = False,
    config_path: Annotated[str | None, "Path to locate-py.json config file"] = None,
) -> list[FileResult | DirResult]:
    """Search for files or directories matching a regular expression."""
    app = _make_app(
        config_path,
        type=type,
        sort=sort,
        sort_order=sort_order,
        limit=limit,
        min_size=min_size,
        max_size=max_size,
        target_dir=target_dir,
        ignore_case=ignore_case,
    )
    try:
        return list(app.search_regex(pattern))
    except re.error as e:
        raise ValueError(f"Invalid regular expression: {e}") from e
    except SystemExit as e:
        raise ValueError(str(e)) from e


@mcp.tool()
def update_index(
    config_path: Annotated[str | None, "Path to locate-py.json config file"] = None,
) -> str:
    """Rebuild the file system index. Returns a status message."""
    app = _make_app(config_path)
    return "\n".join(app.update_db())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
