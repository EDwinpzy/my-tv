#!/usr/bin/env node
/**
 * decrypt_stream.js —— 直播流播放器混淆解密（桌面 Node 版）
 *
 * 用法: node decrypt_stream.js <播放器页.html路径> <matchId>
 * 输出: 最后一行 JSON {"url": "...", "html": "...", "err": "..."}
 *
 * 对齐 Android QuickJS 移植版（QuickJsDecrypt.kt）：
 *  - 提取第一个 <script> 块，清洗反调试（debugger; / while(!![]){}）
 *  - 极简沙箱（document.write 捕获 → __written）
 *  - 流地址提取：m3u8.html?id= → decodeURIComponent → 校验 http；
 *    兜底 .m3u8 直链 / xgplayer.html?id=
 *
 * Node 原生环境完整，atob/decodeURIComponent/escape 均原生正确，
 * 无需 QuickJS 版的自实现（latin1 语义在 Node 原生即满足）。
 */
const fs = require('fs');

// ---------- 沙箱 ----------
const SANDBOX_JS = `
var __written = '';
var __loc = { href:'http://wtmdjxkq.com/ballbar.php?id='+__matchId, protocol:'http:', host:'wtmdjxkq.com', hostname:'wtmdjxkq.com', pathname:'/ballbar.php', search:'', hash:'' };
__loc.assign = function(){}; __loc.replace = function(){};
var debuggerProtection = null;
var document = {
  write: function(s){ __written += String(s); },
  writeln: function(s){ __written += String(s); },
  getElementById: function(){ return { innerHTML:'', style:{}, appendChild:function(){} }; },
  createElement: function(){ return {}; },
  body:{}, head:{}, documentElement:{}, location:__loc,
  cookie:'', readyState:'complete', referrer:'',
  addEventListener:function(){}, removeEventListener:function(){}
};
var navigator = { userAgent:'Mozilla/5.0' };
var location = __loc;
var console = { log:function(){}, info:function(){}, error:function(){}, warn:function(){}, debug:function(){}, trace:function(){} };
var screen = { width:1920, height:1080 };
var history = {};
var setTimeout = function(f){ try{ f(); }catch(e){} return 1; };
var setInterval = function(f){ try{ f(); }catch(e){} return 1; };
var clearTimeout = function(){}; var clearInterval = function(){};
function XMLHttpRequest(){ this.open=function(){}; this.send=function(){}; this.setRequestHeader=function(){}; }
var fetch = function(){ return { then:function(){}, catch:function(){} }; };
var Image = function(){}; var Worker = function(){};
var addEventListener = function(){}; var removeEventListener = function(){};
var requestAnimationFrame = function(){ return 1; }; var cancelAnimationFrame = function(){};
var window = (typeof globalThis !== 'undefined' ? globalThis : this);
var self = window, top = window, parent = window, globalThis = window;
`;

// ---------- 流地址提取 ----------
function extractStreamUrl(html, written) {
  let url = "";
  const fm = written.match(/m3u8\.html\?id=([^"'\s<]*)/);
  if (fm && fm[1]) {
    const raw = fm[1];
    try { url = decodeURIComponent(raw); } catch (e) { url = raw; }
    if (!/^https?:\/\//i.test(url)) url = "";
  }
  if (!url) {
    const dm = written.match(/https?:\/\/[^\s"'<>\\]+\.m3u8[^\s"'<>\\]*/i);
    if (dm) url = dm[0];
  }
  if (!url) {
    const xm = html.match(/xgplayer\.html\?id=([^"'\s<>]*)/);
    if (xm && xm[1]) {
      let u = "";
      try { u = decodeURIComponent(xm[1]); } catch (e) { u = xm[1]; }
      if (/^https?:\/\//i.test(u)) url = u;
    }
  }
  return url;
}

function main() {
  const file = process.argv[2];
  const matchId = process.argv[3] || "";
  const out = { url: "", html: "" };
  try {
    const html = fs.readFileSync(file, "utf-8");
    const m = html.match(/<script[^>]*>([\s\S]*?)<\/script>/);
    if (!m) { console.log(JSON.stringify(out)); return; }
    let code = m[1];
    code = code.replace(/\bdebugger\s*;/, ";");
    code = code.replace(/while\s*\(\s*!\s*\[\s*\]\s*\)\s*\{\s*\}/g, "{}");
    code = code.replace(/while\s*\(\s*!!\s*\[\s*\]\s*\)\s*\{\s*\}/g, "{}");
    // 独立 vm 上下文跑沙箱 + 混淆脚本
    const vm = require("vm");
    // null-prototype 沙箱：切断 __proto__/constructor 原型链逃逸
    // （播放器脚本来自外部站点，一旦被投毒，constructor 链会直达宿主 Function 拿到 process）。
    const sandbox = Object.create(null);
    sandbox.__matchId = JSON.stringify(String(matchId));
    sandbox.__written = "";
    sandbox.require = undefined;
    sandbox.module = undefined;
    sandbox.process = undefined;
    sandbox.Buffer = undefined;
    sandbox.global = undefined;
    // 注意：不能禁用 Function/eval —— 新混淆器（2026-08 实测）依赖 eval 生成代码，
    // 禁用会静默失败（url 恒空）。宿主隔离已由 require/process/Buffer=undefined 保证。
    const ctx = vm.createContext(sandbox, {
      codeGeneration: { strings: true, wasm: false },
    });
    try {
      vm.runInContext(SANDBOX_JS, ctx, { filename: "sandbox.js" });
      vm.runInContext("try{\n" + code + "\n}catch(e){}", ctx, { filename: "player.js" });
    } catch (e) {
      out.err = String(e).slice(0, 200);
    }
    const written = sandbox.__written || "";
    out.html = written.slice(0, 500);
    out.url = extractStreamUrl(html, written);
  } catch (e) {
    out.err = String(e).slice(0, 200);
  }
  console.log(JSON.stringify(out));
}

main();
