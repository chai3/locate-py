# locate-py

A SQLite-based local file search tool. Indexes files and directories for fast searching by path, size, and timestamp.

## Getting Started
### Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

Invoke directly without installing
```shell
uvx --from git+https://github.com/chai3/locate-py locatepy [args]
```

Or globally install

```shell
uv tool install --from git+https://github.com/chai3/locate-py locatepy
```

### Setup(Indexing)

Both files and directories are indexed.

1. Simple indexing method
```shell
cd <target-directory>
locatepy -u # Index current directory
```

1. Advanced index method
```shell
locatepy --create-config
# Configure the targets and other settings in the generated config.json.
locatepy -u # Index based on config.json
```


### locate-py.json example

```json
{
  "database_path": "locate-py.db",
  "target_paths": ["C:\\", "D:\\"], // ex: "C:\\" "\\\\192.168.1.2\\share" "/" "/home"
  "ignore_paths": ["C:\\$Recycle.Bin"],
  "ignore_names": [""] // .git .venv node_modules
}
```


## File Search (`--type file`, default)

### Pattern search (partial match)

```shell
locatepy report
locatepy -i report          # case-insensitive
locatepy -r "\.log$"        # regex
```

### Size filter

```shell
locatepy --min-size 100M               # 100 MB or larger
locatepy --min-size 1G --sort size     # 1 GB or larger, sorted by size
```

### Time filter

```shell
locatepy --mtime-after 2024-01-01
locatepy --mtime-after "2024-06-01 00:00" --mtime-before "2024-06-30 23:59"
```

### Output options

```shell
locatepy report --format path          # path only
locatepy report --format csv           # CSV output
locatepy report -l 20                  # up to 20 results
locatepy report --no-header            # no header row
locatepy report --sort size            # sort by size descending
```

**Sort keys (`--type file`):** `path`, `size`, `lsize`, `mtime`, `ctime`, `atime`

---

## Directory Search (`--type dir`)

### Find large folders (recursive total)

```shell
locatepy --type dir --min-total-size 1G --sort total_size
```

### Find folders with many files (recursive total)

```shell
locatepy --type dir --sort total_files
```

### Find folders with many direct files

```shell
locatepy --type dir --sort files
```

### Filter by direct size

```shell
locatepy --type dir --min-size 500M --sort size
```

### Pattern filter + directory search

```shell
locatepy --type dir Downloads
locatepy --type dir -r "node_modules$" --sort total_size
```

**Sort keys (`--type dir`):** `path`, `size` (direct), `lsize` (direct), `files` (direct), `total_size`, `total_lsize`, `total_files`, `mtime`, `ctime`, `atime`

### Output columns (`--type dir`)

| Column | Description |
|--------|-------------|
| path | Directory path |
| files | Number of direct files |
| size | Total size of direct files (bytes) |
| lsize | Local size of direct files |
| total_files | Total files under directory |
| total_size | Total size under directory (bytes) |
| total_lsize | Total local size under directory |
| ctime / atime / mtime | Directory timestamps |
| attributes | Windows file attributes |

> `lsize` is the local size excluding cloud-only files (e.g. OneDrive files not downloaded locally).

---

## Options Reference

| Option | Description |
|--------|-------------|
| `-u` / `--update` | Update the database |
| `-c PATH` | Path to config file (default: `locate-py.json`) |
| `--type file\|dir` | Type to search (default: `file`) |
| `-r PATTERN` | Regex search |
| `-i` | Case-insensitive search |
| `--sort KEY` | Sort key |
| `--sort-order asc\|desc` | Sort order |
| `--min-size SIZE` | Minimum size (e.g. `1K`, `10M`, `2G`) |
| `--max-size SIZE` | Maximum size |
| `--min-total-size SIZE` | Minimum total size under dir (`--type dir` only) |
| `--max-total-size SIZE` | Maximum total size under dir (`--type dir` only) |
| `--mtime-after DATE` | Modified time lower bound (`YYYY-MM-DD` format) |
| `--mtime-before DATE` | Modified time upper bound |
| `--ctime-after/before` | Creation time filter |
| `--atime-after/before` | Access time filter |
| `-l N` | Maximum number of results |
| `-f tsv\|csv\|path` | Output format (default: `tsv`) |
| `--no-header` | Suppress header row |
| `--no-summary` | Suppress summary line |
| `--create-config` | Generate config file and exit |
