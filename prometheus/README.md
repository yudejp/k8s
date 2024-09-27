# prometheus

## Installation

* Add helm repository
    ```bash
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    ```
* Deploy
    ```bash
    helm install prometheus prometheus-community/prometheus
    ```