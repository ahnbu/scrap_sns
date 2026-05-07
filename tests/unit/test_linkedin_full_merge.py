import linkedin_scrap


def _post(pid, *, sequence_id, text=None, local_images=None, media=None):
    return {
        "platform_id": pid,
        "code": pid,
        "sequence_id": sequence_id,
        "sns_platform": "linkedin",
        "username": "tester",
        "display_name": "Tester",
        "full_text": text or f"text {pid}",
        "media": media if media is not None else [],
        "local_images": local_images if local_images is not None else [],
        "url": f"https://www.linkedin.com/feed/update/urn:li:activity:{pid}",
        "created_at": "2026-05-07 10:00:00",
        "date": "2026-05-07",
        "crawled_at": "2026-05-07T10:00:00",
    }


def test_all_mode_preserves_unobserved_existing_posts():
    old_posts = [
        _post("A", sequence_id=4),
        _post("B", sequence_id=3),
        _post("C", sequence_id=2),
        _post("D", sequence_id=1, local_images=["web_viewer/images/d.jpg"]),
    ]
    scraped_posts = [
        _post("A", sequence_id=4, text="updated A"),
        _post("B", sequence_id=3),
        _post("C", sequence_id=2),
        _post("E", sequence_id=5),
    ]

    final_posts, new_items, merge_report = linkedin_scrap.merge_linkedin_full_posts(
        old_posts,
        scraped_posts,
        crawl_mode="all",
    )

    final_ids = [post["platform_id"] for post in final_posts]

    assert final_ids == ["E", "A", "B", "C", "D"]
    assert [post["platform_id"] for post in new_items] == ["E"]
    assert merge_report["observed_existing_count"] == 3
    assert merge_report["unobserved_existing_count"] == 1
    assert merge_report["unobserved_existing_ids"] == ["D"]
    assert next(post for post in final_posts if post["platform_id"] == "D")[
        "local_images"
    ] == ["web_viewer/images/d.jpg"]


def test_all_mode_preserves_existing_metadata_when_post_is_observed_again():
    old_posts = [
        _post(
            "A",
            sequence_id=10,
            local_images=["web_viewer/images/a.jpg"],
            media=["https://cdn.example.com/a.jpg"],
        )
    ]
    scraped_posts = [
        {
            **_post(
                "A",
                sequence_id=10,
                text="newer text",
                media=["https://cdn.example.com/a2.jpg"],
            ),
            "crawled_at": "2026-05-07T11:00:00",
            "local_images": [],
        }
    ]

    final_posts, new_items, merge_report = linkedin_scrap.merge_linkedin_full_posts(
        old_posts,
        scraped_posts,
        crawl_mode="all",
    )

    assert len(final_posts) == 1
    assert new_items == []
    assert final_posts[0]["sequence_id"] == 10
    assert final_posts[0]["crawled_at"] == "2026-05-07T10:00:00"
    assert final_posts[0]["local_images"] == ["web_viewer/images/a.jpg"]
    assert final_posts[0]["full_text"] == "newer text"
    assert merge_report["observed_existing_count"] == 1
    assert merge_report["unobserved_existing_count"] == 0
