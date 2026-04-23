import hashlib
import json
import subprocess


def _image_name(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest() + ".jpg"


def test_backfill_local_images_dry_run_and_apply(tmp_path):
    media_url = "https://cdn.example.com/path/image.jpg?token=abc"
    image_root = tmp_path / "images"
    image_root.mkdir()
    (image_root / _image_name(media_url)).write_bytes(b"image")

    target = tmp_path / "total_full_20990101.json"
    target.write_text(
        json.dumps(
            {
                "metadata": {"total_count": 1, "max_sequence_id": 1},
                "posts": [
                    {
                        "sequence_id": 1,
                        "platform_id": "ABC123",
                        "sns_platform": "threads",
                        "code": "ABC123",
                        "username": "alice",
                        "full_text": "hello",
                        "media": [media_url],
                        "local_images": [],
                        "url": "https://www.threads.com/@alice/post/ABC123",
                        "created_at": "2026-04-13 00:00:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    dry_run = subprocess.run(
        [
            "node",
            "utils/backfill_local_images.mjs",
            "--target",
            str(target),
            "--image-root",
            str(image_root),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dry_result = json.loads(dry_run.stdout)
    assert dry_result["mode"] == "dry-run"
    assert dry_result["recoverablePosts"] == 1
    assert dry_result["recoveredImages"] == 1
    assert json.loads(target.read_text(encoding="utf-8"))["posts"][0]["local_images"] == []

    applied = subprocess.run(
        [
            "node",
            "utils/backfill_local_images.mjs",
            "--target",
            str(target),
            "--image-root",
            str(image_root),
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    apply_result = json.loads(applied.stdout)
    assert apply_result["mode"] == "apply"
    assert apply_result["backup"]

    data = json.loads(target.read_text(encoding="utf-8-sig"))
    assert data["posts"][0]["local_images"] == [
        f"web_viewer/images/{_image_name(media_url)}"
    ]
