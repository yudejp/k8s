# cockroachdb

## Installation

* Apply the CRD
    ```bash
    kubectl apply -f https://raw.githubusercontent.com/cockroachdb/cockroach-operator/v2.14.0/install/crds.yaml
    ```
* Install the Operator
    ```bash
    kubectl apply -f https://raw.githubusercontent.com/cockroachdb/cockroach-operator/v2.14.0/install/operator.yaml
    ```

## Operation

* Access to SQL shell
    ```bash
    kubectl exec -it cockroachdb-client-secure \
    -- ./cockroach sql \
    --certs-dir=/cockroach/cockroach-certs \
    --host=cockroachdb-public
    ```
    * Add user
        ```sql
        CREATE USER foo WITH PASSWORD 'bar';
        ```
    * Grant a role
        * admin
            ```sql
            GRANT admin TO foo;
            ```
        * all permissions to specific database (e.g. db: piyo, role: foo)
            ```sql
            GRANT ALL ON DATABASE piyo TO foo;
            ```

* Access to Web UI
    ```bash
    kubectl port-forward service/cockroachdb-public 8080
    ```
