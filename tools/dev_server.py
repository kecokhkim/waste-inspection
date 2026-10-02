"""로컬 테스트 서버 — 사이트 파일을 띄우고, 비밀키가 필요한 요청을 대신 전달한다.

사용법:  python tools/dev_server.py   →  http://localhost:8000
  GET  /api/law/<lawService.do|lawSearch.do>?...  →  국가법령정보 OPEN API (OC는 서버가 붙임)
  POST /api/chat  {messages:[...], max_tokens}     →  OpenRouter (키·모델은 서버가 붙임)
키는 .env 에서만 읽고 브라우저로 내보내지 않는다. 공개 배포 시에는 같은 역할을 Cloudflare Worker가 맡는다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("PORT", "8000"))
LAW_API = "https://www.law.go.kr/DRF/"
OR_API = "https://openrouter.ai/api/v1/chat/completions"
LAW_SVCS = {"lawService.do", "lawSearch.do"}


def load_env():
    env = {}
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
MODELS = [m.strip() for m in ENV.get("OPENROUTER_MODELS", "google/gemma-4-31b-it:free").split(",") if m.strip()]


def openrouter(messages, max_tokens):
    """모델 목록을 차례로 시도. 무료 모델의 일시적 429/5xx는 잠깐 쉬고 재시도한다."""
    key = ENV.get("OPENROUTER_API_KEY")
    if not key:
        return 500, {"error": ".env 에 OPENROUTER_API_KEY 가 없습니다."}
    last = (502, {"error": "응답 없음"})
    for model in MODELS:
        for attempt in range(2):
            body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens,
                               "temperature": 0.2}).encode("utf-8")
            req = urllib.request.Request(OR_API, data=body, method="POST", headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json",
                "HTTP-Referer": "https://kecokhkim.github.io/waste-inspection/", "X-Title": "waste-inspection"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read().decode("utf-8"))
                if j.get("error"):
                    last = (502, {"error": j["error"].get("message", "모델 오류"), "model": model})
                    break
                msg = ((j.get("choices") or [{}])[0].get("message") or {})
                text = msg.get("content") or ""
                if not text.strip():
                    last = (502, {"error": "빈 응답", "model": model})
                    break
                return 200, {"content": text, "model": j.get("model", model), "usage": j.get("usage")}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")
                try:
                    d = json.loads(detail)
                    msg = (d.get("error") or {}).get("metadata", {}).get("raw") or (d.get("error") or {}).get("message")
                except Exception:
                    msg = detail[:300]
                last = (e.code, {"error": msg or f"HTTP {e.code}", "model": model})
                if e.code in (401, 402, 403):
                    return last  # 키·한도 문제는 다른 모델로 넘겨도 소용없음
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 + attempt * 3)
                    continue
                break
            except Exception as e:
                last = (504, {"error": str(e), "model": model})
                break
    return last


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _blocked(self):
        # .env 등 숨김 파일과 tools/ 는 절대 내보내지 않는다
        parts = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).split("/")
        return any(p.startswith(".") for p in parts if p) or (len(parts) > 1 and parts[1] == "tools")

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path.startswith("/api/law/"):
            svc = u.path[len("/api/law/"):]
            if svc not in LAW_SVCS:
                return self._json(404, {"error": "허용되지 않은 경로"})
            q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if k != "OC"]
            q.append(("OC", ENV.get("LAW_OC", "")))
            try:
                with urllib.request.urlopen(LAW_API + svc + "?" + urllib.parse.urlencode(q), timeout=60) as r:
                    b = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            except Exception as e:
                self._json(502, {"error": "법령 API 연결 실패: " + str(e)})
            return
        if self._blocked():
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        if self._blocked():
            return self.send_error(404)
        super().do_HEAD()

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/api/chat":
            return self._json(404, {"error": "없는 경로"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 400_000:
                return self._json(413, {"error": "요청이 너무 큽니다"})
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            messages = req["messages"]
            assert isinstance(messages, list) and messages
        except Exception:
            return self._json(400, {"error": "잘못된 요청"})
        code, obj = openrouter(messages, min(int(req.get("max_tokens") or 1500), 4000))
        self._json(code, obj)

    def log_message(self, fmt, *args):
        sys.stderr.write("[dev] " + (fmt % args) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"모델: {', '.join(MODELS)}")
    print(f"OpenRouter 키: {'있음' if ENV.get('OPENROUTER_API_KEY') else '없음'} / 법령 OC: {'있음' if ENV.get('LAW_OC') else '없음'}")
    print(f"http://localhost:{PORT}  (종료: Ctrl+C)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
