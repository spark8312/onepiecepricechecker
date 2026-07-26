from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re

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

def scrape_yuyutei_cards(card_no: str):
    """
    Scrapes all card listings on Yuyutei matching the given card number.
    Returns a list of dicts: [{'name': ..., 'price_jpy': ..., 'img_url': ...}]
    """
    results = []
    try:
        formatted_card_no = card_no.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_card_no}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Decompose sidebar/extra recommendation containers to avoid irrelevant cards
        for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
            extra.decompose()
            
        # Target search result item boxes
        card_boxes = soup.select(".card-unit, .card-product-box, div[class*='card-']")
        
        for box in card_boxes:
            box_text = box.text.upper()
            
            # Verify the card number is actually present inside this box
            if formatted_card_no in box_text:
                # Extract Card Name
                name_tag = box.find(["h4", "h5", "a", "p"], class_=re.compile(r"title|name|card-title"))
                card_name = name_tag.text.strip() if name_tag else "One Piece Card"
                
                # Extract Image URL
                img_tag = box.find("img", src=re.compile(r"/card/"))
                yuyutei_img_url = None
                if img_tag and img_tag.get("src"):
                    src = img_tag["src"]
                    yuyutei_img_url = src if src.startswith("http") else f"https://yuyu-tei.jp{src}"

                # Extract Price
                price_patterns = box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
                card_price = None
                for p in price_patterns:
                    cleaned_val = re.sub(r'[^\d]', '', p)
                    if cleaned_val.isdigit():
                        card_price = float(cleaned_val)
                        break
                
                if card_price is not None:
                    results.append({
                        "cardName": card_name,
                        "priceJpy": card_price,
                        "fallbackImageUrl": yuyutei_img_url
                    })
                    
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
        
    return results

@app.get("/api/prices")
def fetch_card_prices(card: str):
    formatted_card = card.strip().upper()
    
    # Official Asia-EN image URL (default)
    official_image_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{formatted_card}.png"
    
    # Get exchange rates
    jpy_to_myr, usd_to_myr = get_exchange_rates()
    
    # Scrape all matching card variants from Yuyutei
    yuyutei_cards = scrape_yuyutei_cards(formatted_card)
    
    card_items = []
    if yuyutei_cards:
        for item in yuyutei_cards:
            jpy = item["priceJpy"]
            myr = round(jpy * jpy_to_myr, 2) if jpy else "N/A"
            card_items.append({
                "cardNo": formatted_card,
                "cardName": item["cardName"],
                "officialImageUrl": official_image_url,
                "fallbackImageUrl": item["fallbackImageUrl"],
                "yuyutei_jpy": jpy,
                "myr_price": myr
            })
    else:
        # Fallback single row if no items found on Yuyutei
        card_items.append({
            "cardNo": formatted_card,
            "cardName": "N/A",
            "officialImageUrl": official_image_url,
            "fallbackImageUrl": None,
            "yuyutei_jpy": None,
            "myr_price": "N/A"
        })

    return {
        "cardNo": formatted_card,
        "items": card_items
    }
