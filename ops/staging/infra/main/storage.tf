resource "digitalocean_spaces_bucket" "files" {
  name          = "${var.spaces_bucket_prefix}-${random_id.bucket_suffix.hex}"
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

resource "digitalocean_spaces_bucket_cors_configuration" "files" {
  bucket = digitalocean_spaces_bucket.files.name
  region = digitalocean_spaces_bucket.files.region

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD", "POST", "PUT"]
    allowed_origins = ["https://${local.canvas_hostname}"]
    max_age_seconds = 3600
  }
}

resource "digitalocean_spaces_key" "canvas" {
  name = "${var.project_name}-canvas"

  grant {
    bucket     = digitalocean_spaces_bucket.files.name
    permission = "readwrite"
  }
}
