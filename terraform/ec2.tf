
resource "aws_ebs_volume" "suren_devbox_data" {
  availability_zone = "us-east-1a"
  encrypted = true
  final_snapshot = true

  size = 20
  type = "gp3"
  kms_key_id = aws_kms_key.key.arn
}

resource "aws_volume_attachment" "suren_devbox_data_attachment" {
  device_name = "/dev/xvdb"
  volume_id = aws_ebs_volume.suren_devbox_data.id
  instance_id = aws_instance.suren_devbox.id
}

resource "aws_network_interface" "network_interface" {
  subnet_id = aws_subnet.public_ipv6_only["us-east-1a"].id
  security_groups = [aws_security_group.suren_devbox.id]
  ipv6_address_count = 1
}



resource "aws_instance" "suren_devbox" {
  ami =  "ami-0bbdd8c17ed981ef9"
  instance_type = "c7i-flex.large"
  key_name = aws_key_pair.main.key_name
  iam_instance_profile = aws_iam_instance_profile.ec2_s3_profile.name
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted = true
    kms_key_id = aws_kms_key.key.arn
  }
  primary_network_interface {
    network_interface_id = aws_network_interface.network_interface.id
  }

  metadata_options{
    http_endpoint = "enabled"
    http_protocol_ipv6 = "enabled"
  }
}


output "suren_devbox_public_ip" {
  description = "Public IP of the Suren Devbox"
  value       = aws_instance.suren_devbox.public_ip
}

output "suren_devbox_public_ipv6" {
  description = "Public IPv6 of the Suren Devbox"
  value       = aws_instance.suren_devbox.id
}
