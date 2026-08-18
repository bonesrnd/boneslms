resource "digitalocean_spaces_bucket" "state" {
  name          = var.state_bucket_name
  region        = var.region
  acl           = "private"
  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "digitalocean_spaces_key" "tofu" {
  name = "boneslms-staging-opentofu"

  grant {
    bucket     = digitalocean_spaces_bucket.state.name
    permission = "readwrite"
  }
}
