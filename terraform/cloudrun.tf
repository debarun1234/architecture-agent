resource "google_cloud_run_v2_service" "default" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  # Only allow HTTPS traffic from internet (Cloud Run native HTTPS)
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run_sa.email

    # Route internal traffic through the VPC connector → AlloyDB on private network
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      # Fixed: use Artifact Registry instead of deprecated gcr.io
      image = "${var.region}-docker.pkg.dev/${var.project_id}/arch-agent/${var.service_name}:latest"

      ports {
        container_port = 8000
      }

      # Non-sensitive env vars as plain values
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = var.region
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = "global"
      }
      env {
        name  = "ALLOYDB_CLUSTER"
        value = "arch-agent-cluster"
      }
      env {
        name  = "ALLOYDB_INSTANCE"
        value = "arch-agent-instance"
      }
      env {
        name  = "ALLOYDB_USER"
        value = var.db_user
      }
      env {
        name  = "ALLOYDB_NAME"
        value = var.db_name
      }

      # Sensitive: DB password sourced from Secret Manager (KMS-encrypted at rest)
      env {
        name = "ALLOYDB_PASS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_pass.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_alloydb_instance.default,
    google_project_iam_member.vertex_ai_user,
    google_project_iam_member.alloydb_client,
    google_secret_manager_secret_version.db_pass,
    google_vpc_access_connector.connector,
  ]
}

# Public HTTPS access: allow all users to invoke the Cloud Run URL
resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = google_cloud_run_v2_service.default.location
  project  = var.project_id
  name     = google_cloud_run_v2_service.default.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
