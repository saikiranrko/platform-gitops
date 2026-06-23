# Platform GitOps — Architecture

## Overview

Enterprise-grade deployment platform running on Azure AKS, managed via GitOps.
Designed for learning and resume demonstration — realistic patterns, minimal cost.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKFLOW                           │
│                                                                     │
│  git push / PR ──► GitHub Actions ──► ACR (Docker image)           │
│                         │                    │                      │
│                   security scans        image tag update            │
│                   (Trivy, Checkov)           │                      │
│                                              ▼                      │
│                                    gitops/environments/dev/         │
│                                    values-dev.yaml (commit)         │
└─────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ ArgoCD watches repo
                                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AKS CLUSTER (eastus)                         │
│                                                                     │
│  ┌──────────────┐   ┌───────────────┐   ┌────────────────────────┐ │
│  │   ArgoCD     │   │  task-api     │   │  Monitoring Stack      │ │
│  │  (GitOps)    │──►│  Deployment   │   │  Prometheus + Grafana  │ │
│  │  namespace:  │   │  namespace:   │   │  + Loki + Alertmanager │ │
│  │  argocd      │   │  task-api-dev │   │  namespace: monitoring │ │
│  └──────────────┘   └───────────────┘   └────────────────────────┘ │
│         │                  │                         ▲              │
│         │                  │ scrapes /metrics         │              │
│         ▼                  └─────────────────────────┘              │
│  Helm chart in repo                                                  │
└─────────────────────────────────────────────────────────────────────┘
          │                        │                    │
          ▼                        ▼                    ▼
   ACR (pull images)        Key Vault              Log Analytics
   saiacr001                (secrets via          (AKS diagnostics)
                             CSI driver)
```

## Layer Breakdown

### Infrastructure Layer (Terraform)
- **VNet + Subnets** — isolated networking, AKS nodes in dedicated subnet
- **AKS** — `Standard_B2s` × 1 node, Free tier control plane, OIDC enabled
- **ACR** — Basic SKU, no admin user (kubelet managed identity pulls images)
- **Key Vault** — Standard SKU, secrets injected via CSI Secrets Store driver
- **Log Analytics** — 30-day retention, AKS OMS agent sends logs here

### CI Layer (GitHub Actions)
| Workflow | Trigger | What it does |
|---|---|---|
| `ci-app.yml` | Push to `apps/task-api/**` | Test → Trivy scan → Checkov → Build → Push to ACR → Update GitOps values |
| `tf-plan.yml` | PR to `terraform/**` | Init → Validate → Plan → Comment on PR |
| `tf-apply.yml` | Push to `main` on `terraform/**` | Init → Apply (with manual approval gate) |

**OIDC auth** — GitHub Actions authenticates to Azure with federated credentials.
No static secrets stored anywhere.

### CD Layer (ArgoCD GitOps)
- ArgoCD watches this repo (`main` branch)
- Detects changes to `gitops/environments/dev/task-api/values-dev.yaml`
- Syncs Helm chart automatically (`automated.selfHeal: true`)
- Prunes deleted resources (`automated.prune: true`)

### Runtime Layer (Kubernetes)
- `task-api-dev` namespace — application workloads
- `argocd` namespace — GitOps controller
- `monitoring` namespace — observability stack
- All pods run as non-root with `readOnlyRootFilesystem: true`
- Secrets injected from Key Vault via CSI driver (never in k8s Secrets)

### Observability Layer
- **Prometheus** — scrapes `/metrics` from task-api pods
- **Grafana** — pre-loaded dashboard (`monitoring/dashboards/task-api-dashboard.json`)
- **Alertmanager** — fires alerts on error rate, latency, pod availability
- **Log Analytics** — AKS control plane + node logs
- **Loki** — app logs (optional, add via `helm upgrade ... --set loki.enabled=true`)

### Security Layer (DevSecOps)
- **Trivy** — scans filesystem (secrets, CVEs) and container images in CI
- **Checkov** — IaC policy scan on Terraform before apply
- **OIDC** — no static Azure credentials anywhere (GitHub Actions + pod Workload Identity)
- **Key Vault CSI** — secrets never touch Kubernetes etcd
- **Non-root containers** — `runAsNonRoot: true`, `allowPrivilegeEscalation: false`
- **Read-only root filesystem** — `readOnlyRootFilesystem: true`

## Cost Breakdown (estimated, eastus)

| Resource | SKU | Est. monthly |
|---|---|---|
| AKS nodes (1× B2s) | Standard_B2s | ~$30 |
| AKS control plane | Free tier | $0 |
| ACR | Basic | ~$5 |
| Key Vault | Standard | ~$0.03/10k ops |
| Log Analytics | PerGB2018 (30 days) | ~$2-5 |
| Load Balancer | Standard | ~$18 |
| **Total (running 24/7)** | | **~$55-60/month** |

### Cost-saving tips
- **Stop AKS when not using it**: `az aks stop -n sai-aks -g sai-platform-rg`
- **Start it when needed**: `az aks start -n sai-aks -g sai-platform-rg`
- Startup takes ~3 minutes. Stopping saves ~$1/hour on the node.
- Run `python scripts/cost-check.py` to audit spend.
- Use the `cost-check.py` script as a daily GitHub Actions job.

## Azure Services: Required vs Optional

### Required (core platform)
- AKS — the runtime
- ACR — image registry
- Azure Blob Storage — Terraform state
- Key Vault — secret management
- VNet — networking

### Optional (add when needed)
- Log Analytics — useful but AKS works without it
- Azure Monitor Alerts — can use Prometheus alerts instead
- Azure Container Apps — simpler alternative to AKS for very simple apps
- Cosmos DB / PostgreSQL Flexible — when app needs persistent data
