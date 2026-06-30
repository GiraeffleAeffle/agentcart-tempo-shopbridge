variable "server_name" {
  type    = string
  default = "agentcart-woo-staging"
}

variable "server_type" {
  type    = string
  default = "cx23"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "ssh_key_name" {
  type    = string
  default = "agentcart-staging"
}

variable "ssh_public_key_path" {
  type    = string
  default = "../../../.secrets/agentcart_staging_ed25519.pub"
}

variable "ssh_source_ips" {
  type    = list(string)
  default = ["0.0.0.0/0", "::/0"]
}
