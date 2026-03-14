output "cloud_run_url" {
  description = "Public HTTPS URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.default.uri
}

output "alloydb_instance_ip" {
  description = "Public IP address of the AlloyDB primary instance"
  value       = google_alloydb_instance.default.ip_address
}

output "alloydb_connection_name" {
  description = "Full AlloyDB instance path for connector use"
  value       = "projects/${var.project_id}/locations/${var.region}/clusters/arch-agent-cluster/instances/arch-agent-instance"
}

output "kms_keyring" {
  description = "KMS keyring resource ID"
  value       = google_kms_key_ring.arch_agent.id
}

output "secrets_kms_key" {
  description = "KMS key used for Secret Manager encryption"
  value       = google_kms_crypto_key.secrets_key.id
}

output "alloydb_kms_key" {
  description = "KMS CMEK key for AlloyDB data-at-rest encryption"
  value       = google_kms_crypto_key.alloydb_key.id
}

output "db_pass_secret_id" {
  description = "Secret Manager secret holding the AlloyDB password"
  value       = google_secret_manager_secret.db_pass.secret_id
}

output "vpc_connector" {
  description = "Serverless VPC connector used by Cloud Run"
  value       = google_vpc_access_connector.connector.id
}
