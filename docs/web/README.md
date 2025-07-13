# Hot

entry point for HOT https://he.wikipedia.org/wiki/HOT

our entry point is the website as the customer interface for sevral services but the main fucntionality which is the application.

explaratory testing user facing application web application

## prerequisites

```bash
conda create -y -n hot-e2e python=3.12
conda activate hot-e2e && pip install -r requirements.txt
```

## running tests localy

```bash
python -m pytest
```

## vscode settings

```json
{
    "python.testing.pytestArgs": [
        "."
    ],
    "python.testing.unittestEnabled": false,
    "python.testing.pytestEnabled": true,
    "python.defaultInterpreterPath": "/opt/homebrew/Caskroom/miniforge/base/envs/hot-e2e/bin/python",
    "python.testing.pytestPath": "/opt/homebrew/Caskroom/miniforge/base/envs/hot-e2e/bin/pytest"
}
```
## dockerrize

```bash
cd /Users/asafgolan/Hot/web && docker build -t hot-mobile-tests:v2 .
```

```python
update with image tage in k8s/test-job.yaml and k8s/test-cronjob.yaml
```


## running tests in k8s

### one time global monitoring setup per cluster

```bash
kubectl create namespace hot-infra
kubectl apply -f k8s/storage/test-pvc.yaml
kubectl apply -f k8s/monitoring/prometheus-config.yaml
kubectl apply -f k8s/monitoring/prometheus-deployment.yaml
kubectl apply -f k8s/monitoring/test-results-dashboard.yaml
```

### running tests

```bash
kubectl apply -f k8s/test-job.yaml
kubectl apply -f k8s/test-cronjob.yaml
```

### view results in cutom dashbord

```bash
kubectl -n hot-e2e-tests port-forward svc/test-results-dashboard 8080:80
```

then open http://localhost:8080



~/Hot $ kubectl apply -f /Users/asafgolan/Hot/web/k8s/test-job.yaml


Deploy the Pushgateway:

kubectl apply -f /Users/asafgolan/Hot/k8s/monitoring/pushgateway-deployment.yaml

Update Prometheus Config:

kubectl apply -f /Users/asafgolan/Hot/k8s/monitoring/prometheus-config.yaml


kubectl -n hot-e2e-tests port-forward svc/prometheus-pushgateway 9091:9091


kubectl -n hot-e2e-tests port-forward svc/prometheus 9090:9090

#### delete and run new job batch
kubectl -n hot-e2e-tests delete job hot-mobile-e2e-tests


kubectl -n hot-e2e-tests apply -f /Users/asafgolan/Hot/web/k8s/test-job.yaml




Then open http://localhost:9090 and search for metrics with "hot_e2e_" prefix