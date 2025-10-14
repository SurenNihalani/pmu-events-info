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
instance_id_to_budget_consumed = {}
locker_instance_type_prefixes_to_total_vcpus_budget = threading.Lock()


def get_index_in_dict(instance_type):
    for prefixes, total_vcpus_budget in INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET.items():
        if any(instance_type.startswith(prefix) for prefix in prefixes):
            return prefixes
    return None


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
                        'Values': ['running', 'pending', 'initializing']
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
            # Free up budget for terminated instances
            freed_budget = 0
            for instance_id, instance_type, vcpus in terminated_instances:
                # Remove from tracking
                
                # Add budget back to the pool
                # We need to determine which prefix this instance belonged to
                # Since we don't have the instance type here, we'll add to the general pool
                index_in_dict = get_index_in_dict(instance_type)
                with locker_instance_type_prefixes_to_total_vcpus_budget:
                    
                    INSTANCE_TYPE_PREFIXES_TO_TOTAL_VCPUS_BUDGET[index_in_dict] += vcpus
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
        instance_id_to_budget_consumed[(response["Instances"][0]["InstanceId"], ec2_instance_type)] = total_cores
        return response

    except Exception as e:
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
