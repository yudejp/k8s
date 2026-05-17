# victoriametrics

```shell
$ kubectl -n vm create secret generic grafana-cloud \
  --from-literal=username=<INSTANCE_ID> \
  --from-literal=apiKey=<GRAFANA_CLOUD_API_KEY>

$ kubectl -n vm create secret generic grafana-cloud-logs \
  --from-literal=url=https://logs-prod-XXX.grafana.net \
  --from-literal=username=<LOKI_INSTANCE_ID> \
  --from-literal=apiKey=<GRAFANA_CLOUD_LOGS_TOKEN>
```

## logs

- `vlagent.yaml` adds a Kubernetes log collector that runs as a DaemonSet via the operator.
- `vector-loki.yaml` adds a single Vector bridge that accepts `jsonline` from VLAgent and pushes it to Grafana Cloud Loki.
- Collected logs are written from VLAgent to `http://vector-loki.vm.svc:8080/` and then forwarded to Grafana Cloud.
- `grafana-cloud-logs` secret must contain the Loki base URL, the Loki username from Grafana Cloud, and a token or API key that can write logs.
- The Loki URL should be the base URL such as `https://logs-prod-XXX.grafana.net`; Vector appends `/loki/api/v1/push` automatically.
- `VLAgent` buffers up to `1GiB` per remote write target before dropping oldest buffered data.
