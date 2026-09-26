#!/bin/bash
# Deploy the daily SPY job to Cloud Run in us-central1.
# Stays inside Always Free only if this is the shape that runs:
#   1 vCPU, 2 GiB, one task, one Cloud Scheduler job, US BigQuery.
# Do not add a second scheduler job, a larger machine, or a region
# outside the US free-tier pricing.
#
# Requires billing linked on the project (Google's $0 tier still needs it).
# Secrets are read from the environment, never written into the image:
#   DEEPSEEK_API_KEY FRED_API_KEY
#   CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_KV_NAMESPACE_ID
#   GCP_PROJECT
set -euo pipefail

PROJECT="${GCP_PROJECT:-aapl-daily-0926}"
REGION=us-central1
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/sp500-daily"

gcloud builds submit --project "$PROJECT" --tag "$IMAGE" .

# Env vars are taken from the shell that runs this script. They are not
# baked into the image. Create CLOUDFLARE_API_TOKEN in the Cloudflare
# dashboard with Workers KV write on this account.
gcloud run jobs deploy sp500-daily \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --command python \
  --args scripts/daily_sp500.py,--publish \
  --cpu 1 \
  --memory 2Gi \
  --task-timeout 3600 \
  --max-retries 0 \
  --set-env-vars "GCP_PROJECT=${PROJECT},TZ=America/New_York,CLOUDFLARE_ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID},CLOUDFLARE_KV_NAMESPACE_ID=${CLOUDFLARE_KV_NAMESPACE_ID},DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY},FRED_API_KEY=${FRED_API_KEY},CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN},TRADINGAGENTS_LLM_PROVIDER=deepseek,TRADINGAGENTS_QUICK_THINK_LLM=deepseek-flash,TRADINGAGENTS_DEEP_THINK_LLM=deepseek-flash"

# 09:00 America/New_York, thirty minutes before the 09:30 cash open.
# Monday–Friday only. The job itself exits immediately on an NYSE holiday,
# so a holiday does not spend a model run. The first three Scheduler jobs
# on the billing account are free. Do not add another.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
gcloud scheduler jobs create http sp500-daily \
  --project "$PROJECT" \
  --location "$REGION" \
  --schedule "0 9 * * 1-5" \
  --time-zone "America/New_York" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/sp500-daily:run" \
  --http-method POST \
  --oauth-service-account-email "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Drop untagged images on this billing account. The free 0.5 GB is shared.
bash "$(dirname "$0")/gc_artifact_registry.sh"
