terraform {
  required_version = ">= 1.11.0"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "2.99.1"
    }
  }
}

provider "digitalocean" {}
