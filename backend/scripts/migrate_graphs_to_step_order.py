"""One-off: migrate baseline graph JSONs to new format (step_order, no lanes, no format_version, no process_id, no short_id/lane_id on steps)."""
import json
from pathlib import Path

# Default: pharmacy template graphs; override for other template dirs
GRAPHS_DIR = Path(__file__).resolve().parent.parent / "data" / "pharmacy" / "graphs"


def migrate(data: dict) -> dict:
    step_order = []
    for lane in data.get("lanes") or []:
        step_order.extend(lane.get("node_refs") or [])
    out = {k: v for k, v in data.items() if k not in ("format_version", "process_id", "lanes")}
    out["step_order"] = step_order
    steps = []
    for s in out.get("steps") or []:
        step = {k: v for k, v in s.items() if k not in ("short_id", "lane_id")}
        steps.append(step)
    out["steps"] = steps
    return out


def main():
    for path in sorted(GRAPHS_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        migrated = migrate(data)
        path.write_text(json.dumps(migrated, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Migrated {path.name}")


if __name__ == "__main__":
    main()
