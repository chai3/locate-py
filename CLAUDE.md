# CLAUDE.md

LocatePyはSQLiteベースのローカルファイル検索ツール
ファイルとディレクトリをインデックス化し、パス、サイズ、タイムスタンプによる高速検索を可能にする

## Commands

```bash
uv run locatepy [args]
uv run locatepy-mcp [args]

# 実装完了後に以下を実行
uv run pytest
uv run ty check
uv run ruff format
uv run ruff check
```

## ディレクトリ構成

### src/locatepy/cli.py
コアロジック + CLI
Python標準ライブラリのみ使用
cli.py単独で動作可能

### src/locatepy/mcp.py

FastMCPを使ってLocatePyをラップし、ツールをstdio経由で公開


## コーディング規約
- 型ヒントを付ける
- コンテナにはジェネリクスで型を付ける
- 型エイリアスを活用する
- TypedDict, NamedTupleを活用する
