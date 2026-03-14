terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  # Remote state stored in GCS — ensures state is not lost between CI runs.
  # Create the bucket first: `gcloud storage buckets create gs://tf-state-arch-agent --project=project-ef11010f-3538-4e0c-8f1`
  backend "gcs" {
    bucket = "tf-state-arch-agent"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
