#!/usr/bin/env python3
"""汇组网页版 HTTP Web 函数部署包（cloudfunctions/otv-web/）。

用法: python tools/build_web_function.py
产出: cloudfunctions/otv-web/ = backend-src 后端五件套 + www/ 前端
      + scf_bootstrap（PORT=9000, OTV_BIND=0.0.0.0）+ scf_main.py（诊断启动器）
      + package.json + requirements.txt（urllib3 可选，装不上自动走纯标准库分支）
部署: cd cloudfunctions/otv-web
      tcb fn deploy otv-web --httpFn --dir . -e appletv-d5ge1bth794873f76 --force
      网关路由 /web（manageGateway createAccess，path passthrough 由网关剥离前缀）。
      外网入口: https://appletv-d5ge1bth794873f76.service.tcloudbase.com/web/
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "backend-src"
OUT = ROOT / "cloudfunctions" / "otv-web"
WHEEL = ROOT / "tools" / "vendor" / "quickjs-1.19.4-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"

FILES = ["proxy.py", "hhkan.py", "hhkan_snapshot.py", "hhkan_snapshot.json",
         "team_backdrop.py", "scraper.py", "decrypt_stream.js",
         "decrypt_python.py", "douban_catalog.py", "douban_snapshot.json", "media_index.py", "pinyin_map.json",
         "vod_api.py", "vod_sources.py", "vod_sources.default.json"]

BOOTSTRAP = """#!/bin/bash
cd /var/user
export PORT=${PORT:-9000}
export OTV_BIND=0.0.0.0
# 腾讯云数据中心出口会被好好看风控；冷实例先读好好看快照，5 分钟后单次探测恢复。
export OTV_HHKAN_SNAPSHOT_FIRST=1
# 云端自身禁用「云端兜底」（proxy.py 的 yoozb 拉黑回退链路）：云端再请求自己
# 的公网地址会绕一圈网关且可能自环；该兜底只服务设备/本地出口被拉黑的场景。
export OTV_CLOUD_RELAY=0
# quickjs（足球解密兜底）wheel 随包内置（build_web_function.py 解包至 vendor/）
export PYTHONPATH=/var/user/vendor:${PYTHONPATH}
exec python3 scf_main.py
"""

SCF_MAIN = '''#!/usr/bin/env python3
"""SCF Web 函数启动器（otv-web 网页版）：proxy 正常则同进程托管；
任何导入/启动异常则起 500 应答服务器把 traceback 直接回给请求方
（无 CLS 时排查初始化失败用，与 otv-admin 同款）。"""
import sys
import traceback

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def emergency_server(err: str) -> None:
    class H(BaseHTTPRequestHandler):
        def _dump(self) -> None:
            body = ("otv-web 启动失败\\n\\n" + err).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._dump()

        def do_POST(self) -> None:  # noqa: N802
            self._dump()

        def log_message(self, fmt, *args):
            sys.stderr.write("%s\\n" % (fmt % args))

    ThreadingHTTPServer(("0.0.0.0", int(__import__("os").environ.get("PORT") or 9000)), H).serve_forever()


if __name__ == "__main__":
    try:
        import proxy  # noqa: F401  模块级初始化（缓存/线程均在 main 内起）
        proxy.main()          # PORT/OTV_BIND 由 scf_bootstrap 注入：9000 / 0.0.0.0
    except SystemExit:
        raise
    except BaseException:
        emergency_server(traceback.format_exc())
'''

PACKAGE_JSON = """{
  "name": "otv-web",
  "version": "1.21.0",
  "description": "My TV 网页版（HTTP Web 函数：影视点播 + IPTV 直播 + HLS 中继）"
}
"""

REQUIREMENTS = "# urllib3 仅供中继连接复用；运行时未装则自动回落纯 urllib 分支，功能不受影响\\nurllib3>=2.0,<3\\n"


def _reset_dir(p: Path) -> None:
    """清空目录内容但容忍根目录被占用（Windows 下残留 shell 的 cwd 会锁目录本身，
    子文件不受影响——rmtree 整目录会 PermissionError，逐个删除则可通过）。"""
    p.mkdir(parents=True, exist_ok=True)
    for child in p.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def main() -> None:
    _reset_dir(OUT)
    for name in FILES:
        src = SRC / name
        if not src.is_file():
            raise SystemExit("缺少 %s" % src)
        shutil.copy2(src, OUT / name)
        print("otv-web/", name)
    shutil.copytree(SRC / "www", OUT / "www", ignore=shutil.ignore_patterns("*.log"))
    n = sum(1 for _ in (OUT / "www").rglob("*") if _.is_file())
    print("otv-web/www/ (%d 个文件)" % n)
    (OUT / "scf_bootstrap").write_text(BOOTSTRAP, encoding="utf-8", newline="\n")
    (OUT / "scf_main.py").write_text(SCF_MAIN, encoding="utf-8", newline="\n")
    (OUT / "requirements.txt").write_text(REQUIREMENTS.replace("\\n", "\n"), encoding="utf-8", newline="\n")
    # 不放 package.json：tcb 会据此把运行时推断成 Node.js（实测误判为 Nodejs20.19）；
    # requirements.txt + scf_bootstrap 存在时正确推断 Python3.9 Web 函数。
    # quickjs wheel 解包到 vendor/（云函数 PYTHONPATH 注入；足球解密兜底，v1.22）
    import zipfile
    if WHEEL.is_file():
        vendor = OUT / "vendor"
        vendor.mkdir(exist_ok=True)
        with zipfile.ZipFile(WHEEL) as zf:
            zf.extractall(vendor)
        n = sum(1 for _ in vendor.rglob("*") if _.is_file())
        print("vendor/ (quickjs, %d 个文件)" % n)
    else:
        print("⚠ 未找到 quickjs wheel（足球解密兜底不可用）:", WHEEL)
    print("scf_bootstrap / scf_main.py / requirements.txt")
    print("部署包就绪:", OUT)


if __name__ == "__main__":
    main()
