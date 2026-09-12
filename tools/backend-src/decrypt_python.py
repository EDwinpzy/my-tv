# -*- coding: utf-8 -*-
"""
球迹直播 · 桌面 QuickJS 解密（decrypt_python.py）
===================================================
decrypt_stream.js（Node vm 沙箱）的**同源 Python 移植**，引擎用 quickjs（PyPI quickjs，
引擎与安卓壳 app.cash.quickjs 同源 C 实现）。PC 客户端免 Node 依赖的关键。

沙箱 JS 逐字节对齐 QuickJsDecrypt.kt 的 SANDBOX_JS（安卓实测结论：必须极简 + 纯 JS
atob/decodeURIComponent 覆盖，详见那三个坑的注释），保证 PC 与 APK 解密行为一致。

用法: decrypt_python.py 内部函数 decrypt_html(html, matchId) -> {"url":..., "html":...}
"""
import base64
import re


# ===== 极简 JS 沙箱（对齐 QuickJsDecrypt.kt SANDBOX_JS，勿加复杂 mock）=====
SANDBOX_JS = r"""
var __written = '';
var __matchId = '';
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
var atob = function(s) {
  s = String(s).replace(/=+$/, '');
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var r = '', c1, c2, c3, e1, e2, e3, e4, i = 0, n = s.length;
  while (i < n) {
    e1 = chars.indexOf(s.charAt(i++));
    if (i >= n) break;
    e2 = chars.indexOf(s.charAt(i++));
    if (e1 < 0 || e2 < 0) break;
    e3 = (i < n) ? chars.indexOf(s.charAt(i++)) : -1;
    e4 = (i < n) ? chars.indexOf(s.charAt(i++)) : -1;
    c1 = (e1 << 2) | (e2 >> 4);
    r += String.fromCharCode(c1);
    if (e3 >= 0) { c2 = ((e2 & 15) << 4) | (e3 >> 2); if (e3 !== 64) r += String.fromCharCode(c2); }
    if (e4 >= 0) { c3 = ((e3 & 3) << 6) | e4; if (e4 !== 64) r += String.fromCharCode(c3); }
  }
  return r;
};
var btoa = function(s) {
  s = String(s);
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var r = '', i = 0, b1, b2, b3, e1, e2, e3, e4;
  while (i < s.length) {
    b1 = s.charCodeAt(i++) & 255;
    b2 = i < s.length ? s.charCodeAt(i++) & 255 : NaN;
    b3 = i < s.length ? s.charCodeAt(i++) & 255 : NaN;
    e1 = b1 >> 2;
    e2 = ((b1 & 3) << 4) | (b2 >> 4);
    e3 = isNaN(b2) ? 64 : ((b2 & 15) << 2) | (b3 >> 6);
    e4 = isNaN(b3) ? 64 : (b3 & 63);
    r += chars.charAt(e1) + chars.charAt(e2) + (e3 === 64 ? '=' : chars.charAt(e3)) + (e4 === 64 ? '=' : chars.charAt(e4));
  }
  return r;
};
var __decodeURIComponent = function(s) {
  s = String(s);
  var bytes = [], i = 0;
  while (i < s.length) {
    if (s.charAt(i) === '%' && i + 2 < s.length) {
      var v = parseInt(s.substr(i + 1, 2), 16);
      if (!isNaN(v)) { bytes.push(v); i += 3; continue; }
    }
    var code = s.charCodeAt(i);
    if (code < 0x80) { bytes.push(code); }
    else if (code < 0x800) { bytes.push(0xC0 | (code >> 6), 0x80 | (code & 0x3F)); }
    else { bytes.push(0xE0 | (code >> 12), 0x80 | ((code >> 6) & 0x3F), 0x80 | (code & 0x3F)); }
    i++;
  }
  var out = '', j = 0;
  while (j < bytes.length) {
    var b = bytes[j];
    if (b < 0x80) { out += String.fromCharCode(b); j++; }
    else if ((b & 0xE0) === 0xC0 && j + 1 < bytes.length) {
      out += String.fromCharCode(((b & 0x1F) << 6) | (bytes[j + 1] & 0x3F)); j += 2;
    }
    else if ((b & 0xF0) === 0xE0 && j + 2 < bytes.length) {
      out += String.fromCharCode(((b & 0x0F) << 12) | ((bytes[j + 1] & 0x3F) << 6) | (bytes[j + 2] & 0x3F)); j += 3;
    }
    else { out += String.fromCharCode(b); j++; }
  }
  return out;
};
var decodeURIComponent = function(s){ try{ return __decodeURIComponent(s); }catch(e){ return s; } };
var __decodeURI = __decodeURIComponent;
var decodeURI = function(s){ try{ return __decodeURI(s); }catch(e){ return s; } };
function escape(s){ s=String(s); var r=''; for(var i=0;i<s.length;i++){ var c=s.charCodeAt(i); if(c>=256){ r+='%u'+('0000'+c.toString(16)).toUpperCase().slice(-4); } else if(c<32||c>126){ r+='%'+('0'+c.toString(16)).toUpperCase().slice(-2); } else { r+=s[i]; } } return r; }
function unescape(s){ s=String(s); var r='',i=0; while(i<s.length){ if(s[i]==='%'&&s[i+1]==='u'&&i+6<=s.length){ r+=String.fromCharCode(parseInt(s.substr(i+2,4),16)); i+=6; } else if(s[i]==='%'&&i+3<=s.length){ r+=String.fromCharCode(parseInt(s.substr(i+1,2),16)); i+=3; } else { r+=s[i]; i++; } } return r; }
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
"""


def _extract_stream_url(html, written):
    """提取流地址（对齐 QuickJsDecrypt.extractStreamUrl）"""
    url = ""
    fm = re.search(r'm3u8\.html\?id=([^"\'\s<]*)', written)
    if fm and fm.group(1):
        try:
            import urllib.parse
            raw = urllib.parse.unquote(fm.group(1))
        except Exception:
            raw = fm.group(1)
        url = raw if raw.startswith(("https://", "http://")) else ""
    if not url:
        dm = re.search(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', written, re.IGNORECASE)
        if dm:
            url = dm.group(0)
    if not url:
        xm = re.search(r'xgplayer\.html\?id=([^"\'\s<>]*)', html)
        if xm and xm.group(1):
            try:
                import urllib.parse
                u = urllib.parse.unquote(xm.group(1))
            except Exception:
                u = xm.group(1)
            if u.startswith(("https://", "http://")):
                url = u
    return url


def decrypt_html(html, match_id):
    """执行点播混淆脚本解密，返回 {"url":..., "html":...}（与 decrypt_stream.js 输出对齐）。
    quickjs 库必须已安装（PC 客户端打包时内置）；失败返回 {"url":"","html":""}。"""
    import quickjs

    out = {"url": "", "html": ""}
    m = re.search(r'<script[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return out
    code = m.group(1)
    # 清洗反调试（对齐 decrypt_stream.js 22-26 行）
    code = re.sub(r'\bdebugger\s*;', ';', code)
    code = re.sub(r'while\s*\(\s*!\s*\[\s*\]\s*\)\s*\{\s*\}', '{}', code)
    code = re.sub(r'while\s*\(\s*!!\s*\[\s*\]\s*\)\s*\{\s*\}', '{}', code)

    ctx = quickjs.Context()
    ctx.set_time_limit(20000)
    ctx.set_memory_limit(64 * 1024 * 1024)
    try:
        # matchId JSON 转义注入（对齐 Kotlin JSONObject.quote）
        import json as _json
        ctx.eval("var __matchId = " + _json.dumps(str(match_id)) + ";\n" + SANDBOX_JS)
        ctx.eval("try{\n" + code + "\n}catch(e){}")
        written = str(ctx.eval("__written") or "")
    except Exception:
        return out
    out["html"] = written[:500]
    out["url"] = _extract_stream_url(html, written)
    return out
