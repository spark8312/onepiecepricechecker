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

# Known set mappings based on Card Number prefixes
SET_MAP = {
    "ST01": "[ST-01] STARTER DECK -Straw Hat Crew-",
    "ST02": "[ST-02] STARTER DECK -Worst Generation-",
    "ST03": "[ST-03] STARTER DECK -Seven Warlords of the Sea-",
    "ST04": "[ST-04] STARTER DECK -Animal Kingdom Pirates-",
    "ST05": "[ST-05] STARTER DECK -ONE PIECE FILM Edition-",
    "ST06": "[ST-06] STARTER DECK -Navy-",
    "ST07": "[ST-07] STARTER DECK -Big Mom Pirates-",
    "ST08": "[ST-08] STARTER DECK -Monkey D. Luffy-",
    "ST09": "[ST-09] STARTER DECK -Yamato-",
    "ST10": "[ST-10] STARTER DECK -Ultimate Deck- Three Captains",
    "ST11": "[ST-11] STARTER DECK -Uta-",
    "ST12": "[ST-12] STARTER DECK -Zoro & Sanji-",
    "ST13": "[ST-13] 3D2Y",
    "ST14": "[ST-14] 3D2Y",
    "OP01": "[OP-01] BOOSTER PACK -ROMANCE DAWN-",
    "OP02": "[OP-02] BOOSTER PACK -PARAMOUNT WAR-",
    "OP03": "[OP-03] BOOSTER PACK -PILLARS OF STRENGTH-",
    "OP04": "[OP-04] BOOSTER PACK -KINGDOMS OF INTRIGUE-",
    "OP05": "[OP-05] BOOSTER PACK -AWAKENING OF THE NEW ERA-",
    "OP06": "[OP-06] BOOSTER PACK -FLANKED BY LEGENDS-",
    "OP07": "[OP-07] BOOSTER PACK -500 YEARS INTO THE FUTURE-",
    "OP08": "[OP-08] BOOSTER PACK -TWO LEGENDS-",
    "OP09": "[OP-09] BOOSTER PACK -THE FOUR EMPERORS-",
    "EB01": "[EB-01] EXTRA BOOSTER -MEMORIAL COLLECTION-",
}

NAME_CACHE = {}

def get_exchange_rates():
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rates = res.get("rates", {})
        usd_to_myr = rates.get("MYR", 4.40)
        jpy_to_myr = usd_to_myr / rates.get("JPY", 155.0)
        return jpy_to_myr, usd_to_myr
    except Exception:
        return 0.025, 4.40

def translate_jp_name(text: str) -> str:
    """Translates Japanese card names from Yuyutei to English character names."""
    if not text:
        return ""
    
    if text in NAME_CACHE:
        return NAME_CACHE[text]

    try:
        # Clean out common rarity or type tags before translating
        clean_text = re.sub(r'\(.*?\)|（.*?）|【.*?】|パラレル|平行|リーダー|LEADER', '', text).strip()
        if not clean_text:
            clean_text = text

        encoded_text = urllib.parse.quote(clean_text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=en&dt=t&q={encoded_text}"
        
        res = requests.get(url, timeout=5).json()
        translated = "".join([segment[0] for segment in res[0] if segment[0]])
        
        # Format names cleanly
        translated = re.sub(r'\s+', ' ', translated).strip()
        translated = translated.replace("Monkey. D. Luffy", "Monkey D. Luffy")
        translated = translated.replace("Portgas. D. Ace", "Portgas D. Ace")
        translated = translated.replace("Roronoa. Zoro", "Roronoa Zoro")
        
        NAME_CACHE[text] = translated
        return translated
    except Exception:
        return text

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
        
        # Remove unrelated pickup boxes
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            if formatted_query in box_text:
                # 1. Extract exact Card No (e.g. ST01-001, ST01-012)
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                # 2. Extract Japanese Card Name from the box header
                raw_jp_name = ""
                h4_tag = box.find(["h4", "h5", "a"])
                if h4_tag and h4_tag.text.strip():
                    raw_jp_name = h4_tag.text.strip()

                # 3. Determine variant tags (Parallel, Leader, etc.)
                variant_tag = ""
                if "パラレル" in raw_jp_name or "平行" in raw_jp_name:
                    variant_tag = " (Parallel)"
                elif "リーダー" in raw_jp_name or "LEADER" in raw_jp_name:
                    variant_tag = " (Leader)"

                # 4. Extract price in JPY
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
            # Get Set Name based on Card Prefix (e.g. ST01 -> [ST-01] STARTER DECK -Straw Hat Crew-)
            prefix = c_no.split("-")[0] if "-" in c_no else c_no[:4]
            card_set = SET_MAP.get(prefix, f"ONE PIECE CARD GAME ({prefix})")

            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)

            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                # Translate character name from Japanese
                translated_name = translate_jp_name(item["rawJpName"])
                char_name = translated_name if translated_name else c_no
                display_name = f"{char_name}{item['variantTag']}"

                # Image URL construction
                if total > 1 and idx < total - 1:
                    p_num = total - 1 - idx
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}_p{p_num}.png"
                else:
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                base_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                card_items.append({
                    "cardNo": c_no,
                    "cardName": display_name,
                    "cardSet": card_set,
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
