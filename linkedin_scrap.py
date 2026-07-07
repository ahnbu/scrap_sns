from utils.common import clean_text, load_json, save_json
import json
import sys
import os
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from utils.json_to_md import convert_json_to_md
from utils.linkedin_parser import extract_urn_id
from scripts.linkedin_opencli_shadow_parse import parse_shadow_raw

# --- 설정 ---
TARGET_URL = "https://www.linkedin.com/my-items/saved-posts/"
DATA_DIR = "output_linkedin/python"
UPDATE_DIR = os.path.join(DATA_DIR, "update")
OPENCLI_RUNTIME_DIR = os.path.join("output_linkedin", "opencli_runtime")
OPENCLI_PRODUCTION_SESSION = "linkedin_saved_production"

# CLI 인자 파싱
CRAWL_MODE = "update only"  # 기본값 (__main__ 블록에서 CLI 인자로 덮어씀)
CRAWL_START_TIME = datetime.now()

# --- 헬퍼 함수 ---


# 로컬 clean_text 제거 (utils.common 사용)

def configure_text_output(stream=None):
    target = stream or sys.stdout
    encoding = (getattr(target, "encoding", "") or "").lower()
    if encoding and encoding != "utf-8" and hasattr(target, "reconfigure"):
        target.reconfigure(encoding="utf-8", errors="replace")


def get_opencli_command():
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = (
            Path(appdata)
            / "npm"
            / "node_modules"
            / "@jackwener"
            / "opencli"
            / "dist"
            / "src"
            / "main.js"
        )
        if candidate.exists():
            return ["node", str(candidate)]
    return ["opencli"]


def parse_json_stdout(stdout):
    text = (stdout or "").lstrip("\ufeff").strip()
    if not text:
        raise RuntimeError("OpenCLI command returned empty stdout")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenCLI command returned non-JSON stdout: {text[:200]}") from exc


def run_opencli_whoami():
    command = get_opencli_command() + [
        "linkedin",
        "whoami",
        "--site-session",
        "persistent",
        "-f",
        "json",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI LinkedIn session is not logged in: {message}")

    payload = parse_json_stdout(result.stdout)
    if not payload.get("logged_in"):
        raise RuntimeError("OpenCLI LinkedIn session is not logged in")
    return payload


def run_opencli_collector(crawl_start_time, session=OPENCLI_PRODUCTION_SESSION):
    stamp = crawl_start_time.strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(OPENCLI_RUNTIME_DIR, "raw", stamp)
    command = [
        "node",
        "scripts/linkedin_opencli_shadow_collect.mjs",
        "--session",
        session,
        "--url",
        TARGET_URL,
        "--out",
        raw_dir,
        "--until-exhausted",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI LinkedIn collection failed: {message}")

    summary = parse_json_stdout(result.stdout)
    if int(summary.get("pages_collected") or 0) <= 0:
        raise RuntimeError("OpenCLI collection returned no raw pages")
    if int(summary.get("total_unique_activity_ids") or 0) <= 0:
        raise RuntimeError("OpenCLI collection returned no activity IDs")
    return raw_dir, summary


def validate_opencli_payload(payload):
    metadata = payload.get("metadata") or {}
    if int(metadata.get("parsed_post_count") or 0) <= 0:
        raise RuntimeError("OpenCLI parsed post count is zero")
    if int(metadata.get("duplicate_platform_id_count") or 0) > 0:
        raise RuntimeError("OpenCLI duplicate platform_id detected")
    if int(metadata.get("parser_failed_count") or 0) > 0:
        raise RuntimeError("OpenCLI parser failed for one or more posts")
    if int(metadata.get("entity_without_save_state_count") or 0) > 0:
        raise RuntimeError("OpenCLI SaveState verification failed")
    if int(metadata.get("entity_without_cluster_reference_count") or 0) > 0:
        raise RuntimeError("OpenCLI cluster reference verification failed")


def collect_opencli_posts(crawl_start_time):
    whoami = run_opencli_whoami()
    print(f"✅ OpenCLI LinkedIn 로그인 확인: {whoami.get('site', 'linkedin')}")

    raw_dir, collection_summary = run_opencli_collector(crawl_start_time)
    print(
        "📥 OpenCLI raw 수집 완료: "
        f"{collection_summary.get('pages_collected')} pages, "
        f"{collection_summary.get('total_unique_activity_ids')} unique IDs"
    )

    payload = parse_shadow_raw(raw_dir, crawl_start_time, require_save_state=True)
    validate_opencli_payload(payload)
    metadata = payload["metadata"]
    print(
        "✅ OpenCLI parse 검증 통과: "
        f"parsed={metadata.get('parsed_post_count')}, "
        f"duplicates={metadata.get('duplicate_platform_id_count')}, "
        f"parser_failed={metadata.get('parser_failed_count')}"
    )
    metadata["opencli_collection"] = collection_summary
    metadata["opencli_whoami"] = {
        "site": whoami.get("site"),
        "logged_in": whoami.get("logged_in"),
        "public_id": whoami.get("public_id"),
    }
    return payload["posts"], metadata


def get_post_identity(post):
    return post.get("platform_id") or post.get("code")


def merge_linkedin_full_posts(old_posts, scraped_posts, crawl_mode):
    old_by_id = {}
    old_order = []
    for post in old_posts:
        pid = get_post_identity(post)
        if not pid or pid in old_by_id:
            continue
        old_by_id[pid] = post
        old_order.append(pid)

    final_by_id = dict(old_by_id)
    observed_existing_ids = []
    new_items = []

    for post in scraped_posts:
        pid = get_post_identity(post)
        if not pid:
            continue

        existing = old_by_id.get(pid)
        if existing:
            merged = {**existing, **post}
            if existing.get("sequence_id") is not None:
                merged["sequence_id"] = existing.get("sequence_id")
            if existing.get("crawled_at"):
                merged["crawled_at"] = existing.get("crawled_at")
            if existing.get("local_images") and not post.get("local_images"):
                merged["local_images"] = existing.get("local_images")
            final_by_id[pid] = merged
            observed_existing_ids.append(pid)
        else:
            final_by_id[pid] = post
            new_items.append(post)

    observed_existing = set(observed_existing_ids)
    unobserved_existing_ids = [pid for pid in old_order if pid not in observed_existing]

    final_posts = list(final_by_id.values())
    final_posts.sort(key=lambda item: item.get("sequence_id", 0), reverse=True)

    merge_report = {
        "crawl_mode": crawl_mode,
        "observed_existing_count": len(observed_existing),
        "unobserved_existing_count": len(unobserved_existing_ids),
        "unobserved_existing_ids": unobserved_existing_ids[:20],
    }

    return final_posts, new_items, merge_report

class LinkedinScraper:
    def __init__(self):
        self.posts = [] # collected data
        self.new_posts_count = 0
        self.stopped_early = False
        self.collected_codes = set()
        
        # 기존 데이터 로드 (증분 업데이트용)
        self.existing_codes = set()
        self.existing_posts_map = {}
        self.max_sequence_id = 0
        self.consecutive_existing_count = 0
        
        # 전체 파일 경로 (가장 최근 날짜 파일 찾기)
        self.full_file_path = self.get_latest_full_file()
            
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj

            for p in full_posts:
                pid = p.get("platform_id") or p.get("code")
                if pid:
                    self.existing_codes.add(pid)
                    self.existing_posts_map[pid] = p
            
            if isinstance(full_data_obj, dict):
                self.max_sequence_id = full_data_obj.get("metadata", {}).get("max_sequence_id", 0)
            
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨. 현재 max_sequence_id: {self.max_sequence_id}")
            if CRAWL_MODE == "update only":
                print(
                    f"🔄 UPDATE ONLY 모드: 기존 {len(self.existing_codes)}건과 대조, "
                    "OpenCLI 현재 저장목록과 보수 병합합니다."
                )

    def get_latest_full_file(self):
        if not os.path.exists(DATA_DIR):
            return None
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("linkedin_py_full_") and f.endswith(".json")]
        if not files:
            return None
        # 날짜순 정렬 (파일명에 YYYYMMDD가 포함되어 있으므로 문자열 정렬 가능)
        files.sort(reverse=True)
        return os.path.join(DATA_DIR, files[0])

    def run(self):
        start_time_dt = datetime.now()
        print("🚀 링크드인 스크래퍼 시작 (OpenCLI 기본 모드)")

        self.posts, self.opencli_metadata = collect_opencli_posts(CRAWL_START_TIME)
        self.save_results()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        print("\n" + "="*40)
        print(f"시작시간 : {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"종료시간 : {end_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요시간: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print("="*40)

    def save_results(self):
        if not self.posts:
            print("ℹ️ 수집된 새로운 데이터가 없습니다.")
            return

        date_str = CRAWL_START_TIME.strftime("%Y%m%d")
        full_file, final_posts, new_items = self.update_full_version(date_str)

        # 신규 수집된 것들만 업데이트 파일에 저장
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"linkedin_python_update_{timestamp}.json")
        final_indexed_posts = []
        for idx, post in enumerate(new_items):
            final_indexed_posts.append({"index": idx + 1, **post})

        if final_indexed_posts:
            save_json(update_file, final_indexed_posts)
            print(f"💾 업데이트 데이터 저장 완료: {update_file} ({len(final_indexed_posts)}개)")
        else:
            print("ℹ️ 신규 LinkedIn 저장글은 없습니다.")

        print(f"✅ LinkedIn full 저장 기준: {full_file} (총 {len(final_posts)}개)")

    def update_full_version(self, date_str):
        print("🔄 전체 데이터 병합 중...")
        
        # 기존 전체 데이터 로드
        old_posts = []
        existing_merge_history = []
        source_filename = None

        if self.full_file_path:
            source_filename = os.path.basename(self.full_file_path)
            old_data_obj = load_json(self.full_file_path)
            if isinstance(old_data_obj, dict):
                old_posts = old_data_obj.get("posts", [])
                existing_merge_history = old_data_obj.get("metadata", {}).get("merge_history", [])
            else:
                old_posts = old_data_obj

        final_posts, new_items, merge_report = merge_linkedin_full_posts(
            old_posts,
            self.posts,
            CRAWL_MODE,
        )
        duplicate_count = len(self.posts) - len(new_items)

        new_items.sort(key=lambda item: item.get("crawled_at", ""))
        for post in new_items:
            if not post.get("sequence_id"):
                self.max_sequence_id += 1
                post["sequence_id"] = self.max_sequence_id

        # sequence_id 기준으로 내림차순 정렬 (최신순)
        final_posts.sort(key=lambda x: x.get("sequence_id", 0), reverse=True)

        # merge_history 업데이트
        merge_history = list(existing_merge_history)
        if new_items:
            merge_history.append({
                "merged_at": datetime.now().isoformat(),
                "new_items_count": len(new_items),
                "duplicates_removed": duplicate_count,
                "source_file": source_filename,
                "crawl_mode": CRAWL_MODE,
                "observed_existing_count": merge_report["observed_existing_count"],
                "unobserved_existing_count": merge_report["unobserved_existing_count"],
                "unobserved_existing_ids": merge_report["unobserved_existing_ids"],
            })

        full_file = os.path.join(DATA_DIR, f"linkedin_py_full_{date_str}.json")
        
        # 메타데이터 구조 (JS 버전 참고)
        legacy_count = len([p for p in final_posts if "crawled_at" not in p])
        verified_count = len(final_posts) - legacy_count
        opencli_metadata = getattr(self, "opencli_metadata", {}) or {}
        opencli_collection = opencli_metadata.get("opencli_collection") or {}
        opencli_whoami = opencli_metadata.get("opencli_whoami") or {}

        full_data = {
            "metadata": {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "first_code": (final_posts[0].get("platform_id") or final_posts[0].get("code")) if final_posts else None,
                "last_code": (final_posts[-1].get("platform_id") or final_posts[-1].get("code")) if final_posts else None,
                "crawl_mode": CRAWL_MODE,
                "legacy_data_count": legacy_count,
                "verified_data_count": verified_count,
                "collector": "opencli",
                "opencli_logged_in": opencli_whoami.get("logged_in"),
                "opencli_site": opencli_whoami.get("site"),
                "opencli_public_id": opencli_whoami.get("public_id"),
                "opencli_raw_pages": opencli_collection.get("pages_collected"),
                "opencli_unique_activity_ids": opencli_collection.get("total_unique_activity_ids"),
                "opencli_parsed_post_count": opencli_metadata.get("parsed_post_count"),
                "opencli_duplicate_platform_id_count": opencli_metadata.get("duplicate_platform_id_count"),
                "opencli_parser_failed_count": opencli_metadata.get("parser_failed_count"),
                "opencli_entity_without_save_state_count": opencli_metadata.get("entity_without_save_state_count"),
                "opencli_entity_without_cluster_reference_count": opencli_metadata.get("entity_without_cluster_reference_count"),
                "all_mode_observed_existing_count": merge_report["observed_existing_count"],
                "all_mode_unobserved_existing_count": merge_report["unobserved_existing_count"],
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 파일 저장 완료: {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)
        return full_file, final_posts, new_items

if __name__ == "__main__":
    configure_text_output(sys.stdout)
    configure_text_output(sys.stderr)
    parser = argparse.ArgumentParser(description='LinkedIn 스크래퍼')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    args = parser.parse_args()
    CRAWL_MODE = "update only" if args.mode == "update" else "all"
    scraper = LinkedinScraper()
    scraper.run()
