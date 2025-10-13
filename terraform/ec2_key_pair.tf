resource "aws_key_pair" "main" {
  key_name   = "pmu-events-info-key"
  public_key = file("~/.ssh/id_ed25519.pub")

  tags = {
    Name        = "PMU Events Info Key"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Output the key pair name for reference in other resources
output "key_pair_name" {
  description = "Name of the EC2 Key Pair"
  value       = aws_key_pair.main.key_name
}

