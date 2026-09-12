#!/bin/bash
# Helper script for OpsGenome Live Judge Demo

ACTION="${1:-status}"

case "$ACTION" in
  setup)
    echo "=== Initializing Payments Workload in Minikube ==="
    kubectl apply -f "$(dirname "$0")/payments_workload.yaml"
    kubectl rollout status deployment/payments-service -n payments --timeout=60s
    echo "Baseline healthy state established!"
    ;;
  break)
    echo "=== Intentionally Inducing Real Kubernetes Failure ==="
    kubectl -n payments patch configmap payments-config -p '{"data":{"DB_TIMEOUT":"invalid_syntax_error"}}'
    kubectl -n payments delete pod -l app=payments-service --wait=false
    echo "ConfigMap poisoned. Pod recreating into CrashLoopBackOff/Error..."
    sleep 3
    kubectl get pods -n payments
    ;;
  fix)
    echo "=== Applying Remediation to Real Kubernetes Cluster ==="
    kubectl -n payments patch configmap payments-config -p '{"data":{"DB_TIMEOUT":"30s"}}'
    kubectl -n payments delete pod -l app=payments-service --wait=false
    echo "Remediation applied. Waiting for pod recovery..."
    for i in {1..20}; do
      READY=$(kubectl get pods -n payments -l app=payments-service -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null)
      if [ "$READY" = "true" ]; then
        echo "Pod recovered to 1/1 Running!"
        break
      fi
      sleep 1
    done
    kubectl get pods -n payments
    ;;
  status)
    echo "=== Current Kubernetes Cluster State ==="
    kubectl get pods -n payments -o wide
    kubectl get configmap payments-config -n payments -o yaml | grep -A 3 "data:"
    ;;
  verify)
    echo "=== Running OpsGenome Real Kubernetes Collector Verification ==="
    python3 -c "
from opsgenome.watcher.k8s import K8sStateCollector
collector = K8sStateCollector(namespace='payments')
collector.connect()
state, is_h, summary = collector.capture_raw_state()
print('Cluster Health:', is_h)
print('Status Summary:', summary)
cm = state['configmaps'].get('payments-config', {})
print('ConfigMap RV:', cm.get('resource_version'))
print('ConfigMap SHA:', cm.get('checksum'))
"
    ;;
  *)
    echo "Usage: $0 {setup|break|fix|status|verify}"
    exit 1
    ;;
esac
