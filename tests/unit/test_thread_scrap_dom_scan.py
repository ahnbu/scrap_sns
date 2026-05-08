from datetime import datetime

from thread_scrap import append_dom_posts_from_candidates, scroll_saved_page


class FakePage:
    def __init__(self):
        self.scripts = []

    def evaluate(self, script):
        self.scripts.append(script)


def test_append_dom_posts_from_candidates_adds_scroll_rendered_post():
    collected_data = [
        {
            "platform_id": "DYCf3iYHdem",
            "username": "peers_community_office",
        }
    ]
    all_posts_map = {
        "DYCf3iYHdem": collected_data[0],
    }
    candidates = [
        {
            "href": "/@ee.yxx/post/DYBIicQkumF",
            "text": "ee.yxx\n1일\n아 클로드로 피피티 만드는 사람들\n진짜 대체 어떻게 만들고 있는거야.\n262\n99",
            "images": [],
        }
    ]

    added = append_dom_posts_from_candidates(
        candidates=candidates,
        start_time_dt=datetime(2026, 5, 8, 13, 30, 29),
        collected_data=collected_data,
        all_posts_map=all_posts_map,
        existing_codes=set(all_posts_map),
        source="scroll_dom",
    )

    assert added == 1
    assert collected_data[1]["platform_id"] == "DYBIicQkumF"
    assert collected_data[1]["username"] == "ee.yxx"
    assert collected_data[1]["source"] == "scroll_dom"
    assert collected_data[1]["url"] == "https://www.threads.com/@ee.yxx/post/DYBIicQkumF"
    assert collected_data[1]["created_at"] == "2026-05-07 13:30:29"
    assert "아 클로드로 피피티" in collected_data[1]["full_text"]


def test_append_dom_posts_from_candidates_skips_existing_and_collected_codes():
    collected_data = [
        {"platform_id": "DYCf3iYHdem", "username": "peers_community_office"},
    ]
    all_posts_map = {
        "DYCf3iYHdem": collected_data[0],
        "DYCB4gpiXE8": {"platform_id": "DYCB4gpiXE8", "username": "habitcoach2"},
    }
    candidates = [
        {
            "href": "/@peers_community_office/post/DYCf3iYHdem",
            "text": "peers_community_office\n16시간\n이미 수집된 글",
            "images": [],
        },
        {
            "href": "/@habitcoach2/post/DYCB4gpiXE8",
            "text": "habitcoach2\n20시간\n기존 DB 글",
            "images": [],
        },
    ]

    added = append_dom_posts_from_candidates(
        candidates=candidates,
        start_time_dt=datetime(2026, 5, 8, 13, 30, 29),
        collected_data=collected_data,
        all_posts_map=all_posts_map,
        existing_codes=set(all_posts_map),
        source="scroll_dom",
    )

    assert added == 0
    assert len(collected_data) == 1


def test_scroll_saved_page_uses_incremental_scroll_instead_of_bottom_jump():
    page = FakePage()

    scroll_saved_page(page)

    assert page.scripts
    assert "scrollBy" in page.scripts[0]
    assert "document.body.scrollHeight" not in page.scripts[0]
