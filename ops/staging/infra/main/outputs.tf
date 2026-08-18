output "canvas_url" {
  value = "https://${local.canvas_hostname}"
}

output "rce_url" {
  value = "https://${local.rce_hostname}"
}

output "ssh_hostname" {
  value = local.ssh_hostname
}

output "ssh_known_hosts" {
  value = "${local.ssh_hostname} ${trimspace(tls_private_key.host.public_key_openssh)}"
}

output "ssh_private_key" {
  value     = tls_private_key.deploy.private_key_openssh
  sensitive = true
}

output "cloudflare_access_client_id" {
  value     = cloudflare_zero_trust_access_service_token.github.client_id
  sensitive = true
}

output "cloudflare_access_client_secret" {
  value     = cloudflare_zero_trust_access_service_token.github.client_secret
  sensitive = true
}

output "runtime_secrets" {
  sensitive = true
  value = {
    CANVAS_ENCRYPTION_KEY     = random_password.canvas_encryption_key.result
    CANVAS_JWT_ENCRYPTION_KEY = random_password.canvas_jwt_encryption_key.result
    CANVAS_LMS_ACCOUNT_NAME   = var.canvas_account_name
    CANVAS_LMS_ADMIN_EMAIL    = var.admin_email
    CANVAS_LMS_ADMIN_PASSWORD = random_password.canvas_admin_password.result
    DATABASE_CA_CERT_BASE64   = base64encode(data.digitalocean_database_ca.postgres.certificate)
    DATABASE_ADMIN_PASSWORD   = digitalocean_database_cluster.postgres.password
    DATABASE_ADMIN_USERNAME   = digitalocean_database_cluster.postgres.user
    DATABASE_HOST             = digitalocean_database_cluster.postgres.private_host
    DATABASE_NAME             = digitalocean_database_db.canvas.name
    DATABASE_PASSWORD         = digitalocean_database_user.canvas.password
    DATABASE_PORT             = tostring(digitalocean_database_cluster.postgres.port)
    DATABASE_USERNAME         = digitalocean_database_user.canvas.name
    RCE_ECOSYSTEM_KEY         = random_password.rce_ecosystem_key.result
    RCE_ECOSYSTEM_SECRET      = random_password.rce_ecosystem_secret.result
    SPACES_ACCESS_KEY_ID      = digitalocean_spaces_key.canvas.access_key
    SPACES_BUCKET_NAME        = digitalocean_spaces_bucket.files.name
    SPACES_SECRET_ACCESS_KEY  = digitalocean_spaces_key.canvas.secret_key
  }
}

output "droplet_id" {
  value = digitalocean_droplet.app.id
}

output "droplet_ipv4" {
  value = digitalocean_droplet.app.ipv4_address
}
