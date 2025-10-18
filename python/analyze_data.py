import pathlib
import re
from dataclasses import dataclass, field
import enum
import dataclasses
import json
from collections import Counter, defaultdict
import pprint
event_pattern = re.compile(r'^[ ]+([a-zA-Z0-9/=<>:,\[\]._ -]+)([ ]+(\[([a-zA-Z ]+)\])?)?$')
section_header_pattern = re.compile(r'^([A-Za-z0-9]+):\s*(.*)$')
gcc_help_option_pattern = re.compile(r'^  -m([a-zA-Z0-9-<,>=\.]+)[=]?\s+(.*)$')

class EventType(enum.Enum):
    HARDWARE = "Hardware event"
    SOFTWARE = "Software event"
    RAW_HARDWARE_EVENT_DESCRIPTOR = "Raw hardware event descriptor"
    HARDWARE_BREAKPOINT = "Hardware breakpoint"
    TRACEPOINT_EVENT = "Tracepoint event"
    KERNEL_PMU_EVENT = "Kernel PMU event"
    UNSPECIFIED = ""


@dataclass
class LscpuCache:
    name: str
    one_size: str
    all_size: str
    ways: str
    type: str
    level: str
    sets: str
    phy_line: str
    coherency_size: str | None = None
    

PRECISE_SUBSTRINGS = ["Precise event"]


@dataclass
class Event:
    name: str
    type: EventType
    description: str | None = None
    is_precise: bool = False

    def __post_init__(self):
        if self.description and any(substring in self.description.replace("\n", " ") for substring in PRECISE_SUBSTRINGS):
            self.is_precise = True


@dataclass
class EventSection:
    section_name: str
    description: str | None = None
    events: list[Event] = field(default_factory=list)

@dataclass
class InstanceTypeDataset:
    instance_type: str
    perf_list: list[EventSection]
    gcc_help: dict[str, str]
    lscpu: dict[str, str]
    lscpu_cache: list[LscpuCache]

def parse_header_events(lines):
    events = []
    for line in lines:
        try:
            if line.startswith("    "):
                last_event = events[-1]
                if last_event.description is None:
                    last_event.description = line.strip()
                else:
                    last_event.description += "\n" + line.strip()
                continue
            match = event_pattern.match(line)
            if match:
                event_type = match.group(4)
                if event_type == "" or event_type is None:
                    event_type = EventType.UNSPECIFIED
                else:
                    event_type = EventType(event_type.strip())
                events.append(Event(name=match.group(1), type=event_type))
            elif line == "":
                continue
            else:
                raise ValueError(f"Invalid event line: {line!r}")
        except Exception as e:
            print(f"Error parsing event line: {line!r}")
            print(e)
            raise e
    return events



def parse_perf_list(data):
    sections = data.split("\n\n")
    event_sections = []
    for section in sections:
        all_lines = section.split("\n")
        first_line = all_lines[0]
        if section.startswith("  "):
            events = parse_header_events(all_lines)
            event_sections.append(EventSection(section_name="unspecified", events=events))
        elif ":" in first_line:
            events = parse_header_events(all_lines[1:])
            match = section_header_pattern.match(first_line)
            if match:
                section_name = match.group(1)
                description = match.group(2)
            else:
                section_name = first_line.rstrip(":")
                description = None
            event_sections.append(EventSection(section_name=section_name, description=description, events=events))
        else:
            raise ValueError(f"Invalid section: {section}")
    return event_sections


def parse_gcc_help(data):
    sections = data.split("\n\n")
    option_to_value: dict[str, str] = {}
    for section in sections:
        section = section.removeprefix("The following options are target specific:").lstrip('\n')
        lines = section.split("\n")
        for line in lines:
            match = gcc_help_option_pattern.match(line)
            if match:
                option_to_value[match.group(1)] = match.group(2)
            else:
                raise ValueError(f"Invalid gcc help option line: {line!r}")
        break
    return option_to_value


lscpu_pattern = re.compile(r'^([A-Za-z0-9 ()-]+):\s+(.*)$')


def parse_lscpu(data):
    key_to_value: dict[str, str] = {}
    lines = data.split("\n")
    for line in lines:
        if not line.strip():
            continue
        match = lscpu_pattern.match(line)
        if match:
            key_to_value[match.group(1)] = match.group(2)
        else:
            raise ValueError(f"Invalid lscpu line: {line!r}")
    return key_to_value

def parse_lscpu_cache(data):
    lines = data.split("\n")
    first_line = lines[0].split()
    index_to_column_name = {i: name for i, name in enumerate(first_line)}
    dataset = []
    for line in lines[1:]:
        if not line.strip():
            continue
        data = line.split()
        data = {index_to_column_name[i].lower().replace("-", "_"): value for i, value in enumerate(data)}
        dataset.append(LscpuCache(**data))
    return dataset

def encode_value(x):
    if dataclasses.is_dataclass(x):
        return dataclasses.asdict(x)
    if isinstance(x, enum.Enum):
        return x.value
    raise ValueError(f"Invalid value: {x!r}")


def main():
    instance_type_to_dataset: dict[str, InstanceTypeDataset] = {}
    instance_type_to_gcc_help: dict[str, dict[str, str]] = {}
    instance_type_to_lscpu: dict[str, dict[str, str]] = {}
    instance_type_to_lscpu_cache: dict[str, list[LscpuCache]] = {}
    all_instance_types = set()  
    for path in pathlib.Path("dataset").glob("**/*.txt"):
        full_path = str(path.absolute()).split("/dataset/")[1]
        instance_type = full_path.split("/")[0]
        filename = full_path.split("/")[1]
        all_instance_types.add(instance_type)
        with open(path, "r") as f:
            data = f.read()
        if filename == "perf_list.txt":
            event_sections: list[EventSection] = parse_perf_list(data)
            # print(event_sections)
            instance_type_to_dataset[instance_type] = InstanceTypeDataset(instance_type=instance_type, perf_list=event_sections, gcc_help={}, lscpu={}, lscpu_cache=[])
        elif filename == "gcc_help.txt":
            instance_type_to_gcc_help[instance_type] = parse_gcc_help(data)
        elif filename == "lscpu.txt":
            instance_type_to_lscpu[instance_type] = parse_lscpu(data)
        elif filename == "lscpu_c.txt":
            instance_type_to_lscpu_cache[instance_type] = parse_lscpu_cache(data)
        else:
            raise ValueError(f"Invalid filename: {filename}")
        # print(data[:100])
        # print(data)
    bad_instance_types = []
    for instance_type in all_instance_types:
        if instance_type not in instance_type_to_dataset:
            print(f"Instance type {instance_type} not found")
            bad_instance_types.append(instance_type)
            continue
        if instance_type not in instance_type_to_gcc_help:
            print(f"Instance type {instance_type} not found")
            bad_instance_types.append(instance_type)
            continue
        if instance_type not in instance_type_to_lscpu:
            print(f"Instance type {instance_type} not found")
            bad_instance_types.append(instance_type)
            continue
        if instance_type not in instance_type_to_lscpu_cache:
            print(f"Instance type {instance_type} not found")
            bad_instance_types.append(instance_type)
            continue
        instance_type_to_dataset[instance_type] = InstanceTypeDataset(
            instance_type=instance_type, 
            perf_list=instance_type_to_dataset[instance_type].perf_list, 
            gcc_help=instance_type_to_gcc_help[instance_type], 
            lscpu=instance_type_to_lscpu[instance_type], 
            lscpu_cache=instance_type_to_lscpu_cache[instance_type]
        )
    instance_type_to_event_count = Counter()
    
    event_name_to_instance_type = defaultdict(set)
    instance_type_to_tma_events = defaultdict(set)
    for instance_type in instance_type_to_dataset:
        for event_section in instance_type_to_dataset[instance_type].perf_list:
            for event in event_section.events:
                instance_type_to_event_count[instance_type] += 1
                event_name_to_instance_type[event.name].add(instance_type)
                if event.name.startswith("tma"):
                    instance_type_to_tma_events[instance_type].add(event.name)
    how_many_to_print_instance_types = 0
    for i, (k, v) in enumerate(instance_type_to_event_count.most_common(10000)):
        if k.startswith("g"):
            how_many_to_print_instance_types = i + 1
            break
    pprint.pprint(instance_type_to_event_count.most_common(how_many_to_print_instance_types))
    event_name_to_instance_type_sorted = sorted(event_name_to_instance_type.items(), key=lambda x: len(x[1]), reverse=True)
    event_name_to_instance_type_sorted = [
        (k, v) for k, v in event_name_to_instance_type_sorted if k.startswith("tma")
    ]
    with open("event_name_to_instance_type_sorted.txt", "w") as f:
        f.write(pprint.pformat(event_name_to_instance_type_sorted) + "\n")
    instance_type_to_tma_event_count = Counter()
    with open("tma_events.txt", "w") as f:
        for instance_type, events in instance_type_to_tma_events.items():
            instance_type_to_tma_event_count[instance_type] += len(events)
            f.write(pprint.pformat((instance_type, len(events), events)) + "\n")
    with open("instance_type_dataset.json", "w") as f:
        json.dump(instance_type_to_dataset, f, default=encode_value, indent=2)
        
    pprint.pprint(instance_type_to_tma_event_count.most_common(200))
if __name__ == "__main__":
    main()
