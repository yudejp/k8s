# Tapo power collector for Grafana Cloud

Tapo スマートプラグから取得した電力メトリクスを Grafana Cloud へ送信する、
Go 製 collector の Deployment です。`default` namespace に 1 replica で配置します。
同じ時刻の二重収集を避けるため、更新方式は `Recreate` です。

## Secret の作成

実値は Git にコミットしません。このディレクトリでは `secret.yaml` がリポジトリ全体の
`.gitignore` 対象になっており、kustomization にも含めていません。

```bash
cd manifests/tapo-power-grafana
cp secret.example.yaml secret.yaml
uuidgen
```

出力した UUID と TP-Link/Grafana Cloud の値を `secret.yaml` に設定します。
`TAPO_TERMINAL_ID` は初回認証後も変更しないでください。`TAPO_DEVICE_IDS` が空なら、
検出したプラグ・スイッチ・電源タップをすべて対象にします。

## 検証とデプロイ

```bash
kubectl kustomize manifests/tapo-power-grafana/ >/dev/null
kubectl apply -f manifests/tapo-power-grafana/secret.yaml
kubectl apply -k manifests/tapo-power-grafana/
kubectl rollout status deployment/tapo-power-grafana
kubectl logs deployment/tapo-power-grafana -f
```

Deployment は ServiceAccount token をマウントせず、非 root、read-only root filesystem、
全 Linux capability drop、RuntimeDefault seccomp で動作します。イメージは可変な `main`
ではなく、対応するソース commit の短縮 SHA tag と OCI index digest に固定しています。

## 初回のメール確認

TP-Link は 2 段階認証を明示的に有効にしていなくても、新しい terminal ID にメール確認を
要求することがあります。ログに確認コード送信後の待機が出た場合だけ、次を行います。

1. メールで届いたコードを `secret.yaml` の `TAPO_MFA_CODE` に一時設定する。
2. `kubectl apply -f manifests/tapo-power-grafana/secret.yaml` を実行する。
3. Secret volume の更新を collector が読み、認証が完了するまでログを確認する。
4. 成功後は `TAPO_MFA_CODE` を空へ戻し、もう一度 Secret を apply する。

Secret volume の更新には通常は短い遅延があります。`TAPO_MFA_WAIT_TIMEOUT` の既定値は
10 分です。期限を過ぎた場合は Pod を再起動すると、同じ terminal ID で新しいコードを
要求します。

## 確認

```bash
kubectl get pod -l app=tapo-power-grafana
kubectl logs deployment/tapo-power-grafana --tail=100
kubectl describe pod -l app=tapo-power-grafana
```

collector のイメージは scratch ベースで shell を含みません。readiness は
`kubectl get pod`、詳細は Pod events とログで確認してください。
