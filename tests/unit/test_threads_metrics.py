"""Threads 참여지표 추출과 병합 시 기존값 보존.

`consumer_detail` 경로(상세 수집)는 본문·미디어만 가져오고 지표를 버렸다.
여기서 두 가지를 고정한다.

1. `data.media` 응답에서 지표를 공통 스키마 필드명으로 뽑는다.
2. 상세 재수집이 이미 확보한 지표를 덮어쓰지 않는다 - `promote_to_full_history`
   가 기존 레코드를 통째로 교체하기 때문에 가드가 없으면 조용히 사라진다.
"""
import os

from thread_scrap_single import preserve_existing_metrics
from utils.threads_parser import (
    extract_engagement_metrics,
    extract_items_from_media_html,
)

GOLDEN_DIR = os.path.join("tests", "fixtures", "golden", "threads")


def load(name):
    with open(os.path.join(GOLDEN_DIR, f"{name}.html"), encoding="utf-8") as file:
        return file.read()


class TestExtractEngagementMetrics:
    def test_maps_threads_names_to_schema_names(self):
        post = {
            "like_count": 140,
            "direct_reply_count": 8,
            "repost_count": 3,
            "quote_count": 1,
        }
        result = extract_engagement_metrics(post)

        # metrics_updated_at 은 시각이라 값을 고정할 수 없으므로 따로 뗀다.
        assert result.pop("metrics_updated_at", None), "읽은 시각이 기록되지 않았다"
        assert result == {
            "like_count": 140,
            "comment_count": 8,
            "share_count": 3,
            "quote_count": 1,
        }

    def test_records_read_time_only_when_a_value_was_found(self):
        """값이 하나도 없으면 시각도 남기지 않는다.

        빈 dict 를 반환해야 병합 단계의 보존 가드가 기존값을 지킨다.
        시각만 실어 보내면 "읽었는데 값이 없었다"와 "안 읽었다"가 뒤섞인다.
        계획: _docs/20260826_02 (W3)
        """
        assert extract_engagement_metrics({"like_count": -1}) == {}
        assert "metrics_updated_at" in extract_engagement_metrics({"like_count": 0})

    def test_zero_is_a_real_value(self):
        assert extract_engagement_metrics({"like_count": 0})["like_count"] == 0

    def test_missing_fields_are_omitted_not_nulled(self):
        # 키를 만들지 않아야 normalize_post 기본값과 보존 가드가 작동한다.
        assert "comment_count" not in extract_engagement_metrics({"like_count": 5})

    def test_negative_marker_is_dropped(self):
        # -1 은 과거 DOM 경로가 쓰던 '값 없음' 표식이다.
        assert extract_engagement_metrics({"like_count": -1}) == {}

    def test_non_numeric_is_dropped(self):
        assert extract_engagement_metrics({"like_count": "many"}) == {}

    def test_bool_is_not_treated_as_number(self):
        assert extract_engagement_metrics({"like_count": True}) == {}

    def test_non_dict_input(self):
        assert extract_engagement_metrics(None) == {}

    def test_reads_from_text_post_app_info_fallback(self):
        post = {"text_post_app_info": {"direct_reply_count": 12}}
        assert extract_engagement_metrics(post)["comment_count"] == 12


class TestGoldenFixturesCarryMetrics:
    def test_media_single_items_have_metrics(self):
        items = extract_items_from_media_html(load("media_single"), "DbkBQE2CXD8", "tofukyung")
        assert items, "golden fixture 에서 아이템을 못 뽑으면 나머지 검증이 무의미하다"
        assert any(item.get("like_count") is not None for item in items)

    def test_metrics_use_schema_field_names_only(self):
        items = extract_items_from_media_html(load("media_single"), "DbkBQE2CXD8", "tofukyung")
        for item in items:
            # 2026-08-24 폐기된 옛 이름이 되살아나면 뷰어가 못 읽는다.
            assert "reply_count" not in item
            assert "repost_count" not in item


class TestPreserveExistingMetrics:
    def test_keeps_existing_when_new_is_none(self):
        new = {"like_count": None}
        preserve_existing_metrics(new, {"like_count": 12})
        assert new["like_count"] == 12

    def test_keeps_existing_zero(self):
        # 0 은 falsy 라서 truthy 검사로 구현하면 여기서 깨진다.
        new = {"like_count": None}
        preserve_existing_metrics(new, {"like_count": 0})
        assert new["like_count"] == 0

    def test_new_value_wins_over_existing(self):
        new = {"like_count": 30}
        preserve_existing_metrics(new, {"like_count": 12})
        assert new["like_count"] == 30

    def test_new_zero_wins_over_existing(self):
        new = {"like_count": 0}
        preserve_existing_metrics(new, {"like_count": 12})
        assert new["like_count"] == 0

    def test_missing_key_is_filled_from_existing(self):
        new = {}
        preserve_existing_metrics(new, {"comment_count": 7})
        assert new["comment_count"] == 7

    def test_existing_negative_marker_is_not_carried(self):
        new = {"like_count": None}
        preserve_existing_metrics(new, {"like_count": -1})
        assert new["like_count"] is None

    def test_all_metric_fields_covered(self):
        new = {}
        existing = {
            "like_count": 1,
            "comment_count": 2,
            "share_count": 3,
            "quote_count": 4,
            "bookmark_count": 5,
            "view_count": 6,
        }
        preserve_existing_metrics(new, existing)
        assert new == existing

    def test_non_dict_input_is_safe(self):
        assert preserve_existing_metrics(None, {"like_count": 1}) is None
