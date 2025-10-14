import boto3
from pprint import pprint
import time
import logging
import base64
import concurrent.futures
import threading
import random
import traceback


INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET = {
    ('a', 'c', 'd', 'h', 'i', 'm', 'r', 't', 'z'): 384,
}
locker_instance_type_prefixes_to_total_vcpus_budget = threading.Lock()


def get_index_in_dict(instance_type):
    for prefixes, total_vcpus_budget in INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET.items():
        if any(instance_type.startswith(prefix) for prefix in prefixes):
            return prefixes
    return None



def process_instance_type(instance_type, ec2, s3, logging, exceptions_list, not_found_list):
    """Process a single instance type in a separate thread"""
    total_cores = instance_type["VCpuInfo"]["DefaultVCpus"]
    ec2_instance_type = instance_type["InstanceType"]
    index_in_dict = get_index_in_dict(instance_type["InstanceType"])
    to_add = 0
    try:
        architecture = instance_type["ProcessorInfo"]["SupportedArchitectures"][0]
        if architecture == "arm64":
            image_id = "ami-01b2110eef525172b"
        elif architecture == "x86_64":
            image_id = "ami-0bbdd8c17ed981ef9"
        else:
            exceptions_list.append(f"Unsupported architecture: {architecture}")
            return None

        if s3.list_objects_v2(Bucket="suren-terraform", Prefix=f"pmu_data/{ec2_instance_type}")["KeyCount"] > 0:
            logging.info(f"Instance {ec2_instance_type} already exists")
            return None

        logging.info(f"Running instance {ec2_instance_type} with image {image_id}")
        while index_in_dict is not None:
            logging.info(f"Waiting for {ec2_instance_type} to be available")
            with locker_instance_type_prefixes_to_total_vcpus_budget:
                total_vcpus_budget = INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET[index_in_dict]
                if total_vcpus_budget >= total_cores:
                    INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET[index_in_dict] -= total_cores
                    to_add = total_cores
                    break
            time.sleep(random.randint(1, 10))
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
        return response

    except Exception as e:
        exceptions_list.append(e)
        not_found_list.append(ec2_instance_type)
        logging.error(f"Error running instance {ec2_instance_type}: {e}")
        return None
    finally:
        with locker_instance_type_prefixes_to_total_vcpus_budget:
            INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET[index_in_dict] += to_add


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

    # Thread-safe collections for results
    exceptions = []
    not_found_instance_types = []

    # Use ThreadPoolExecutor for parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all tasks
        future_to_instance = {
            executor.submit(process_instance_type, instance_type, ec2, s3, logging, exceptions, not_found_instance_types): instance_type
            for instance_type in instance_types
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_instance):
            instance_type = future_to_instance[future]
            try:
                response = future.result()
                if response and "Instances" in response:
                    pprint(response["Instances"])
                time.sleep(2)  # Rate limiting between instances
            except Exception as exc:
                traceback.print_exc()
                logging.error(f'{instance_type} generated an exception: {exc}')

    # Handle exceptions and not found instances
    for exception in exceptions:
        logging.error(exception)
    with open("not_found_instance_types.txt", "w") as f:
        for instance_type in not_found_instance_types:
            f.write(instance_type + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
