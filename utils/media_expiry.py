"""미디어 CDN 서명 URL의 만료 판정 정본.

LinkedIn(`media.licdn.com`)은 이미지 URL 쿼리 `e=` 에 만료 epoch(초)를 담는다.
만료된 URL은 어떤 요청 헤더를 붙여도 403 을 돌려주므로, 다운로드를 시도하기 전에
여기서 걸러야 한다. 헤더 튜닝으로 우회되지 않는다는 것은 실측으로 확인했다
(UA 보강 / Referer / Accept + Sec-Fetch-* / 헤더 없음 4조합 모두 403).

`utils/post_schema.py` 에 넣지 않는 이유: 그쪽은 스키마 정본이라 시간 의존 로직이
섞이면 계약 테스트의 범위가 흐려진다.

`web_viewer/script.js` 의 `isMediaUrlExpired()` 가 같은 규칙을 JS 로 구현한다.
규칙을 바꿀 때는 양쪽을 함께 고친다 - 이 파일이 참조 정본이다.
"""

import time
from urllib.parse import parse_qs, urlsplit

# 만료 epoch 를 담는 쿼리 파라미터. licdn 규약이다.
EXPIRY_QUERY_KEY = "e"


def get_media_url_expiry(img_url):
    """URL 에서 만료 epoch(초)를 정수로 꺼낸다. 없거나 정수가 아니면 None.

    fbcdn 등 다른 CDN 은 만료 파라미터 이름이 달라서, `e=` 가 없으면
    '만료 정보를 모른다'로 둔다. 모르는 것을 만료로 단정하면 멀쩡한 URL 을
    통째로 버리게 된다.
    """
    if not img_url:
        return None

    query = urlsplit(str(img_url)).query
    if not query:
        return None

    values = parse_qs(query).get(EXPIRY_QUERY_KEY) or []
    if not values:
        return None

    raw = str(values[0]).strip()
    if not raw.isdigit():
        return None

    return int(raw)


def is_media_url_expired(img_url, now_ts=None):
    """만료가 확인된 URL 만 True. 만료 정보를 모르면 False.

    False 는 '유효함'이 아니라 '만료로 단정할 수 없음'이다. 호출부는 이 값을
    다운로드 시도 여부에만 쓰고, 성공을 보장하는 신호로 쓰지 않는다.
    """
    expiry = get_media_url_expiry(img_url)
    if expiry is None:
        return False

    current = time.time() if now_ts is None else now_ts
    return expiry <= current


def has_live_media_url(media_list, now_ts=None):
    """미디어 목록에 만료되지 않은 이미지 URL 이 하나라도 있으면 True.

    동영상(`.mp4`)은 이미지 다운로드 대상이 아니라 세지 않는다.
    """
    for img_url in media_list or []:
        if not img_url:
            continue
        if ".mp4" in str(img_url).lower():
            continue
        if not is_media_url_expired(img_url, now_ts):
            return True
    return False
