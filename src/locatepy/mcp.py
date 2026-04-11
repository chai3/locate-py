"""MCP server for locatepy."""

import argparse
import re
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from locatepy.cli import (
    DirResult,
    FileResult,
    LocateArgs,
    LocatePy,
    load_config,
)

_state: dict[str, str] = {"config_path": "locate-py.json"}

mcp = FastMCP(
    name="locatepy",
    instructions=(
        "Search files and directories indexed by locatepy. "
        "Use 'search' for pattern searches (substring by default, "
        "regex when regex=True)."
    ),
)


def _make_locate_args(  # noqa: PLR0913
    *,
    entry_type: str = "file",
    name: str | None = None,
    sort: str | None = None,
    sort_order: str | None = None,
    limit: int | None = None,
    min_size: str | None = None,
    max_size: str | None = None,
    min_total_size: str | None = None,
    max_total_size: str | None = None,
    modified_time_after: str | None = None,
    modified_time_before: str | None = None,
    created_time_after: str | None = None,
    created_time_before: str | None = None,
    accessed_time_after: str | None = None,
    accessed_time_before: str | None = None,
    target_dir: str | None = None,
    ignore_case: bool = False,
) -> LocateArgs:
    args = LocateArgs()
    args.type = entry_type
    args.name = name
    args.sort = sort
    args.sort_order = sort_order
    args.limit = limit
    args.min_size = min_size
    args.max_size = max_size
    args.min_total_size = min_total_size
    args.max_total_size = max_total_size
    args.modified_time_after = modified_time_after
    args.modified_time_before = modified_time_before
    args.created_time_after = created_time_after
    args.created_time_before = created_time_before
    args.accessed_time_after = accessed_time_after
    args.accessed_time_before = accessed_time_before
    args.target_dir = target_dir
    args.ignore_case = ignore_case
    args.format = "json"
    return args


def _make_app(config_path: str | None, **kwargs: Any) -> LocatePy:  # noqa: ANN401
    path = Path(config_path) if config_path else Path(_state["config_path"])
    config = load_config(path)
    return LocatePy(config, _make_locate_args(**kwargs))


@mcp.tool()
def search(  # noqa: PLR0913
    pattern: Annotated[str, "Pattern to search for in file/directory paths"],
    regex: Annotated[bool, "Treat pattern as a regular expression"] = False,  # noqa: FBT002
    type: Annotated[str, "Entry type: 'file' or 'dir'"] = "file",  # noqa: A002
    name: Annotated[
        str | None, "Search by file/directory name only (basename, not parent dirs)"
    ] = None,
    sort: Annotated[
        str | None,
        "Sort key (name, path, size, modified_time, created_time, accessed_time, ...)",
    ] = None,
    sort_order: Annotated[str | None, "Sort order: 'asc' or 'desc'"] = None,
    limit: Annotated[int | None, "Maximum number of results"] = None,
    min_size: Annotated[str | None, "Minimum file size (e.g. '1M', '500K')"] = None,
    max_size: Annotated[str | None, "Maximum file size (e.g. '100M', '1G')"] = None,
    min_total_size: Annotated[
        str | None, "Minimum total dir size (dir type only)"
    ] = None,
    max_total_size: Annotated[
        str | None, "Maximum total dir size (dir type only)"
    ] = None,
    modified_time_after: Annotated[
        str | None, "Modified after (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"
    ] = None,
    modified_time_before: Annotated[str | None, "Modified before"] = None,
    created_time_after: Annotated[str | None, "Created after"] = None,
    created_time_before: Annotated[str | None, "Created before"] = None,
    accessed_time_after: Annotated[str | None, "Accessed after"] = None,
    accessed_time_before: Annotated[str | None, "Accessed before"] = None,
    target_dir: Annotated[str | None, "Restrict search to this directory"] = None,
    ignore_case: Annotated[bool, "Case-insensitive search"] = False,  # noqa: FBT002
    config_path: Annotated[str | None, "Path to locate-py.json config file"] = None,
) -> list[FileResult | DirResult]:
    """Search for files or directories matching a pattern (substring or regex)."""
    app = _make_app(
        config_path,
        entry_type=type,
        name=name,
        sort=sort,
        sort_order=sort_order,
        limit=limit,
        min_size=min_size,
        max_size=max_size,
        min_total_size=min_total_size,
        max_total_size=max_total_size,
        modified_time_after=modified_time_after,
        modified_time_before=modified_time_before,
        created_time_after=created_time_after,
        created_time_before=created_time_before,
        accessed_time_after=accessed_time_after,
        accessed_time_before=accessed_time_before,
        target_dir=target_dir,
        ignore_case=ignore_case,
    )
    try:
        if regex:
            return list(app.search_regex(pattern))
        return list(app.search_pattern(pattern))
    except re.error as e:
        raise ValueError(f"Invalid regular expression: {e}") from e
    except SystemExit as e:
        raise ValueError(str(e)) from e


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for locatepy")
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        default="locate-py.json",
        help="Path to config file (default: locate-py.json)",
    )
    args = parser.parse_args(argv)
    _state["config_path"] = args.config
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
