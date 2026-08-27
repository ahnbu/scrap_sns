import json
import os
import subprocess
import sys
from pathlib import Path


def test_merge_results_excludes_duplicate_of_canonical_threads(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    script = r"""
import json
from pathlib import Path
import total_scrap

threads_dir = Path("output_threads/python")
threads_dir.mkdir(parents=True)
(threads_dir / "threads_py_full_20260623.json").write_text(
    '''
    {
      "metadata": {"total_count": 2},
      "posts": [
        {
          "platform_id": "DYk4nq4ExZn",
          "code": "DYk4nq4ExZn",
          "username": "oatplat_",
          "sns_platform": "threads",
          "detail_status": "duplicate_of_canonical",
          "duplicate_of": "DYizvvNE_Kf",
          "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn"
        },
        {
          "platform_id": "DYizvvNE_Kf",
          "code": "DYizvvNE_Kf",
          "username": "tonyahn_80",
          "sns_platform": "threads",
          "full_text": "canonical",
          "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
        }
      ]
    }
    ''',
    encoding="utf-8-sig",
)

total_scrap.OUTPUT_THREADS_DIR = str(threads_dir)
total_scrap.OUTPUT_LINKEDIN_DIR = "output_linkedin"
total_scrap.OUTPUT_TWITTER_DIR = "output_twitter"
total_scrap.OUTPUT_YOUTUBE_DIR = "output_youtube"
# 내 게시물 디렉터리도 tmp 로 돌려놔야 한다. 비워두면 절대경로 기본값이 남아
# 실제 레포의 내 글이 이 테스트 결과에 섞인다(계획 _docs/20260826_03 3.4.1).
total_scrap.OUTPUT_LINKEDIN_OWN_DIR = "output_linkedin_own"
total_scrap.OUTPUT_THREADS_OWN_DIR = "output_threads_own"

posts, threads_count, linkedin_count, twitter_count, youtube_count = total_scrap.merge_results()
print(json.dumps({
    "codes": [post["code"] for post in posts],
    "threads_count": threads_count,
    "linkedin_count": linkedin_count,
    "twitter_count": twitter_count,
    "youtube_count": youtube_count,
}, ensure_ascii=False))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload == {
        "codes": ["DYizvvNE_Kf"],
        "threads_count": 1,
        "linkedin_count": 0,
        "twitter_count": 0,
        "youtube_count": 0,
    }
