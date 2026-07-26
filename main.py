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

def fetch_official_opcg_details(card_no: str):
    """Fetches official English card name and Card Set from official Bandai OPCG site."""
    try:
        clean_no = card_no.strip().upper()
        url = f"https://asia-en.onepiece-cardgame.com/cardlist/?seek={clean_no}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Find matching card container block in official OPCG page
            card_dl = soup.find("dl", class_="modalCol") or soup.find("div", class_="cardDetail")
            if not card_dl:
                # Fallback search across list items
                for dl in soup.select(".cardListItem, dl"):
                    if clean_no in dl.text.upper():
                        card_dl = dl
                        break

            if card_dl:
                # Extract official card name
                name_elem = card_dl.select_one(".cardName, .card-name, .name")
                official_name = name_elem.text.strip() if name_elem else ""

                # Extract Card Set name (e.g. -ROMANCE DAWN- [OP01])
                set_elem = card_dl.select_one(".series, .cardSet, .setName")
                card_set = set_elem.text.strip() if set_elem else ""

                # Clean up extracted strings
                official_name = re.sub(r'\s+', ' ', official_name)
                card_set = re.sub(r'\s+', ' ', card_set)

                return official_name, card_set
    except Exception as e:
        print(f"Error fetching official OPCG details: {e}")
    
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
    
    # Fetch official English Card Name and Card Set from official OPCG
    official_name, card_set = fetch_official_opcg_details(formatted_query)
    
    card_items = []
    if yuyutei_cards:
        # Group by cardNo
        card_groups = {}
        for item in yuyutei_cards:
            c_no = item["cardNo"]
            card_groups.setdefault(c_no, []).append(item)

        for c_no, items in card_groups.items():
            items.sort(key=lambda x: x["priceJpy"], reverse=True)
            total = len(items)

            # Look up card-specific OPCG details if query was a set code like ST01
            group_official_name, group_card_set = official_name, card_set
            if not group_official_name or c_no != formatted_query:
                specific_name, specific_set = fetch_official_opcg_details(c_no)
                group_official_name = specific_name or c_no
                group_card_set = specific_set or "Official OPCG"

            for idx, item in enumerate(items):
                jpy = item["priceJpy"]
                myr = round(jpy * jpy_to_myr, 2) if jpy else 0
                
                full_card_name = f"{group_official_name}{item['variantTag']}"

                if total > 1 and idx < total - 1:
                    p_num = total - 1 - idx
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}_p{p_num}.png"
                else:
                    img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                base_img_url = f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{c_no}.png"

                card_items.append({
                    "cardNo": c_no,
                    "cardName": full_card_name,
                    "cardSet": group_card_set,
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
