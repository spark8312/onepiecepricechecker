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

# Global caches to improve speed and avoid rate limits
OFFICIAL_SET_MAP = {}
CARD_DETAIL_CACHE = {}

def get_exchange_rates():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rates = res.get("rates", {})
        usd_to_myr = rates.get("MYR", 4.40)
        jpy_to_myr = usd_to_myr / rates.get("JPY", 155.0)
        return jpy_to_myr, usd_to_myr
    except Exception:
        return 0.025, 4.40

def load_official_sets():
    """Builds a lookup table from official Bandai <option> tags."""
    global OFFICIAL_SET_MAP
    if OFFICIAL_SET_MAP:
        return OFFICIAL_SET_MAP

    try:
        url = "https://asia-en.onepiece-cardgame.com/cardlist/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            options = soup.find_all("option")
            
            for opt in options:
                raw_text = html.unescape(opt.decode_contents())
                clean_set_name = re.sub(r'<[^>]+>', ' ', raw_text)
                clean_set_name = re.sub(r'\s+', ' ', clean_set_name).strip()
                
                if clean_set_name and "ALL" not in clean_set_name.upper():
                    # Extract set codes like OP-01, ST-01, OP01, ST01, etc.
                    codes = re.findall(r'\[(.*?)\]', clean_set_name)
                    for code in codes:
                        norm_code = code.replace("-", "").upper()
                        OFFICIAL_SET_MAP[norm_code] = clean_set_name
                        OFFICIAL_SET_MAP[code.upper()] = clean_set_name

                    # Also index keywords like ROMANCE DAWN
                    words = re.findall(r'[A-Z0-9\-]{3,}', clean_set_name.upper())
                    for w in words:
                        if w not in ["PACK", "DECK", "BOOSTER", "STARTER", "EXTRA"]:
                            OFFICIAL_SET_MAP[w] = clean_set_name

    except Exception as e:
        print(f"Error loading official set list: {e}")
        
    return OFFICIAL_SET_MAP

def fetch_official_card_info(card_no: str, yyt_set_tag: str = ""):
    """Gets official Card Name and matches Official Card Set."""
    clean_no = card_no.strip().upper()
    
    if clean_no in CARD_DETAIL_CACHE:
        return CARD_DETAIL_CACHE[clean_no]

    official_sets = load_official_sets()
    matched_set = ""

    # Match YYT set tag (e.g. "[OP01]ROMANCE DAWN") against official sets
    if yyt_set_tag:
        # Check set code in brackets first (e.g. OP01)
        code_match = re.search(r'\[(.*?)\]', yyt_set_tag)
        if code_match:
            raw_code = code_match.group(1).replace("-", "").upper()
            if raw_code in official_sets:
                matched_set = official_sets[raw_code]

        # Check full text keywords if code match wasn't found
        if not matched_set:
            for kw, bandai_name in official_sets.items():
                if kw in yyt_set_tag.upper():
                    matched_set = bandai_name
                    break

    try:
        url = f"https://asia-en.onepiece-cardgame.com/cardlist/?seek={clean_no}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            for item in soup.select(".cardListItem, dl.modalCol, div.cardDetail"):
                if clean_no in item.text.upper():
                    name_elem = item.select_one(".cardName, .card-name, .name, dt")
                    official_card_name = name_elem.text.strip() if name_elem else ""

                    set_elem = item.select_one(".series, .cardSet, .setName, .set")
                    if set_elem and not matched_set:
                        matched_set = set_elem.text.strip()

                    official_card_name = re.sub(r'\s+', ' ', official_card_name)
                    matched_set = re.sub(r'\s+', ' ', matched_set)

                    if official_card_name:
                        CARD_DETAIL_CACHE[clean_no] = (official_card_name, matched_set or yyt_set_tag)
                        return CARD_DETAIL_CACHE[clean_no]

    except Exception as e:
        print(f"Error fetching card info for {clean_no}: {e}")

    return None, matched_set or yyt_set_tag or "ONE PIECE CARD GAME"

def scrape_yuyutei_cards(search_query: str):
    results = []
    try:
        formatted_query = search_query.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_query}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Extract Set Title tag from YYT header or <title>
        yyt_set_tag = ""
        if soup.title:
            # Extract pattern like "[OP01]ROMANCE DAWN" from page title
            match = re.search(r'\[(.*?)\][^\s|]*', soup.title.text)
            if match:
                yyt_set_tag = match.group(0)
            else:
                yyt_set_tag = soup.title.text
        
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            if formatted_query in box_text:
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                raw_jp_name = ""
                h4_tag = box.find(["h4", "h5"])
                if h4_tag and h4_tag.text.strip():
                    raw_jp_name = h4_tag.text.strip()

                price_patterns = box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
                card_price = None
                for p in price_patterns:
                    cleaned_val = re.sub(r'[^\d]', '', p)
                    if cleaned_val.isdigit():
                        card_price = float(cleaned_val)
                        break
                
                if card_price is not None:
                    variant_tag = ""
                    if "パラレル" in raw_jp_name or "平行" in raw_jp_name:
                        variant_tag = " (Parallel)"
                    elif "リーダー" in raw_jp_name:
                        variant_tag = " (Leader)"

                    results.append({
                        "cardNo": extracted_card_no,
                        "variantTag": variant_tag,
                        "priceJpy": card_price,
                        "yytSetTag": yyt_set_tag
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
            yyt_tag = items[0].get("yytSetTag", "")
            official_name, official_set = fetch_official_card_info(c_no, yyt_tag)

            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)

            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                display_name = f"{official_name}{item['variantTag']}" if official_name else f"Card ({c_no}){item['variantTag']}"

                if total > 1 and idx < total - 1:
                    p_num = total - 1 - idx
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}_p{p_num}.png"
                else:
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                base_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                card_items.append({
                    "cardNo": c_no,
                    "cardName": display_name,
                    "cardSet": official_set,
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
