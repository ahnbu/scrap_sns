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
