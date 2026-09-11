/**
 * 볼트 자료 검증 전용 서버. 운영 볼트·운영 인덱스 파일을 건드리지 않는다.
 *
 * 표본 볼트(tests/fixtures/golden/library/vault)를 임시 폴더에 복사하고, 서버가
 * 그 사본만 보도록(`SNS_LIBRARY_VAULT`) 띄운다. 인덱스 산출물도 임시 경로로
 * 보낸다(`SNS_LIBRARY_INDEX_PATH`) - 안 그러면 운영 `web_viewer/sns_library_index.json`
 * 을 표본으로 덮어 CLI 결과가 틀어진다.
 *
 * 볼트 편집 → 화면 반영(60초) 검증과 악성 노트 렌더 검증이 이 서버를 쓴다 -
 * 운영 볼트 노트를 고쳤다 되돌리는 방식은 되돌리기가 실패하면 볼트가 더러워진다.
 *
 * 포트 17602 는 포트 대장(D:/vibe-coding/_ports/PORTS.md)이 이 레포에 예약해 둔
 * 백업 번호다(17601 은 벤치마킹 검증 서버가 쓴다).
 * 계획: _docs/20260911_01 (W2 검증)
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_PORT = Number(process.env.SNS_LIBRARY_VERIFY_PORT || 17602);
const FIXTURE_VAULT = path.join('tests', 'fixtures', 'golden', 'library', 'vault');
const READY_TIMEOUT_MS = 90000;

async function waitForReady(baseUrl, child) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`검증 서버가 기동 중 종료됐다 (exit ${child.exitCode})`);
    }
    try {
      const res = await fetch(`${baseUrl}api/status`);
      if (res.ok) return;
    } catch {
      // 아직 안 떴다.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`검증 서버가 ${READY_TIMEOUT_MS}ms 안에 준비되지 않았다`);
}

/**
 * @returns {Promise<{baseUrl: string, vaultPath: string, indexPath: string, stop: () => Promise<void>}>}
 *   `vaultPath` 는 임시 사본이다. 검증이 마음대로 고쳐도 된다.
 */
export async function startLibraryVerifyServer(options = {}) {
  const port = Number(options.port || DEFAULT_PORT);
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sns-library-verify-'));
  const vaultPath = path.join(workDir, 'vault');
  fs.cpSync(FIXTURE_VAULT, vaultPath, { recursive: true });
  const indexPath = path.join(workDir, 'sns_library_index.json');
  // 계정 연결 파일. 재시작 후 유지를 보려면 호출자가 작업 폴더 밖 경로를 넘긴다
  // (stop() 이 작업 폴더를 지우므로). 운영 web_viewer/sns_creator_links.json 은 쓰지 않는다.
  const linksPath = options.linksPath || path.join(workDir, 'sns_creator_links.json');
  // 뷰어 상태 파일도 운영 사본을 작업 폴더에 두고 가리킨다. 검증 페이지는 로드 때 자동
  // 태그를 적용해 태그 파일 전체를 저장하므로, 운영 파일을 같이 쓰면 표본 볼트 키가 운영
  // 태그에 섞인다(2026-09-11 실측 4건 → 재실행으로 6건). 계획: _docs/20260911_02 (W2 T2-b)
  const stateEnv = {};
  for (const [envName, fileName] of [
    ['SNS_TAGS_PATH', 'sns_tags.json'],
    ['SNS_TAG_CATALOG_PATH', 'sns_tag_catalog.json'],
    ['SNS_USER_METADATA_PATH', 'sns_user_metadata.json'],
  ]) {
    const source = path.join('web_viewer', fileName);
    const target = path.join(workDir, fileName);
    if (fs.existsSync(source)) fs.copyFileSync(source, target);
    stateEnv[envName] = target;
  }

  const child = spawn('python', ['scrap_sns_server.py'], {
    env: {
      ...process.env,
      PORT: String(port),
      SNS_LIBRARY_VAULT: vaultPath,
      SNS_LIBRARY_INDEX_PATH: indexPath,
      SNS_CREATOR_LINKS_PATH: linksPath,
      ...stateEnv,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const logs = [];
  child.stdout.on('data', (chunk) => logs.push(String(chunk)));
  child.stderr.on('data', (chunk) => logs.push(String(chunk)));

  const baseUrl = `http://127.0.0.1:${port}/`;
  let stopped = false;
  const stop = async () => {
    if (stopped) return;
    stopped = true;
    if (child.exitCode === null) {
      child.kill();
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 5000);
        child.once('exit', () => { clearTimeout(timer); resolve(); });
      });
    }
    fs.rmSync(workDir, { recursive: true, force: true });
  };

  try {
    await waitForReady(baseUrl, child);
  } catch (error) {
    await stop();
    throw new Error(`${error.message}\n${logs.join('').slice(-2000)}`);
  }
  return { baseUrl, vaultPath, indexPath, linksPath, stop };
}
