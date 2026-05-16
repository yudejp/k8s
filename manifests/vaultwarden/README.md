# vaultwarden

## Installation

* First time: `helm install vaultwarden-release vaultwarden/vaultwarden -f values.yaml`
* Update values: `helm upgrade vaultwarden-release vaultwarden/vaultwarden -f values.yaml`

## Note

Recent chart versions expect persistent storage settings under `storage.data`, not top-level `data`.
