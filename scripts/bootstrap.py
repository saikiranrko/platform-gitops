#!/usr/bin/env python3
"""
bootstrap.py — One-shot platform setup script.

Run this ONCE before anything else. It:
  1. Creates the Terraform remote state storage account
  2. Creates the GitHub Actions OIDC federated credential
  3. Installs ArgoCD on the AKS cluster
  4. Installs kube-prometheus-stack (Prometheus + Grafana)
  5. Prints the values you need to fill into GitHub Secrets

Prerequisites:
  pip install azure-identity azure-mgmt-resource azure-mgmt-storage azure-mgmt-authorization
  az login
  kubectl context pointing at your AKS cluster
"""

import json
import os
import subprocess
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Config — update these if you change the Terraform variables
# ---------------------------------------------------------------------------
SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
LOCATION = "eastus"
PREFIX = "sai"
SUFFIX = "001"

TFSTATE_RG = "sai-tfstate-rg"
TFSTATE_SA = f"saitfstate{SUFFIX}"       # storage account name (globally unique)
TFSTATE_CONTAINER = "tfstate"

GITHUB_ORG = "saikiranrko"
GITHUB_REPO = "platform-gitops"
APP_NAME = f"{PREFIX}-github-actions"    # Azure AD app for OIDC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(cmd: str, check: bool = True, capture: bool = False) -> Optional[str]:
    """Run a shell command, print it, return output if capture=True."""
    print(f"\n$ {cmd}")
    result = subprocess.run(
        cmd, shell=True, check=check,
        capture_output=capture, text=True
    )
    if capture:
        return result.stdout.strip()
    return None


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Step 1: Terraform remote state storage
# ---------------------------------------------------------------------------
def setup_tfstate_backend() -> None:
    section("1. Terraform Remote State — Azure Blob Storage")

    run(f"az group create --name {TFSTATE_RG} --location {LOCATION}")
    run(
        f"az storage account create "
        f"--name {TFSTATE_SA} "
        f"--resource-group {TFSTATE_RG} "
        f"--location {LOCATION} "
        f"--sku Standard_LRS "           # cheapest tier
        f"--allow-blob-public-access false "
        f"--min-tls-version TLS1_2"
    )
    run(
        f"az storage container create "
        f"--name {TFSTATE_CONTAINER} "
        f"--account-name {TFSTATE_SA} "
        f"--auth-mode login"
    )
    print(f"\n✅ TF state backend ready: {TFSTATE_SA}/{TFSTATE_CONTAINER}")


# ---------------------------------------------------------------------------
# Step 2: GitHub Actions OIDC (no static secrets!)
# ---------------------------------------------------------------------------
def setup_github_oidc() -> dict:
    section("2. GitHub Actions OIDC Federated Credential")

    # Create App Registration
    app_id = run(
        f"az ad app create --display-name {APP_NAME} --query appId -o tsv",
        capture=True
    )
    sp_object_id = run(
        f"az ad sp create --id {app_id} --query id -o tsv",
        capture=True
    )

    # Assign Contributor on subscription
    run(
        f"az role assignment create "
        f"--assignee {app_id} "
        f"--role Contributor "
        f"--scope /subscriptions/{SUBSCRIPTION_ID}"
    )
    # Also assign Storage Blob Data Contributor for Terraform state
    run(
        f"az role assignment create "
        f"--assignee {app_id} "
        f"--role 'Storage Blob Data Contributor' "
        f"--scope /subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{TFSTATE_RG}"
        f"/providers/Microsoft.Storage/storageAccounts/{TFSTATE_SA}"
    )

    # Federated credential for main branch push
    cred_body = {
        "name": "github-main",
        "issuer": "https://token.actions.githubusercontent.com",
        "subject": f"repo:{GITHUB_ORG}/{GITHUB_REPO}:ref:refs/heads/main",
        "audiences": ["api://AzureADTokenExchange"]
    }
    run(
        f"az ad app federated-credential create "
        f"--id {app_id} "
        f"--parameters '{json.dumps(cred_body)}'"
    )

    # Federated credential for PRs
    cred_pr = {**cred_body, "name": "github-pr",
                "subject": f"repo:{GITHUB_ORG}/{GITHUB_REPO}:pull_request"}
    run(
        f"az ad app federated-credential create "
        f"--id {app_id} "
        f"--parameters '{json.dumps(cred_pr)}'"
    )

    print(f"\n✅ OIDC configured — no static secrets needed")
    return {
        "AZURE_CLIENT_ID": app_id,
        "AZURE_TENANT_ID": TENANT_ID,
        "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION_ID,
        "GITHUB_ACTIONS_SP_OBJECT_ID": sp_object_id,
    }


# ---------------------------------------------------------------------------
# Step 3: ArgoCD
# ---------------------------------------------------------------------------
def install_argocd() -> None:
    section("3. ArgoCD")

    run("kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -")
    run(
        "kubectl apply -n argocd -f "
        "https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml"
    )
    run("kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s")

    # Patch to use LoadBalancer so we can reach the UI (dev only)
    run(
        "kubectl patch svc argocd-server -n argocd "
        "-p '{\"spec\": {\"type\": \"LoadBalancer\"}}'"
    )

    initial_password = run(
        "kubectl -n argocd get secret argocd-initial-admin-secret "
        "-o jsonpath='{.data.password}' | base64 -d",
        capture=True
    )
    print(f"\n✅ ArgoCD installed")
    print(f"   Initial admin password: {initial_password}")
    print("   Get the UI URL:  kubectl get svc argocd-server -n argocd")
    print("   ⚠️  Change the password after first login!")


# ---------------------------------------------------------------------------
# Step 4: kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
# ---------------------------------------------------------------------------
def install_monitoring() -> None:
    section("4. Prometheus + Grafana (kube-prometheus-stack)")

    run("helm repo add prometheus-community https://prometheus-community.github.io/helm-charts")
    run("helm repo update")
    run("kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -")
    run(
        "helm upgrade --install prometheus prometheus-community/kube-prometheus-stack "
        "--namespace monitoring "
        "--set grafana.adminPassword=changeme123 "   # change this!
        "--set prometheus.prometheusSpec.retention=7d "  # 7 days logs (cost control)
        "--set alertmanager.enabled=true "
        "--wait --timeout 10m"
    )

    # Import our custom dashboard
    run(
        "kubectl create configmap task-api-dashboard "
        "--from-file=monitoring/dashboards/task-api-dashboard.json "
        "-n monitoring "
        "--dry-run=client -o yaml | "
        "kubectl label --local -f - grafana_dashboard=1 -o yaml | "
        "kubectl apply -f -",
        check=False   # don't fail if run before cluster exists
    )
    print("\n✅ Monitoring stack installed")
    print("   Get Grafana URL:  kubectl get svc prometheus-grafana -n monitoring")
    print("   Login: admin / changeme123")


# ---------------------------------------------------------------------------
# Step 5: Print GitHub Secrets
# ---------------------------------------------------------------------------
def print_secrets(secrets: dict) -> None:
    section("5. GitHub Secrets — Add these to your repo")

    print("\nGo to: https://github.com/saikiranrko/platform-gitops/settings/secrets/actions\n")
    for key, value in secrets.items():
        print(f"  {key}={value}")
    print(
        "\nAlso set these in GitHub Environments > dev:\n"
        "  AZURE_CLIENT_ID\n"
        "  AZURE_TENANT_ID\n"
        "  AZURE_SUBSCRIPTION_ID\n"
        "  GITHUB_ACTIONS_SP_OBJECT_ID"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not SUBSCRIPTION_ID:
        print("ERROR: Set AZURE_SUBSCRIPTION_ID environment variable")
        print("  export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)")
        sys.exit(1)
    if not TENANT_ID:
        print("ERROR: Set AZURE_TENANT_ID environment variable")
        print("  export AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)")
        sys.exit(1)

    setup_tfstate_backend()
    secrets = setup_github_oidc()
    install_argocd()
    install_monitoring()
    print_secrets(secrets)

    print("\n" + "="*60)
    print("  Bootstrap complete! Next steps:")
    print("  1. Add GitHub Secrets shown above")
    print("  2. Run: terraform -chdir=terraform/environments/dev init")
    print("  3. Push a PR to trigger tf-plan.yml")
    print("  4. Merge to trigger tf-apply.yml")
    print("  5. kubectl apply -f gitops/environments/dev/task-api/application.yaml")
    print("="*60)
