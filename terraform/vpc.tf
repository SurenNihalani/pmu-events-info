# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "pmu-events-info-vpc"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Internet Gateway for public subnet
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "pmu-events-info-igw"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Data source for availability zones in us-east-1
data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "region-name"
    values = ["us-east-1"]
  }
}

# Public Subnets for each availability zone
resource "aws_subnet" "public" {
  for_each = {
    for i, az in data.aws_availability_zones.available.names :
    az => cidrsubnet("10.0.0.0/16", 8, i)
  }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = {
    Name        = "pmu-events-info-public-${each.key}"
    Type        = "Public"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}


# Route Table for Public Subnet
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name        = "pmu-events-info-public-rt"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}


# Route Table Associations for all public subnets
resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}


# Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of all public subnets"
  value       = { for az, subnet in aws_subnet.public : az => subnet.id }
}

output "public_subnet_cidrs" {
  description = "CIDR blocks of all public subnets"
  value       = { for az, subnet in aws_subnet.public : az => subnet.cidr_block }
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway"
  value       = aws_internet_gateway.main.id
}
