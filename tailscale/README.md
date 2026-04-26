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
    --set-string apiServerProxyConfig.mode="noauth" \
    --set-string apiServerProxyConfig.mode="true" \
    --wait

$ kubectl get proxygroup
NAME       STATUS            URL                                 TYPE             AGE
nrt1-kwo   ProxyGroupReady   https://nrt1-kwo.tail5b1c5.ts.net   kube-apiserver   20m

$ tailscale configure kubeconfig https://nrt1-kwo.tail5b1c5.ts.net
```
