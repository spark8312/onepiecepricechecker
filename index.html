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

def translate_to_english(text: str) -> str:
    translations = [
        ("レッドスーパーパラレル", " (Red Super Parallel)"),
        ("スーパーパラレル", " (Super Parallel / Manga Rare)"),
        ("特別パラレル", " (Special Parallel)"),
        ("パラレル", " (Parallel)"),
        ("リーダー", " (Leader)"),
        ("モンキー・D・ルフィ", "Monkey D. Luffy"),
        ("ポートガス・D・エース", "Portgas.D.Ace"),
        ("サボ", "Sabo"),
        ("ヤマト", "Yamato"),
        ("シャンクス", "Shanks"),
        ("トラファルガー・ロー", "Trafalgar Law"),
        ("ロロノア・ゾロ", "Roronoa Zoro"),
        ("ナミ", "Nami"),
        ("サンジ", "Sanji"),
        ("ウタ", "Uta"),
        ("ボア・ハンコック", "Boa Hancock"),
        ("エドワード・ニューゲート", "Edward Newgate"),
        ("ゴール・D・ロジャー", "Gol D. Roger"),
        ("シャーロット・カタクリ", "Charlotte Katakuri"),
        ("クザン", "Kuzan"),
        ("ユースタス・キッド", "Eustass Kid"),
        ("シルバーズ・レイリー", "Silvers Rayleigh"),
    ]
    
    clean_text = text
    for jp, en in translations:
        clean_text = clean_text.replace(jp, en)
        
    clean_text = re.sub(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', '', clean_text)
    clean_text = re.sub(r'[\(\[\{]\s*[\)\]\}]', '', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    return clean_text

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
                # Extract full card number (e.g. OP13-001, OP13-118)
                card_no_match = re.search(r'[A-Z]{2,3}\d{2}-\d{3}', box_text)
                extracted_card_no = card_no_match.group(0) if card_no_match else formatted_query

                jp_name = None
                h4_tag = box.find(["h4", "h5"])
                if h4_tag and h4_tag.text.strip():
                    jp_name = h4_tag.text.strip()
                else:
                    a_tags = box.find_all("a")
                    for a in a_tags:
                        text = a.text.strip()
                        if text and not text.isdigit() and "円" not in text and "YEN" not in text.upper():
                            jp_name = text
                            break
                            
                card_name = translate_to_english(jp_name) if jp_name else f"Card ({extracted_card_no})"

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
                        "cardName": card_name,
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
        yuyutei_cards.sort(key=lambda x: x["priceJpy"], reverse=True)
        total_items = len(yuyutei_cards)
        
        for idx, item in enumerate(yuyutei_cards):
            jpy = item["priceJpy"]
            myr = round(jpy * jpy_to_myr, 2) if jpy else 0
            full_card_no = item["cardNo"]
            
            # Form official English Bandai CDN host using full card number
            if total_items > 1 and idx < total_items - 1:
                p_suffix = f"_p{total_items - 1 - idx}"
                image_url = f"https://en.onepiece-cardgame.com/images/cardlist/card/{full_card_no}{p_suffix}.png"
            else:
                image_url = f"https://en.onepiece-cardgame.com/images/cardlist/card/{full_card_no}.png"
            
            fallback_base_url = f"https://en.onepiece-cardgame.com/images/cardlist/card/{full_card_no}.png"

            card_items.append({
                "cardNo": full_card_no,
                "cardName": item["cardName"],
                "imageUrl": image_url,
                "baseImageUrl": fallback_base_url,
                "yuyutei_jpy": jpy,
                "myr_price": myr
            })

    return {
        "searchQuery": formatted_query,
        "conversionRate": jpy_to_myr,
        "items": card_items
    }
