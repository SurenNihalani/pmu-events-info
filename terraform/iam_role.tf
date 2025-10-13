# IAM Role for EC2 instances to access S3 bucket
resource "aws_iam_role" "ec2_s3_access" {
  name = "pmu-events-info-ec2-s3-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = "EC2AssumeRole"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "PMU Events Info EC2 S3 Access Role"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# IAM Policy for S3 bucket access
resource "aws_iam_policy" "s3_access" {
  name        = "pmu-events-info-s3-access-policy"
  description = "Policy for S3 access to suren-terraform bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::suren-terraform",
          "arn:aws:s3:::suren-terraform/*"
        ]
      }
    ]
  })

  tags = {
    Name        = "PMU Events Info S3 Access Policy"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Attach the S3 policy to the role
resource "aws_iam_role_policy_attachment" "s3_access_attachment" {
  role       = aws_iam_role.ec2_s3_access.name
  policy_arn = aws_iam_policy.s3_access.arn
}

# Attach AmazonSSMManagedInstanceCore managed policy for SSM access
resource "aws_iam_role_policy_attachment" "ssm_managed_instance_core" {
  role       = aws_iam_role.ec2_s3_access.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# IAM Instance Profile to attach the role to EC2 instances
resource "aws_iam_instance_profile" "ec2_s3_profile" {
  name = "pmu-events-info-ec2-s3-profile"
  role = aws_iam_role.ec2_s3_access.name

  tags = {
    Name        = "PMU Events Info EC2 S3 Profile"
    Environment = "dev"
    Project     = "pmu-events-info"
  }
}

# Outputs
output "iam_role_arn" {
  description = "ARN of the IAM role for EC2 S3 access"
  value       = aws_iam_role.ec2_s3_access.arn
}

output "iam_role_name" {
  description = "Name of the IAM role for EC2 S3 access"
  value       = aws_iam_role.ec2_s3_access.name
}

output "instance_profile_name" {
  description = "Name of the IAM instance profile"
  value       = aws_iam_instance_profile.ec2_s3_profile.name
}
