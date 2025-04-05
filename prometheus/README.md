# prometheus

## Installation

* Add helm repository
    ```bash
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    ```
* Deploy
    ```bash
    helm upgrade prometheus prometheus-community/prometheus -f values.yaml
    ```