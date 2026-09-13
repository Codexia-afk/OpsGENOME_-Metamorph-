# OpsGenome Multi-Stack Incident Demo Project

This directory contains real multi-stack application components and incident logs used during multi-agent cross-stack resolution and cluster auditing demonstrations.

## Architecture

| Service / Component | Language / Stack | Path | Injected Defect |
|---|---|---|---|
| **Payment Engine** | Python 3 | `services/payment-engine/main.py` | Undefined variable `fee_rate` (`NameError`) |
| **API Gateway** | Node.js (Express) | `services/api-gateway/index.js` | Unawaited async Promise on `resp.json()` (`TypeError`) |
| **Billing Processor** | Java / JVM | `services/billing/PaymentProcessor.java` | Unchecked primitive unboxing on null `amount` (`NullPointerException`) |
| **Kubernetes Deployment** | Kubernetes YAML | `deployments/k8s/payment-deployment.yaml` | Undersized memory limit `64Mi` triggering container cgroup `OOMKilled` |

## Live Incident Logs

- `logs/cross_stack_incident.log`: Raw multiline incident log stream showing simultaneous container failures across Python, Node.js, Java, and Kubernetes.
- `logs/k8s_cluster_events.log`: Cluster event stream demonstrating 5 concurrent Kubernetes & Docker failure modes (`CrashLoopBackOff`, `OOMKilled`, `SelectorMismatch`, `ReadinessProbeFailed`, `PortConflict`).

## Running Multi-Agent Resolution Against These Files

```bash
# Analyze these files live with the multi-agent swarm:
./bin/opsgenome multi-agent analyze \
  --file demo-projects/multi-stack-incident/services/payment-engine/main.py \
  --file demo-projects/multi-stack-incident/services/api-gateway/index.js \
  --file demo-projects/multi-stack-incident/services/billing/PaymentProcessor.java \
  --file demo-projects/multi-stack-incident/deployments/k8s/payment-deployment.yaml

# Or use the built-in demo flag:
./bin/opsgenome multi-agent analyze --demo

# Or run the cluster auditor:
./bin/opsgenome multi-agent cluster-audit
```
