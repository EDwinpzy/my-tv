// OptimalTV v1.18 热更新端点（公测版）——CloudBase HTTP 云函数
//
// 入参: POST /check  { hotVersion, apkVersion, deviceId }  → { ret, hasUpdate, pkg{...} }
//       POST /report { deviceId, apkVersion, fromVersion, toVersion, result, detail } → { ret }
//
// 设计（docs/_archive-20260906-文档合并/热更新-方案与实施.md（已并入 docs/项目文档.md））：
// - 与 activate 同款骨架：函数内 signin svc_activate 换 2h token 内存缓存，调 PG RPC。
//   hotupdate_check / hotupdate_report 是公开语义 RPC（grant anon+authenticated，无表直读），
//   本函数账号即使被攻破也无特权提升——只能查已发布包元数据、写上报日志。
// - 下载走 pgstore 公开桶 hotupdate 的稳定匿名 URL（无签名无过期，支持 Range 断点续传），
//   本函数不代理 35MB 包体。
// - 紧急停更：控制台把函数环境变量 OTV_HU_OFF 设为 "1" 即全局关闭检查（一律返回无更新）。
const http = require("http");
const { URL } = require("url");

const HOST = "https://appletv-d5ge1bth794873f76.api.tcloudbasegateway.com";
const DOWNLOAD_BASE = HOST + "/v1/storages/object/hotupdate/";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const tokenCache = { token: null, exp: 0 };
// PostgreSQL CU 降耗：旧客户端每 60 秒请求一次公告，且每次都直接执行 RPC。
// 同一云函数实例内把公告结果合并缓存 5 分钟；即使旧版客户端尚未升级，
// 数据库查询也从「每设备每分钟一次」收敛为「每热实例每 5 分钟一次」。
const ANNOUNCE_CACHE_MS = 5 * 60 * 1000;
const CHECK_CACHE_MS = 2 * 60 * 1000;
const VOD_SOURCE_CACHE_MS = 2 * 60 * 1000;
const announcementCache = { data: null, ts: 0, pending: null };
const checkCache = new Map();
const vodSourceCache = new Map();

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

function sendJson(res, data, cacheControl = "no-store") {
  res.writeHead(200, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": cacheControl,
    ...CORS_HEADERS,
  });
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

function toInt(v, def) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 && n <= 2147483647 ? n : def;
}

async function rpc(name, payload) {
  const tok = await getToken();
  const r = await fetch(`${HOST}/v1/rdb/rest/rpc/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + tok },
    body: JSON.stringify(payload),
  });
  const text = await r.text();
  try { return JSON.parse(text); } catch (e) { throw new Error(`rpc ${name} bad json: ${text.slice(0, 120)}`); }
}

async function announcementLatestCached() {
  const now = Date.now();
  if (announcementCache.data && now - announcementCache.ts < ANNOUNCE_CACHE_MS) {
    return announcementCache.data;
  }
  if (announcementCache.pending) return announcementCache.pending;
  announcementCache.pending = rpc("announcement_latest", {})
    .then((out) => {
      announcementCache.data = out;
      announcementCache.ts = Date.now();
      return out;
    })
    .finally(() => { announcementCache.pending = null; });
  return announcementCache.pending;
}

async function hotupdateCheckCached(hotVersion, apkVersion) {
  const key = `${hotVersion}:${apkVersion}`;
  const now = Date.now();
  const hit = checkCache.get(key);
  if (hit && hit.data && now - hit.ts < CHECK_CACHE_MS) return hit.data;
  if (hit && hit.pending) return hit.pending;
  const pending = rpc("hotupdate_check", {
    p_hot_version: hotVersion,
    p_apk_version: apkVersion,
  }).then((out) => {
    checkCache.set(key, { data: out, ts: Date.now(), pending: null });
    if (checkCache.size > 100) checkCache.clear();
    return out;
  }).catch((err) => {
    checkCache.delete(key);
    throw err;
  });
  checkCache.set(key, { data: null, ts: now, pending });
  return pending;
}

async function vodSourceCheckCached(version) {
  const key = String(version);
  const now = Date.now();
  const hit = vodSourceCache.get(key);
  if (hit && hit.data && now - hit.ts < VOD_SOURCE_CACHE_MS) return hit.data;
  if (hit && hit.pending) return hit.pending;
  const pending = rpc("vod_source_public_check", { p_version: version })
    .then((out) => {
      vodSourceCache.set(key, { data: out, ts: Date.now(), pending: null });
      if (vodSourceCache.size > 100) vodSourceCache.clear();
      return out;
    })
    .catch((err) => { vodSourceCache.delete(key); throw err; });
  vodSourceCache.set(key, { data: null, ts: now, pending });
  return pending;
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, CORS_HEADERS);
    return res.end();
  }
  const url = new URL(req.url || "/", "http://127.0.0.1");

  // v1.20 运营公告：公开 GET，无入参——app 启动 + 周期轮询拉最新 published 公告
  if (req.method === "GET" && url.pathname === "/announce") {
    try {
      const out = await announcementLatestCached();
      return sendJson(res, { ret: 0, ...out }, "public, max-age=60, stale-while-revalidate=300");
    } catch (e) {
      return sendJson(res, { ret: 502, msg: "upstream_error" });
    }
  }

  const body = req.method === "POST" ? await readJsonBody(req) : {};
  if (body === null) return sendJson(res, { ret: 400, msg: "bad_json" });
  const deviceId = String(body.deviceId || "").trim();
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(deviceId)) return sendJson(res, { ret: 400, msg: "bad_device" });

  try {
    if (req.method === "POST" && url.pathname === "/vod-sources/check") {
      const out = await vodSourceCheckCached(toInt(body.version, 0));
      return sendJson(res, out);
    }
    if (req.method === "POST" && (url.pathname === "/" || url.pathname === "/check")) {
      // 紧急停更开关：参数校验之后触发，使 /check 在停更时仍可区分 blackout（返回
      // blackout:true），管理端状态条据此显示 BLACKOUT: ON 而非误判「端点异常」
      const apkVersion = toInt(body.apkVersion, 0);
      if (apkVersion <= 0) return sendJson(res, { ret: 400, msg: "bad_apk" });
      if (process.env.OTV_HU_OFF === "1") return sendJson(res, { ret: 0, hasUpdate: false, blackout: true });
      const hotVersion = toInt(body.hotVersion, 0);
      if (apkVersion <= 0) return sendJson(res, { ret: 400, msg: "bad_apk" });
      const out = await hotupdateCheckCached(hotVersion, apkVersion);
      if (out && out.hasUpdate && out.pkg && out.pkg.objectKey) {
        out.pkg.url = DOWNLOAD_BASE + out.pkg.objectKey;
      }
      return sendJson(res, out);
    }
    if (req.method === "POST" && url.pathname === "/report") {
      const out = await rpc("hotupdate_report", {
        p_device: deviceId,
        p_apk_version: toInt(body.apkVersion, null),
        p_from_version: toInt(body.fromVersion, null),
        p_to_version: toInt(body.toVersion, null),
        p_result: String(body.result || "").slice(0, 32),
        p_detail: String(body.detail || "").slice(0, 500),
      });
      return sendJson(res, out);
    }
    return sendJson(res, { ret: 404, msg: "not_found" });
  } catch (e) {
    return sendJson(res, { ret: 502, msg: "upstream_error" });
  }
});

server.listen(9000);
