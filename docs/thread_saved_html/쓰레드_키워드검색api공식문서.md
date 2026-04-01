---
title: "키워드 검색 - Threads API"
created: "2023-10-17 05:42"
---

# 키워드 검색 - Threads API

URL: https://developers.facebook.com/docs/threads/keyword-search?locale=ko_KR
Saved: 2026년 2월 6일 오후 12:55

# 키워드 및 주제 태그 검색

특정 키워드 또는 주제 태그로 공개 Threads 미디어를 검색합니다.

### 제한 사항

- 사용자는 연속 24시간 이내에 최대 2,200개의 쿼리를 전송할 수 있습니다. 쿼리가 전송되면 24시간 동안 이 한도에서 차감됩니다.
- 이 제한은 여러 앱에 걸쳐 한 사용자에게 적용되며 앱에 따라 구분되지 않습니다. 여러 앱이 동일한 사용자에 대해 요청을 전송하는 경우 이러한 쿼리는 해당 사용자의 동일한 한도에 적용됩니다.
- 이 기간 내에 발생하는 동일한 키워드에 대한 후속 쿼리 역시 이 한도에서 차감됩니다.
- 결과를 반환하지 않는 쿼리는 해당 한도에서 차감되지 않습니다. 결과가 반환되지 않는 경우 쿼리를 수정하거나 더 짧게 만들어 보세요.
- API는 Meta에서 민감하거나 불쾌하다고 간주하는 키워드가 포함되어 있는 요청에 대해서는 빈 배열을 반환합니다.

### 권한

Threads 키워드 검색 API에는 적절한 액세스 토큰과 권한이 필요합니다. 테스트하는 동안 그래프 API 탐색기를 사용하여 손쉽게 토큰을 생성하고 앱에 권한을 부여할 수 있습니다.

- `threads_basic` - 모든 Threads API 엔드포인트에 호출을 보낼 때 필수입니다.
- `threads_keyword_search` - 키워드 검색 엔드포인트에 GET 호출을 보낼 때 필수입니다.

앱이 `threads_keyword_search` 권한에 대해 승인되지 않은 경우, 검색은 인증된 사용자가 소유한 게시물에 대해서만 수행됩니다. 승인을 받은 후에는 전체 공개 게시물을 검색할 수 있게 됩니다.

## 키워드 검색

전체 공개 Threads 미디어를 키워드로 검색하려면 쿼리할 키워드를 포함하여 `/keyword_search` 엔드포인트로 `GET` 요청을 보내세요.

### 매개변수

| 이름 | 설명 |
| --- | --- |
|  |  |
| `q` |  |

문자열

|

**필수.**
쿼리할 키워드입니다.

|
|

`search_type`

문자열

|

**선택 사항.**
검색 동작을 지정합니다.

**값:**

- `TOP`(*기본값*) - 가장 인기 있는 검색 결과를 가져옵니다.
- `RECENT` - 가장 최근 검색 결과를 가져옵니다.

|
|

`search_mode`

문자열

|

**선택 사항.**
검색 모드를 지정합니다.

**값:**

- `KEYWORD`(*기본값*) - 쿼리가 키워드로 처리됩니다.
- `TAG` - 쿼리가 주제 태그로 처리됩니다.

|
|

`media_type`

문자열

|

**선택 사항.**
검색할 미디어의 유형을 지정합니다. 아래에 나열된 미디어 유형만 지원됩니다.

**값:**

- `TEXT` - 쿼리를 통해 텍스트 게시물을 검색합니다.
- `IMAGE` - 쿼리를 통해 이미지 게시물을 검색합니다.
- `VIDEO` - 쿼리를 통해 동영상 게시물을 검색합니다.

|
|

`since`

|

**선택 사항.**
가져오기 시작 날짜를 나타내는 쿼리 문자열 매개변수입니다(Unix 타임스탬프 또는 `strtotime();`으로 파싱 가능한 날짜/시간 형식이어야 하며, 타임스탬프는 `1688540400` 이상이고 `until` 매개변수 미만이어야 합니다).

|
|

`until`

|

**선택 사항.**
가져오기 종료 날짜를 나타내는 열 매개변수입니다(Unix 타임스탬프 또는 `strtotime();`으로 파싱 가능한 날짜/시간 형식이어야 하며, 타임스탬프는 현재 타임스탬프 이하이고 `since` 매개변수를 초과해야 합니다).

|
|

`limit`

|

**선택 사항.**
반환하도록 요청된 미디어 개체 또는 기록의 최대 개수를 나타내는 쿼리 문자열 매개변수이며, 기본값은 **25**이고 최댓값은 **100**입니다(음수가 아닌 숫자만 허용됩니다).

|
|

`author_username`

|

**선택 사항.**
특정 사용자 이름 또는 프로필에서 만든 게시물만 포함하도록 검색 결과를 필터링합니다. 사용자 이름은 `@` 기호 없이 정확히 일치해야 합니다.

|

사용 가능한 필드의 리스트는 [미디어](https://developers.facebook.com/docs/threads/threads-media) 문서를 참조하세요. **참고:** 소유자 필드는 제외되고 반환되지 않습니다.

### 요청 예시

curl -s -X GET \
-F "q=" \
-F "search_type=TOP" \
-F "fields=id,text,media_type,permalink,timestamp,username,has_replies,is_quote_post,is_reply" \
-F "access_token=<THREADS_ACCESS_TOKEN>" \
"[https://graph.threads.net/v1.0/keyword_search"](https://graph.threads.net/v1.0/keyword_search%22)

### 응답 예시

{
"data": [
{
"id": "1234567890",
"text": "first thread",
"media_type": "TEXT",
"permalink": "[https://www.threads.net/@/post/abcdefg",](https://www.threads.net/@%3CUSER%3E/post/abcdefg%22,)
"timestamp": "2023-10-17T05:42:03+0000",
"username": "",
"has_replies": false,
"is_quote_post": false,
"is_reply": false
}
]
}

## 주제 태그 검색

전체 공개 Threads 미디어를 주제 태그로 검색하려면 쿼리할 주제를 포함하여 `/keyword_search` 엔드포인트로 `GET` 요청을 보내세요. 주제 태그 검색을 수행하려면 `search_mode` 매개변수를 사용하고 값을 `TAG`로 설정해야 합니다.

### 요청 예시

curl -s -X GET \
-F "q=" \
-F "search_mode=TAG" \
-F "search_type=TOP" \
-F "fields=id,text,media_type,permalink,timestamp,username,has_replies,is_quote_post,is_reply" \
-F "access_token=<THREADS_ACCESS_TOKEN>" \
"[https://graph.threads.net/v1.0/keyword_search"](https://graph.threads.net/v1.0/keyword_search%22)

### 응답 예시

{
"data": [
{
"id": "1234567890",
"text": "second thread",
"media_type": "TEXT",
"permalink": "[https://www.threads.net/@/post/abcdefg",](https://www.threads.net/@%3CUSER%3E/post/abcdefg%22,)
"timestamp": "2023-10-17T05:42:03+0000",
"username": "",
"has_replies": false,
"is_quote_post": false,
"is_reply": false
}
]
}

## 미디어 유형으로 검색

미디어 유형으로 전체 공개 Threads 게시물을 검색하려면 `media_type` 매개변수를 포함하여 `/keyword_search` 엔드포인트로 `GET` 요청을 보내세요. 텍스트, 이미지, 동영상 미디어 유형에 대해 검색할 수 있습니다. `media_type` 매개변수가 전송되지 않는 경우, 응답에 모든 미디어 유형이 반환됩니다.

### 요청 예시

curl -s -X GET \
-F "q=" \
-F "media_type=IMAGE"
-F "fields=id,text,media_type,permalink,timestamp,username" \
-F "access_token=<THREADS_ACCESS_TOKEN>" \
"[https://graph.threads.net/v1.0/keyword_search"](https://graph.threads.net/v1.0/keyword_search%22)

### 응답 예시

{
"data": [
{
"id": "1234567890",
"text": "third thread",
"media_type": "IMAGE",
"permalink": "[https://www.threads.net/@/post/abcdefg",](https://www.threads.net/@%3CUSER%3E/post/abcdefg%22,)
"timestamp": "2023-10-17T05:42:03+0000",
"username": ""
}
]
}

최근에 검색한 전체 공개 Threads 미디어와 상호 작용할 수 있습니다. 이러한 행동에는 [답글 달기](https://developers.facebook.com/docs/threads/reply-management), [인용하기](https://developers.facebook.com/docs/threads/posts/quote-posts), [리포스트하기](https://developers.facebook.com/docs/threads/posts/reposts)가 포함됩니다.

**참고:** 해당 페이지에 나와 있는 대로 추가 권한이 필요할 수 있습니다.

## 최근 검색한 키워드

`/me` 엔드포인트에 `GET` 요청을 보내고 `recently_searched_keywords` 필드를 요청하여 현재 인증된 사용자에 대해 최근 검색된 키워드의 리스트를 가져올 수 있습니다.

### 요청 예시

curl -s -X GET \
-F "fields=recently_searched_keywords" \
-F "access_token=<THREADS_ACCESS_TOKEN>" \
"[https://graph.threads.net/v1.0/me"](https://graph.threads.net/v1.0/me%22)

### 응답 예시

{
"id": "1234567890",
"recently_searched_keywords": [
{
"query": "some keyword",
"timestamp": 1735707600000,
},
{
"query": "some other keyword",
"timestamp": 1735707600000,
}
]
}