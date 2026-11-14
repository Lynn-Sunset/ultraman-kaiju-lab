"""Reproduce the explicit contact-sheet review performed on 2026-11-14.

These decisions apply ONLY to the stored snapshot with these image URLs.
Future images require another visual review; labels are not inferred from names.
"""
import json
import hashlib

from collect_dataset import ROOT
from review_dataset import main as apply_review


def main():
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    snapshot = hashlib.sha256(json.dumps([(r["sample_id"], r["image_url"]) for r in manifest]).encode()).hexdigest()
    if snapshot != "95bcf683a3dff790d71a1ee9e8af23a68d1adbd412cb79d3c300357e4a034e88":
        raise ValueError("Dataset changed: these visual decisions cannot be applied to a different snapshot.")
    accepted = {1, 8, 9, 17, 18, 19, 20, 31, 32, 46, 47, 50, 51, 52, 53, 54, 57, 58, 59, 68, 69, 70, 73, 74, 87, 88, 95, *range(96, 102), 104, *range(108, 112), *range(118, 123), *range(130, 135), 136}
    multiple = {10, 55, 71, 89, 102, 103, 113, 123, 135}
    near_duplicates = {11, 49, 56, 72, 90}
    unrelated = {105, 106, 107, 114, 115, 116, 117, 124, 125, 126, 127, 128, 129, 137, 138, 139, 140, 141}
    decisions = {}
    for row in manifest:
        index = int(row["sample_id"][1:])
        if index in accepted:
            status, note = "accepted", "Visually reviewed: one identifiable target character; consistent with official character reference."
        else:
            status = "rejected"
            if index in multiple:
                note = "Multiple characters or comparison composition; unsuitable for single-label classification."
            elif index in near_duplicates:
                note = "Near-duplicate of an accepted pose with added promotional text."
            elif index in unrelated:
                note = "Related-product recommendation: wrong character or accessories; page-level label is incorrect."
            elif index == 30:
                note = "Character name/logo only; no monster visible."
            elif index == 80:
                note = "Pedanium Zetton fusion variant, outside the original Zetton class definition."
            else:
                note = "Packaging/card graphic, vehicle, egg or transforming toy; unsuitable visual domain for this seed classifier."
        decisions[row["sample_id"]] = dict(status=status, note=note, image_url=row["image_url"])
    (ROOT / "data" / "review-decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_review()


if __name__ == "__main__":
    main()
