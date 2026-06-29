import sqlite3

import streamlit as st

from main import (
    init_db,
    save_product,
    get_lowest_previous_price,
    get_naver_shopping_prices,
    filter_price_results,
    compare_prices,
    save_price_history,
    get_active_products,
    update_all_products,
    send_telegram_message,
    make_alert_message,
)


DB_NAME = "hotdeal.db"


st.set_page_config(
    page_title="핫딜 가격 추적 AI Agent",
    page_icon="🛒",
    layout="wide"
)


init_db()


st.title("🛒 핫딜 가격 추적 AI Agent")
st.write(
    "상품명과 목표 가격을 등록하면 네이버 쇼핑 API로 실제 가격을 검색하고, "
    "목표가 이하 또는 이전 최저가 갱신 시 알림을 보냅니다."
)


# =========================
# Sidebar
# =========================

st.sidebar.header("메뉴")
menu = st.sidebar.radio(
    "기능 선택",
    [
        "상품 등록 및 가격 확인",
        "저장된 상품 목록",
        "전체 상품 가격 업데이트",
        "최근 가격 이력",
        "상품 삭제",
    ],
)


DEFAULT_EXCLUDE_KEYWORDS = "스킨,그립,파우치,케이스,보호필름,스티커,커버,중고,리퍼,벌크"


# =========================
# 1. 상품 등록 및 가격 확인
# =========================

if menu == "상품 등록 및 가격 확인":
    st.header("1. 상품 등록 및 가격 확인")

    product_name = st.text_input(
        "상품명",
        placeholder="예: MX Master 3S",
    )

    target_price = st.number_input(
        "목표 가격",
        min_value=0,
        step=1000,
        value=90000,
    )

    exclude_keywords = st.text_input(
        "제외 키워드",
        value=DEFAULT_EXCLUDE_KEYWORDS,
        help="쉼표로 구분하세요. 예: 스킨,파우치,케이스",
    )

    if st.button("상품 등록 및 가격 확인"):
        if not product_name.strip():
            st.error("상품명을 입력해주세요.")
        else:
            product_id = save_product(
                product_name=product_name.strip(),
                target_price=int(target_price),
                exclude_keywords=exclude_keywords,
            )

            previous_lowest_price = get_lowest_previous_price(product_id)

            current_prices = get_naver_shopping_prices(product_name.strip())
            current_prices = filter_price_results(current_prices, exclude_keywords)

            if not current_prices:
                st.warning("제외 키워드 적용 후 남은 검색 결과가 없습니다.")
            else:
                alerts = compare_prices(
                    target_price=int(target_price),
                    current_prices=current_prices,
                    previous_lowest_price=previous_lowest_price,
                )

                save_price_history(product_id, current_prices)

                st.success("상품 등록 및 가격 확인 완료")

                st.subheader("현재 가격 검색 결과")

                for item in current_prices:
                    with st.container(border=True):
                        st.write(f"**{item['product_name']}**")
                        st.write(f"가격: **{item['price']:,}원**")
                        st.write(f"사이트: {item['site']}")
                        st.link_button("상품 링크 열기", item["url"])

                st.subheader("판단 결과")

                if alerts:
                    st.success("알림 대상 상품을 발견했습니다.")

                    for item in alerts:
                        reasons = ", ".join(item["reasons"])
                        with st.container(border=True):
                            st.write(f"**{item['product_name']}**")
                            st.write(f"가격: **{item['price']:,}원**")
                            st.write(f"이유: {reasons}")
                            st.link_button("상품 링크 열기", item["url"])

                            if st.button(
                                f"Telegram 알림 보내기 - {item['price']:,}원",
                                key=f"send_{product_id}_{item['price']}_{item['url']}",
                            ):
                                message = make_alert_message(product_name, item)
                                sent = send_telegram_message(message)

                                if sent:
                                    st.success("Telegram 알림 전송 완료")
                                else:
                                    st.error("Telegram 알림 전송 실패")
                else:
                    st.info("아직 목표 조건을 만족하는 상품이 없습니다.")


# =========================
# 2. 저장된 상품 목록
# =========================

elif menu == "저장된 상품 목록":
    st.header("2. 저장된 상품 목록")

    products = get_active_products()

    if not products:
        st.info("저장된 활성 상품이 없습니다.")
    else:
        for product in products:
            with st.container(border=True):
                st.write(f"**ID {product['id']} | {product['product_name']}**")
                st.write(f"목표가: {product['target_price']:,}원")
                st.write(f"제외 키워드: {product['exclude_keywords']}")


# =========================
# 3. 전체 상품 가격 업데이트
# =========================

elif menu == "전체 상품 가격 업데이트":
    st.header("3. 전체 상품 가격 업데이트")
    st.write("등록된 모든 활성 상품의 가격을 다시 확인합니다.")

    if st.button("전체 상품 가격 업데이트 실행"):
        products = get_active_products()

        if not products:
            st.info("등록된 활성 상품이 없습니다.")
        else:
            for product in products:
                product_id = product["id"]
                product_name = product["product_name"]
                target_price = product["target_price"]
                exclude_keywords = product["exclude_keywords"]

                st.subheader(f"상품 ID {product_id}: {product_name}")

                previous_lowest_price = get_lowest_previous_price(product_id)

                if previous_lowest_price is not None:
                    st.write(f"이전 최저가: {previous_lowest_price:,}원")
                else:
                    st.write("이전 최저가: 기록 없음")

                current_prices = get_naver_shopping_prices(product_name)
                current_prices = filter_price_results(current_prices, exclude_keywords)

                if not current_prices:
                    st.warning("검색 결과가 없습니다.")
                    continue

                alerts = compare_prices(
                    target_price=target_price,
                    current_prices=current_prices,
                    previous_lowest_price=previous_lowest_price,
                )

                save_price_history(product_id, current_prices)

                lowest_now = min(item["price"] for item in current_prices)
                st.write(f"현재 검색 최저가: **{lowest_now:,}원**")

                st.write("현재 검색 결과")

                for item in current_prices[:5]:
                    with st.container(border=True):
                        st.write(f"**{item['product_name']}**")
                        st.write(f"가격: {item['price']:,}원")
                        st.link_button("상품 링크 열기", item["url"])

                if alerts:
                    st.success("알림 대상 발견")

                    for item in alerts:
                        reasons = ", ".join(item["reasons"])
                        with st.container(border=True):
                            st.write(f"**{item['product_name']}**")
                            st.write(f"가격: **{item['price']:,}원**")
                            st.write(f"이유: {reasons}")
                            st.link_button("상품 링크 열기", item["url"])

                            message = make_alert_message(product_name, item)
                            sent = send_telegram_message(message)

                            if sent:
                                st.success("Telegram 알림 전송 완료")
                            else:
                                st.warning("Telegram 알림 전송 실패 또는 설정 없음")
                else:
                    st.info("알림 조건을 만족하는 상품이 없습니다.")


# =========================
# 4. 최근 가격 이력
# =========================

elif menu == "최근 가격 이력":
    st.header("4. 최근 가격 이력")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT product_id, site, product_name, price, url, checked_at
    FROM price_history
    ORDER BY id DESC
    LIMIT 30
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        st.info("저장된 가격 이력이 없습니다.")
    else:
        for row in rows:
            product_id, site, product_name, price, url, checked_at = row

            with st.container(border=True):
                st.write(f"**{product_name}**")
                st.write(f"상품 ID: {product_id}")
                st.write(f"사이트: {site}")
                st.write(f"가격: **{price:,}원**")
                st.write(f"확인 시간: {checked_at}")
                st.link_button("상품 링크 열기", url)


# =========================
# 5. 상품 삭제
# =========================

elif menu == "상품 삭제":
    st.header("5. 상품 삭제")

    products = get_active_products()

    if not products:
        st.info("삭제할 활성 상품이 없습니다.")
    else:
        product_options = {
            f"ID {p['id']} | {p['product_name']} | 목표가 {p['target_price']:,}원": p["id"]
            for p in products
        }

        selected_label = st.selectbox(
            "삭제할 상품을 선택하세요",
            list(product_options.keys()),
        )

        if st.button("선택한 상품 삭제"):
            selected_id = product_options[selected_label]

            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()

            cur.execute("""
            UPDATE products
            SET is_active = 0
            WHERE id = ?
            """, (selected_id,))

            conn.commit()
            conn.close()

            st.success(f"상품 ID {selected_id}를 삭제 처리했습니다.")
            st.rerun()