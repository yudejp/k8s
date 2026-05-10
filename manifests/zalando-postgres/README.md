# zalando-postgres

## Install

* Install the operator via Kustomize
    ```
    kubectl apply -k github.com/zalando/postgres-operator/manifests
    ```
* Install the operator UI via Kustomize
    ```
    kubectl apply -k github.com/zalando/postgres-operator/ui/manifests
    ```

## Memo

* ttj1sh1.tun.y2e.org 上の pg replica を削除した際、primary (za-pg-16.default.svc.cluster.local) 上でも以下を実行する
    ```
    SELECT pg_drop_replication_slot('nrt1_replica');
    ```
