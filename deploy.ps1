$ErrorActionPreference = "Stop"

$PROJECT_ID = "project-ef11010f-3538-4e0c-8f1"
$REGION = "us-central1"
$SERVICE_NAME = "architecture-review-agent"

Write-Host "=================================================="
Write-Host "🚀 Deploying Architecture Review Agent to Cloud Run"
Write-Host "=================================================="

# Ensure gcloud is configured
gcloud config set project $PROJECT_ID

Write-Host "`n[1/3] Building the container image with Cloud Build..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

Write-Host "`n[2/3] Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME `
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME `
  --region $REGION `
  --allow-unauthenticated `
  --platform managed `
  --memory 1Gi `
  --timeout 300 `
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_REGION=$REGION

Write-Host "`n[3/3] Deployment complete!"
gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
