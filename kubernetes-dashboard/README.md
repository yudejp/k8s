# kubernetes-dashboard

## Gaining access to Kubernetes Dashboard

* Apply manifests located in this directory.
* `kubectl create token -n kubernetes-dashboard dashboard-admin-sa --duration=720h`
