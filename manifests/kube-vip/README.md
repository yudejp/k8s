# kube-vipによるコントロールプレーンVIP

このマニフェストは、TUN の `192.168.30.233:6443` をK3s APIの固定エンドポイントとして提供します。
kube-vipはARP方式のコントロールプレーンVIP専用で動作し、Kubernetesの
`LoadBalancer` Serviceは管理しません。また、Flannelやkube-proxyを置き換えません。

## 適用前の確認

現在のコントロールプレーンではノードごとにインターフェース名が異なるため、
`vip_interface` は意図的に指定していません。各ノードで、物理側の
`192.168.30.0/24` インターフェースが選択されることを確認してください。

```console
ip route get 192.168.30.233
```

クラスタを変更せず、生成されるリソースを検証します。

```console
kubectl kustomize manifests/kube-vip/ > /dev/null
kubectl apply --dry-run=server -k manifests/kube-vip/
```

## 適用と確認

3台すべてのserverでkeepalivedを停止した後に限り、次のコマンドを実行します。

```console
kubectl apply -k manifests/kube-vip/
kubectl rollout status daemonset/kube-vip -n kube-system
kubectl get pods -n kube-system \
  -l app.kubernetes.io/name=kube-vip -o wide
kubectl get lease kube-vip-control-plane -n kube-system -o yaml
```

期待値は次のとおりです。

- 各コントロールプレーンノードでPodが1つずつRunningになる。
- Lease holderが1台だけになる。
- `192.168.30.233/32` がコントロールプレーンノード1台だけに付与される。
- 各Podのログに、そのノードで期待する物理インターフェースが表示される。
- K3sのclient証明書を使った `https://192.168.30.233:6443/readyz` が成功する。

このDaemonSetは `KUBERNETES_SERVICE_HOST` と `KUBERNETES_SERVICE_PORT` を
上書きし、in-cluster ServiceAccount clientを各ノードのローカルAPI server
`127.0.0.1:6443` へ接続します。そのためleader electionは、VIP、cluster DNS、
Service network、CNI、kube-proxyに依存しません。

## rollback

Tailscale経由のAPIエンドポイントを使用して、このKustomizationのリソースを削除します。
その後、VIPがすべてのノードから消えていることを確認してからkeepalivedを再度有効化します。
kube-vipとkeepalivedに `192.168.30.233` を同時に広告させてはいけません。

```console
kubectl delete -k manifests/kube-vip/
```
