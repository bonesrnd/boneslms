variable "region" {
  description = "DigitalOcean region for the state bucket."
  type        = string
  default     = "nyc3"
}

variable "state_bucket_name" {
  description = "Globally unique Spaces bucket name for OpenTofu state."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Use a valid lowercase Spaces bucket name."
  }
}
