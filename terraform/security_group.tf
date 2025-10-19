resource "aws_security_group" "main" {
  name        = "pmu-events-info-main-sg"
  description = "Main security group for PMU Events Info project"
  vpc_id      = aws_vpc.main.id

  # Unlimited egress (outbound) rule
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["2a09:bac0:1001:3fc::1d1:ed/128"]
    description      = "Allow all outbound traffic"
  }
  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = ["104.30.177.31/32"]
    ipv6_cidr_blocks = ["2a09:bac0:1001:3fc::1d1:ed/128"]
    description      = "Allow SSH traffic"
  }

  tags = {
    Name        = "pmu-events-info-main-sg"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Output the security group ID
output "security_group_id" {
  description = "ID of the main security group"
  value       = aws_security_group.main.id
}


resource "aws_security_group" "suren_devbox" {
  name        = "pmu-events-info-suren-devbox-sg"
  description = "Security group for Suren Devbox"
  vpc_id      = aws_vpc.main.id
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
    description      = "Allow all outbound traffic"
  }
  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = ["104.30.177.31/32", "107.196.178.208/32"]
    ipv6_cidr_blocks = ["2a09:bac0:1001:300::/56", "2600:1700:368f:5c00::/56"]
    description      = "Allow SSH traffic"
  }
}
