/**
 * 벤치마킹 검증 전용 서버. 운영 계정 파일을 건드리지 않는다.
 *
 * 종전 결함: 검증 5종이 API 로 `web_viewer/benchmark_accounts.json` 을 바꾼 뒤
 * `finally` 에서 되돌렸다. 되돌리기 한 줄에 전부를 걸었기 때문에 스크립트가
 * 중간에 죽으면 계정이 꺼진 채 굳었고, 검증 도중 사용자가 화면에서 켠 계정은
 * 통째로 덮여 사라졌다.
 *
 * 여기서는 계정 파일을 임시 경로에 복사하고 서버를 그 사본만 보도록 띄운다.
 * 되돌릴 것을 만들지 않으므로 되돌리기가 실패할 수 없다.
 *
 * `npm run restart`(scripts/restart_viewer_server.ps1)는 환경변수를 주입하지
 * 않는다 - 그 서버로 검증하면 여전히 운영 파일을 본다. 그래서 검증이 자기
 * 서버를 직접 띄운다.
 *
 * 포트 17601 은 포트 대장(D:/vibe-coding/_ports/PORTS.md)이 이 레포에 예약해
 * 둔 백업 번호다. 임의 번호를 새로 만들지 않는다.
 *
 * 계획: _docs/20260906_03 (W2)
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_PORT = Number(process.env.SNS_BENCH_VERIFY_PORT || 17601);
const SOURCE_ACCOUNTS = path.join('web_viewer', 'benchmark_accounts.json');
const READY_TIMEOUT_MS = 90000;

async function waitForReady(baseUrl, child) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`검증 서버가 기동 중 종료됐다 (exit ${child.exitCode})`);
    }
    try {
      const res = await fetch(`${baseUrl}api/get-benchmark-accounts`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data?.accounts)) return;
      }
    } catch {
      // 아직 안 떴다. 다시 시도한다.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`검증 서버가 ${READY_TIMEOUT_MS}ms 안에 준비되지 않았다`);
}

/**
 * 검증 전용 서버를 띄운다.
 *
 * @returns {Promise<{baseUrl: string, accountsPath: string, port: number, stop: () => Promise<void>}>}
 *   `accountsPath` 는 임시 사본이다. 검증이 이 파일을 마음대로 바꿔도 된다.
 */
export async function startBenchmarkVerifyServer(options = {}) {
  const port = Number(options.port || DEFAULT_PORT);
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sns-bench-verify-'));
  const accountsPath = path.join(workDir, 'benchmark_accounts.json');
  fs.copyFileSync(SOURCE_ACCOUNTS, accountsPath);

  const child = spawn('python', ['scrap_sns_server.py'], {
    env: {
      ...process.env,
      PORT: String(port),
      SNS_BENCHMARK_ACCOUNTS_PATH: accountsPath,
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
      // Windows 에서 SIGTERM 이 안 먹는 경우가 있어 확인 후 강제 종료한다.
      await new Promise((resolve) => setTimeout(resolve, 800));
      if (child.exitCode === null) child.kill('SIGKILL');
    }
    try {
      fs.rmSync(workDir, { recursive: true, force: true });
    } catch {
      // 임시 폴더 정리 실패는 검증 결과에 영향을 주지 않는다.
    }
  };

  try {
    await waitForReady(baseUrl, child);
  } catch (error) {
    await stop();
    throw new Error(`${error.message}\n--- 서버 로그 ---\n${logs.join('').slice(-2000)}`);
  }

  return { baseUrl, accountsPath, port, stop };
}
