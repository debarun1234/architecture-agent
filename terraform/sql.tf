resource "google_alloydb_cluster" "default" {
  cluster_id = "arch-agent-cluster"
  location   = var.region
  project    = var.project_id
  
  network_config {
    network = "projects/${var.project_id}/global/networks/default"
  }

  initial_user {
    user     = var.db_user
    password = var.db_pass
  }
}

resource "google_alloydb_instance" "default" {
  cluster       = google_alloydb_cluster.default.name
  instance_id   = "arch-agent-instance"
  instance_type = "PRIMARY"
  
  machine_config {
    cpu_count = 2
  }

  annotations = {
    "alloydb.googleapis.com/enable_public_endpoint" = "true"
  }
}
