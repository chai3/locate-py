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

```shell
$ locatepy --init
This utility will walk you through creating a locate-py config file.
Press ^C at any time to quit.

database path: (locate-py.db)
target paths(comma-separated): (C:\Users\user) 
ignore paths(comma-separated): 
ignore names(comma-separated) : 

About to write to locate-py.json:
{
  "database_path": "locate-py.db",
  "target_paths": [
    "C:\\Users\\user\\locate-py"
  ],
  "ignore_paths": [],
  "ignore_names": []
}

Is this OK? ([Y]es / [N]o): yes

Config file created: locate-py.json

Build database now? ([Y]es / [N]o): yes
Starting database creation.
Indexed 2,973 files.
Indexed 538 directories.
Database built successfully.
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
locatepy --name report      # match filename only (not parent dirs)
```

### Size filter

```shell
locatepy --min-size 100M               # 100 MB or larger
locatepy --min-size 1G --sort size     # 1 GB or larger, sorted by size
```

### Time filter

```shell
locatepy --modified-time-after 2024-01-01
locatepy --modified-time-after "2024-06-01 00:00" --modified-time-before "2024-06-30 23:59"
```

### Output options

```shell
locatepy report --format path          # path only
locatepy report --format csv           # CSV output
locatepy report --format json          # JSON output
locatepy report -l 20                  # up to 20 results
locatepy report --sort size            # sort by size descending
locatepy report --output-fields path,size,modified_time  # custom fields
locatepy report --target-dir C:\Users  # restrict to directory
```

**Sort keys (`--type file`):** `path`, `name`, `size`, `local_size`, `modified_time`, `created_time`, `accessed_time`

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


## Command Reference

```shell
$ uv run locatepy --help
usage: locatepy [-h] [-c PATH] [-u] [-r PATTERN] [--name PATTERN] [--sort KEY] [--sort-order ORDER] [--min-size SIZE] [--max-size SIZE] [--min-total-size SIZE] [--max-total-size SIZE]
                [--type {file,dir}] [--modified-time-after DATE] [--modified-time-before DATE] [--created-time-after DATE] [--created-time-before DATE] [--accessed-time-after DATE]
                [--accessed-time-before DATE] [--target-dir DIR] [-l N] [-i] [-f {human,tsv,csv,path,json,jsonl}] [--output-fields FIELDS] [--init] [--mcp]
                [pattern]

Simple locate command

positional arguments:
  pattern               Search by pattern (partial match)

options:
  -h, --help            show this help message and exit
  -c PATH, --config PATH
                        Path to config file (default: locate-py.json)
  -u, --update          Update the database
  -r PATTERN, --regex PATTERN
                        Search with regex pattern
  --name PATTERN        Search by file/directory name only (basename, not parent dirs)
  --sort KEY            Sort key (--type file): path, name, size, local_size, modified_time, created_time, accessed_time / (--type dir): path, name, size, local_size, modified_time,    
                        created_time, accessed_time, files, total_size, total_local_size, total_files
  --sort-order ORDER    Sort order: asc / desc (default: path→asc, others→desc)
  --min-size SIZE       Minimum size (e.g. 1K, 10M)
  --max-size SIZE       Maximum size (e.g. 100M, 1G)
  --min-total-size SIZE
                        (--type dir only) Minimum total size under directory (e.g. 1G)
  --max-total-size SIZE
                        (--type dir only) Maximum total size under directory
  --type {file,dir}     Type to search: file (default), dir
  --modified-time-after DATE
                        Modified time lower bound
  --modified-time-before DATE
                        Modified time upper bound
  --created-time-after DATE
                        Creation time lower bound
  --created-time-before DATE
                        Creation time upper bound
  --accessed-time-after DATE
                        Access time lower bound
  --accessed-time-before DATE
                        Access time upper bound
  --target-dir DIR      Restrict search to the specified directory
  -l N, --limit N       Maximum number of matches
  -i, --ignore-case     Case-insensitive search
  -f {human,tsv,csv,path,json,jsonl}, --format {human,tsv,csv,path,json,jsonl}
                        Output format: human (default), tsv, csv, path, json, jsonl
  --output-fields FIELDS
                        Comma-separated fields to output (e.g. path,size,modified_time). Default for --type file: path,size,modified_time. Default for --type dir:
                        path,total_size,modified_time. File fields: path,size,local_size,created_time,accessed_time,modified_time,attributes. Dir fields:
                        path,files,size,local_size,total_files,total_size,total_local_size,created_time,accessed_time,modified_time,attributes.
  --init                Interactively create config file and optionally build database
  --mcp                 Run as MCP server (stdio transport)
```