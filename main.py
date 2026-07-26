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

def scrape_yuyutei_data(card_no: str):
    """
    Extracts price and image directly from Yuyutei's exact card search result row,
    avoiding sidebar items like 'Latest release' or 'Featured Products'.
    """
    price = None
    yuyutei_img_url = None
    
    try:
        formatted_card_no = card_no.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_card_no}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Look specifically for the card result unit containing the card code text
        # Yuyutei card entries contain the card code in <span> or text node inside card-product-box/card-unit
        card_boxes = soup.select(".card-unit, .card-product-box, .card-list3 .col-md-6, div[class*='card-']")
        
        target_box = None
        for box in card_boxes:
            if formatted_card_no in box.text.upper():
                target_box = box
                break
                
        # If no specific container match, isolate main content list area and exclude sidebar/pickup
        if not target_box:
            # Remove sidebar sections from parsing
            for extra in soup.select("#PICKUP, .pickup-box, div[id*='pickup'], .latest-box"):
                extra.decompose()
            target_box = soup
            
        # Extract Image from Yuyutei search result
        img_tag = target_box.find("img", src=re.compile(r"/card/"))
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            yuyutei_img_url = src if src.startswith("http") else f"https://yuyu-tei.jp{src}"

        # Extract Price from Yuyutei search result
        price_patterns = target_box.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
        prices = []
        for p in price_patterns:
            cleaned_val = re.sub(r'[^\d]', '', p)
            if cleaned_val.isdigit():
                prices.append(float(cleaned_val))
                
        if prices:
            price = min(prices)
            
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
        
    return price, yuyutei_img_url

@app.get("/api/prices")
def fetch_card_prices(card: str):
    formatted_card = card.strip().upper()
    
    # Official Asia-EN image URL
    official_image_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{formatted_card}.png"
    
    # Get exchange rates & Yuyutei data
    jpy_to_myr, usd_to_myr = get_exchange_rates()
    yuyutei_jpy, yuyutei_img_url = scrape_yuyutei_data(formatted_card)
    
    myr_price = (yuyutei_jpy * jpy_to_myr) if yuyutei_jpy else None

    return {
        "cardNo": formatted_card,
        "officialImageUrl": official_image_url,
        "fallbackImageUrl": yuyutei_img_url,
        "yuyutei_jpy": yuyutei_jpy,
        "myr_price": round(myr_price, 2) if myr_price else "N/A"
    }
