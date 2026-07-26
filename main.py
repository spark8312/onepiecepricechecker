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

# Set map fallback in case Yuyutei search page doesn't list set breadcrumbs
SET_MAP = {
    "ST01": "[ST01] STARTER DECK -Straw Hat Crew-",
    "ST02": "[ST02] STARTER DECK -Worst Generation-",
    "ST03": "[ST03] STARTER DECK -Seven Warlords of the Sea-",
    "ST04": "[ST04] STARTER DECK -Animal Kingdom Pirates-",
    "ST05": "[ST05] STARTER DECK -ONE PIECE FILM Edition-",
    "ST06": "[ST06] STARTER DECK -Navy-",
    "ST07": "[ST07] STARTER DECK -Big Mom Pirates-",
    "ST08": "[ST08] STARTER DECK -Monkey D. Luffy-",
    "ST09": "[ST09] STARTER DECK -Yamato-",
    "ST10": "[ST10] STARTER DECK -Ultimate Deck- Three Captains",
    "ST11": "[ST11] STARTER DECK -Uta-",
    "ST12": "[ST12] STARTER DECK -Zoro & Sanji-",
    "ST13": "[ST13] 3D2Y",
    "ST14": "[ST14] 3D2Y",
    "OP01": "[OP01] BOOSTER PACK -ROMANCE DAWN-",
    "OP02": "[OP02] BOOSTER PACK -PARAMOUNT WAR-",
    "OP03": "[OP03] BOOSTER PACK -PILLARS OF STRENGTH-",
    "OP04": "[OP04] BOOSTER PACK -KINGDOMS OF INTRIGUE-",
    "OP05": "[OP05] Protagonist of the New Era",
    "OP06": "[OP06] BOOSTER PACK -FLANKED BY LEGENDS-",
    "OP07": "[OP07] BOOSTER PACK -500 YEARS INTO THE FUTURE-",
    "OP08": "[OP08] BOOSTER PACK -TWO LEGENDS-",
    "OP09": "[OP09] BOOSTER PACK -THE FOUR EMPERORS-",
    "EB01": "[EB01] EXTRA BOOSTER -MEMORIAL COLLECTION-",
}

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

        # 1. Try extracting Card Set from Yuyutei breadcrumbs or title
        yyt_card_set = ""
        page_title = soup.title.text if soup.title else ""
        
        set_match = re.search(r'\[(.*?)\]\s*([^|]+)', page_title)
        if set_match:
            raw_set_name = auto_translate_jp_to_en(set_match.group(2).strip())
            yyt_card_set = f"[{set_match.group(1)}] {raw_set_name}"

        # Clear pickup sections
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            if formatted_query in box_text:
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                # Determine set name from card prefix if title scraping didn't match
                prefix = extracted_card_no.split("-")[0] if "-" in extracted_card_no else extracted_card_no[:4]
                final_card_set = yyt_card_set if yyt_card_set else SET_MAP.get(prefix, f"[{prefix}] ONE PIECE Card Game")

                raw_jp_name = ""
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

                price_patterns = box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
                card_price = None
                for p in price_patterns:
                    cleaned_val = re.sub(r'[^\d]', '', p)
                    if cleaned_val.isdigit():
                        card_price = float(cleaned_val)
                        break
                
                if card_price is not None:
                    card_name_en = auto_translate_jp_to_en(raw_jp_name) if raw_jp_name else f"Card ({extracted_card_no})"
                    is_parallel = "パラレル" in raw_jp_name or "parallel" in card_name_en.lower()
                    
                    results.append({
                        "cardNo": extracted_card_no,
                        "cardName": card_name_en,
                        "cardSet": final_card_set,
                        "priceJpy": card_price,
                        "isParallel": is_parallel
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
