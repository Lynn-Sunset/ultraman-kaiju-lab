"""Apply explicit visual-review decisions and export useful annotation artifacts."""
import csv
import json
import shutil
from pathlib import Path

from backend.catalog import MONSTERS

ROOT = Path(__file__).resolve().parent


def main():
    manifest = ROOT / "data" / "manifest.json"
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    decisions = json.loads((ROOT / "data" / "review-decisions.json").read_text(encoding="utf-8"))
    for row in rows:
        decision = decisions.get(row["sample_id"])
        if decision:
            if decision["image_url"] != row["image_url"]:
                raise ValueError(f"Review image mismatch: {row['sample_id']}")
            if decision["status"] not in {"accepted", "rejected"}:
                raise ValueError("Invalid review status")
            row.update(review_status=decision["status"], review_note=decision["note"], reviewed_by="Codex visual review", reviewed_at=decision.get("reviewed_at", "2026-11-14"))
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "data" / "labels.csv").open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["sample_id", "path", "class_id", "label", "review_status", "review_note", "source_group", "source_url", "image_url", "derived_from", "bbox", "rights"]
        writer = csv.DictWriter(file, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    portraits = ROOT / "web" / "portraits"
    portraits.mkdir(parents=True, exist_ok=True)
    for monster in MONSTERS:
        accepted = [r for r in rows if r["class_id"] == monster["id"] and r["review_status"] == "accepted"]
        # Prefer an isolated official soft-vinyl product photo for a readable archive.
        choice = next((r for r in accepted if r["source_group"].startswith("bandai:")), accepted[0] if accepted else None)
        if choice:
            shutil.copyfile(ROOT / choice["path"], portraits / f"{monster['id']}.jpg")
    print({m["id"]: sum(r["class_id"] == m["id"] and r["review_status"] == "accepted" for r in rows) for m in MONSTERS})
    print(f"Accepted {sum(r['review_status'] == 'accepted' for r in rows)} / {len(rows)}")


if __name__ == "__main__":
    main()
