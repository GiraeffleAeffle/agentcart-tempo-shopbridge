output "server_id" {
  value = hcloud_server.staging.id
}

output "server_ipv4" {
  value = hcloud_server.staging.ipv4_address
}

output "server_ipv6" {
  value = hcloud_server.staging.ipv6_address
}

output "ssh_command" {
  value = "ssh -i ../../../.secrets/agentcart_staging_ed25519 root@${hcloud_server.staging.ipv4_address}"
}

output "dns_record_hint" {
  value = "Create A record: woo-staging -> ${hcloud_server.staging.ipv4_address}"
}
