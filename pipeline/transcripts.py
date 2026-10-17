"""Load the call transcripts and their index."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Call:
    call_id: str
    timestamp: str
    staff: str
    seconds: int
    customer_lines: list[str]
    agent_lines: list[str]


def load_transcripts(folder: Path, index_csv: Path) -> list[Call]:
    index = {row["call_id"]: row for row in csv.DictReader(index_csv.open())}
    calls = []
    for path in sorted(folder.glob("CALL-*.txt")):
        customer, agent = [], []
        for line in path.read_text().splitlines():
            if line.startswith("Customer:"):
                customer.append(line[len("Customer:"):].strip())
            elif line.startswith("Agent:"):
                agent.append(line[len("Agent:"):].strip())
        meta = index[path.stem]
        calls.append(Call(path.stem, meta["timestamp"], meta["agent"], int(meta["duration_sec"]), customer, agent))
    return calls
