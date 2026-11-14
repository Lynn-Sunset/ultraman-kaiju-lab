"""Export class coverage and measured recall alongside reviewed annotations."""
import csv
import json
from pathlib import Path

import torch

from backend.catalog import MONSTERS

ROOT = Path(__file__).resolve().parent


def main():
    rows = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    checkpoint = torch.load(ROOT / "models" / "monster.pt", map_location="cpu", weights_only=True)
    metrics = checkpoint["metrics"]
    stats = []
    for monster in MONSTERS:
        accepted = [r for r in rows if r["class_id"] == monster["id"] and r["review_status"] == "accepted"]
        stats.append(dict(class_id=monster["id"], name=monster["name"], accepted=len(accepted), independent_groups=len({r["source_group"] for r in accepted}), **metrics["per_class"][monster["id"]]))
    with (ROOT / "data" / "class-summary.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(stats[0]))
        writer.writeheader()
        writer.writerows(stats)
    summary = dict(downloaded=sum(not r.get("derived_from") for r in rows), annotation_records=len(rows), accepted=sum(r["review_status"] == "accepted" for r in rows), pending=sum(r["review_status"] == "pending" for r in rows), classes=stats, metrics=metrics)
    (ROOT / "data" / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"classes", "metrics"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
