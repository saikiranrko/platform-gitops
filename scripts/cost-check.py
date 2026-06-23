#!/usr/bin/env python3
"""
cost-check.py — Query Azure Cost Management and warn when spending is high.

Usage:
  export AZURE_SUBSCRIPTION_ID=<your-sub-id>
  python scripts/cost-check.py

  Or as a scheduled GitHub Action (run daily):
    - name: Cost check
      run: python scripts/cost-check.py
      env:
        AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
# Warn at $20, critical at $40 (student credit is limited!)
WARN_THRESHOLD_USD = float(os.environ.get("COST_WARN_USD", "20"))
CRIT_THRESHOLD_USD = float(os.environ.get("COST_CRIT_USD", "40"))
RESOURCE_GROUP = "sai-platform-rg"


def run_az(cmd: str) -> dict:
    result = subprocess.run(
        f"az {cmd} -o json",
        shell=True, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def get_cost_this_month() -> float:
    """Query Azure Cost Management for current month spend."""
    today = datetime.utcnow()
    start = today.replace(day=1).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    try:
        result = subprocess.run(
            f"az costmanagement query "
            f"--scope /subscriptions/{SUBSCRIPTION_ID} "
            f"--type ActualCost "
            f"--timeframe Custom "
            f"--time-period from={start} to={end} "
            f"--dataset-aggregation '{{\"totalCost\":{{\"name\":\"Cost\",\"function\":\"Sum\"}}}}' "
            f"--dataset-granularity None "
            f"-o json",
            shell=True, capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        rows = data.get("rows", [])
        if rows:
            return float(rows[0][0])
    except Exception as e:
        print(f"Warning: Could not fetch cost data: {e}")
    return 0.0


def get_resource_group_cost() -> float:
    """Cost breakdown by resource group."""
    today = datetime.utcnow()
    start = today.replace(day=1).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    try:
        result = subprocess.run(
            f"az costmanagement query "
            f"--scope /subscriptions/{SUBSCRIPTION_ID} "
            f"--type ActualCost "
            f"--timeframe Custom "
            f"--time-period from={start} to={end} "
            f"--dataset-aggregation '{{\"totalCost\":{{\"name\":\"Cost\",\"function\":\"Sum\"}}}}' "
            f"--dataset-granularity None "
            f"--dataset-grouping '[{{\"type\":\"Dimension\",\"name\":\"ResourceGroup\"}}]' "
            f"-o json",
            shell=True, capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        costs = {}
        for row in data.get("rows", []):
            costs[row[1]] = float(row[0])
        return costs
    except Exception as e:
        print(f"Warning: Could not fetch RG cost data: {e}")
    return {}


def check_running_resources() -> list[str]:
    """List potentially expensive always-running resources."""
    warnings = []

    # Check for running AKS clusters
    try:
        clusters = run_az(
            f"aks list --subscription {SUBSCRIPTION_ID} "
            "--query '[].{{name:name,rg:resourceGroup,state:powerState.code}}'"
        )
        for c in clusters:
            if c.get("state") != "Stopped":
                warnings.append(
                    f"⚠️  AKS cluster '{c['name']}' in '{c['rg']}' is RUNNING "
                    f"(~$1/hr) — stop it when not in use: "
                    f"az aks stop -n {c['name']} -g {c['rg']}"
                )
    except Exception:
        pass

    # Check for running VMs
    try:
        vms = run_az(
            f"vm list --subscription {SUBSCRIPTION_ID} "
            "--query '[].{{name:name,rg:resourceGroup}}'"
        )
        if vms:
            warnings.append(f"⚠️  {len(vms)} VMs found — verify they should be running")
    except Exception:
        pass

    return warnings


def main():
    if not SUBSCRIPTION_ID:
        print("ERROR: Set AZURE_SUBSCRIPTION_ID")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  Azure Cost Report — {datetime.utcnow().strftime('%Y-%m-%d')}")
    print(f"{'='*50}")

    total = get_cost_this_month()
    print(f"\n  Total spend this month: ${total:.2f} USD")
    print(f"  Warn threshold:         ${WARN_THRESHOLD_USD:.2f}")
    print(f"  Critical threshold:     ${CRIT_THRESHOLD_USD:.2f}")

    rg_costs = get_resource_group_cost()
    if rg_costs:
        print("\n  Breakdown by Resource Group:")
        for rg, cost in sorted(rg_costs.items(), key=lambda x: x[1], reverse=True):
            print(f"    {rg:<40} ${cost:.2f}")

    print("\n  Running resource check:")
    warnings = check_running_resources()
    if warnings:
        for w in warnings:
            print(f"  {w}")
    else:
        print("  ✅ No expensive always-running resources detected")

    # Exit codes for CI integration
    if total >= CRIT_THRESHOLD_USD:
        print(f"\n🚨 CRITICAL: Monthly spend ${total:.2f} exceeds ${CRIT_THRESHOLD_USD:.2f}!")
        print("   Consider: az aks stop, destroy non-essential infra")
        sys.exit(2)
    elif total >= WARN_THRESHOLD_USD:
        print(f"\n⚠️  WARNING: Monthly spend ${total:.2f} approaching limit")
        sys.exit(1)
    else:
        print(f"\n✅ Spend ${total:.2f} is within budget")
        sys.exit(0)


if __name__ == "__main__":
    main()
