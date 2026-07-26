from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup

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
        res = requests.get("https://open.er-api.com/v6/latest/USD").json()
        rates = res.get("rates", {})
        usd_to_myr = rates.get("MYR", 4.40)
        jpy_to_myr = usd_to_myr / rates.get("JPY", 155.0)
        return jpy_to_myr, usd_to_myr
    except Exception:
        return 0.03, 4.40  # Fallback rates if API fails

def scrape_yuyutei(card_no: str):
    try:
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={card_no}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")

        # Look for prices on Yuyutei
        price_tags = soup.find_all("b")
        for tag in price_tags:
            text = tag.text.replace("yen", "").replace(",", "").strip()
            if text.isdigit():
                return float(text)
    except Exception:
        pass
    return None

@app.get("/api/prices")
def fetch_card_prices(card: str):
    jpy_to_myr, usd_to_myr = get_exchange_rates()

    # Scrape Yuyutei price
    yuyutei_jpy = scrape_yuyutei(card)

    # Convert Yuyutei JPY to MYR
    myr_price = yuyutei_jpy * jpy_to_myr if yuyutei_jpy else None

    return {
        "cardNo": card,
        "yuyutei_jpy": yuyutei_jpy,
        "myr_price": round(myr_price, 2) if myr_price else "N/A"
    }
