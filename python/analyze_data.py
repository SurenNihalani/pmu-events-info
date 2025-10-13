import pathlib
import re
from dataclasses import dataclass
import enum

event_pattern = re.compile(r'^(\S+(?:\s+\S+)*)\s+\[([^\]]+)\]$')

class EventType(enum.Enum):
    HARDWARE = "Hardware event"
    SOFTWARE = "Software event"

@dataclass
class Event:
    name: str
    type: EventType


class HeaderEvents:
    events: list[Event]


def parse_header_events(section):
    events = []
    return section.split("\n")[0]



def parse_perf_list(data):
    sections = data.split("\n\n")
    for section in sections:
        if section.startswith("  "):


        print("=================================")
        print(section)



def main():
    for path in pathlib.Path("dataset").glob("**/*.txt"):
        print(path)

        full_path = str(path.absolute()).split("/dataset/")[1]
        instance_type = full_path.split("/")[0]
        filename = full_path.split("/")[1]
        with open(path, "r") as f:
            data = f.read()
        if filename == "perf_list.txt":
            print(instance_type)
            parse_perf_list(data)
            break
        print(data[:100])
        break
        # print(data)

if __name__ == "__main__":
    main()
