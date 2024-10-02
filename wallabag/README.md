# wallabag

## Installation

* Install using Helm
    ```bash
    helm install wallabag k8s-at-home/wallabag -f values.yaml
    ```
* Clear cache
    ```bash
     kubectl exec <pod name> --stdin --tty -- /var/www/wallabag/bin/console cache:clear --env=prod
    ```
* Migrate database
    ```bash
    kubectl exec <pod name> --stdin --tty -- /var/www/wallabag/bin/console doctrine:migrations:migrate --env=prod --no-interaction
    ```
* Create user
    ```bash
    kubectl exec <pod name> --stdin --tty -- /var/www/wallabag/bin/console fos:user:create --env=prod <name> <email> <password>
    ```
