# kube-vipによるコントロールプレーンVIP

このマニフェストは、TUN の `192.168.30.233:6443` をK3s APIの固定エンドポイントとして提供します。
kube-vipはARP方式のコントロールプレーンVIP専用で動作し、Kubernetesの
`LoadBalancer` Serviceは管理しません。また、Flannelやkube-proxyを置き換えません。

## 適用前の確認

現在のコントロールプレーンではノードごとにインターフェース名が異なります。
kube-vipの自動検出はdefault route側を選ぶため、ノード別overlayでホスト側の
`192.168.30.0/24` インターフェースを明示しています。各ノードで設定値とrouteが
一致することを確認してください。

```console
ip route get 192.168.30.233
```

現在の期待値は次のとおりです。

- `nrt1kwo1`: `ens224`、source `192.168.30.224`
- `nrt1kwo2`: `enp1s0.20`、source `192.168.30.211`
- `nrt1kwo3`: `ens19`、source `192.168.30.225`

`nrt1kwo2` の `enp1s0.20` はVLANサブインターフェースです。kube-vip v1.2.3の
`vip_loseleadership` によるリンク監視は物理インターフェース
（`netlink.Device`）だけを受け付けるため、このノードのoverlayに限って
`vip_loseleadership: false` を設定しています。VIPのARP広告とKubernetes Lease
によるleader electionは引き続き有効です。ローカルAPIがetcd quorumへ書き込めず
Leaseを更新できなくなれば、別ノードがLeaseを取得します。ただし、API/etcdは正常な
ままVLANインターフェースだけが停止した場合、このノードは即座にはLeaseを手放しません。

新しいK3s serverを追加するときは、そのホスト名とホストインターフェースに対応する
node overlayを追加してからkube-vipを起動してください。

クラスタを変更せず、生成されるリソースを検証します。

```console
kubectl kustomize manifests/kube-vip/ > /dev/null
kubectl apply --dry-run=server -k manifests/kube-vip/
```

## interface自動検出版からの切替

interface自動検出版の `daemonset/kube-vip` がすでに動いている場合、同じnode identityで
新旧Podを重複実行してはいけません。Tailscale経由のAPI接続を使用し、旧DaemonSetを
正確な名前で削除して、PodとVIPが消えたことを確認してから修正版を適用します。

```console
kubectl delete daemonset kube-vip -n kube-system
kubectl wait --for=delete pod \
  -n kube-system \
  -l app.kubernetes.io/name=kube-vip \
  --timeout=60s
```

各ノードで次のコマンドを実行し、出力がないことを確認します。

```console
ip -4 -o addr show | grep '192\.168\.30\.233/32'
```

## 適用と確認

3台すべてのserverでkeepalivedを停止した後に限り、次のコマンドを実行します。

```console
kubectl apply -k manifests/kube-vip/
kubectl rollout status daemonset/kube-vip-nrt1kwo1 -n kube-system
kubectl rollout status daemonset/kube-vip-nrt1kwo2 -n kube-system
kubectl rollout status daemonset/kube-vip-nrt1kwo3 -n kube-system
kubectl get pods -n kube-system \
  -l app.kubernetes.io/name=kube-vip -o wide
kubectl get lease kube-vip-control-plane -n kube-system -o yaml
```

期待値は次のとおりです。

- ノード別の3つのDaemonSetがそれぞれ `DESIRED=1`、`READY=1` になる。
- 各コントロールプレーンノードでPodが1つずつRunningになる。
- Lease holderが1台だけになる。
- `192.168.30.233/32` がコントロールプレーンノード1台だけに付与される。
- 各Podのログに `ens224`、`enp1s0.20`、`ens19` のうち、そのノードで期待する
  ホストインターフェースが表示される。
- K3s server CAとclient証明書を含むkubeconfigを使った
  `https://192.168.30.233:6443/readyz` が成功する。

Tailscale側でTLS終端するAPIエンドポイント用のkubeconfigには、K3s server CAが
含まれていない場合があります。そのkubeconfigに `--server=https://192.168.30.233:6443`
だけを指定すると、VIPと証明書SANが正常でも `certificate signed by unknown authority`
になります。VIP直結の確認にはK3sが生成したkubeconfigのCA/client情報を使用してください。

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
