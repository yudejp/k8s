# tailscale-operator

## Installation

```
$ helm upgrade \
    --install \
    tailscale-operator \
    tailscale/tailscale-operator \
    --namespace=tailscale \
    --create-namespace \
    --set-string oauth.clientId="<OAauth client ID>" \
    --set-string oauth.clientSecret="<OAuth client secret>" \
    --wait
```