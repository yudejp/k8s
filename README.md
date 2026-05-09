# k8s

🐙 Kubernetes manifests [worker status](https://gri.yude.jp.eu.org/?h=kwo&sysdescr=&n=&d=&sort=a&ly=0&start=nil&search=1)

## Initalizing the cluster

### Prerequisites

* Reachability to tun.y2e.org (192.168.30.0/24) and assigned hostname within this network.
* Running Debian 13 (trixie).
* Reachability to the Internet.
* At least 16GB RAM.

### Setup k3s worker

```
$ ansible-playbook -i "nrt1kwoX.tun.y2e.org," playbooks/init-worker.yaml
```

### Setup k3s agent

* [クイックスタートガイド | K3s](https://docs.k3s.io/ja/quick-start)
    ```
    $ curl -sfL https://get.k3s.io | sh -s - server --server https://192.168.30.X:6443 --token <redacted> --node-name nrt1kwoN --node-ip 192.168.30.Y --flannel-iface <nic name> --tls-san 192.168.30.233 --tls-san nrt1kwo0.tun.y2e.org --tls-san nrt1-kwo.tail5b1c5.ts.net
    ```
    * `X`: other k3s worker node
    * `Y`: set up target node
    * `N`: set up target node

## License

MIT
