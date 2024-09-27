# kubedb

## Installation

* Obtain license from [here](https://appscode.com/issue-license?p=kubedb)
* Install the operator
    ```bash
    helm install kubedb oci://ghcr.io/appscode-charts/kubedb \
    --version v2024.8.21 \
    --namespace kubedb --create-namespace \
    --set-file global.license=license.txt \
    --wait --burst-limit=10000 --debug
    ```