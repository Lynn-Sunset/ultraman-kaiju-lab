"""Supplement the expanded snapshot with explicitly identified official galleries."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.catalog import BY_ID
from collect_dataset import INDEX, ROOT, contact_sheets, download, fetch
from expand_dataset import find_sources

PAGES = {
    "kingjoe": "https://tamashiiweb.com/item/16183/",
    "twintail": "https://tamashiiweb.com/item/12466/",
    "gudon": "https://tamashiiweb.com/item/12643/",
    "antlar": "https://tamashiiweb.com/item/16167/",
    "metron": "https://tamashiiweb.com/item/11652/",
    "golza": "https://tamashiiweb.com/store/tokyo/items/detail/15712.html",
    "dada": "https://www.bandaispirits.co.jp/products/search/detail.php?grp_id=5312&prd_id=12205",
}


def gallery(key, url):
    page = BeautifulSoup(fetch(url).content, "html.parser")
    title = page.title.get_text(strip=True)
    if BY_ID[key]["jp"] not in title:
        raise ValueError(f"Unexpected gallery: {title}")
    if "/store/" in url:
        product = next((a["href"] for a in page.select("a[href]") if re.search(r"/item/15712/", a["href"])), None)
        if product:
            url = urljoin(url, product)
            page = BeautifulSoup(fetch(url).content, "html.parser")
    product_id = "12205" if key == "dada" else re.search(r"(?:item/|detail/)(\d+)", url)[1]
    candidates = []
    for img in page.select("img"):
        src = img.get("data-src") or img.get("src", "")
        if not re.search(r"item_0*" + product_id + "_", src):
            continue
        candidates.append(dict(class_id=key, label=BY_ID[key]["name"], image_url=urljoin(url, src), source_url=url, source_title=title, source_group=f"tamashii:{product_id}"))
    found = list({r["image_url"]: r for r in candidates}.values())[:12]
    print(f"{key}: {len(found)} extra candidates", flush=True)
    return found


def main():
    manifest = ROOT / "data" / "manifest.json"
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        candidates = [r for found in pool.map(lambda item: gallery(*item), PAGES.items()) for r in found]
    # Bandai uses full-width Q plus a form suffix in the official catalog.
    _, extra = find_sources(("ganq", "眼Q", "GAN-Q", "ガンＱ（コードNo.01）"), {"GAN-Q": BY_ID["ganq"]["source"]}, fetch(INDEX).text)
    candidates.extend(extra)
    (ROOT / "data" / "expanded-gallery-candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    old_urls = {r["image_url"] for r in rows}
    known = {r["pixel_sha256"] for r in rows}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(download, [r for r in candidates if r["image_url"] not in old_urls]):
            if row and row["pixel_sha256"] not in known:
                known.add(row["pixel_sha256"])
                row["sample_id"] = f"K{len(rows) + 1:03d}"
                rows.append(row)
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(rows)
    print(f"Total {len(rows)} candidates.", flush=True)


if __name__ == "__main__":
    main()
