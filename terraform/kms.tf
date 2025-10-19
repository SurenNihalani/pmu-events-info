resource "aws_kms_key" "key" {
    description = "Key for PMU Events Info"
    enable_key_rotation = true
    tags = {
        Name        = "PMU Events Info Key"
        Environment = "dev"
        Project     = "pmu-events-info"
    }
}
