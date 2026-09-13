// OptimalTV 授权协议 v2 端点——CloudBase HTTP 云函数
//
// 入参: POST /  { protocol: 2, action, code, deviceId, currentCode? }
// 出参: { ret: 0, ticket, licenseCode, activatedAt, expireAt, serverNow }
//       或 { ret: 40x/50x, msg }
//
// 设计（方案文档 §3.2 + 实施修订）：
// - 函数内无签名能力、无长期密钥：PG 访问凭据 = svc_activate 服务账号
//   （env 注入），signin 换 2h access_token 内存缓存；账号被吊销/改密即断供。
// - PG 侧 activate_code RPC（SECURITY DEFINER）承担查表+行锁+激活/校验/续费，
//   本函数只做参数校验与转发——云端被黑伪造不了新授权（票据由本机私钥预签名）。
// - 码格式 OTV-XXXXX-XXXXX（字母表剔除 0/O/1/I），deviceId 为完整 SHA-256。
const http = require("http");
const { URL } = require("url");

const HOST = "https://appletv-d5ge1bth794873f76.api.tcloudbasegateway.com";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const tokenCache = { token: null, exp: 0 };

async function getToken() {
  if (tokenCache.token && Date.now() < tokenCache.exp - 120000) return tokenCache.token;
  const r = await fetch(`${HOST}/auth/v1/signin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: process.env.OTV_AUTH_USER, password: process.env.OTV_AUTH_PASS }),
  });
  if (!r.ok) throw new Error(`signin ${r.status}`);
  const out = await r.json();
  if (!out.access_token) throw new Error("no access_token");
  tokenCache.token = out.access_token;
  tokenCache.exp = Date.now() + (out.expires_in || 7200) * 1000;
  return tokenCache.token;
}

function sendJson(res, data) {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8", ...CORS_HEADERS });
  res.end(JSON.stringify(data));
}

function readJsonBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch (e) { resolve(null); }
    });
    req.on("error", () => resolve(null));
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS_HEADERS);
    return res.end();
  }
  const url = new URL(req.url || "/", "http://127.0.0.1");
  if (req.method !== "POST" || (url.pathname !== "/" && url.pathname !== "/activate")) {
    return sendJson(res, { ret: 404, msg: "not_found" });
  }
  const body = await readJsonBody(req);
  if (body === null) return sendJson(res, { ret: 400, msg: "bad_json" });
  const protocol = Number(body.protocol || 0);
  const action = String(body.action || "").trim().toLowerCase();
  const code = String(body.code || "").trim().toUpperCase();
  const currentCode = String(body.currentCode || "").trim().toUpperCase();
  const deviceId = String(body.deviceId || "").trim().toLowerCase();
  const actions = ["activate", "verify", "renew"];
  if (protocol !== 2) return sendJson(res, { ret: 426, msg: "upgrade_required" });
  if (!actions.includes(action)) return sendJson(res, { ret: 400, msg: "bad_action" });
  if (!/^OTV-[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}$/.test(code)) return sendJson(res, { ret: 400, msg: "bad_code" });
  if (!/^[a-f0-9]{64}$/.test(deviceId)) return sendJson(res, { ret: 400, msg: "bad_device" });
  if (action === "renew" &&
      (!/^OTV-[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}$/.test(currentCode) || currentCode === code)) {
    return sendJson(res, { ret: 400, msg: "bad_current_code" });
  }
  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || null;

  try {
    const tok = await getToken();
    const r = await fetch(`${HOST}/v1/rdb/rest/rpc/activate_code`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + tok },
      body: JSON.stringify({
        p_protocol: protocol,
        p_action: action,
        p_code: code,
        p_device: deviceId,
        p_current_code: action === "renew" ? currentCode : null,
        p_ip: ip,
      }),
    });
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch (e) { data = null; }
    if (!data || typeof data.ret !== "number") data = { ret: 500, msg: "upstream_error" };
    sendJson(res, data);
  } catch (e) {
    sendJson(res, { ret: 502, msg: "upstream_error" });
  }
});

server.listen(9000);
