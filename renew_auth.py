import subprocess
import sys

from utils.auth_paths import runtime_renew_script


def main(argv: list[str]) -> int:
    target = runtime_renew_script()
    if not target.exists():
        print(f"❌ 중앙 renew 스크립트가 없습니다: {target}")
        print("먼저 scripts/sync_auth_runtime.ps1 를 실행하세요.")
        return 1
    return subprocess.run([sys.executable, str(target), *argv], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
