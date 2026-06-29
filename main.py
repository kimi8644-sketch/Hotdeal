import json
import os
import re
import sqlite3
from datetime import datetime

import requests
from openai import OpenAI


DB_NAME = "hotdeal.db"


# =========================
# 1. DB 관련 함수
# =========================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        target_price INTEGER NOT NULL,
        exclude_keywords TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        site TEXT NOT NULL,
        product_name TEXT NOT NULL,
        price INTEGER NOT NULL,
        url TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)

    # 기존 DB를 쓰고 있을 때 컬럼이 없으면 추가
    try:
        cur.execute("ALTER TABLE products ADD COLUMN exclude_keywords TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def save_product(product_name, target_price, exclude_keywords=""):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
    INSERT INTO products (product_name, target_price, exclude_keywords, is_active, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (product_name, target_price, exclude_keywords, 1, created_at))

    product_id = cur.lastrowid

    conn.commit()
    conn.close()

    return product_id

def save_price_history(product_id, price_results):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in price_results:
        cur.execute("""
        INSERT INTO price_history (product_id, site, product_name, price, url, checked_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            item["site"],
            item["product_name"],
            item["price"],
            item["url"],
            checked_at
        ))

    conn.commit()
    conn.close()


def get_lowest_previous_price(product_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT MIN(price)
    FROM price_history
    WHERE product_id = ?
    """, (product_id,))

    result = cur.fetchone()[0]

    conn.close()

    return result


def show_saved_products():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT id, product_name, target_price, exclude_keywords, created_at
    FROM products
    WHERE is_active = 1
    ORDER BY id DESC
    """)

    rows = cur.fetchall()
    conn.close()

    print("\n[저장된 상품 목록]")

    if not rows:
        print("저장된 상품이 없습니다.")
        return

    for row in rows:
        product_id, product_name, target_price, exclude_keywords, created_at = row

        print(f"- ID {product_id} | {product_name} | 목표가 {target_price:,}원 | {created_at}")
        if exclude_keywords:
            print(f"  제외 키워드: {exclude_keywords}")

def get_active_products():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT id, product_name, target_price, exclude_keywords
    FROM products
    WHERE is_active = 1
    ORDER BY id ASC
    """)

    rows = cur.fetchall()
    conn.close()

    products = []

    for row in rows:
        product_id, product_name, target_price, exclude_keywords = row

        products.append({
            "id": product_id,
            "product_name": product_name,
            "target_price": target_price,
            "exclude_keywords": exclude_keywords
        })

    return products
def update_all_products():
    products = get_active_products()

    if not products:
        print("\n등록된 활성 상품이 없습니다.")
        return

    print("\n=== 등록된 상품 전체 가격 업데이트 ===")

    for product in products:
        product_id = product["id"]
        product_name = product["product_name"]
        target_price = product["target_price"]
        exclude_keywords = product["exclude_keywords"]

        print("\n------------------------------")
        print(f"상품 ID: {product_id}")
        print(f"상품명: {product_name}")

        if target_price > 0:
            print(f"목표가: {target_price:,}원")
        else:
            print("목표가: 설정 없음")

        previous_lowest_price = get_lowest_previous_price(product_id)

        if previous_lowest_price is not None:
            print(f"이전 최저가: {previous_lowest_price:,}원")
        else:
            print("이전 최저가: 기록 없음")

        current_prices = get_naver_shopping_prices(product_name)
        current_prices = filter_price_results(current_prices, exclude_keywords)

        if not current_prices:
            print("검색 결과가 없습니다.")
            continue

        alerts = compare_prices(
            target_price=target_price,
            current_prices=current_prices,
            previous_lowest_price=previous_lowest_price
        )

        save_price_history(product_id, current_prices)

        lowest_now = min(item["price"] for item in current_prices)

        print(f"현재 검색 최저가: {lowest_now:,}원")

        print("\n[현재 검색 결과]")
        for item in current_prices[:5]:
            print(f"- {item['price']:,}원 | {item['product_name']}")
            print(f"  URL: {item['url']}")

        print("\n[판단 결과]")
        if alerts:
            print("알림 대상 발견!")

            for item in alerts:
                reasons = ", ".join(item["reasons"])
                print(f"- {item['price']:,}원 | {reasons}")
                print(f"  상품명: {item['product_name']}")
                print(f"  URL: {item['url']}")

                message = make_alert_message(product_name, item)
                sent = send_telegram_message(message)

                if sent:
                    print("  Telegram 알림 전송 완료")
        else:
            print("알림 조건을 만족하는 상품이 없습니다.")

    print("\n전체 업데이트 완료.")

def show_price_history():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT product_id, site, product_name, price, url, checked_at
    FROM price_history
    ORDER BY id DESC
    LIMIT 10
    """)

    rows = cur.fetchall()
    conn.close()

    print("\n[최근 가격 이력]")

    if not rows:
        print("저장된 가격 이력이 없습니다.")
        return

    for row in rows:
        product_id, site, product_name, price, url, checked_at = row
        print(f"- 상품ID {product_id} | {site} | {price:,}원 | {checked_at}")
        print(f"  상품명: {product_name}")
        print(f"  URL: {url}")


# =========================
# 2. AI 자연어 분석 함수
# =========================

def parse_user_request_with_ai(user_text):
    """
    사용자의 자연어 문장에서 상품명과 목표 가격을 추출하는 함수.
    예:
    'MX Master 3S 9만 원 이하로 뜨면 알려줘'
    ->
    {"product_name": "MX Master 3S", "target_price": 90000}
    """

    client = OpenAI()

    prompt = f"""
너는 핫딜 가격 추적 Agent의 입력 분석기야.

사용자의 문장에서 구매 추적 정보를 추출해줘.

사용자 문장:
{user_text}

반드시 아래 JSON 형식으로만 답해.
설명 문장은 쓰지 마.

{{
  "product_name": "상품명",
  "target_price": 숫자
}}

규칙:
- target_price는 반드시 원 단위 정수로 변환해.
- 예를 들어 9만 원은 90000으로 변환해.
- 예를 들어 12.5만 원은 125000으로 변환해.
- 가격이 없으면 target_price를 0으로 둬.
- 상품명에는 '알려줘', '뜨면', '이하로' 같은 조건 문장은 넣지 마.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    text = response.output_text.strip()

    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        print("[AI 응답 파싱 실패]")
        print(text)
        return None


def parse_user_request_without_ai(user_text):
    """
    API 키가 없거나 AI 연결 전 테스트용 간단 파서.
    '9만', '90000원' 같은 표현만 대략 처리.
    """

    target_price = 0
    clean_text = user_text.replace(",", "")

    manwon_decimal_match = re.search(r"(\d+(?:\.\d+)?)\s*만", clean_text)
    won_match = re.search(r"(\d{4,})\s*원?", clean_text)

    if manwon_decimal_match:
        target_price = int(float(manwon_decimal_match.group(1)) * 10000)
    elif won_match:
        target_price = int(won_match.group(1))

    product_name = clean_text

    # 가격 표현 제거
    product_name = re.sub(r"\d+(?:\.\d+)?\s*만\s*원?", "", product_name)
    product_name = re.sub(r"\d{4,}\s*원?", "", product_name)

    # 조건 문장 제거
    remove_words = [
        "이하로",
        "이하면",
        "이하",
        "뜨면",
        "뜨면 알려줘",
        "알려줘",
        "핫딜",
        "나오면",
        "나오면 알려줘",
        "사고 싶음",
        "사고싶음",
        "추적해줘",
        "등록해줘"
    ]

    for word in remove_words:
        product_name = product_name.replace(word, "")

    product_name = product_name.strip()

    return {
        "product_name": product_name,
        "target_price": target_price
    }


# =========================
# 3. 가격 검색 함수
# =========================

def get_dummy_prices(product_name):
    """
    네이버 API 실패 시 사용하는 더미 가격 데이터.
    """

    return [
        {
            "site": "Dummy - Naver Shopping",
            "product_name": product_name,
            "price": 95000,
            "url": "https://example.com/naver"
        },
        {
            "site": "Dummy - Coupang",
            "product_name": product_name,
            "price": 89000,
            "url": "https://example.com/coupang"
        },
        {
            "site": "Dummy - Danawa",
            "product_name": product_name,
            "price": 91000,
            "url": "https://example.com/danawa"
        }
    ]


def clean_html_tags(text):
    """
    네이버 쇼핑 API 결과에 포함된 <b> 태그 제거.
    """
    return re.sub(r"<.*?>", "", text)

def filter_price_results(price_results, exclude_keywords):
    """
    제외 키워드가 포함된 상품을 검색 결과에서 제거.
    예: 스킨, 그립, 파우치, 케이스 등
    """

    if not exclude_keywords:
        return price_results

    keywords = [
        keyword.strip().lower()
        for keyword in exclude_keywords.split(",")
        if keyword.strip()
    ]

    filtered = []

    for item in price_results:
        title = item["product_name"].lower()

        is_excluded = False

        for keyword in keywords:
            if keyword in title:
                is_excluded = True
                break

        if not is_excluded:
            filtered.append(item)

    return filtered

def get_naver_shopping_prices(product_name, display=5):
    """
    네이버 쇼핑 검색 API에서 실제 상품 가격 데이터를 가져오는 함수.
    """

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n[Naver API 키 없음]")
        print("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 설정되어 있지 않습니다.")
        print("더미 가격 데이터로 대체합니다.")
        return get_dummy_prices(product_name)

    url = "https://openapi.naver.com/v1/search/shop.json"

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    params = {
        "query": product_name,
        "display": display,
        "sort": "sim"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        print("\n[네이버 쇼핑 API 요청 오류]")
        print(e)
        print("더미 가격 데이터로 대체합니다.")
        return get_dummy_prices(product_name)

    if response.status_code != 200:
        print("\n[네이버 쇼핑 API 호출 실패]")
        print(f"상태 코드: {response.status_code}")
        print(response.text)
        print("더미 가격 데이터로 대체합니다.")
        return get_dummy_prices(product_name)

    data = response.json()
    price_results = []

    for item in data.get("items", []):
        title = clean_html_tags(item.get("title", ""))
        price_text = item.get("lprice", "0")
        link = item.get("link", "")

        try:
            price = int(price_text)
        except ValueError:
            continue

        if price <= 0:
            continue

        price_results.append({
            "site": "Naver Shopping",
            "product_name": title,
            "price": price,
            "url": link
        })

    if not price_results:
        print("\n[네이버 쇼핑 검색 결과 없음]")
        print("더미 가격 데이터로 대체합니다.")
        return get_dummy_prices(product_name)

    return price_results


# =========================
# 4. 가격 비교 함수
# =========================

def compare_prices(target_price, current_prices, previous_lowest_price=None):
    alerts = []

    for item in current_prices:
        reason_list = []

        if target_price > 0 and item["price"] <= target_price:
            reason_list.append("목표가 이하")

        if previous_lowest_price is not None and item["price"] < previous_lowest_price:
            reason_list.append("이전 최저가 갱신")

        if reason_list:
            alerts.append({
                **item,
                "reasons": reason_list
            })

    return alerts

def send_telegram_message(message):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("\n[Telegram 알림 생략]")
        print("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되어 있지 않습니다.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        print("\n[Telegram 요청 오류]")
        print(e)
        return False

    if response.status_code != 200:
        print("\n[Telegram 전송 실패]")
        print(response.status_code)
        print(response.text)
        return False

    return True

def make_alert_message(product_name, alert_item):
    reasons = ", ".join(alert_item["reasons"])

    message = f"""[핫딜 알림]

등록 상품: {product_name}
발견 상품: {alert_item['product_name']}
가격: {alert_item['price']:,}원
이유: {reasons}

링크:
{alert_item['url']}
"""

    return message

# =========================
# 5. 메뉴 기능
# =========================

def run_price_tracking():
    print("\n=== 상품 가격 추적 ===")
    print("예시: MX Master 3S 9만 원 이하로 뜨면 알려줘")
    print()

    user_text = input("무엇을 추적할까요?: ")

    use_ai = input("AI로 문장 분석할까요? (y/n): ").lower().strip()

    if use_ai == "y":
        if not os.getenv("OPENAI_API_KEY"):
            print("\n[OpenAI API 키 없음]")
            print("OPENAI_API_KEY가 설정되어 있지 않습니다.")
            print("일단 AI 없이 간단 분석으로 진행합니다.")
            parsed = parse_user_request_without_ai(user_text)
        else:
            try:
                parsed = parse_user_request_with_ai(user_text)

                if parsed is None:
                    print("AI 분석에 실패해서 간단 분석으로 진행합니다.")
                    parsed = parse_user_request_without_ai(user_text)

            except Exception as e:
                print("\n[AI 분석 오류]")
                print(e)
                print("AI 없이 간단 분석으로 진행합니다.")
                parsed = parse_user_request_without_ai(user_text)
    else:
        parsed = parse_user_request_without_ai(user_text)

    product_name = parsed["product_name"]
    target_price = int(parsed["target_price"])

    if not product_name:
        print("\n상품명을 인식하지 못했습니다. 다시 실행해주세요.")
        return

    print("\n[입력 분석 결과]")
    print(f"상품명: {product_name}")

    if target_price > 0:
        print(f"목표가: {target_price:,}원")
    else:
        print("목표가: 설정 없음")

    default_exclude_keywords = "스킨,그립,파우치,케이스,보호필름,스티커,커버,중고,리퍼,벌크"

    print("\n기본 제외 키워드:")
    print(default_exclude_keywords)

    custom_exclude = input("추가/수정할 제외 키워드를 입력하세요. 그대로 쓰려면 Enter: ").strip()

    if custom_exclude:
        exclude_keywords = custom_exclude
    else:
        exclude_keywords = default_exclude_keywords

    product_id = save_product(product_name, target_price, exclude_keywords)

    previous_lowest_price = get_lowest_previous_price(product_id)

    # 1. 먼저 네이버 쇼핑 API로 가격 검색
    current_prices = get_naver_shopping_prices(product_name)

    # 2. 그 다음 제외 키워드 필터링
    current_prices = filter_price_results(current_prices, exclude_keywords)

    if not current_prices:
        print("\n제외 키워드 적용 후 남은 상품이 없습니다.")
        print("제외 키워드를 줄이거나 검색어를 더 구체적으로 입력해보세요.")
        return

    alerts = compare_prices(
        target_price=target_price,
        current_prices=current_prices,
        previous_lowest_price=previous_lowest_price
    )

    save_price_history(product_id, current_prices)

    print("\n[현재 가격 검색 결과]")
    for item in current_prices:
        print(f"- {item['site']}: {item['price']:,}원")
        print(f"  상품명: {item['product_name']}")
        print(f"  URL: {item['url']}")

    print("\n[판단 결과]")
    if alerts:
        print("알림 대상 상품을 발견했습니다!")

        for item in alerts:
            reasons = ", ".join(item["reasons"])
            print()
            print(f"사이트: {item['site']}")
            print(f"상품명: {item['product_name']}")
            print(f"가격: {item['price']:,}원")
            print(f"이유: {reasons}")
            print(f"URL: {item['url']}")
    else:
        print("아직 목표 조건을 만족하는 상품이 없습니다.")

    print("\nDB 저장 완료: hotdeal.db")


def main():
    init_db()

    while True:
        print("\n==============================")
        print("핫딜 가격 추적 AI Agent MVP")
        print("==============================")
        print("1. 상품 등록 및 가격 확인")
        print("2. 저장된 상품 목록 보기")
        print("3. 상품 삭제")
        print("4. 등록된 상품 전체 가격 업데이트")
        print("5. 최근 가격 이력 보기")
        print("6. 종료")

        menu = input("메뉴를 선택하세요: ").strip()

        if menu == "1":
            run_price_tracking()
        elif menu == "2":
            show_saved_products()
        elif menu == "3":
            delete_product()
        elif menu == "4":
            update_all_products()
        elif menu == "5":
            show_price_history()
        elif menu == "6":
            print("프로그램을 종료합니다.")
            break
        else:
            print("잘못된 입력입니다. 1~6 중에서 선택하세요.")

def delete_product():
    show_saved_products()

    product_id = input("\n삭제할 상품 ID를 입력하세요: ").strip()

    if not product_id.isdigit():
        print("상품 ID는 숫자로 입력해야 합니다.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    UPDATE products
    SET is_active = 0
    WHERE id = ?
    """, (int(product_id),))

    conn.commit()

    if cur.rowcount == 0:
        print("해당 ID의 상품을 찾지 못했습니다.")
    else:
        print(f"상품 ID {product_id}를 삭제 처리했습니다.")

    conn.close()

if __name__ == "__main__":
    main()