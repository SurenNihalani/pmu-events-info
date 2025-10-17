import boto3
from pprint import pprint
import time
import logging
import base64
import concurrent.futures
import threading
import random
import traceback
from collections import OrderedDict

import re
from dataclasses import dataclass

INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS = OrderedDict()
INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS[('dl',)] = 192
INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS[('a', 'c', 'd', 'h', 'i', 'm', 'r', 't', 'z')] = 384
INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS[('g', 'g5', 'g4',)] = 64
INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS[('f',)] = 192
BANNED_INSTANCE_TYPES = ["f1.4xlarge", "f1.2xlarge", "f1.16xlarge", "f1.8xlarge", "f2.12xlarge", "f2.48xlarge", "f2.6xlarge"]
# BANNED_INSTANCE_TYPES = []

instance_id_to_budget_consumed = {}
locker_instance_type_prefixes_to_total_vcpus_budget = threading.Lock()
subnet_ids = [
    "subnet-004077e406f91a888",
    "subnet-00d0804a57ea1ab06",
    "subnet-0905b6b818ef04815",
    "subnet-08588fb7ec518fe1f",
    "subnet-0058acf1112279638",
    "subnet-02664a3434f505201",
]
# subnet_ids = [
#     "subnet-0a7c5108b4d7d6703",
#     "subnet-0a62d78eeb906cc6d",
#     "subnet-027d549f2b446b68d",
#     "subnet-0e5f9982266e10c94",
#     "subnet-02a36836727e603af",
#     "subnet-091d9e6b2975a1569",
# ]

def get_index_in_dict(instance_type):
    for prefixes, total_vcpus_budget in INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS.items():
        if InstanceType.from_instance_type(instance_type).series in prefixes:
            return prefixes
    return ("default",)


@dataclass
class InstanceType:
    series: str
    generation: int
    options: str
    instance_size: str


    @staticmethod
    def from_instance_type(instance_type):
        regex = re.compile(r"^(?P<series>[a-z]+)(?P<generation>\d+)(?P<options>[a-z0-9-]+)?\.(?P<instance_size>[a-z0-9-]+)?$")
        match = regex.match(instance_type)
        if not match:
            raise ValueError(f"Invalid instance type: {instance_type}")
        series = match.group("series")
        generation = int(match.group("generation"))
        options = match.group("options")
        instance_size = match.group("instance_size")
        return InstanceType(series=series, generation=generation, options=options, instance_size=instance_size)



def calculate_available_budget(index_in_dict):
    """
    Calculate available vCPU budget for a given instance type prefix.
    
    Args:
        index_in_dict: Tuple of prefixes (e.g., ('a', 'c', 'd', ...))
    
    Returns:
        Available vCPUs remaining for this prefix group
    """
    if index_in_dict is None:
        return 10000
    
    max_budget = INSTANCE_TYPE_PREFIXES_TO_MAX_VCPUS[index_in_dict]
    
    # Calculate currently consumed budget from active instances
    consumed = 0
    for (instance_id, instance_type), vcpus in instance_id_to_budget_consumed.items():
        if get_index_in_dict(instance_type) == index_in_dict:
            consumed += vcpus
    
    available = max_budget - consumed
    return available


def cleanup_terminated_instances(ec2, logging, stop_event):
    """
    Continuously check for terminated instances and free up their vCPU budget.
    Runs in a separate thread and sleeps every 2 seconds.

    Args:
        ec2: boto3 EC2 client
        logging: logger instance
        stop_event: threading.Event to signal when to stop
    """
    logging.info("Starting cleanup thread - will run every 2 seconds")

    while not stop_event.is_set():
        try:
            # Get all active instances (running, pending, initializing)
            response = ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running', 'pending', 'initializing', 'stopped', 'stopping', 'shutting-down']
                    }
                ]
            )

            # Extract active instance IDs (store as set of just IDs for comparison)
            active_instance_ids = set()
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    active_instance_ids.add(instance['InstanceId'])

            logging.info(f"Found {len(active_instance_ids)} active instances")
    
            # Find terminated instances (those in our tracking but not active)
            # instance_id_to_budget_consumed has (instance_id, instance_type) as keys
            terminated_instances = []
            for (instance_id, instance_type), vcpus in instance_id_to_budget_consumed.items():
                if instance_id not in active_instance_ids:
                    terminated_instances.append((instance_id, instance_type, vcpus))
            logging.info(f"Found {len(terminated_instances)} terminated instances")
            # Remove terminated instances from tracking (budget will be recalculated automatically)
            freed_budget = 0
            with locker_instance_type_prefixes_to_total_vcpus_budget:
                for instance_id, instance_type, vcpus in terminated_instances:
                    del instance_id_to_budget_consumed[(instance_id, instance_type)]
                    freed_budget += vcpus
                    logging.info(f"Freed {vcpus} vCPUs for terminated instance {instance_id}")

            if terminated_instances:
                logging.info(f"Cleaned up {len(terminated_instances)} terminated instances, freed {freed_budget} vCPUs")
            else:
                logging.info("No terminated instances to clean up")

        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            traceback.print_exc()

        # Sleep for 2 seconds before next cleanup cycle
        time.sleep(2)

    logging.info("Cleanup thread stopped")



def process_instance_type(instance_type, ec2, s3, logging, exceptions_list, not_found_list):
    """Process a single instance type in a separate thread"""
    total_cores = instance_type["VCpuInfo"]["DefaultVCpus"]
    ec2_instance_type = instance_type["InstanceType"]
    index_in_dict = get_index_in_dict(instance_type["InstanceType"])
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
                available_budget = calculate_available_budget(index_in_dict)
                logging.info(f"Available budget for {ec2_instance_type}: {available_budget} vCPUs (need {total_cores})")
                logging.info(f"Current consumption: {instance_id_to_budget_consumed}")
                if available_budget >= total_cores:
                    logging.info(f"Sufficient budget available, proceeding with instance launch")
                else:
                    time.sleep(1)
                    continue
                for subnet_id in subnet_ids:
                    logging.info(f"Launching instance {ec2_instance_type} in subnet {subnet_id}")
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
                            SubnetId=subnet_id,
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
                        instance_id_to_budget_consumed[(response["Instances"][0]["InstanceId"], ec2_instance_type)] = total_cores
                        return response
                    except Exception as e:
                        logging.error(f"Error launching instance {ec2_instance_type} in subnet {subnet_id}: {e}")
                        traceback.print_exc()
                        if "Unsupported" in e.args[0]:
                            continue
                        elif "your current vCPU limit of 0" in e.args[0]:
                            break
                        else:
                            break
                
    except Exception as e:
        print("==================================================")
        print(repr(e.args))
        
        print("==================================================")
        exceptions_list.append(e)
        not_found_list.append(ec2_instance_type)
        logging.error(f"Error running instance {ec2_instance_type}: {e}")
        return None

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

    # Start cleanup thread to run every 2 seconds
    stop_cleanup_event = threading.Event()
    cleanup_thread = threading.Thread(
        target=cleanup_terminated_instances,
        args=(ec2, logging, stop_cleanup_event),
        daemon=True
    )
    cleanup_thread.start()
    logging.info("Started cleanup thread")

 
    # Use ThreadPoolExecutor for parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=1023) as executor:
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

    # Stop the cleanup thread
    logging.info("Stopping cleanup thread...")
    stop_cleanup_event.set()
    cleanup_thread.join(timeout=5)  # Wait up to 5 seconds for cleanup thread to stop

    # Handle exceptions and not found instances
    for exception in exceptions:
        logging.error(exception)
    with open("not_found_instance_types.txt", "w") as f:
        for instance_type in not_found_instance_types:
            f.write(instance_type + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
