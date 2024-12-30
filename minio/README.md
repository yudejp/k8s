```
helm install minio \
  --namespace minio --create-namespace \
  --set accessKey=minio,secretKey=minio123 \
  --set mode=standalone \
  --set service.type=ClusterIP \
  --set service.nodePort=32000 \
  --set persistence.enabled=true \
  --set persistence.size=100Gi \
  --set persistence.storageClass=longhorn \
  --set resources.requests.memory=1024Mi \
   minio/minio
  ```
