output "cloud_run_url" {
  value = google_cloud_run_v2_service.default.uri
}

output "alloydb_instance_ip" {
  value = google_alloydb_instance.default.public_ip_address
}

output "alloydb_connection_name" {
  value = "projects/${var.project_id}/locations/${var.region}/clusters/arch-agent-cluster/instances/arch-agent-instance"
}
