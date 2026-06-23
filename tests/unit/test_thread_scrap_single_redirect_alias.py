import json
from datetime import datetime

from thread_scrap_single import (
    _apply_redirect_metadata,
    import_from_simple_database,
    promote_to_full_history,
)
from utils.threads_http_adapter import ThreadsFetchResult


def test_apply_redirect_metadata_marks_redirect_alias_to_canonical():
    result = ThreadsFetchResult(
        html="<html></html>",
        status_code=200,
        requested_url="https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
        final_url="https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
        redirect_chain=[
            {
                "status_code": 301,
                "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                "location": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
            }
        ],
    )

    items = _apply_redirect_metadata(
        [
            {
                "code": "DYizvvNE_Kf",
                "username": "tonyahn_80",
                "display_name": "AI컨설턴트 안재윤",
                "full_text": "canonical text",
            }
        ],
        result,
        requested_code="DYk4nq4ExZn",
        requested_username="oatplat_",
    )

    assert items[0]["code"] == "DYizvvNE_Kf"
    assert items[0]["username"] == "tonyahn_80"
    assert items[0]["detail_status"] == "redirected"
    assert items[0]["requested_url"] == "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn"
    assert items[0]["final_url"] == "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
    assert items[0]["canonical_code"] == "DYizvvNE_Kf"
    assert items[0]["canonical_username"] == "tonyahn_80"


def test_promote_redirect_alias_does_not_create_duplicate_canonical_card(tmp_path):
    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    today = datetime.now().strftime("%Y%m%d")
    full_path = output_dir / f"threads_py_full_{today}.json"
    simple_path = output_dir / f"threads_py_simple_{today}.json"
    full_path.write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "total_count": 2, "max_sequence_id": 933},
                "posts": [
                    {
                        "sequence_id": 933,
                        "platform_id": "DYk4nq4ExZn",
                        "code": "DYk4nq4ExZn",
                        "username": "oatplat_",
                        "display_name": "오트플랫 |",
                        "full_text": "",
                        "media": ["https://example.com/alias.jpg"],
                        "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                        "sns_platform": "threads",
                        "source": "network",
                        "is_detail_collected": False,
                    },
                    {
                        "sequence_id": 922,
                        "platform_id": "DYizvvNE_Kf",
                        "code": "DYizvvNE_Kf",
                        "username": "tonyahn_80",
                        "display_name": "AI컨설턴트 안재윤",
                        "full_text": "existing canonical",
                        "media": ["https://example.com/canonical.jpg"],
                        "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                        "sns_platform": "threads",
                        "created_at": "2026-05-21",
                        "source": "consumer_detail",
                        "is_detail_collected": True,
                    },
                ],
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8-sig",
    )
    simple_path.write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "total_count": 1, "max_sequence_id": 933},
                "posts": [
                    {
                        "sequence_id": 933,
                        "platform_id": "DYk4nq4ExZn",
                        "code": "DYk4nq4ExZn",
                        "username": "oatplat_",
                        "display_name": "오트플랫 |",
                        "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                        "sns_platform": "threads",
                        "created_at": "2026-06-14",
                    }
                ],
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8-sig",
    )

    promote_to_full_history(
        {
            "DYk4nq4ExZn": [
                {
                    "platform_id": "DYizvvNE_Kf",
                    "code": "DYizvvNE_Kf",
                    "username": "tonyahn_80",
                    "display_name": "AI컨설턴트 안재윤",
                    "full_text": "redirected canonical",
                    "media": ["https://example.com/canonical.jpg"],
                    "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                    "sns_platform": "threads",
                    "root_code": "DYk4nq4ExZn",
                    "detail_status": "redirected",
                    "requested_url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                    "final_url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                    "canonical_code": "DYizvvNE_Kf",
                    "canonical_username": "tonyahn_80",
                    "source": "consumer_detail",
                    "created_at": "2026-05-21",
                    "taken_at": 1779244470,
                }
            ]
        },
        output_dir=str(output_dir),
    )

    saved = json.loads(full_path.read_text(encoding="utf-8-sig"))
    codes = [post["code"] for post in saved["posts"]]
    canonical = next(post for post in saved["posts"] if post["code"] == "DYizvvNE_Kf")
    simple_saved = json.loads(simple_path.read_text(encoding="utf-8-sig"))

    assert codes.count("DYizvvNE_Kf") == 1
    assert "DYk4nq4ExZn" not in codes
    assert canonical["redirect_aliases"] == [
        {
            "code": "DYk4nq4ExZn",
            "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
            "username": "oatplat_",
        }
    ]
    assert simple_saved["posts"][0]["detail_status"] == "duplicate_of_canonical"
    assert simple_saved["posts"][0]["duplicate_of"] == "DYizvvNE_Kf"


def test_import_from_simple_database_skips_duplicate_of_canonical(tmp_path):
    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    today = datetime.now().strftime("%Y%m%d")
    (output_dir / f"threads_py_simple_{today}.json").write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "total_count": 1, "max_sequence_id": 933},
                "posts": [
                    {
                        "sequence_id": 933,
                        "platform_id": "DYk4nq4ExZn",
                        "code": "DYk4nq4ExZn",
                        "username": "oatplat_",
                        "display_name": "오트플랫 |",
                        "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                        "sns_platform": "threads",
                        "created_at": "2026-06-14",
                        "detail_status": "duplicate_of_canonical",
                        "duplicate_of": "DYizvvNE_Kf",
                    }
                ],
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8-sig",
    )
    full_path = output_dir / f"threads_py_full_{today}.json"
    full_path.write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "total_count": 1, "max_sequence_id": 922},
                "posts": [
                    {
                        "sequence_id": 922,
                        "platform_id": "DYizvvNE_Kf",
                        "code": "DYizvvNE_Kf",
                        "username": "tonyahn_80",
                        "display_name": "AI컨설턴트 안재윤",
                        "full_text": "existing canonical",
                        "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                        "sns_platform": "threads",
                        "created_at": "2026-05-21",
                    }
                ],
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8-sig",
    )

    import_from_simple_database(output_dir=str(output_dir))

    saved = json.loads(full_path.read_text(encoding="utf-8-sig"))
    assert [post["code"] for post in saved["posts"]] == ["DYizvvNE_Kf"]
