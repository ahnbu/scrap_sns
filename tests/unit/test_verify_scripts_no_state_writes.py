"""뷰어 조회를 가짜로 바꾸는 검증 스크립트는 저장 요청도 가짜로 받아야 한다.

뷰어는 로드 때 자동 태그를 적용해 태그 맵 **전체**를 `/api/save-tags` 로 저장한다.
`/api/get-tags`·`/api/posts` 만 가짜로 바꾸고 저장·자동 태그 요청을 운영 서버로 보내면
「가짜(빈) 태그 + 자동 태그」가 운영 `web_viewer/sns_tags.json` 을 통째로 덮어쓴다.
2026-09-11 에 이 경로로 SNS 태그 키 60건이 사라지고 135건이 줄었다(백업으로 복구).

계획: _docs/20260911_02 (§9 실행 중 발견)
"""
import glob
import re

MOCKS_READ = re.compile(r"route\(\s*['\"]\*\*/api/(?:get-tags|posts)")
REQUIRED = ["save-tags", "save-tag-catalog", "save-user-metadata", "auto-tag/apply"]


def test_scripts_mocking_reads_also_mock_writes():
    offenders = {}
    for path in sorted(glob.glob("scripts/*.mjs")):
        with open(path, encoding="utf-8") as handle:
            src = handle.read()
        if not MOCKS_READ.search(src):
            continue
        missing = [name for name in REQUIRED if f"/api/{name}" not in src]
        if missing:
            offenders[path] = missing
    assert not offenders, f"조회만 가짜로 바꾸고 저장은 운영 서버로 보낸다: {offenders}"
