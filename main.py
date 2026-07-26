def scrape_yuyutei(card_no: str):
    try:
        url = f"https://yuyu-tei.jp/sell/opc/s/search?search_word={card_no}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        price_tags = soup.find_all("b")
        for tag in price_tags:
            text = tag.text.replace("yen", "").replace("円", "").replace(",", "").strip()
            if text.isdigit():
                return float(text)
    except Exception as e:
        print(f"Error scraping Yuyutei: {e}")
    return None
