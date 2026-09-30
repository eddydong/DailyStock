#!/bin/bash
# Deploy the two pre-open jobs to Cloud Run in us-central1.
# Each job is 1 vCPU and 2 GiB. They do not run at the same time:
# Hong Kong fires at 08:15 Asia/Hong_Kong, the US job at 08:15 America/New_York.
# Do not add a larger machine or a region outside the US free-tier pricing.
# Cloud Run jobs bill for the whole run, and this billing account's free
# allowance is 240,000 vCPU-seconds and 450,000 GiB-seconds a month, shared
# with dipalerts-research. At 1 vCPU and 2 GiB, keep each job under 6000
# seconds. A second Cloud Scheduler job is the Hong Kong clock. The first
# three Scheduler jobs on the billing account are free.
#
# Requires billing linked on the project (Google's $0 tier still needs it).
# Secrets are read from the environment, never written into the image:
#   DEEPSEEK_API_KEY FRED_API_KEY
#   CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_KV_NAMESPACE_ID
#   PAGE_PUBLISH_TOKEN
#   GCP_PROJECT
set -euo pipefail

PROJECT="${GCP_PROJECT:-aapl-daily-0926}"
REGION=us-central1
# The US job is the one Cloud Scheduler already runs. The Hong Kong job is
# a second Cloud Run job on the same image, so the two clocks stay separate.
US_JOB=aapl-daily
HK_JOB=hk-daily
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/${US_JOB}"
PAGE_PUBLISH_URL="${PAGE_PUBLISH_URL:-https://stock.eddykd.com/publish}"
ENV_COMMON="GCP_PROJECT=${PROJECT},CLOUDFLARE_ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID},CLOUDFLARE_KV_NAMESPACE_ID=${CLOUDFLARE_KV_NAMESPACE_ID},DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY},FRED_API_KEY=${FRED_API_KEY},CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN},PAGE_PUBLISH_URL=${PAGE_PUBLISH_URL},PAGE_PUBLISH_TOKEN=${PAGE_PUBLISH_TOKEN},TRADINGAGENTS_LLM_PROVIDER=deepseek,TRADINGAGENTS_QUICK_THINK_LLM=deepseek-flash,TRADINGAGENTS_DEEP_THINK_LLM=deepseek-flash"

gcloud builds submit --project "$PROJECT" --tag "$IMAGE" .

# Env vars are taken from the shell that runs this script. They are not
# baked into the image. PAGE_PUBLISH_TOKEN is the Worker secret for
# PUT /publish. CLOUDFLARE_API_TOKEN remains the direct KV path.
gcloud run jobs deploy "$US_JOB" \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --command python \
  --args scripts/daily_sp500.py,--market,us,--publish \
  --cpu 1 \
  --memory 2Gi \
  --task-timeout 6000 \
  --max-retries 0 \
  --set-env-vars "${ENV_COMMON},TZ=America/New_York"

gcloud run jobs deploy "$HK_JOB" \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --command python \
  --args scripts/daily_sp500.py,--market,hk,--publish \
  --cpu 1 \
  --memory 2Gi \
  --task-timeout 6000 \
  --max-retries 0 \
  --set-env-vars "${ENV_COMMON},TZ=Asia/Hong_Kong"

# 08:15 local time. Five serial names take about 40 minutes, so this
# finishes before the 09:30 cash open. A 09:00 start does not.
# Monday–Friday only. Each job exits immediately on that market's holiday,
# so a holiday does not spend a model run. Both schedulers stay in
# us-central1. The timezone is what moves the clock.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

upsert_scheduler() {
  local name="$1" zone="$2" uri="$3"
  local common=(
    --project "$PROJECT" --location "$REGION"
    --schedule "15 8 * * 1-5" --time-zone "$zone"
    --uri "$uri" --http-method POST
    --oauth-service-account-email "$SA"
  )
  if gcloud scheduler jobs describe "$name" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" "${common[@]}"
  else
    gcloud scheduler jobs create http "$name" "${common[@]}"
  fi
}

upsert_scheduler "$US_JOB" "America/New_York" \
  "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${US_JOB}:run"
upsert_scheduler "$HK_JOB" "Asia/Hong_Kong" \
  "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${HK_JOB}:run"

# Drop untagged images on this billing account. The free 0.5 GB is shared.
bash "$(dirname "$0")/gc_artifact_registry.sh"
