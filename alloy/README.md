# alloy

## Installation

```
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm upgrade --install --version ^1 --atomic --timeout 300s grafana-k8s-monitoring grafana/k8s-monitoring \
    --namespace "default" --create-namespace -f values.yaml
```
