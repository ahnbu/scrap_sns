import json
from pathlib import Path
from datetime import datetime

WORK_DIR = Path(__file__).resolve().parent
RESULT_DIR = WORK_DIR / "results"
REF_FILE = RESULT_DIR / "scrap_single_post_test_result.json"
CUR_FILE = RESULT_DIR / "thread_scrap_single_current_logic_result.json"
REPORT_MD = RESULT_DIR / "comparison_report_75058dc_vs_current.md"
REPORT_JSON = RESULT_DIR / "comparison_report_75058dc_vs_current.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def index_results(payload):
    out = {}
    for r in payload.get("results", []):
        target = r.get("target", {})
        code = target.get("code")
        if code:
            out[code] = r
    return out


def item_map(result):
    return {i.get("code"): i for i in result.get("items", []) if i.get("code")}


def main():
    ref = load_json(REF_FILE)
    cur = load_json(CUR_FILE)

    ref_idx = index_results(ref)
    cur_idx = index_results(cur)
    all_codes = sorted(set(ref_idx.keys()) | set(cur_idx.keys()))

    details = []
    for code in all_codes:
        r = ref_idx.get(code, {"items": [], "reason": "missing", "ok": False})
        c = cur_idx.get(code, {"items": [], "reason": "missing", "ok": False})

        r_items = item_map(r)
        c_items = item_map(c)

        r_set = set(r_items.keys())
        c_set = set(c_items.keys())

        detail = {
            "target_code": code,
            "reference": {
                "ok": r.get("ok", False),
                "reason": r.get("reason"),
                "item_count": len(r_set),
            },
            "current": {
                "ok": c.get("ok", False),
                "reason": c.get("reason"),
                "item_count": len(c_set),
            },
            "diff": {
                "only_in_reference": sorted(r_set - c_set),
                "only_in_current": sorted(c_set - r_set),
                "common": sorted(r_set & c_set),
            },
        }
        details.append(detail)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "target_count": len(all_codes),
        "reference_success": ref.get("summary", {}).get("success_targets", 0),
        "current_success": cur.get("summary", {}).get("success_targets", 0),
        "reference_total_items": ref.get("summary", {}).get("total_items", 0),
        "current_total_items": cur.get("summary", {}).get("total_items", 0),
    }

    report = {
        "summary": summary,
        "details": details,
        "root_cause_hypothesis": [
            "current logic reads only data.data.thread_items path; tested pages did not expose items there.",
            "reference logic supports edges/containing_thread/thread_items and applies author-consistency filtering.",
            "result: reference extracted 9 items from 4 targets; current extracted 0.",
        ],
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# Threads 단건 수집 비교 리포트 (75058dc 기준)")
    lines.append("")
    lines.append(f"- 생성시각: {summary['generated_at']}")
    lines.append(f"- 대상 URL 수: {summary['target_count']}")
    lines.append(f"- 참조 로직 성공: {summary['reference_success']}/4, 총 아이템 {summary['reference_total_items']}건")
    lines.append(f"- 현재 로직 성공: {summary['current_success']}/4, 총 아이템 {summary['current_total_items']}건")
    lines.append("")
    lines.append("## 타깃별 비교")
    lines.append("")
    lines.append("| target_code | 참조(item/reason) | 현재(item/reason) | 참조만 존재 code 수 |")
    lines.append("|---|---:|---:|---:|")

    for d in details:
        lines.append(
            f"| {d['target_code']} | {d['reference']['item_count']} / {d['reference']['reason']} | "
            f"{d['current']['item_count']} / {d['current']['reason']} | {len(d['diff']['only_in_reference'])} |"
        )

    lines.append("")
    lines.append("## 핵심 차이")
    lines.append("")
    lines.append("- 참조(75058dc 계열): `edges`, `containing_thread`, `thread_items` 3경로를 모두 탐색")
    lines.append("- 현재(`thread_scrap_single.py`): `data.data.thread_items` 단일 경로에 의존")
    lines.append("- 이번 4개 URL에서는 단일 경로에서 아이템이 비어 `no_items_extracted` 발생")
    lines.append("")
    lines.append("## 재현 결과 파일")
    lines.append("")
    lines.append(f"- 참조 실행 결과: `{REF_FILE.as_posix()}`")
    lines.append(f"- 현재 실행 결과: `{CUR_FILE.as_posix()}`")
    lines.append(f"- 구조화 비교(JSON): `{REPORT_JSON.as_posix()}`")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(str(REPORT_MD))


if __name__ == "__main__":
    main()
