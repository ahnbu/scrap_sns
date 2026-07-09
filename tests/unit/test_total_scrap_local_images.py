import json
import os
import subprocess
import sys
from pathlib import Path


def test_collect_preserved_local_images_matches_only_image_media(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    image_root = tmp_path / "web_viewer" / "images"
    image_root.mkdir(parents=True)
    (image_root / "image-one.jpg").write_bytes(b"one")
    (image_root / "image-two.jpg").write_bytes(b"two")

    output_total = tmp_path / "output_total"
    output_total.mkdir()
    image_one = "https://cdn.example.com/one.jpg"
    video = "https://cdn.example.com/video.mp4"
    image_two = "https://cdn.example.com/two.jpg"
    (output_total / "total_full_20990101.json").write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "POST1",
                        "media": [image_one, video, image_two],
                        "local_images": [
                            "web_viewer/images/image-one.jpg",
                            "web_viewer/images/image-two.jpg",
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    script = f"""
import json
import total_scrap

image_one = {image_one!r}
video = {video!r}
image_two = {image_two!r}

total_scrap.PROJECT_ROOT = {str(tmp_path)!r}
total_scrap.OUTPUT_TOTAL_DIR = {str(output_total)!r}

preserved = total_scrap.collect_preserved_local_images()
print(json.dumps({{
    "image_one": preserved.get(image_one),
    "image_two": preserved.get(image_two),
    "video": preserved.get(video),
}}, ensure_ascii=False))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    preserved = json.loads(completed.stdout.strip().splitlines()[-1])
    assert preserved["image_one"] == "web_viewer/images/image-one.jpg"
    assert preserved["image_two"] == "web_viewer/images/image-two.jpg"
    assert preserved["video"] is None


def test_linkedin_signed_url_query_change_reuses_preserved_local_image(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    image_root = tmp_path / "web_viewer" / "images"
    image_root.mkdir(parents=True)
    expected_image = "web_viewer/images/linkedin-existing.jpg"
    (image_root / "linkedin-existing.jpg").write_bytes(b"linkedin")

    output_total = tmp_path / "output_total"
    output_total.mkdir()
    old_url = (
        "https://media.licdn.com/dms/image/v2/D5622AQH-image/feedshare-shrink_800/"
        "feedshare-shrink_800/0/1771147145934?e=1784764800&v=beta&t=old-token"
    )
    new_url = (
        "https://media.licdn.com/dms/image/v2/D5622AQH-image/feedshare-shrink_800/"
        "feedshare-shrink_800/0/1771147145934?e=1785369600&v=beta&t=new-token"
    )
    (output_total / "total_full_20990101.json").write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "LINKEDIN1",
                        "sns_platform": "linkedin",
                        "media": [old_url],
                        "local_images": [expected_image],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    script = f"""
import json
import total_scrap

new_url = {new_url!r}

total_scrap.PROJECT_ROOT = {str(tmp_path)!r}
total_scrap.OUTPUT_TOTAL_DIR = {str(output_total)!r}

preserved = total_scrap.collect_preserved_local_images()
fs_path, web_path = total_scrap.get_local_image_paths(new_url)
print(json.dumps({{
    "preserved": preserved.get(total_scrap.get_image_identity_key(new_url)),
    "web_path": web_path,
}}, ensure_ascii=False))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["preserved"] == expected_image
    assert payload["web_path"].startswith("web_viewer/images/")
