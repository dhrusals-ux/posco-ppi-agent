/*
 * 클라우드(Supabase) 연결 설정 — 여기에 값을 넣어두면 접속하는 모든 기기에서 자동 연결됩니다.
 *
 *   Supabase 대시보드 → Project Settings → API 에서
 *     Project URL      → supabaseUrl
 *     anon public key  → supabaseAnonKey
 *
 * anon key 는 공개되어도 되는 값입니다. 실제 데이터 접근은 Supabase의 RLS 정책이 막습니다.
 * 비워두면 앱 안의 "☁️ 클라우드 연결 설정" 메뉴에서 직접 입력할 수도 있습니다.
 * (설정이 없으면 이 브라우저에만 저장하는 모드로 동작합니다.)
 */
window.TJ_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: ""
};
