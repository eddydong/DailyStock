#!/bin/bash
# Delete unused Artifact Registry images on this billing account.
# Free storage is 0.5 GB for the whole account. Untagged leftovers from
# earlier deploys are what incurs the fee. Keeps `latest` and any digest
# a Cloud Run job or service still runs.
set -euo pipefail

PROJECT="${GCP_PROJECT:-aapl-daily-0926}"
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' | awk -F/ '{print $NF}')"
POLICY="$(mktemp)"
trap 'rm -f "$POLICY"' EXIT
cat > "$POLICY" << 'EOF'
[
  {
    "name": "delete-untagged",
    "action": {"type": "Delete"},
    "condition": {"tagState": "untagged", "olderThan": "86400s"}
  }
]
EOF

echo "Billing account ${BILLING}"
gcloud billing projects list --billing-account="$BILLING" --format='value(projectId)' | while read -r proj; do
  [ -n "$proj" ] || continue
  gcloud artifacts repositories list --project="$proj" --format=json 2>/dev/null \
    | python3 -c 'import json,sys
raw=sys.stdin.read()
start=raw.find("[")
data=json.loads(raw[start:]) if start>=0 else []
for repo in data:
    name=repo.get("name","").split("/")[-1]
    loc=(repo.get("name","").split("/locations/")[-1].split("/")[0]) if "/locations/" in repo.get("name","") else ""
    if name and loc:
        print(name, loc)' \
    | while read -r repo_name location; do
      gcloud artifacts repositories set-cleanup-policies "$repo_name" \
        --location="$location" --project="$proj" --policy="$POLICY" --quiet >/dev/null
      live="$(
        gcloud run jobs list --project="$proj" --format='value(spec.template.template.containers[0].image)' 2>/dev/null || true
        gcloud run services list --project="$proj" --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true
      )"
      host="${location}-docker.pkg.dev/${proj}/${repo_name}"
      gcloud artifacts docker images list "$host" --include-tags --format=json --project="$proj" 2>/dev/null \
        | LIVE_IMAGES="$live" python3 -c 'import json,os,sys
raw=sys.stdin.read()
start=raw.find("[")
data=json.loads(raw[start:]) if start>=0 else []
live=[line for line in os.environ.get("LIVE_IMAGES","").splitlines() if line.strip()]
for item in data:
    if item.get("tags"):
        continue
    version=item.get("version") or ""
    digest=version.split("@")[-1]
    if any(digest and digest in ref for ref in live):
        continue
    if version:
        print(version)' \
        | while read -r version; do
          echo "Deleting ${version}"
          gcloud artifacts docker images delete "$version" --project="$proj" --quiet
        done
    done
done
echo "Artifact Registry garbage collection done."
