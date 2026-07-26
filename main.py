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
        
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            if formatted_query in box_text:
                # Extract card number
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                # Extract image URL directly from Yuyutei
                img_tag = box.find("img")
                card_img_url = ""
                if img_tag:
                    card_img_url = img_tag.get("src") or img_tag.get("data-src") or ""
                    if card_img_url.startswith("//"):
                        card_img_url = "https:" + card_img_url
                    elif card_img_url.startswith("/"):
                        card_img_url = "https://yuyu-tei.jp" + card_img_url

                # Extract Japanese title
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

                # Extract price
                price_patterns = box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
                card_price = None
                for p in price_patterns:
                    cleaned_val = re.sub(r'[^\d]', '', p)
                    if cleaned_val.isdigit():
                        card_price = float(cleaned_val)
                        break
                
                if card_price is not None:
                    card_name_en = auto_translate_jp_to_en(raw_jp_name) if raw_jp_name else f"Card ({extracted_card_no})"
                    
                    # Fallback URL format using official Bandai structure if missing
                    fallback_img = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{extracted_card_no}.png"
                    
                    results.append({
                        "cardNo": extracted_card_no,
                        "cardName": card_name_en,
                        "priceJpy": card_price,
                        "imageUrl": card_img_url if card_img_url else fallback_img
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
        yuyutei_cards.sort(key=lambda x: x["priceJpy"], reverse=True)
        
        for item in yuyutei_cards:
            jpy = item["priceJpy"]
            myr = round(jpy * jpy_to_myr, 2) if jpy else 0
            
            card_items.append({
                "cardNo": item["cardNo"],
                "cardName": item["cardName"],
                "imageUrl": item["imageUrl"],
                "yuyutei_jpy": jpy,
                "myr_price": myr
            })

    return {
        "searchQuery": formatted_query,
        "conversionRate": jpy_to_myr,
        "items": card_items
    }
