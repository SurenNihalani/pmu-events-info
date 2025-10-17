import pytest
from launch_instances_and_collect_data import InstanceType



def test_instance_type():
    instance_type = "g4ad.16xlarge"
    instance_type_obj = InstanceType.from_instance_type(instance_type)
    assert instance_type_obj.series == "g"
    assert instance_type_obj.generation == 4
    assert instance_type_obj.options == "ad"
    assert instance_type_obj.instance_size == "16xlarge"

    instance_type = "r8i-flex.16xlarge"
    instance_type_obj = InstanceType.from_instance_type(instance_type)
    assert instance_type_obj.series == "r"
    assert instance_type_obj.generation == 8
    assert instance_type_obj.options == "i-flex"
    assert instance_type_obj.instance_size == "16xlarge"

    instance_type = "u-3tb1.56xlarge"
    instance_type_obj = InstanceType.from_instance_type(instance_type)
    assert instance_type_obj.series == "u"
    assert instance_type_obj.generation == 0
    assert instance_type_obj.options == "-3tb1"
    assert instance_type_obj.instance_size == "56xlarge"


if __name__ == "__main__":
    pytest.main()
