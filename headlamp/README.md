# headlamp

## Installation

* `kubectl apply -f .`
* Create a Service Account
    ```bash
    kubectl -n kube-system create serviceaccount headlamp-admin
    ```
* Create the token
    ```bash
    kubectl create token headlamp-admin -n kube-system --duration=720h
    ```