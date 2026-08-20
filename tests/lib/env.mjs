/* 테스트 공용 설정 — 환경변수로 덮어쓸 수 있습니다. */
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, "../..");                 // 저장소 루트
export const TMP  = process.env.TJ_TMP  || resolve(ROOT, "tests/.tmp");
mkdirSync(TMP, { recursive: true });

export const CHROME     = process.env.TJ_CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
export const CHART      = resolve(TMP, "chart.png");        // 작은 캡처
export const CHART_BIG  = resolve(TMP, "chart-big.png");    // 1600x900 캡처

export const APP_URL    = process.env.TJ_APP_URL    || "http://127.0.0.1:8030/index.html"; // 정적 서빙
export const SERVER_URL = process.env.TJ_SERVER_URL || "http://127.0.0.1:8010/";           // 자체 서버
export const MOCK_URL   = process.env.TJ_MOCK_URL   || "http://127.0.0.1:8020";            // Supabase 목
export const FILE_URL   = process.env.TJ_FILE_URL   || "file://" + resolve(ROOT, "trading-journal/index.html");
export const WRAP_URL   = process.env.TJ_WRAP_URL   || "file://" + TMP + "/";              // 아티팩트 래핑본

export const STANDALONE_URL        = process.env.TJ_STANDALONE_URL        || "http://127.0.0.1:8040/index.html";
export const STANDALONE_SERVER_URL = process.env.TJ_STANDALONE_SERVER_URL || "http://127.0.0.1:8050/";

/* 예상되는 잡음은 실패로 보지 않는다 (미로그인 401, 오답 로그인 400, 정적 서버의 /api/health 404 등) */
const BENIGN = [
  /status of 40[0134]/, /Invalid login credentials/, /JWT expired/,
  /Failed to load resource/, /net::ERR_/,
];

/** 테스트 종료 리포트 — 예상 외 오류가 있으면 종료 코드 1 */
export function report(name, errors) {
  const real = (errors || []).filter(e => !BENIGN.some(r => r.test(String(e))));
  if (real.length) {
    console.error(`✗ ${name} — 오류 ${real.length}건`);
    real.forEach(e => console.error("   ", e));
    process.exitCode = 1;
  } else {
    console.log(`✓ ${name}`);
  }
}
