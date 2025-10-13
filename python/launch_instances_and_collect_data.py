import boto3
from pprint import pprint
import time
import logging
import base64


def main():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")
    # get all instance types. paginated.
    instance_types = []
    next_token = None
    while True:
        additional_kwargs = {}
        if next_token:
            additional_kwargs["NextToken"] = next_token
        response = ec2.describe_instance_types(**additional_kwargs)
        instance_types.extend(response["InstanceTypes"])
        next_token = response.get("NextToken")
        if not next_token:
            break
    instance_types.sort(key=lambda x: x["InstanceType"])
    instance_types = instance_types
    exceptions = []
    for instance_type in instance_types:
        ec2_instance_type = instance_type["InstanceType"]
        architecture = instance_type["ProcessorInfo"]["SupportedArchitectures"][0]
        if architecture == "arm64":
            image_id = "ami-01b2110eef525172b"
        elif architecture == "x86_64":
            image_id = "ami-0bbdd8c17ed981ef9"
        else:
            exceptions.append(f"Unsupported architecture: {architecture}")
            continue
        if s3.list_objects_v2(Bucket="suren-terraform", Prefix=f"pmu_data/{ec2_instance_type}")["KeyCount"] > 0:
            logging.info(f"Instance {ec2_instance_type} already exists")
            continue
        logging.info(f"Running instance {ec2_instance_type} with image {image_id}")
        try:
            response = ec2.run_instances(
                # aws ssm get-parameters --names \
                # /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id
                ImageId=image_id,
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/xvda",
                        "Ebs": {
                            "VolumeSize": 20,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    },
                ],
                InstanceType=ec2_instance_type,
                KeyName="pmu-events-info-key",
                SubnetId="subnet-004077e406f91a888",
                SecurityGroupIds=["sg-0d7ddef649615c1ce"],
                MinCount=1,
                MaxCount=1,
                IamInstanceProfile={"Name": "pmu-events-info-ec2-s3-profile"},
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [   
                            {
                                "Key": "Name",
                                "Value": "pmu-events-info-ec2-test",
                            },
                        ],
                    },
                ],
                UserData=base64.b64encode(open("user_data.sh", "rb").read()).decode("utf-8"),
                InstanceInitiatedShutdownBehavior="terminate",
            )
        except Exception as e:
            exceptions.append(e)
            print(e.response)
            logging.error(f"Error running instance {ec2_instance_type}: {e}")
            continue
        if "Instances" in response:
            response = response["Instances"]
        pprint(response)
        time.sleep(2)
    for exception in exceptions:
        logging.error(exception)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
