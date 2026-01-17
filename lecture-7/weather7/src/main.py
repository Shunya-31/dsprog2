from __future__ import annotations

import csv
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://surfsnow.jp"
START_URL = "https://surfsnow.jp/search/list/spl_area01.php"

OUT_DIR = "output"
CSV_PATH = os.path.join(OUT_DIR, "ski_resorts.csv")
PLOT_DIR = os.path.join(OUT_DIR, "plots")

SLEEP_SEC = 1.5
TIMEOUT_SEC = 20
MAX_PAGES = 15
MAX_RESORTS = 150



HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://surfsnow.jp/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}



@dataclass
class Resort:
    name: str
    prefecture: Optional[str]
    url: str
    kencd: Optional[int]
    beginner_pct: Optional[int]
    intermediate_pct: Optional[int]
    advanced_pct: Optional[int]
    fetched_at: str



def ensure_dirs() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(PLOT_DIR, exist_ok=True)


def fetch_html(url: str, session: requests.Session) -> str:
    resp = session.get(url, headers=HEADERS, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text


def normalize_url(href: str) -> Optional[str]:
    if not href:
        return None
    full = urljoin(BASE_URL, href)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
        return None
    return full


def looks_like_resort_url(url: str) -> bool:
    return any(key in url for key in ("/ski/", "/snow/", "/search/", "/guide/", "gelski", "gelande")) or True


def extract_resort_links_from_list(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        full = normalize_url(href)
        if not full:
            continue

        if looks_like_resort_url(full):
            links.add(full)
    bad = ("/admin/", "/sp/my/", "/review/my/", "/mailmaga/", "/snolog/")
    filtered = [u for u in links if not any(b in u for b in bad)]
    filtered.sort(key=lambda x: ("/search/list/" in x, len(x)))
    return filtered


def extract_prefecture_from_title(text: str) -> Optional[str]:
    m = re.search(r"【\s*([^】]+?)\s*】", text)
    if m:
        return m.group(1).strip()

    m2 = re.search(r"\[\s*([^\]]+?)\s*\]", text)
    if m2:
        return m2.group(1).strip()

    return None


def extract_difficulty_pcts(text: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    def find(label: str) -> Optional[int]:
        m = re.search(rf"{label}\s*[:：]?\s*([0-9]{{1,3}})\s*%", text)
        if not m:
            return None
        try:
            v = int(m.group(1))
            if 0 <= v <= 100:
                return v
        except ValueError:
            return None
        return None

    beginner = find("初級")
    intermediate = find("中級")
    advanced = find("上級")

    return beginner, intermediate, advanced


def parse_resort_page(url: str, html: str, kencd: Optional[int]) -> Resort:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        title = soup.title.get_text(strip=True) if soup.title else ""
        name = title.split("|")[0].strip() if title else "Unknown"

    title_text = ""
    if soup.title:
        title_text = soup.title.get_text(" ", strip=True)
    prefecture = extract_prefecture_from_title(name) or extract_prefecture_from_title(title_text)

    body_text = soup.get_text(" ", strip=True)
    b, m, a = extract_difficulty_pcts(body_text)

    return Resort(
    name=name,
    prefecture=prefecture,
    url=url,
    kencd=kencd,
    beginner_pct=b,
    intermediate_pct=m,
    advanced_pct=a,
    fetched_at=datetime.now().isoformat(timespec="seconds"),
)



def is_valid_resort(resort: Resort) -> bool:
    if resort.beginner_pct is None or resort.intermediate_pct is None or resort.advanced_pct is None:
        return False
    s = resort.beginner_pct + resort.intermediate_pct + resort.advanced_pct
    return 95 <= s <= 105


def crawl() -> List[Resort]:
    ensure_dirs()
    session = requests.Session()
    try:
        session.get("https://surfsnow.jp/", headers=HEADERS, timeout=TIMEOUT_SEC)
        time.sleep(SLEEP_SEC)
    except requests.RequestException:
        pass
    print("[1/3] Collecting resort links from list pages...")
    resort_urls: List[tuple[str, int]] = []
    seen: Set[str] = set()

    list_urls: List[Tuple[str, int]] = []

    for kencd in range(1, 48):
        list_urls.append((f"{START_URL}?kencd={kencd}", kencd))



    for i, (list_url, kencd) in enumerate(list_urls[:MAX_PAGES], start=1):
        try:
            print(f"  - Fetch list page ({i}/{min(MAX_PAGES, len(list_urls))}): {list_url}")
            html = fetch_html(list_url, session)
            links = extract_resort_links_from_list(html)
            for u in links:
                if u not in seen:
                    seen.add(u)
                    resort_urls.append((u, kencd))

            time.sleep(SLEEP_SEC)
        except requests.RequestException as e:
            print(f"    ! Failed to fetch list page: {e}")

        if len(resort_urls) >= MAX_RESORTS * 2:
            break

    print(f"  Collected {len(resort_urls)} candidate URLs")

    print("[2/3] Crawling resort pages and extracting difficulty percentages...")
    resorts: List[Resort] = []

    for idx, (url, kencd) in enumerate(resort_urls, start=1):
        if len(resorts) >= MAX_RESORTS:
            break

        try:
            print(f"  - ({idx}/{len(resort_urls)}) {url}")
            html = fetch_html(url, session)
            resort = parse_resort_page(url, html, kencd)

            if is_valid_resort(resort):
                resorts.append(resort)
                print(f"    OK: {resort.name} | 初級{resort.beginner_pct}% 中級{resort.intermediate_pct}% 上級{resort.advanced_pct}%")
            else:
                pass

            time.sleep(SLEEP_SEC)

        except requests.RequestException as e:
            print(f"    ! Failed: {e}")

    print(f"  Extracted {len(resorts)} resorts with valid difficulty data")
    return resorts


def save_csv(resorts: List[Resort], path: str) -> None:
    ensure_dirs()
    fields = ["name", "prefecture", "url", "kencd",
          "beginner_pct", "intermediate_pct", "advanced_pct", "fetched_at"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in resorts:
            w.writerow(asdict(r))
    print(f"[3/3] Saved CSV -> {path}")


def make_plots(resorts: List[Resort]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Skip plotting.")
        return

    ensure_dirs()

    beginner = [r.beginner_pct for r in resorts if r.beginner_pct is not None]
    if not beginner:
        print("No data for plotting.")
        return

    plt.figure()
    plt.hist(beginner, bins=10)
    plt.title("Distribution of Beginner Course Percentage")
    plt.xlabel("Beginner %")
    plt.ylabel("Count")
    hist_path = os.path.join(PLOT_DIR, "beginner_hist.png")
    plt.savefig(hist_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot -> {hist_path}")

    sorted_resorts = sorted(
        [r for r in resorts if r.beginner_pct is not None],
        key=lambda x: x.beginner_pct,
        reverse=True
    )[:10]

    plt.figure()
    plt.bar([r.name for r in sorted_resorts], [r.beginner_pct for r in sorted_resorts])
    plt.title("Top 10 Resorts by Beginner %")
    plt.xlabel("Resort")
    plt.ylabel("Beginner %")
    plt.xticks(rotation=60, ha="right")
    top10_path = os.path.join(PLOT_DIR, "beginner_top10.png")
    plt.savefig(top10_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot -> {top10_path}")


def main() -> None:
    resorts = crawl()
    save_csv(resorts, CSV_PATH)
    make_plots(resorts)
    if resorts:
        b = [r.beginner_pct for r in resorts if r.beginner_pct is not None]
        avg = sum(b) / len(b) if b else 0.0
        print(f"\nSummary:")
        print(f"- Resorts: {len(resorts)}")
        print(f"- Avg beginner %: {avg:.2f}")


if __name__ == "__main__":
    main()
