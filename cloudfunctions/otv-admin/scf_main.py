#!/usr/bin/env python3
"""SCF Web 函数诊断启动器：admin_server 正常则同进程托管；
任何导入/启动异常则起 500 应答服务器把 traceback 直接回给请求方
（SCF 无 CLS 时排查初始化失败用）。"""
import sys
import traceback

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def emergency_server(err: str) -> None:
    class H(BaseHTTPRequestHandler):
        def _dump(self) -> None:
            body = ("otv-admin 启动失败\n\n" + err).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._dump()

        def do_POST(self) -> None:  # noqa: N802
            self._dump()

        def log_message(self, fmt, *args):  # 静默访问日志
            sys.stderr.write("%s\n" % (fmt % args))

    ThreadingHTTPServer(("0.0.0.0", int(__import__("os").environ.get("PORT") or 9000)), H).serve_forever()


if __name__ == "__main__":
    try:
        import admin_server  # noqa: F401  导入即完成凭据注入等模块级初始化
        admin_server.main()
    except SystemExit:
        raise
    except BaseException:
        emergency_server(traceback.format_exc())
