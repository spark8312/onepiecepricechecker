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

def translate_jp_to_en(text: str) -> str:
    """Translates Japanese card/character names from Yuyutei to English."""
    if not text:
        return ""
    try:
        # Clean common brackets/suffixes before translating
        clean_input = re.sub(r'\(.*?\)|（.*?）|【.*?】', '', text).strip()
        if not clean_input:
            clean_input = text

        encoded_text = urllib.parse.quote(clean_input)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=en&dt=t&q={encoded_text}"
        
        res = requests.get(url, timeout=5).json()
        translated = "".join([segment[0] for segment in res[0] if segment[0]])
        
        # Format common names cleanly
        translated = re.sub(r'\s+', ' ', translated).strip()
        translated = translated.replace("Monkey. D. Luffy", "Monkey D. Luffy")
        translated = translated.replace("Roronoa. Zoro", "Roronoa Zoro")
        return translated
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def load_official_sets():
    """Builds set lookup table directly from Bandai's select options."""
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
                    codes = re.findall(r'\[(.*?)\]', clean_set_name)
                    for code in codes:
                        norm_code = code.replace("-", "").upper()
                        OFFICIAL_SET_MAP[norm_code] = clean_set_name
                        OFFICIAL_SET_MAP[code.upper()] = clean_set_name

    except Exception as e:
        print(f"Error loading official set list: {e}")
        
    return OFFICIAL_SET_MAP

def get_official_set_name(card_no: str) -> str:
    """Matches official set name by card number prefix (e.g. ST01 -> STARTER DECK -Straw Hat Crew- [ST-01])."""
    official_sets = load_official_sets()
    prefix_match = re.match(r'^([A-Z]{2,3}\d{2})', card_no.strip().upper())
    set_prefix = prefix_match.group(1) if prefix_match else ""
    return official_sets.get(set_prefix, "ONE PIECE CARD GAME")

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
                        "rawJpName": raw_jp_name,
                        "variantTag": variant_tag,
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
            official_set = get_official_set_name(c_no)

            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)

            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                # Clean and translate Japanese card title from Yuyutei to Character Name
                if c_no not in CARD_DETAIL_CACHE:
                    translated_char_name = translate_jp_to_en(item["rawJpName"])
                    CARD_DETAIL_CACHE[c_no] = translated_char_name
                else:
                    translated_char_name = CARD_DETAIL_CACHE[c_no]

                char_name = translated_char_name if translated_char_name else c_no
                display_name = f"{char_name}{item['variantTag']}"

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
