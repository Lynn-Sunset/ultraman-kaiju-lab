"""Explicit visual decisions for expansion contact sheets 6–13, 2026-11-14."""
import hashlib
import json

from PIL import Image

from collect_dataset import ROOT, contact_sheets
from review_dataset import main as apply_review

ACCEPTED = {
    142,143,145,148,149,150,151,152,162,164,167,168,169,170,
    172,173,174,178,179,180,184,185,189,190,192,
    *range(193,208),209,211,212,213,214,215,217,218,219,220,221,222,223,
    229,230,231,232,234,235,236,237,239,240,241,242,
    *range(247,259),264,*range(265,270),271,*range(273,278),*range(281,296),
}
MULTIPLE = {144,147,153,157,161,216,260,270,272,278,279}
DUPLICATE = {154,163,181,191,210,233,259}
VARIANT = {155,156,158,159,160,165,166,171,175,176,182,183,186,187,224,225,227,228,243,244,245,246,261,262}
LOGO = {208,238}
PACKAGING = {146,177,188,226,263,280}


def main():
    path = ROOT / "data" / "manifest.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    previous = json.loads((ROOT / "data" / "review-decisions.json").read_text(encoding="utf-8"))
    snapshot_path = ROOT / "data" / "expansion-review-snapshot.json"
    snapshot = {r["sample_id"]: r["image_url"] for r in rows if 142 <= int(r["sample_id"][1:]) <= 295}
    if snapshot_path.exists() and json.loads(snapshot_path.read_text(encoding="utf-8")) != snapshot:
        raise ValueError("Snapshot changed. New images require new visual review.")
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        number = int(row["sample_id"][1:])
        if not 142 <= number <= 295:
            continue
        if number in ACCEPTED:
            status, note = "accepted", "Visually checked: one identifiable target monster, matching official reference; pose or facial detail suitable for this class."
        else:
            status = "rejected"
            if number in MULTIPLE:
                note = "Multiple different characters or product-comparison composition."
            elif number in DUPLICATE:
                note = "Near-duplicate/catalog copy of an accepted product pose."
            elif number in VARIANT:
                note = "Distinct derivative, fusion, mechanical, powered, armed or stylized toy variant outside the class definition."
            elif number in LOGO:
                note = "Name/logo graphic without the character."
            elif number in PACKAGING:
                note = "Card, accessory or long promotional collage instead of a usable character photo."
            else:
                raise ValueError(f"Missing explicit decision for {row['sample_id']}")
        previous[row["sample_id"]] = dict(status=status, note=note, image_url=row["image_url"])
    # Crop a reviewed bounding box around Ace-Killer, keeping its original source group.
    # This is a derived view of the same source, not an additional independent image.
    if not any(r.get("derived_from") == "K216" for r in rows):
        original = next(r for r in rows if r["sample_id"] == "K216")
        with Image.open(ROOT / original["path"]) as image:
            box = [60, 325, 525, image.height]
            crop = image.crop(box).convert("RGB")
            digest = hashlib.sha256(crop.tobytes() + str(crop.size).encode()).hexdigest()
            relative = f"data/images/acekiller/crop-{digest[:16]}.jpg"
            crop.save(ROOT / relative, quality=93)
        derived = dict(original, sample_id=f"K{len(rows)+1:03d}", path=relative, pixel_sha256=digest, width=crop.width, height=crop.height, derived_from="K216", bbox=box, review_status="pending")
        rows.append(derived)
    derived = next(r for r in rows if r.get("derived_from") == "K216")
    previous[derived["sample_id"]] = dict(status="accepted", note="Reviewed target bounding-box crop from K216; background character faces excluded. Shares the original source group to prevent split leakage.", image_url=derived["image_url"])
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data" / "review-decisions.json").write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_review()
    contact_sheets(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
