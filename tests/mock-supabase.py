"""테스트용 Supabase 흉내 서버 (GoTrue + PostgREST + Storage 최소 구현)."""
import json, re, secrets, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

USERS, SESSIONS, ROWS, OBJECTS = {}, {}, {}, {}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "*")

    def reply(self, code, payload=None, raw=None, ctype="application/json"):
        self.send_response(code); self.cors()
        body = raw if raw is not None else json.dumps({} if payload is None else payload).encode()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def uid(self):
        auth = self.headers.get("Authorization", "")
        return SESSIONS.get(auth.replace("Bearer ", ""))

    def do_OPTIONS(self): self.reply(204, raw=b"")

    def do_POST(self):
        path, _, q = self.path.partition("?")
        qs = urllib.parse.parse_qs(q)
        raw = self.body()

        if path == "/auth/v1/signup" or path.startswith("/auth/v1/token"):
            grant = (qs.get("grant_type") or [""])[0]
            data = json.loads(raw or b"{}")
            if grant == "refresh_token":
                uid = SESSIONS.get("refresh:" + data.get("refresh_token", ""))
                if not uid: return self.reply(400, {"error": "invalid refresh"})
                email = USERS[uid]["email"]
            else:
                email, pw = data.get("email", ""), data.get("password", "")
                if path.endswith("signup"):
                    if any(u["email"] == email for u in USERS.values()):
                        return self.reply(400, {"msg": "User already registered"})
                    uid = secrets.token_hex(8); USERS[uid] = {"email": email, "pw": pw}
                else:
                    uid = next((k for k, u in USERS.items() if u["email"] == email and u["pw"] == pw), None)
                    if not uid: return self.reply(400, {"error_description": "Invalid login credentials"})
            tok, ref = secrets.token_hex(12), secrets.token_hex(12)
            SESSIONS[tok] = uid; SESSIONS["refresh:" + ref] = uid
            return self.reply(200, {"access_token": tok, "refresh_token": ref,
                                    "user": {"id": uid, "email": USERS[uid]["email"]}})

        if path == "/auth/v1/logout":
            return self.reply(204, raw=b"")

        uid = self.uid()
        if not uid: return self.reply(401, {"message": "JWT expired"})

        if path == "/rest/v1/entries":
            payload = json.loads(raw or b"[]")
            items = payload if isinstance(payload, list) else [payload]
            out = []
            for it in items:
                it["user_id"] = uid
                ROWS[(uid, it["id"])] = it
                out.append(it)
            prefer = self.headers.get("Prefer", "")
            return self.reply(201, out if "return=representation" in prefer else [])

        m = re.match(r"^/storage/v1/object/charts/(.+)$", path)
        if m:
            key = urllib.parse.unquote(m.group(1))
            if not key.startswith(uid + "/"): return self.reply(403, {"message": "not owner"})
            OBJECTS[key] = (raw, self.headers.get("Content-Type", "image/jpeg"))
            return self.reply(200, {"Key": key})

        self.reply(404, {"message": "not found"})

    def do_GET(self):
        path, _, q = self.path.partition("?")
        uid = self.uid()
        if not uid: return self.reply(401, {"message": "JWT expired"})

        if path == "/rest/v1/entries":
            rows = [r for (u, _), r in ROWS.items() if u == uid]
            rows.sort(key=lambda r: (r.get("date") or "", r.get("time") or ""))
            return self.reply(200, rows)

        m = re.match(r"^/storage/v1/object/charts/(.+)$", path)
        if m:
            key = urllib.parse.unquote(m.group(1))
            if not key.startswith(uid + "/"): return self.reply(403, {"message": "not owner"})
            if key not in OBJECTS: return self.reply(404, {"message": "Object not found"})
            data, ctype = OBJECTS[key]
            return self.reply(200, raw=data, ctype=ctype)

        self.reply(404, {"message": "not found"})

    def do_DELETE(self):
        path, _, q = self.path.partition("?")
        uid = self.uid()
        if not uid: return self.reply(401, {"message": "JWT expired"})

        if path == "/rest/v1/entries":
            qs = urllib.parse.parse_qs(q)
            f = (qs.get("id") or [""])[0]
            if f.startswith("eq."):
                ROWS.pop((uid, f[3:]), None)
            else:                                   # id=not.is.null → 전체 삭제
                for k in [k for k in ROWS if k[0] == uid]: ROWS.pop(k)
            return self.reply(204, raw=b"")

        m = re.match(r"^/storage/v1/object/charts/(.+)$", path)
        if m:
            key = urllib.parse.unquote(m.group(1))
            if not key.startswith(uid + "/"): return self.reply(403, {"message": "not owner"})
            if key not in OBJECTS: return self.reply(404, {"message": "Object not found"})
            OBJECTS.pop(key)
            return self.reply(200, {"message": "deleted"})

        self.reply(404, {"message": "not found"})

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8020), H).serve_forever()
