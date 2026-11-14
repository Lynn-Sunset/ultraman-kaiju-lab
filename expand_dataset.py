"""Append new official-source classes without renumbering reviewed samples."""
import argparse
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collect_dataset import INDEX, ROOT, SEARCH, contact_sheets, download, fetch

TARGETS = [
    ("pigmon", "皮古蒙", "PIGMON", "ピグモン"),
    ("kingjoe", "金古桥", "KING JOE", "キングジョー"),
    ("dada", "达达", "DADA", "ダダ"),
    ("neronga", "内隆嘎", "NERONGA", "ネロンガ"),
    ("bemular", "百慕拉", "BEMULAR", "ベムラー"),
    ("gubila", "古维拉", "GUBILA", "グビラ"),
    ("antlar", "安东拉", "ANTLAR", "アントラー"),
    ("jamila", "贾米拉", "JAMILA", "ジャミラ"),
    ("gudon", "古敦", "GUDON", "グドン"),
    ("twintail", "双尾怪", "TWINTAIL", "ツインテール"),
    ("bemstar", "贝蒙斯坦", "BEMSTAR", "ベムスター"),
    ("blackking", "布莱克王", "BLACK KING", "ブラックキング"),
    ("birdon", "巴顿", "BIRDON", "バードン"),
    ("tyrant", "泰兰特", "TYRANT", "タイラント"),
    ("acekiller", "艾斯杀手", "ACE-KILLER", "エースキラー"),
    ("vakishim", "巴克西姆", "VAKISHIM", "バキシム"),
    ("golza", "哥尔赞", "GOLZA", "ゴルザ"),
    ("melba", "美尔巴", "MELBA", "メルバ"),
    ("gazort", "加佐特", "GAZORT", "ガゾート"),
    ("silvergon", "希尔巴贡", "SILVERGON", "シルバゴン"),
    ("ganq", "眼Q", "GAN-Q", "ガンQ"),
    ("galactron", "加拉特隆", "GALACTRON", "ギャラクトロン"),
    ("fiveking", "五帝王", "FIVE KING (SDU)", "ファイブキング"),
    ("metron", "梅特龙星人", "ALIEN METRON", "メトロン星人"),
]
BAD_PRODUCTS = ["カード", "エッグ", "ビークル", "セット", "アーマー", "シン・", "スフィア", "サイバー", "クリスタル", "カプセル", "メダル", "指人形"]


def find_sources(target, links, index_html):
    key, name, english, japanese = target
    source = links[english]
    page = BeautifulSoup(fetch(source).text, "html.parser")
    # Keep source evidence for the translated ability descriptions.
    text = page.get_text(" ", strip=True)
    start = text.find(english)
    end = text.find("Related News", start)
    evidence = text[start:end if end > start else start + 6500]
    metadata = dict(id=key, name=name, en=english, jp=japanese, source=source, source_excerpt=" ".join(evidence.split()[:120]))
    candidates = []

    def add(src, url, title, group):
        if src and not src.startswith("data:"):
            candidates.append(dict(class_id=key, label=name, image_url=urljoin(url, src), source_url=url, source_title=title, source_group=group))

    for img in page.select("img"):
        alt = img.get("alt", "").upper()
        src = img.get("data-src") or img.get("src", "")
        if "/wp-content/uploads/" in src and english.replace(" (SDU)", "") in alt:
            add(src, source, english, source)
    for img in BeautifulSoup(index_html, "html.parser").select("img"):
        if img.get("alt") == japanese:
            src = img.get("src", "")
            match = re.search(r"/(\d+)_", src)
            add(src, INDEX, japanese, "bandai:" + match[1] if match else INDEX + key)
    listing = BeautifulSoup(fetch(SEARCH, params={"q": japanese, "series": "ultraman"}).text, "html.parser")
    products = []
    for a in listing.select("a[href]"):
        title = a.get_text(" ", strip=True)
        if "/item/01_" in a["href"] and japanese in title and not any(word in title for word in BAD_PRODUCTS):
            url = urljoin(SEARCH, a["href"])
            if url not in products:
                products.append(url)
    for url in products[:3]:
        try:
            soup = BeautifulSoup(fetch(url).text, "html.parser")
            title = soup.title.get_text(strip=True)
            seen = set()
            for img in soup.select("img"):
                src = img.get("src", "")
                if src in seen or japanese not in img.get("alt", "") or "bandai-a.akamaihd.net/bc/img/" not in src:
                    continue
                seen.add(src)
                if len(seen) > 6:
                    break
                match = re.search(r"/(\d+)_", src)
                add(src, url, title, "bandai:" + match[1] if match else url)
        except requests.RequestException as exc:
            print(f"Skip {url}: {type(exc).__name__}", flush=True)
    return metadata, list({r["image_url"]: r for r in candidates}.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()
    manifest = ROOT / "data" / "manifest.json"
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    encyclopedia = "https://tsuburaya-prod.com/encyclopedialist"
    soup = BeautifulSoup(fetch(encyclopedia).text, "html.parser")
    links = {a.get_text(" ", strip=True).upper(): urljoin(encyclopedia, a["href"]) for a in soup.select("a[href]") if "/encyclopedia/" in a["href"]}
    index_html = fetch(INDEX).text
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(find_sources, target, links, index_html) for target in TARGETS]
        for target, future in zip(TARGETS, futures):
            metadata, candidates = future.result()
            results.append((metadata, candidates))
            print(f"{target[0]}: {len(candidates)} candidates", flush=True)
    (ROOT / "data" / "expanded-sources.json").write_text(json.dumps([m for m, _ in results], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.discover_only:
        return
    candidates = [r for _, found in results for r in found]
    old_urls = {r["image_url"] for r in rows}
    known = {r["pixel_sha256"] for r in rows}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(download, [r for r in candidates if r["image_url"] not in old_urls]):
            if not row or row["pixel_sha256"] in known:
                continue
            known.add(row["pixel_sha256"])
            row["sample_id"] = f"K{len(rows) + 1:03d}"
            rows.append(row)
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(rows)
    print(f"Total {len(rows)} candidate images; new samples pending review.", flush=True)


if __name__ == "__main__":
    main()
