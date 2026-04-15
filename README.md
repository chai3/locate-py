# locate-py

A SQLite-based local file search tool. Indexes files and directories for fast searching by path, size, and timestamp.

## Getting Started
### Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

Invoke directly without installing

```shell
$ uvx --from git+https://github.com/chai3/locate-py locatepy [args]
```

Or globally install

```shell
$ uv tool install --from git+https://github.com/chai3/locate-py locatepy
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

Indexing 1 million files takes about 3 minutes. Searching takes about 1 second.


### locate-py.json example

```json
{
  "database_path": "locate-py.db",
  "target_paths": ["C:\\", "D:\\"], // ex: "C:\\" "\\\\192.168.1.2\\share" "/" "/home"
  "ignore_paths": ["C:\\$Recycle.Bin"], // "/dev", "/sys", "/proc", "/run", "/mnt"
  "ignore_names": [""] // .git .venv node_modules
}
```


## File Search (`--type file`, default)

### Pattern search (partial match)

```shell
$ locatepy mp4
$ locatepy -r "\.log$"        # regex
$ locatepy --name report      # match filename only (not parent dirs)
```

### Size/Time filter

```shell
$ locatepy --min-size 100M  mp4                  # 100 MB or larger
$ locatepy --min-size 1G --sort size --limit 10  # 1 GB or larger, sorted by size
$ locatepy --modified-time-after 2026-01-01
$ locatepy --modified-time-after "2026-06-01 00:00" --modified-time-before "2026-06-30 23:59"
```

### Output options

```shell
$ locatepy report --format path            # path only
$ locatepy report --format csv --output-fields path,size,modified_time  # custom fields
$ locatepy report --target-dir "C:\Users"  # restrict to directory
```

### Example output

```shell
$ locatepy --min-size 1G --sort size --limit 3
path,size,modified_time
C:\hiberfil.sys,27328634880,2026-04-14 11:57:06
C:\Users\user\.foundry\cache\models\Microsoft\Phi-4-generic-cpu\cpu-int4-rtn-block-32-acc-level-4\phi-4-medium-cpu-int4-rtn-block-32-acc-level-4.onnx.data,10906062848,2025-05-29 09:57:06
C:\Users\user\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\vm_bundles\claudevm.bundle\rootfs.vhdx,10192158720,2026-04-14 19:24:58
Search complete: 3 entries / 45.1 GB
```

## Directory Search (`--type dir`)

### Find large folders (recursive total)

```shell
$ locatepy --type dir --min-total-size 1G --sort total_size
```

### Find folders with many direct files

```shell
$ locatepy --type dir --sort files
```

### Filter by direct size

```shell
$ locatepy --type dir --min-size 500M --sort size
```

### Pattern filter + directory search

```shell
$ locatepy --type dir --name ".venv" --sort total_size
```

### Example Output + directory search

```
$ locatepy --type dir --sort total_size --limit 4 --name "node_modules" 
path,total_size,total_files,modified_time
C:\Prog\VSCode\41dd792b5e\resources\app\node_modules,123501343,4026,2026-04-08 22:05:23
C:\Users\user\AppData\Local\npm-cache\_npx\5a9d879542beca3a\node_modules,102593250,11944,2025-08-02 01:17:30
C:\Users\user\AppData\Roaming\npm\node_modules,58245114,8368,2025-07-31 20:56:22
C:\Users\user\AppData\Local\Yarn\Cache\v6\npm-typescript-5.2.2-5ebb5e5a5b75f085f22bc3f8460fba308310fa78-integrity\node_modules,47855557,116,2024-09-27 02:35:24
Search complete: 4 entries


$ locatepy --type dir --sort total_size --limit 10
path,total_size,total_files,modified_time
C:\,361774114201,1087267,2026-04-11 22:16:17
C:\Users,177260282868,783137,2025-01-31 02:42:58
C:\Users\user,177254435552,783036,2026-04-14 17:57:01
C:\Users\user\AppData,88332736394,677959,2025-01-31 02:43:25
C:\Users\user\AppData\Local,79765678800,620343,2026-04-13 20:26:01
C:\Users\user\Downloads,64434140326,5757,2026-04-09 01:31:47
C:\Windows,42707951160,180237,2026-04-08 13:11:24
C:\Data,38852969047,458,2024-07-02 23:28:18
C:\ProgramData,25766780523,9100,2026-03-20 04:30:05
C:\Program Files,22144993244,41360,2026-01-14 19:37:28
Search complete: 10 entries
```

## Model Context Protocol(MCP)

```
{
  "mcpServers": {
    "locatepy": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/chai3/locate-py", "locatepy", "--mcp", "--config", "locate-py.json"]
    }
  }
}
```

```
The locatepy tool search the 10 largest files and notes whether they are necessary for Windows.
```

```
Here are the 10 largest files on your system with Windows necessity assessment:

| File | Size | Windows Required | Description |
|------|------|------------------|-------------|
| C:\hiberfil.sys | 27.3 GB | **Yes** | Windows Hibernation file |
| Phi-4 ONNX Model | 10.9 GB | **No** | Machine learning model cache - can be deleted |
| Claude VM rootfs | 10.2 GB | **Optional** | Development environment - deletable if not needed |
| C:\pagefile.sys | 4.3 GB | **Yes** | Windows Virtual Memory |
| Chrome Optimization Model | 4.3 GB | **No** | Cache file - can be deleted |
| RSA ROM Image 1 | 3.9 GB | **Device-specific** | Firmware update file - keep if needed |
| Ubuntu ISO | 3.8 GB | **No** | Linux installation media - can be deleted if not using Linux |
| RSA ROM Image 2 | 3.8 GB | **Device-specific** | Firmware file - keep if needed |
| CUDA 12.0 | 3.7 GB | **Optional** | GPU development toolkit - deletable if not needed |
| CUDA 12.4.1 | 3.2 GB | **Optional** | GPU development toolkit - older version can be deleted |

**Windows Required**: hiberfil.sys and pagefile.sys (31.6 GB total)
**Recommended for Deletion**: Ubuntu ISO, older CUDA versions, cache files (14.5+ GB possible space recovery)
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