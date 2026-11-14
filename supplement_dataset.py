"""Add bounded official S.H.Figuarts galleries for visual review."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.catalog import BY_ID
from collect_dataset import ROOT, contact_sheets, download, fetch


def main():
    manifest = ROOT / "data" / "manifest.json"
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    pages = {"gomora": ["https://tamashiiweb.com/item/11744/"], "baltan": ["https://tamashiiweb.com/item/11316/"], "zetton": ["https://tamashiiweb.com/item/15639/"], "eleking": ["https://tamashiiweb.com/item/14347/"], "redking": []}
    listing_url = "https://tamashiiweb.com/item_character/ultraman/"
    listing = BeautifulSoup(fetch(listing_url).text, "html.parser")
    for link in listing.select("a[href]"):
        if "レッドキング" in link.get_text(" ", strip=True) and "/item/" in link["href"]:
            pages["redking"] = [urljoin(listing_url, link["href"])]
            break
    candidates = []
    for key, sources in pages.items():
        for url in sources:
            soup = BeautifulSoup(fetch(url).text, "html.parser")
            title = soup.title.get_text(strip=True)
            if BY_ID[key]["jp"] not in title:
                print(f"Skip title mismatch: {url} {title}", flush=True)
                continue
            images = []
            for img in soup.select("img"):
                src = img.get("data-src") or img.get("src", "")
                product_id = url.rstrip("/").split("/")[-1]
                if re.search(r"/item_0*" + re.escape(product_id) + r"_", src) and src not in images:
                    images.append(src)
            print(f"{key}: {url} {len(images)} gallery images", flush=True)
            for src in images[:12]:
                candidates.append(dict(class_id=key, label=BY_ID[key]["name"], image_url=urljoin(url, src), source_url=url, source_title=title, source_group=url))
    existing = {r["pixel_sha256"] for r in rows}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(download, candidates):
            if row and row["pixel_sha256"] not in existing:
                existing.add(row["pixel_sha256"])
                row["sample_id"] = f"K{len(rows) + 1:03d}"
                rows.append(row)
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(rows)
    print(f"Total {len(rows)} candidates", flush=True)


if __name__ == "__main__":
    main()
