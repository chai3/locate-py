# locate-py

A SQLite-based local file search tool. Indexes files and directories for fast searching by path, size, and timestamp.

## Setup

```bash
# Generate config file (first time)
python main.py --create-config

# Edit locate-py.json to configure target_paths etc.
```

### locate-py.json example

```json
{
  "database_path": "locate-py.db",
  "target_paths": ["C:\\Users\\user\\Documents"],
  "ignore_paths": ["C:\\Users\\user\\AppData"],
  "ignore_names": [".git"]
}
```

## Update Database

```bash
python main.py -u
```

Both files and directories are indexed.

---

## File Search (`--type file`, default)

### Pattern search (partial match)

```bash
python main.py report
python main.py -i report          # case-insensitive
python main.py -r "\.log$"        # regex
```

### Size filter

```bash
python main.py --min-size 100M               # 100 MB or larger
python main.py --min-size 1G --sort size     # 1 GB or larger, sorted by size
```

### Time filter

```bash
python main.py --mtime-after 2024-01-01
python main.py --mtime-after "2024-06-01 00:00" --mtime-before "2024-06-30 23:59"
```

### Output options

```bash
python main.py report --format path          # path only
python main.py report --format csv           # CSV output
python main.py report -l 20                  # up to 20 results
python main.py report --no-header            # no header row
python main.py report --sort size            # sort by size descending
```

**Sort keys (`--type file`):** `path`, `size`, `lsize`, `mtime`, `ctime`, `atime`

---

## Directory Search (`--type dir`)

### Find large folders (recursive total)

```bash
python main.py --type dir --min-total-size 1G --sort total_size
```

### Find folders with many files (recursive total)

```bash
python main.py --type dir --sort total_files
```

### Find folders with many direct files

```bash
python main.py --type dir --sort files
```

### Filter by direct size

```bash
python main.py --type dir --min-size 500M --sort size
```

### Pattern filter + directory search

```bash
python main.py --type dir Downloads
python main.py --type dir -r "node_modules$" --sort total_size
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
