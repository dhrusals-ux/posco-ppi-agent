#!/usr/bin/env bash
# 매매일지 전체 검증 — 브라우저 자동화로 세 저장 방식(브라우저·자체 서버·클라우드)을 모두 확인합니다.
#
#   bash tests/run.sh              전체 실행
#   bash tests/run.sh market-tab   특정 파일만 실행
#
# 필요: python3(+fastapi, uvicorn), node, playwright-core, Chromium
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"; TMP="$ROOT/tests/.tmp"; mkdir -p "$TMP"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  rm -f "$TMP"/server.db*
}
trap cleanup EXIT

need() { command -v "$1" >/dev/null || { echo "✗ $1 이 필요합니다"; exit 1; }; }
need python3; need node

echo "▶ 테스트 자료 준비"
python3 tests/fixtures/make-charts.py "$TMP" || exit 1
python3 tests/lib/make-wrapped.py "$TMP"     || exit 1

if [ ! -d node_modules/playwright-core ] && [ ! -d "$HOME/node_modules/playwright-core" ]; then
  echo "▶ playwright-core 설치"
  npm install --no-save playwright-core@1.55.0 >/dev/null 2>&1 || {
    echo "✗ playwright-core 설치 실패 — 수동으로 npm i playwright-core 후 다시 실행하세요"; exit 1; }
fi

for port in 8010 8020 8030; do
  if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
    exec 3>&- 3<&-
    echo "✗ 포트 $port 를 이미 사용 중입니다. 해당 프로세스를 종료한 뒤 다시 실행하세요."
    exit 1
  fi
done

echo "▶ 서버 기동"
python3 -m http.server 8030 --directory trading-journal >"$TMP/static.log" 2>&1 &            PIDS+=($!)
python3 tests/mock-supabase.py                          >"$TMP/mock.log"   2>&1 &            PIDS+=($!)
TJ_DB="$TMP/server.db" TJ_SECRET=test-secret-please-change TJ_ALLOW_REGISTER=1 \
  python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8010 >"$TMP/server.log" 2>&1 &  PIDS+=($!)

for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8010/api/health >/dev/null && \
  curl -sf http://127.0.0.1:8030/index.html >/dev/null && break
  sleep 0.5
done

FILES=()
if [ $# -gt 0 ]; then
  for a in "$@"; do FILES+=("tests/browser/${a%.mjs}.mjs"); done
else
  # 독립 트리 테스트는 별도 서버가 필요해 기본 실행에서 제외한다
  for f in tests/browser/*.mjs; do [ "$(basename "$f")" = "standalone-tree.mjs" ] || FILES+=("$f"); done
fi

fail=0
for f in "${FILES[@]}"; do
  name=$(basename "$f" .mjs)
  printf '  %-22s ' "$name"
  if out=$(timeout 240 node "$f" 2>&1); then
    echo "$out" | grep -q '^✓' && echo "PASS" || { echo "PASS(무결과)"; }
  else
    echo "FAIL"; echo "$out" | tail -12 | sed 's/^/      /'; fail=1
  fi
done

echo
[ "$fail" -eq 0 ] && echo "✅ 전체 통과" || echo "❌ 실패한 테스트가 있습니다"
exit $fail
