# locate-py

SQLite ベースのローカルファイル検索ツール。ファイルとディレクトリのインデックスを作成し、高速にパス・サイズ・日時で検索できます。

## セットアップ

```bash
# 設定ファイルを生成（初回）
python main.py --create-config

# locate-py.json を編集して target_paths などを設定
```

### locate-py.json の例

```json
{
  "database_path": "locate-py.db",
  "target_paths": ["C:\\Users\\user\\Documents"],
  "ignore_paths": ["C:\\Users\\user\\AppData"],
  "ignore_names": [".git"]
}
```

## データベースの更新

```bash
python main.py -u
```

ファイルとディレクトリ両方がインデックスされます。

---

## ファイル検索（`--type file`、デフォルト）

### パターン検索（部分一致）

```bash
python main.py report
python main.py -i report          # 大文字小文字を区別しない
python main.py -r "\.log$"        # 正規表現
```

### サイズフィルタ

```bash
python main.py --min-size 100M               # 100MB 以上
python main.py --min-size 1G --sort size     # 1GB 以上・サイズ降順
```

### 日時フィルタ

```bash
python main.py --mtime-after 2024-01-01
python main.py --mtime-after "2024-06-01 00:00" --mtime-before "2024-06-30 23:59"
```

### 出力オプション

```bash
python main.py report --format path          # パスのみ出力
python main.py report --format csv           # CSV 出力
python main.py report -l 20                  # 最大 20 件
python main.py report --no-header            # ヘッダ行なし
python main.py report --sort size            # サイズ降順ソート
```

**ソートキー（`--type file`）:** `path`, `size`, `lsize`, `mtime`, `ctime`, `atime`

---

## ディレクトリ検索（`--type dir`）

### 大きいフォルダを探す（配下全体）

```bash
python main.py --type dir --min-total-size 1G --sort total_size
```

### ファイル数が多いフォルダを探す（配下全体）

```bash
python main.py --type dir --sort total_files
```

### 直下ファイル数が多いフォルダ

```bash
python main.py --type dir --sort files
```

### 直下サイズのフィルタ

```bash
python main.py --type dir --min-size 500M --sort size
```

### パターン絞り込み + ディレクトリ検索

```bash
python main.py --type dir Downloads
python main.py --type dir -r "node_modules$" --sort total_size
```

**ソートキー（`--type dir`）:** `path`, `size`（直下）, `lsize`（直下）, `files`（直下）, `total_size`, `total_lsize`, `total_files`, `mtime`, `ctime`, `atime`

### 出力カラム（`--type dir`）

| カラム | 内容 |
|--------|------|
| path | ディレクトリパス |
| files | 直下ファイル数 |
| size | 直下ファイルの合計サイズ（バイト） |
| lsize | 直下ファイルのローカルサイズ合計 |
| total_files | 配下全ファイル数 |
| total_size | 配下全ファイルの合計サイズ（バイト） |
| total_lsize | 配下全ファイルのローカルサイズ合計 |
| ctime / atime / mtime | ディレクトリのタイムスタンプ |
| attributes | Windows ファイル属性 |

> `lsize` はオンラインストレージ（OneDrive 等）のファイルを除いたローカルサイズ。

---

## 共通オプション一覧

| オプション | 説明 |
|-----------|------|
| `-u` / `--update` | データベースを更新 |
| `-c PATH` | 設定ファイルのパス（デフォルト: `locate-py.json`） |
| `--type file\|dir` | 検索対象（デフォルト: `file`） |
| `-r PATTERN` | 正規表現検索 |
| `-i` | 大文字小文字を区別しない |
| `--sort KEY` | ソートキー |
| `--sort-order asc\|desc` | ソート順 |
| `--min-size SIZE` | 最小サイズ（例: `1K`, `10M`, `2G`） |
| `--max-size SIZE` | 最大サイズ |
| `--min-total-size SIZE` | 最小配下全サイズ（`--type dir` 専用） |
| `--max-total-size SIZE` | 最大配下全サイズ（`--type dir` 専用） |
| `--mtime-after DATE` | 更新日時の下限（`YYYY-MM-DD` 形式） |
| `--mtime-before DATE` | 更新日時の上限 |
| `--ctime-after/before` | 作成日時フィルタ |
| `--atime-after/before` | アクセス日時フィルタ |
| `-l N` | 最大表示件数 |
| `-f tsv\|csv\|path` | 出力フォーマット（デフォルト: `tsv`） |
| `--no-header` | ヘッダ行を非表示 |
| `--no-summary` | 合計行を非表示 |
| `--create-config` | 設定ファイルを生成して終了 |
