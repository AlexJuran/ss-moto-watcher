from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


SEARCH_URL = "https://www.ss.com/lv/transport/moto-transport/motorcycles/search-result/"


HEADERS = {
    # Нормальный User-Agent помогает не выглядеть как “сломанный бот”
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "lv,ru;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class Listing:
    url: str
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    cc: Optional[int]
    price_eur: Optional[int]
    location: Optional[str]
    date_text: Optional[str]  # на SS дата выводится строкой
    title: Optional[str]


def fetch_html(url: str) -> str:
    """Скачивает HTML. Отдельная функция — чтобы код был читаемым и тестируемым."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_ad_urls(search_html: str, limit: int = 30) -> list[str]:
    """
    На странице результатов ищем ссылки вида /msg/...html.
    Это самый простой и достаточно устойчивый способ.
    """
    soup = BeautifulSoup(search_html, "lxml")
    urls: list[str] = []

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("/msg/") and href.endswith(".html"):
            full = "https://www.ss.com" + href
            urls.append(full)

    # Убираем дубликаты, сохраняя порядок
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)

    return uniq[:limit]

from urllib.parse import urljoin

def extract_ad_urls_paged(search_url: str, limit: int = 50, max_pages: int = 20) -> list[str]:
    """
    Собирает ссылки на объявления с нескольких страниц поиска SS.com.
    limit — сколько всего ссылок нужно.
    max_pages — ограничение по страницам (защита от бесконечного цикла).
    """
    urls: list[str] = []
    page = 1

    print(f"[PAGED_INIT] limit={limit} max_pages={max_pages}")

    while len(urls) < limit and page <= max_pages:
        if page == 1:
            page_url = search_url
        else:
            page_url = search_url.rstrip("/") + f"/page{page}.html"

        print(f"[PAGE] {page_url}")

        html = fetch_html(page_url)
        if not html:
            break

        page_urls = extract_ad_urls(html, limit=10_000)

        print(f"[PAGE_URLS] page={page} got={len(page_urls)} total_before={len(urls)}")

        # добавляем только новые ссылки
        for u in page_urls:
            if u not in urls:
                urls.append(u)

        print(f"[TOTAL_URLS] total_after={len(urls)}")

        time.sleep(0.0)

        page += 1

    return urls[:limit]


def _parse_int(s: str) -> Optional[int]:
    s = s.strip()
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else None


def parse_listing(ad_html: str, url: str) -> Listing:
    """
    На странице объявления SS.com поля идут в виде меток:
    'Marka:', 'Modelis:', 'Izlaiduma gads:', 'Motora tilpums, cm3:', 'Cena:' и т.д.
    Простейшая стратегия: найти текст всей страницы и вытащить значения regex-ом.
    """
    soup = BeautifulSoup(ad_html, "lxml")

    # Заголовок объявления (верхняя строка)
    title = soup.find("h2")
    title_text = title.get_text(" ", strip=True) if title else None

    text = soup.get_text("\n", strip=True)

    def find_after(label: str) -> Optional[str]:
        # Ищем строку "label:   value"
        m = re.search(rf"{re.escape(label)}\s*(.+)", text)
        return m.group(1).strip() if m else None

    brand = find_after("Marka:")
    model = find_after("Modelis:")
    year = _parse_int(find_after("Izlaiduma gads:") or "")
    cc = _parse_int(find_after("Motora tilpums, cm3:") or "")
    price_eur = _parse_int(find_after("Cena:") or "")
    location = find_after("Vieta:")

    # Дата на странице обычно как "Datums: 24.01.2026 17:33"
    date_text = None
    mdate = re.search(r"Datums:\s*([0-9.\s:]+)", text)
    if mdate:
        date_text = mdate.group(1).strip()

    return Listing(
        url=url,
        brand=brand,
        model=model,
        year=year,
        cc=cc,
        price_eur=price_eur,
        location=location,
        date_text=date_text,
        title=title_text,
    )


def matches_filters(item: Listing, *, max_price: int | None = None,
                    brand_contains: str | None = None,
                    cc_min: int | None = None, cc_max: int | None = None) -> bool:
    """Твои условия поиска. Начнём с простых."""
    if max_price is not None and item.price_eur is not None:
        if item.price_eur > max_price:
            return False

    if brand_contains:
        b = (item.brand or "").lower()
        if brand_contains.lower() not in b:
            return False

    if cc_min is not None and item.cc is not None and item.cc < cc_min:
        return False
    if cc_max is not None and item.cc is not None and item.cc > cc_max:
        return False

    return True

def normalize(text: str) -> str:
    return (
        text.lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

import re

def tokenize(text: str) -> list[str]:
    """
    Превращает строку в список токенов:
    'YZF-R6' -> ['yzf', 'r6']
    'XR 650L' -> ['xr', '650l']
    'XSR700' -> ['xsr700']
    """
    parts = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return [p for p in parts if p]

def main() -> None:
    search_html = fetch_html(SEARCH_URL)
    ad_urls = extract_ad_urls(search_html, limit=35)

    print(f"Нашёл ссылок: {len(ad_urls)}")
    print("Проверяю объявления...\n")

    brands = ["Kawasaki", "Honda", "BMW", "Suzuki", "Yamaha", "Triumph"]
    matches = []

    for i, url in enumerate(ad_urls, 1):
        ad_html = fetch_html(url)
        item = parse_listing(ad_html, url)

        print(f"[SEEN ] {item.brand} {item.model} | cc={item.cc} | price={item.price_eur} | {item.url}")

        brand_ok = any(
            matches_filters(item, max_price=6000, brand_contains=b, cc_min=350, cc_max=750)
            for b in brands
        )

        hay = f"{item.model or ''} {item.title or ''}"
        tokens = tokenize(hay)

        query_models = ["KL", "sl", "DL", "xf", "fre", "freewind", "V-Strom", "strom", "Transalp",
                        "xl", "xr", "xt", "tenere", "wr", "tt",
                        "dominator", "nx", "crf", "DR", "DRZ", "gs", "tiger"] # вводишь как в поиске SS
        haystack = normalize(f"{item.model or ''} {item.title or ''}")
        model_ok = any(normalize(q) in haystack for q in query_models)

        ok = brand_ok and model_ok

        if ok:
            matches.append(item)

    print("\n=== RESULTS (MATCH) ===")
    if not matches:
        print("Ничего не найдено по фильтрам.")
    else:
        for item in matches:
            print(f"- {item.brand} {item.model} | {item.year} | {item.cc}cc | {item.price_eur}€ | {item.location} | {item.date_text}")
            print(f"  {item.url}")

def find_matches(
    *,
    limit: int = 35,
    max_price: int = 6000,
    cc_min: int = 350,
    cc_max: int = 750,
    brands: list[str] | None = None,
    query_models: list[str] | None = None,
    debug_seen: bool = False,
    delay_seconds: float = 0.0,
) -> list[Listing]:
    if brands is None:
        brands = ["Kawasaki", "Honda", "BMW", "Suzuki", "Yamaha", "Triumph"]

    if query_models is None:
        query_models = ["dr", "drz", "xr", "klr", "klx", "dl650", "vstrom", "freewind", "transalp"]

    ad_urls = extract_ad_urls_paged(SEARCH_URL, limit=limit, max_pages=10)

    matches: list[Listing] = []

    for url in ad_urls:
        ad_html = fetch_html(url)
        item = parse_listing(ad_html, url)

        if debug_seen:
            print(f"[SEEN ] {item.brand} {item.model} | cc={item.cc} | price={item.price_eur} | {item.url}")

        brand_ok = any(
            matches_filters(item, max_price=max_price, brand_contains=b, cc_min=cc_min, cc_max=cc_max)
            for b in brands
        )

        # модельная логика (используй ту, которая у тебя сейчас финальная)
        haystack = normalize(f"{item.model or ''} {item.title or ''}")
        model_ok = any(normalize(q) in haystack for q in query_models)

        if brand_ok and model_ok:
            matches.append(item)

        if delay_seconds:
            import time
            time.sleep(delay_seconds)

    return matches

if __name__ == "__main__":
    main()
