# couchdb

## Installation

* Installing from Helm
    ```bash
    $ helm repo add couchdb https://apache.github.io/couchdb-helm
    $ helm install couchdb couchdb/couchdb \
    --version=4.5.3 \
    -f values.yaml \
    --set couchdbConfig.couchdb.uuid=$(curl https://www.uuidgenerator.net/api/version4 2>/dev/null | tr -d -)
    ```

## Operation

* Obtain secret
    ```bash
    kubectl -n default get secret couchdb-couchdb --template='{{index .data "erlangCookie" | base64decode}}'
    ```
