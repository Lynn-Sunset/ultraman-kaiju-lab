"""Collect a bounded seed set from named official character/product pages.

All downloads are pending until a reviewer inspects the generated contact sheets.
No license for commercial use is inferred from public availability.
"""
import argparse
import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

from backend.catalog import MONSTERS

ROOT = Path(__file__).resolve().parent
INDEX = "https://toy.bandai.co.jp/ja/series/ultraman/sofubi/"
SEARCH = "https://toy.bandai.co.jp/ja/item/"
EXCLUDE = ["ハイパー", "EXゴモラ", "ＥＸ", "メカ", "サイバー", "スフィア", "スカル", "アーマー", "ベーシカル", "シン・", "サンダー", "ダーク", "バーニング", "EXレッド", "エックス", "ウルトラマンゼット", "融合"]


def fetch(url, **kwargs):
    response = requests.get(url, timeout=30, headers={"User-Agent": "KaijuLabResearch/1.0 (bounded educational prototype)"}, **kwargs)
    response.raise_for_status()
    return response


def discover(monster, index_html, max_products):
    candidates = []
    def add(image_url, page_url, title, group):
        if not image_url:
            return
        candidates.append(dict(class_id=monster["id"], label=monster["name"], image_url=urljoin(page_url, image_url), source_url=page_url, source_title=title, source_group=group))

    soup = BeautifulSoup(fetch(monster["source"]).text, "html.parser")
    for image in soup.select("img"):
        alt = image.get("alt", "").upper()
        if alt in {monster["en"], monster["id"].upper(), "ALIEN BALTAN", "ALIEN ZETTON"}:
            add(image.get("data-src") or image.get("src"), monster["source"], alt, monster["source"])
    for image in BeautifulSoup(index_html, "html.parser").select("img"):
        if image.get("alt") == monster["jp"]:
            src = image.get("src")
            # This shares its group with the corresponding product, not the index page.
            match = re.search(r"/(\d+)_", src or "")
            add(src, INDEX, monster["jp"], f"bandai:{match[1]}" if match else INDEX + monster["id"])
    listing = BeautifulSoup(fetch(SEARCH, params={"q": monster["jp"], "series": "ultraman"}).text, "html.parser")
    links = []
    for link in listing.select("a[href]"):
        title = link.get_text(" ", strip=True)
        if "/item/01_" in link["href"] and monster["jp"] in title and not any(word in title for word in EXCLUDE):
            url = urljoin(SEARCH, link["href"])
            if url not in links:
                links.append(url)
    for url in links[:max_products]:
        try:
            page = BeautifulSoup(fetch(url).text, "html.parser")
            title = page.title.get_text(strip=True) if page.title else monster["jp"]
            images = []
            for image in page.select("img"):
                src = image.get("src", "")
                if monster["jp"] in image.get("alt", "") and "bandai-a.akamaihd.net/bc/img/" in src and src not in images:
                    images.append(src)
            for src in images[:8]:
                match = re.search(r"/(\d+)_", src)
                add(src, url, title, f"bandai:{match[1]}" if match else url)
        except requests.RequestException as exc:
            print(f"Skip source {url}: {type(exc).__name__}", flush=True)
    return list({row["image_url"]: row for row in candidates}.values())


def download(row):
    try:
        response = fetch(row["image_url"], stream=True)
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 12 * 1024 * 1024:
                raise ValueError("image too large")
            chunks.append(chunk)
        with Image.open(io.BytesIO(b"".join(chunks))) as opened:
            if opened.width * opened.height > 20_000_000 or min(opened.size) < 160:
                raise ValueError("unsuitable dimensions")
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image).convert("RGB")
            image.thumbnail((1024, 1024))
            digest = hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest()
            filename = f"data/images/{row['class_id']}/{digest[:16]}.jpg"
            path = ROOT / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, quality=93)
            return dict(row, path=filename, pixel_sha256=digest, width=image.width, height=image.height, review_status="pending", rights="Copyright belongs to original owner; no training/redistribution license verified", collected_at=datetime.now(timezone.utc).isoformat())
    except (requests.RequestException, OSError, ValueError) as exc:
        print(f"Skip image {row['image_url']}: {type(exc).__name__}", flush=True)


def contact_sheets(rows):
    folder = ROOT / "data" / "contact-sheets"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for start in range(0, len(rows), 24):
        batch = rows[start:start + 24]
        canvas = Image.new("RGB", (1200, 4 * 220), "#ecece5")
        draw = ImageDraw.Draw(canvas)
        for index, row in enumerate(batch):
            x, y = index % 6 * 200, index // 6 * 220
            with Image.open(ROOT / row["path"]) as im:
                im.thumbnail((190, 180))
                canvas.paste(im, (x + (200 - im.width) // 2, y + 5))
            draw.text((x + 8, y + 186), f"{row['sample_id']} | {row['class_id']}", fill="black", font=font)
            draw.text((x + 8, y + 205), row["source_group"].split(":")[-1][-20:], fill="#555555", font=font)
        canvas.save(folder / f"sheet-{start // 24 + 1:02d}.jpg")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-products", type=int, default=5)
    parser.add_argument("--sheets-only", action="store_true")
    args = parser.parse_args()
    manifest = ROOT / "data" / "manifest.json"
    if args.sheets_only:
        contact_sheets(json.loads(manifest.read_text(encoding="utf-8")))
        return
    existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    index_html = fetch(INDEX).text
    candidates = []
    for monster in MONSTERS:
        try:
            found = discover(monster, index_html, args.max_products)
            candidates.extend(found)
            print(f"{monster['id']}: {len(found)} candidates", flush=True)
        except requests.RequestException as exc:
            print(f"Discovery failed for {monster['id']}: {exc}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloaded = list(pool.map(download, candidates))
    unique = {row["pixel_sha256"]: row for row in existing}
    for row in filter(None, downloaded):
        digest = row["pixel_sha256"]
        if digest in unique and unique[digest]["class_id"] != row["class_id"]:
            raise ValueError(f"Conflicting source labels for {row['image_url']}; existing annotations were preserved.")
        if digest not in unique:
            row["sample_id"] = f"K{len(unique) + 1:03d}"
        unique.setdefault(digest, row)
    rows = list(unique.values())
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(rows)
    print(f"Saved {len(rows)} unique images. All new samples pending visual review.", flush=True)


if __name__ == "__main__":
    main()
