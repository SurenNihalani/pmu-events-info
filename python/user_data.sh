#!/bin/bash
set -x 
sudo bash -c "echo net.ipv6.conf.all.disable_ipv6 = 1 >> /etc/sysctl.conf"
sudo bash -c "echo net.ipv6.conf.default.disable_ipv6 = 1 >> /etc/sysctl.conf"
sudo bash -c "echo net.ipv6.conf.lo.disable_ipv6 = 1 >> /etc/sysctl.conf"
sudo sysctl -p
sudo apt-get update
sudo apt install unzip
if [ "$(uname -m)" == "x86_64" ]; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
fi
if [ "$(uname -m)" == "aarch64" ]; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
fi
instance_type=$(curl http://169.254.169.254/latest/meta-data/instance-type)
sudo bash -c "perf list > perf_list.txt"
sudo apt install -y gcc
sudo bash -c "gcc -march=native -Q --help=target" > gcc_help.txt
sudo lscpu > lscpu.txt
sudo lscpu -C > lscpu_c.txt
aws s3 cp perf_list.txt s3://suren-terraform/pmu_data/${instance_type}/perf_list.txt
aws s3 cp gcc_help.txt s3://suren-terraform/pmu_data/${instance_type}/gcc_help.txt
aws s3 cp lscpu.txt s3://suren-terraform/pmu_data/${instance_type}/lscpu.txt
aws s3 cp lscpu_c.txt s3://suren-terraform/pmu_data/${instance_type}/lscpu_c.txt
sudo shutdown now
