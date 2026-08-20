/* 매매일지 서비스 워커 — 오프라인에서도 앱 화면이 열리도록 최소한만 캐시한다.
   · 화면(HTML/JS/아이콘): 네트워크 우선, 실패 시 캐시 (배포 직후 최신 화면이 보이도록)
   · API·클라우드 요청: 캐시하지 않음 (항상 최신 데이터) */
const CACHE = "tj-shell-v1";
const SHELL = ["./", "./index.html", "./config.js", "./manifest.json",
               "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // Supabase 등 외부 요청은 건드리지 않음
  if (url.pathname.startsWith("/api/")) return;      // 자체 서버 API도 통과

  e.respondWith(
    fetch(req)
      .then(res => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then(hit => hit || caches.match("./index.html")))
  );
});
