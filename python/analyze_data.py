import pathlib
import re
from dataclasses import dataclass, field
import enum

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
class Event:
    name: str
    type: EventType
    description: str | None = None


@dataclass
class EventSection:
    section_name: str
    description: str | None = None
    events: list[Event] = field(default_factory=list)

@dataclass
class InstanceTypeDataset:
    instance_type: str
    perf_list: list[EventSection]


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
        # print("=================================")
        # print(section)
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


def main():
    instance_type_to_dataset: dict[str, InstanceTypeDataset] = {}
    for path in pathlib.Path("dataset").glob("**/*.txt"):
        print(path)
        full_path = str(path.absolute()).split("/dataset/")[1]
        instance_type = full_path.split("/")[0]
        filename = full_path.split("/")[1]
        with open(path, "r") as f:
            data = f.read()
        if filename == "perf_list.txt":
            print(instance_type)
            event_sections: list[EventSection] = parse_perf_list(data)
            # print(event_sections)
            instance_type_to_dataset[instance_type] = InstanceTypeDataset(instance_type=instance_type, perf_list=event_sections)
        elif filename == "gcc_help.txt":
            parse_gcc_help(data)
        else:
            print(data)
            raise ValueError(f"Invalid filename: {filename}")
        # print(data[:100])
        # print(data)

if __name__ == "__main__":
    main()
