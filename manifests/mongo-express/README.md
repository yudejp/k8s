# Mongo Express

`secret.yaml` is intentionally excluded from `kustomization.yaml` so a normal
`kubectl apply -k` cannot overwrite the live credentials with a local example.

For initial provisioning, copy `secret.example.yaml` to the ignored
`secret.yaml`, replace every placeholder, and apply it explicitly before the
rest of the manifests:

```bash
kubectl apply -n mongodb -f manifests/mongo-express/secret.yaml
kubectl apply -k manifests/mongo-express/
```
