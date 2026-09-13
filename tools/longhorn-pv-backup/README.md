# Longhorn PV ローカルバックアップ

`longhorn-pv-backup.py` は、指定した1つのLonghornファイルシステムPVを、
コマンドを実行したローカルマシンへバックアップするツールです。PVに紐づくPVCを
厳密に解決し、一時的な読み取り専用Podを作成したうえで、`kubectl exec` 経由で
tarアーカイブをストリーミングします。Longhornのレプリカファイルを直接読み取ったり、
ノードへSSH接続したりする必要はありません。

## 安全性

- PVが `Bound` 状態であり、`driver.longhorn.io` を使用する
  `Filesystem` ボリュームであることを検証します。
- PVのclaimRefとPVCの名前・UIDを照合します。
- Longhornボリュームのrobustnessは、既定では `healthy` でなければなりません。
  ただし、安全にデタッチされたボリュームは通常 `unknown` と表示されるため、
  `Scheduled` conditionがfalseでなければ `detached/unknown` も許可します。
- PVCを参照している稼働中のPodが存在する場合、既定では処理を中止します。
  ワークロードを停止するか、アプリケーション側で書き込みを静止してから再実行して
  ください。クラッシュコンシステントなコピーで問題ない場合に限り、`--allow-live` を
  指定できます。ただし、データベースファイルのアプリケーション整合性は保証されません。
- 接続済みのRWOボリュームでは、クロスノードのmulti-attachを避けるため、
  一時Podを現在のLonghorn接続先ノードへ固定します。
- PVCとコンテナのルートファイルシステムは読み取り専用です。Capabilityは、
  アプリケーションUIDが所有するファイルを読み取るための `DAC_READ_SEARCH` を除いて
  すべて削除し、ServiceAccountトークンもマウントしません。
- 後処理では、生成した一時Podの完全名だけを指定して削除します。
- 既存のローカルアーカイブまたはメタデータファイルは上書きしません。

## 使用方法

次のものが必要です。

- Python 3.10以降
- `kubectl`
- PV、PVC、Pod、およびLonghorn Volumeリソースの読み取り権限
- PVCのNamespaceでPodを作成・exec・削除する権限

最初に、クラスタへ変更を加えないdry-runで対象を確認します。

```console
./tools/longhorn-pv-backup/longhorn-pv-backup.py \
  pvc-0af8a0ba-0cc6-41dc-93a4-a3397f5d6975 --dry-run
```

対象のワークロードを停止するか、書き込みを静止したあとにバックアップを実行します。

```console
./tools/longhorn-pv-backup/longhorn-pv-backup.py \
  pvc-0af8a0ba-0cc6-41dc-93a4-a3397f5d6975 \
  --output /srv/backups/meilisearch-20260913.tar.gz
```

クラッシュコンシステントなライブコピーを明示的に許容する場合は、次のように実行します。

```console
./tools/longhorn-pv-backup/longhorn-pv-backup.py \
  pvc-0af8a0ba-0cc6-41dc-93a4-a3397f5d6975 \
  --allow-live --output ./meilisearch-live.tar.gz
```

コマンドはアーカイブと、隣接する `.json` メタデータファイルを出力します。
メタデータには、対象のPV・PVC・Longhorn Volumeハンドル・ヘルス状態・容量・
作成日時・アーカイブサイズ・SHA-256チェックサムが記録されます。チェックサムは
次のように確認できます。

```console
sha256sum /srv/backups/meilisearch-20260913.tar.gz
```

これは、ファイルの内容・所有者・モード・タイムスタンプ・リンク・ディレクトリを
保存する可搬性のあるtarバックアップです。BusyBox tarは拡張属性とPOSIX ACLを
保存しません。これらが必要な場合は、GNU tarを含む検証済みイメージを使用し、
tarオプションも変更したうえで復元テストを実施してください。

圧縮処理を省いて高速化する場合は `--compression none` を指定します。一時Podの
イメージは既定で `busybox:1.37.0` です。クラスタ内のレジストリミラーを使う場合は
`--image` で変更できます。すべてのオプションは `--help` で確認できます。

## テスト

テストはクラスタへ接続せずに実行できます。

```console
python3 -m unittest discover -s tools/longhorn-pv-backup -p 'test_*.py'
```
