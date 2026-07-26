from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import html
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OFFICIAL_SET_CACHE = {}
DETAIL_CACHE = {}

def get_exchange_rates():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rates = res.get("rates", {})
        usd_to_myr = rates.get("MYR", 4.40)
        jpy_to_myr = usd_to_myr / rates.get("JPY", 155.0)
        return jpy_to_myr, usd_to_myr
    except Exception:
        return 0.025, 4.40

def load_official_set_map():
    """Scrapes official set names from Bandai's official site and builds a code-to-set lookup dict."""
    global OFFICIAL_SET_CACHE
    if OFFICIAL_SET_CACHE:
        return OFFICIAL_SET_CACHE

    try:
        url = "https://asia-en.onepiece-cardgame.com/cardlist/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Find select/option tags or series list elements
            options = soup.find_all("option")
            for opt in options:
                raw_text = html.unescape(opt.decode_contents())
                clean_set_name = re.sub(r'<[^>]+>', ' ', raw_text)
                clean_set_name = re.sub(r'\s+', ' ', clean_set_name).strip()

                if clean_set_name and "ALL" not in clean_set_name.upper():
                    # Extract codes like OP-05, OP05, ST-01, EB-01, PRB-01 inside brackets [OP-05]
                    codes = re.findall(r'\[(.*?)\]', clean_set_name)
                    for code in codes:
                        norm_code = code.replace("-", "").upper()
                        OFFICIAL_SET_CACHE[norm_code] = clean_set_name
                        OFFICIAL_SET_CACHE[code.upper()] = clean_set_name

            # Fallback parsing for button/modal lists if select options aren't rendered
            if not OFFICIAL_SET_CACHE:
                for elem in soup.find_all(text=re.compile(r'\[(OP|ST|EB|PRB)-?\d+\]', re.I)):
                    text = elem.strip()
                    codes = re.findall(r'\[(.*?)\]', text)
                    for code in codes:
                        norm_code = code.replace("-", "").upper()
                        OFFICIAL_SET_CACHE[norm_code] = text
                        OFFICIAL_SET_CACHE[code.upper()] = text

    except Exception as e:
        print(f"Error fetching official set list: {e}")

    return OFFICIAL_SET_CACHE

def get_official_set_name(card_no: str) -> str:
    """Matches the card number series prefix (e.g. OP13, ST01) against official sets."""
    official_sets = load_official_set_map()
    
    # Extract series code prefix (e.g., OP13 from OP13-001, ST01 from ST01-012)
    match = re.match(r'^([A-Z]{2,3}\d{2})', card_no.strip().upper())
    if match:
        series_code = match.group(1)
        if series_code in official_sets:
            return official_sets[series_code]
            
    return "N/A"

def auto_translate_jp_to_en(text: str) -> str:
    if not text:
        return ""
    try:
        clean_input = text.replace('（', '(').replace('）', ')').replace('【', '(').replace('】', ')')
        encoded_text = urllib.parse.quote(clean_input)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=en&dt=t&q={encoded_text}"
        
        response = requests.get(url, timeout=5).json()
        translated_text = "".join([segment[0] for segment in response[0] if segment[0]])
        
        translated_text = translated_text.replace("Monkey. D. Luffy", "Monkey D. Luffy")
        translated_text = re.sub(r'\(\s*\)', '', translated_text)
        translated_text = re.sub(r'\(\s*\((.*?)\)\s*\)', r'(\1)', translated_text)
        translated_text = re.sub(r'\s+', ' ', translated_text).strip()
        
        return translated_text
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def scrape_card_detail_name(detail_url: str) -> str:
    """Optionally fetches character name from detail page."""
    if detail_url in DETAIL_CACHE:
        return DETAIL_CACHE[detail_url]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }

    card_name_en = ""
    try:
        res = requests.get(detail_url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            heading = soup.find(["h1", "h2", "h3"], class_=re.compile(r'title|card-title|name', re.I))
            if heading and heading.text.strip():
                raw_jp_name = heading.text.strip()
                card_name_en = auto_translate_jp_to_en(raw_jp_name)
    except Exception as e:
        print(f"Error scraping detail page {detail_url}: {e}")

    DETAIL_CACHE[detail_url] = card_name_en
    return card_name_en

def scrape_yuyutei_cards(search_query: str):
    results = []
    try:
        formatted_query = search_query.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_query}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            if formatted_query in box_text:
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                # Map series code to official set title or return "N/A"
                card_set_en = get_official_set_name(extracted_card_no)

                raw_jp_name = ""
                card_name_en = ""
                
                detail_link_tag = box.find("a", href=re.compile(r'/sell/opc/card/'))
                if detail_link_tag and detail_link_tag.get("href"):
                    detail_href = detail_link_tag["href"]
                    full_detail_url = detail_href if detail_href.startswith("http") else f"https://yuyu-tei.jp{detail_href}"
                    card_name_en = scrape_card_detail_name(full_detail_url)

                if not card_name_en:
                    h4_tag = box.find(["h4", "h5"])
                    if h4_tag and h4_tag.text.strip():
                        raw_jp_name = h4_tag.text.strip()
                    else:
                        a_tags = box.find_all("a")
                        for a in a_tags:
                            text = a.text.strip()
                            if text and not text.isdigit() and "円" not in text and "YEN" not in text.upper():
                                raw_jp_name = text
                                break

                    card_name_en = auto_translate_jp_to_en(raw_jp_name) if raw_jp_name else f"Card ({extracted_card_no})"

                price_patterns = box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
                card_price = None
                for p in price_patterns:
                    cleaned_val = re.sub(r'[^\d]', '', p)
                    if cleaned_val.isdigit():
                        card_price = float(cleaned_val)
                        break
                
                if card_price is not None:
                    results.append({
                        "cardNo": extracted_card_no,
                        "cardName": card_name_en,
                        "cardSet": card_set_en,
                        "priceJpy": card_price
                    })
                    
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
        
    return results

@app.get("/api/prices")
def fetch_card_prices(card: str):
    formatted_query = card.strip().upper()
    jpy_to_myr, usd_to_myr = get_exchange_rates()
    
    yuyutei_cards = scrape_yuyutei_cards(formatted_query)
    
    card_items = []
    if yuyutei_cards:
        card_groups = {}
        for item in yuyutei_cards:
            c_no = item["cardNo"]
            card_groups.setdefault(c_no, []).append(item)

        for c_no, items in card_groups.items():
            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)
            
            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                if total > 1 and idx < total - 1:
                    p_num = total - 1 - idx
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}_p{p_num}.png"
                else:
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                base_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                card_items.append({
                    "cardNo": c_no,
                    "cardName": item["cardName"],
                    "cardSet": item["cardSet"],
                    "imageUrl": img_url,
                    "baseImageUrl": base_img_url,
                    "yuyutei_jpy": jpy,
                    "myr_price": myr
                })

    return {
        "searchQuery": formatted_query,
        "conversionRate": jpy_to_myr,
        "items": card_items
    }
