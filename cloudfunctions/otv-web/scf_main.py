#!/usr/bin/env python3
"""SCF Web 函数启动器（otv-web 网页版）：proxy 正常则同进程托管；
任何导入/启动异常则起 500 应答服务器把 traceback 直接回给请求方
（无 CLS 时排查初始化失败用，与 otv-admin 同款）。"""
import sys
import traceback

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def emergency_server(err: str) -> None:
    class H(BaseHTTPRequestHandler):
        def _dump(self) -> None:
            body = ("otv-web 启动失败\n\n" + err).encode("utf-8")
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
            sys.stderr.write("%s\n" % (fmt % args))

    ThreadingHTTPServer(("0.0.0.0", int(__import__("os").environ.get("PORT") or 9000)), H).serve_forever()


if __name__ == "__main__":
    try:
        import proxy  # noqa: F401  模块级初始化（缓存/线程均在 main 内起）
        proxy.main()          # PORT/OTV_BIND 由 scf_bootstrap 注入：9000 / 0.0.0.0
    except SystemExit:
        raise
    except BaseException:
        emergency_server(traceback.format_exc())
