from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI()

# Allows any website to talk to this backend
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
        return 0.03, 4.40  # Fallback rates

def scrape_yuyutei(card_no: str):
    try:
        # Convert card_no to uppercase (e.g. p-074 -> P-074)
        formatted_card_no = card_no.strip().upper()
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={formatted_card_no}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Search for price numbers in text nodes ending with "yen" or "円"
        # Yuyutei prices typically look like "120 yen" or "120円" or "1,980 yen"
        price_patterns = soup.find_all(text=re.compile(r'[\d,]+\s*(yen|円)'))
        
        prices = []
        for p in price_patterns:
            # Extract digits only
            cleaned_val = re.sub(r'[^\d]', '', p)
            if cleaned_val.isdigit():
                prices.append(float(cleaned_val))
                
        if prices:
            # Return lowest found price for that card number
            return min(prices)
            
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
        
    return None

@app.get("/api/prices")
def fetch_card_prices(card: str):
    jpy_to_myr, usd_to_myr = get_exchange_rates()

    # Scrape Yuyutei price
    yuyutei_jpy = scrape_yuyutei(card)
    
    # Convert Yuyutei JPY to MYR
    myr_price = (yuyutei_jpy * jpy_to_myr) if yuyutei_jpy else None

    return {
        "cardNo": card.upper(),
        "yuyutei_jpy": yuyutei_jpy,
        "myr_price": round(myr_price, 2) if myr_price else "N/A"
    }
