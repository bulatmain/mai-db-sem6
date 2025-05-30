# Deployment guide

This project is deployed on Kubernetes.

There are 4 services that are deployed in this project:
- postgres;
- pgadmin;
- spark;
- clickhouse.

First create project namespace:

```
kubectl create namespace lab
```

To deploy clickhouse, postgres and pgadmin run

```
kubectl apply -k k8s/
```

To deploy spark task first it's needed to deploy spark operator. You can do it by following this guide: https://github.com/apache/spark-kubernetes-operator;

Then run 
```
kubectl apply -f spark-application.yaml
```

