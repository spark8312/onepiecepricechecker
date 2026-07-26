from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache to avoid repeatedly hitting Bandai's site for the same card number
OPCG_CACHE = {}

def get_exchange_rates():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rates = res.get("rates", {})
        usd_to_myr = rates.get("MYR", 4.40)
        jpy_to_myr = usd_to_myr / rates.get("JPY", 155.0)
        return jpy_to_myr, usd_to_myr
    except Exception:
        return 0.025, 4.40

def auto_translate_jp_to_en(text: str) -> str:
    """Fallback translator if official OPCG details are missing."""
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
        return re.sub(r'\s+', ' ', translated_text).strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return text

def fetch_official_opcg_details(card_no: str):
    """Fetches exact official English card name and Card Set by specific Card No."""
    clean_no = card_no.strip().upper()
    
    if clean_no in OPCG_CACHE:
        return OPCG_CACHE[clean_no]

    try:
        url = f"https://asia-en.onepiece-cardgame.com/cardlist/?seek={clean_no}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Target card block containing the matching card_no
            card_items = soup.select(".cardListItem, dl.modalCol, div.cardDetail")
            for item in card_items:
                item_text = item.text.upper()
                if clean_no in item_text:
                    # Name extraction
                    name_elem = item.select_one(".cardName, .card-name, .name, dt")
                    official_name = name_elem.text.strip() if name_elem else ""

                    # Set extraction
                    set_elem = item.select_one(".series, .cardSet, .setName, .set")
                    card_set = set_elem.text.strip() if set_elem else ""

                    official_name = re.sub(r'\s+', ' ', official_name)
                    card_set = re.sub(r'\s+', ' ', card_set)

                    if official_name:
                        OPCG_CACHE[clean_no] = (official_name, card_set or "Starter Deck / Booster Pack")
                        return OPCG_CACHE[clean_no]
    except Exception as e:
        print(f"Error fetching official OPCG details for {clean_no}: {e}")

    return None, None

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
                # Extract clean card number format (e.g., ST01-001)
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
                    is_parallel = "パラレル" in raw_jp_name or "平行" in raw_jp_name
                    is_leader = "リーダー" in raw_jp_name or "LEADER" in raw_jp_name
                    
                    variant_tag = ""
                    if is_parallel:
                        variant_tag = " (Parallel)"
                    elif is_leader:
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
        # Group by cardNo so that parallel arts and standard cards share the base official info
        card_groups = {}
        for item in yuyutei_cards:
            c_no = item["cardNo"]
            card_groups.setdefault(c_no, []).append(item)

        for c_no, items in card_groups.items():
            # Query official OPCG for the specific card number
            official_name, official_set = fetch_official_opcg_details(c_no)

            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)

            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                # Determine name
                if official_name:
                    card_title = f"{official_name}{item['variantTag']}"
                else:
                    # Fallback to dynamic translation if not found on English OPCG
                    translated_jp = auto_translate_jp_to_en(item["rawJpName"])
                    card_title = translated_jp if translated_jp else f"Card ({c_no}){item['variantTag']}"

                set_title = official_set if official_set else "ONE PIECE CARD GAME"

                # Assign image links
                if total > 1 and idx < total - 1:
                    p_num = total - 1 - idx
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}_p{p_num}.png"
                else:
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                base_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                card_items.append({
                    "cardNo": c_no,
                    "cardName": card_title,
                    "cardSet": set_title,
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
