/**
 * Vercel 서버 함수 — 법령 AI 챗봇용 OpenRouter 중계  (POST /api/chat)
 *
 * Vercel 환경변수(Project → Settings → Environment Variables):
 *   OPENROUTER_API_KEY  (필수)  OpenRouter 키
 *   OPENROUTER_MODELS   (선택)  쉼표로 구분한 모델 목록. 앞에서부터 시도
 *   ALLOWED_ORIGINS     (선택)  같은 사이트 외에 호출을 허용할 주소(쉼표 구분)
 *
 * 요청 {messages:[...], max_tokens}  →  응답 {content, model}
 * 로컬에서는 tools/dev_server.py 가 같은 경로·형식으로 .env 의 키를 써서 동작한다.
 */
const DEFAULT_MODELS = "nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-31b-it:free";
const TIME_BUDGET_MS = 50000; // 함수 제한시간(60초) 안에 끝내도록

module.exports = async (req, res) => {
  const origin = req.headers.origin || "";
  const host = req.headers["x-forwarded-host"] || req.headers.host || "";
  const extra = (process.env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
  // 같은 사이트에서 온 요청만 받는다 (다른 사이트가 이 키로 호출하지 못하게)
  const sameSite = origin && new URL(origin).host === host;
  if (!(sameSite || extra.includes(origin))) return res.status(403).json({ error: "허용되지 않은 사이트" });
  if (req.method !== "POST") return res.status(405).json({ error: "POST만 허용" });

  const key = process.env.OPENROUTER_API_KEY;
  if (!key) return res.status(500).json({ error: "Vercel 환경변수 OPENROUTER_API_KEY가 설정되지 않았습니다" });

  const body = typeof req.body === "string" ? safeJson(req.body) : req.body;
  if (!body || !Array.isArray(body.messages) || !body.messages.length) return res.status(400).json({ error: "잘못된 요청" });
  if (JSON.stringify(body.messages).length > 400000) return res.status(413).json({ error: "요청이 너무 큽니다" });

  const models = (process.env.OPENROUTER_MODELS || DEFAULT_MODELS).split(",").map(s => s.trim()).filter(Boolean);
  const maxTokens = Math.min(parseInt(body.max_tokens) || 1500, 4000);
  const t0 = Date.now();
  let last = [502, { error: "응답 없음" }];

  for (const model of models) {
    for (let attempt = 0; attempt < 2; attempt++) {
      if (Date.now() - t0 > TIME_BUDGET_MS) return res.status(last[0]).json(last[1]);
      const r = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: { "Authorization": "Bearer " + key, "Content-Type": "application/json",
                   "HTTP-Referer": "https://" + host + "/", "X-Title": "waste-inspection" },
        body: JSON.stringify({ model, messages: body.messages, max_tokens: maxTokens, temperature: 0.2 }),
      });
      const j = await r.json().catch(() => ({}));
      const text = (((j.choices || [])[0] || {}).message || {}).content || "";
      if (r.ok && !j.error && text.trim()) return res.status(200).json({ content: text, model: j.model || model });
      const err = j.error || {};
      last = [r.ok ? 502 : r.status, { error: (err.metadata && err.metadata.raw) || err.message || ("HTTP " + r.status), model }];
      if ([401, 402, 403].includes(r.status)) return res.status(last[0]).json(last[1]); // 키·한도 문제
      if (r.status === 429 || r.status >= 500) { await sleep(1500 + attempt * 2500); continue; }
      break;
    }
  }
  return res.status(last[0]).json(last[1]);
};

function safeJson(s) { try { return JSON.parse(s); } catch { return null; } }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
