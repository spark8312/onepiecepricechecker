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

DETAIL_CACHE = {}

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

def scrape_card_detail_page(detail_url: str):
    """Fetches Card Set and Card Name directly from Yuyutei individual card page."""
    if detail_url in DETAIL_CACHE:
        return DETAIL_CACHE[detail_url]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }

    card_set_en = "ONE PIECE Card Game"
    card_name_en = ""

    try:
        res = requests.get(detail_url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Extract set name from <title> e.g., "... | [OP05] 主役のRank | ONE PIECE..."
            page_title = soup.title.text if soup.title else ""
            set_match = re.search(r'\[(.*?)\]\s*([^|]+)', page_title)
            if set_match:
                set_code = set_match.group(1).strip()
                raw_set_jp = set_match.group(2).strip()
                translated_set = auto_translate_jp_to_en(raw_set_jp)
                card_set_en = f"[{set_code}] {translated_set}"

            # Extract card name from main <h2>/<h1> heading on the detail page
            heading = soup.find(["h1", "h2", "h3"], class_=re.compile(r'title|card-title|name', re.I))
            if heading and heading.text.strip():
                raw_jp_name = heading.text.strip()
                card_name_en = auto_translate_jp_to_en(raw_jp_name)

    except Exception as e:
        print(f"Error scraping detail page {detail_url}: {e}")

    result = {"cardSet": card_set_en, "cardName": card_name_en}
    DETAIL_CACHE[detail_url] = result
    return result

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
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                # Find link to individual card detail page
                detail_link_tag = box.find("a", href=re.compile(r'/sell/opc/card/'))
                card_set_en = "ONE PIECE Card Game"
                raw_jp_name = ""

                if detail_link_tag and detail_link_tag.get("href"):
                    detail_href = detail_link_tag["href"]
                    full_detail_url = detail_href if detail_href.startswith("http") else f"https://yuyu-tei.jp{detail_href}"
                    
                    detail_data = scrape_card_detail_page(full_detail_url)
                    if detail_data.get("cardSet"):
                        card_set_en = detail_data["cardSet"]
                    if detail_data.get("cardName"):
                        card_name_en = detail_data["cardName"]

                # Fallback card name extraction if detail page name wasn't found
                if not raw_jp_name:
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
                    final_card_name = card_name_en if 'card_name_en' in locals() and card_name_en else auto_translate_jp_to_en(raw_jp_name)
                    if not final_card_name:
                        final_card_name = f"Card ({extracted_card_no})"

                    results.append({
                        "cardNo": extracted_card_no,
                        "cardName": final_card_name,
                        "cardSet": card_set_en,
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
