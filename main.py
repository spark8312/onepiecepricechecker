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
        return 0.03, 4.40

def get_official_card_image(card_no: str) -> str:
    """Generates and verifies official card image URL from asia-en.onepiece-cardgame.com"""
    formatted_card = card_no.strip().upper()
    
    # Official Asia-EN image URL template
    official_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{formatted_card}.png"
    
    try:
        # Check if the image exists on the official server
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.head(official_img_url, headers=headers, timeout=5)
        if response.status_code == 200:
            return official_img_url
    except Exception as e:
        print(f"Error checking official image: {e}")
        
    return None

def scrape_yuyutei(card_no: str):
    try:
        formatted_card_no = card_no.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_card_no}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Extract Price from Yuyutei
        price_patterns = soup.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
        prices = []
        for p in price_patterns:
            cleaned_val = re.sub(r'[^\d]', '', p)
            if cleaned_val.isdigit():
                prices.append(float(cleaned_val))
                
        if prices:
            return min(prices)
            
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
        
    return None

@app.get("/api/prices")
def fetch_card_prices(card: str):
    formatted_card = card.strip().upper()
    
    # Get official Asia-EN image
    image_url = get_official_card_image(formatted_card)
    
    # Get exchange rates & Yuyutei price
    jpy_to_myr, usd_to_myr = get_exchange_rates()
    yuyutei_jpy = scrape_yuyutei(formatted_card)
    
    myr_price = (yuyutei_jpy * jpy_to_myr) if yuyutei_jpy else None

    return {
        "cardNo": formatted_card,
        "imageUrl": image_url,
        "yuyutei_jpy": yuyutei_jpy,
        "myr_price": round(myr_price, 2) if myr_price else "N/A"
    }
