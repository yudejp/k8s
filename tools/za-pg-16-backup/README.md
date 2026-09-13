# za-pg-16 データベースバックアップ

Kubernetesクラスタ上のZalando Postgresクラスタ `za-pg-16` から、指定した
1つのデータベースをローカルへバックアップするツールです。

現在のprimary Spilo Pod内で `pg_dump` を実行し、標準出力をローカルの
PostgreSQL custom archive形式（`.dump`）へ直接保存します。Kubernetes Secretを
ローカルへコピーせず、Pod内にも一時バックアップファイルを残しません。

## 必要なもの

- Bash
- `kubectl`
- 対象クラスタを操作できるkubeconfig
- `pods` の一覧取得と `pods/exec` の権限

## 使い方

リポジトリのルートから実行します。

```bash
# カレントディレクトリに
# ./misskey-y2e-org_YYYYmmddTHHMMSS.dump を作成する
./tools/za-pg-16-backup/backup-database.sh misskey-y2e-org

# 保存先を明示する
./tools/za-pg-16-backup/backup-database.sh \
  --output /path/to/backups/misskey.dump \
  misskey-y2e-org
```

保存先の親ディレクトリは事前に作成してください。既存ファイルは上書きしません。

### オプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `-o`, `--output PATH` | 出力ファイル | `./DATABASE_TIMESTAMP.dump` |
| `-n`, `--namespace NAME` | Kubernetes namespace | `default` |
| `-c`, `--cluster NAME` | Zalando Postgresクラスタ名 | `za-pg-16` |
| `--context NAME` | 使用するkubectl context | 現在のcontext |
| `-h`, `--help` | ヘルプを表示 | - |

`kubectl` の実行ファイルを変更する場合は、環境変数 `KUBECTL` に実行ファイルの
パスを指定できます。

## 安全性

- `application=spilo`、`cluster-name`、`spilo-role=master` の3ラベルで
  DB本体のprimary Podだけを選択します。
- バックアップ直前に `pg_is_in_recovery()` を確認し、選択したPodがwritable
  primaryでなければ停止します。
- `pg_dump` が失敗した場合や、出力がcustom archiveでない場合は、部分ファイルを
  削除します。
- 完成したバックアップは同一ディレクトリ内で原子的に公開し、処理中に同名の
  ファイルが作成された場合も上書きしません。
- バックアップファイルはパーミッション `0600` で作成します。

## 確認と復元

アーカイブの内容は `pg_restore --list` で確認できます。Podで使われている
`pg_dump` と同じか、それより新しいバージョンの `pg_restore` を使用してください。

```bash
pg_restore --list /path/to/backups/misskey.dump
```

復元先のデータベースを準備したうえで、次のように復元できます。

```bash
pg_restore \
  --no-owner \
  --dbname TARGET_DATABASE \
  /path/to/backups/misskey.dump
```

このツールは1つのデータベースだけをバックアップします。PostgreSQLのロールなど、
クラスタ全体のグローバルオブジェクトは含まれません。
