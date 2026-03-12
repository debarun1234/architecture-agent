resource "google_cloud_run_v2_service" "default" {
  name     = var.service_name
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run_sa.email
    
    containers {
      image = "gcr.io/${var.project_id}/${var.service_name}:latest"
      
      ports {
        container_port = 8000
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = var.region
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
        name  = "ALLOYDB_PASS"
        value = var.db_pass
      }
      env {
        name  = "ALLOYDB_NAME"
        value = var.db_name
      }
    }
  }

  depends_on = [
    google_alloydb_instance.default,
    google_project_iam_member.vertex_ai_user,
    google_project_iam_member.alloydb_client
  ]
}

resource "google_cloud_run_v2_service_iam_member" "noauth" {
  location = google_cloud_run_v2_service.default.location
  project  = var.project_id
  name     = google_cloud_run_v2_service.default.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
