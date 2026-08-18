output "state_bucket_name" {
  value = digitalocean_spaces_bucket.state.name
}

output "state_endpoint" {
  value = "https://${digitalocean_spaces_bucket.state.endpoint}"
}

output "tofu_spaces_access_key_id" {
  value     = digitalocean_spaces_key.tofu.access_key
  sensitive = true
}

output "tofu_spaces_secret_access_key" {
  value     = digitalocean_spaces_key.tofu.secret_key
  sensitive = true
}
