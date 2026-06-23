# Runbook — Platform GitOps

## Prerequisites

```bash
# Install tools
brew install terraform helm kubectl argocd azure-cli
pip install azure-identity azure-mgmt-resource azure-mgmt-storage azure-mgmt-authorization

# Login to Azure
az login
export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)
```

---

## Day 0: First-time Setup (Run Once)

### Step 1 — Bootstrap the platform
```bash
python scripts/bootstrap.py
```
This creates TF state storage, sets up OIDC, installs ArgoCD and Prometheus.
**Copy the GitHub Secrets it prints at the end.**

### Step 2 — Add GitHub Secrets
Go to: `https://github.com/saikiranrko/platform-gitops/settings/secrets/actions`

Add:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `GITHUB_ACTIONS_SP_OBJECT_ID`

Also create a GitHub Environment called `dev` and add the same secrets there.

### Step 3 — Deploy infrastructure
```bash
# Open a PR with your changes — tf-plan.yml runs and comments the plan
git checkout -b infra/initial-setup
git add terraform/
git commit -m "feat: initial AKS + ACR + Key Vault"
git push -u origin infra/initial-setup
# Create PR on GitHub → review plan comment → merge → tf-apply.yml runs
```

### Step 4 — Get AKS credentials
```bash
az aks get-credentials --name sai-aks --resource-group sai-platform-rg
kubectl get nodes  # should show 1 node Ready
```

### Step 5 — Fill in Workload Identity values
After Terraform apply, run:
```bash
# Get OIDC issuer
az aks show -n sai-aks -g sai-platform-rg --query oidcIssuerProfile.issuerUrl -o tsv

# Create user-assigned managed identity for the app
az identity create -n task-api-identity -g sai-platform-rg --location eastus
CLIENT_ID=$(az identity show -n task-api-identity -g sai-platform-rg --query clientId -o tsv)
OBJECT_ID=$(az identity show -n task-api-identity -g sai-platform-rg --query principalId -o tsv)

# Grant Key Vault access
az keyvault set-policy --name sai-kv-001 \
  --object-id $OBJECT_ID \
  --secret-permissions get list

# Create federated credential (links k8s ServiceAccount to Azure identity)
OIDC_ISSUER=$(az aks show -n sai-aks -g sai-platform-rg --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create \
  --name task-api-fedcred \
  --identity-name task-api-identity \
  --resource-group sai-platform-rg \
  --issuer $OIDC_ISSUER \
  --subject "system:serviceaccount:task-api-dev:task-api" \
  --audience api://AzureADTokenExchange
```

Then fill in `gitops/environments/dev/task-api/values-dev.yaml`:
```yaml
keyVaultSecrets:
  tenantId: "<your-tenant-id>"
  userAssignedIdentityID: "<CLIENT_ID from above>"
serviceAccount:
  annotations:
    azure.workload.identity/client-id: "<CLIENT_ID from above>"
```

### Step 6 — Deploy ArgoCD Application
```bash
kubectl apply -f gitops/environments/dev/task-api/application.yaml
# Watch sync status
argocd app get task-api-dev
argocd app sync task-api-dev
```

### Step 7 — Verify
```bash
kubectl get pods -n task-api-dev
kubectl port-forward svc/task-api 8080:80 -n task-api-dev
curl http://localhost:8080/healthz
curl http://localhost:8080/tasks
```

---

## Day 2: Common Operations

### Start/stop AKS (save credits)
```bash
# Stop (saves ~$1/hr on node costs)
az aks stop --name sai-aks --resource-group sai-platform-rg

# Start (takes ~3 min)
az aks start --name sai-aks --resource-group sai-platform-rg
```

### Check costs
```bash
python scripts/cost-check.py
```

### Deploy a new app version
Just push code to `apps/task-api/` — the CI/CD pipeline handles everything:
1. `ci-app.yml` builds, scans, pushes to ACR
2. CI commits the new image tag to `gitops/environments/dev/task-api/values-dev.yaml`
3. ArgoCD detects the change and deploys automatically

### Access Grafana
```bash
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
# Open http://localhost:3000 — admin / changeme123
```

### Access ArgoCD UI
```bash
kubectl port-forward svc/argocd-server 8080:443 -n argocd
# Open https://localhost:8080
# Username: admin
# Password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

### View app logs
```bash
kubectl logs -n task-api-dev -l app.kubernetes.io/name=task-api --tail=100 -f
```

### Scale down to save credits
```bash
# Scale to 0 replicas (keeps cluster running but stops app pods)
kubectl scale deployment task-api -n task-api-dev --replicas=0
# Scale back up
kubectl scale deployment task-api -n task-api-dev --replicas=1
```

---

## Tear Down (Destroy Everything)

```bash
# 1. Destroy app
kubectl delete -f gitops/environments/dev/task-api/application.yaml

# 2. Destroy infra (costs stop immediately)
cd terraform/environments/dev
terraform destroy -var="github_actions_sp_object_id=<sp-object-id>"

# 3. Destroy TF state storage (optional — it's cheap)
az group delete --name sai-tfstate-rg --yes
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| ArgoCD not syncing | `argocd app get task-api-dev` — look at Sync Status and Conditions |
| Pods CrashLoopBackOff | `kubectl describe pod <pod> -n task-api-dev` |
| Image pull errors | Check AcrPull role assignment: `az role assignment list --assignee <kubelet-object-id>` |
| Key Vault 403 | Verify federated credential subject matches `system:serviceaccount:<namespace>:<sa-name>` |
| Terraform OIDC error | Verify `ARM_USE_OIDC=true` and AZURE_CLIENT_ID secret is set |
| GitHub Actions OIDC error | Check that the federated credential subject matches the branch/PR trigger |
