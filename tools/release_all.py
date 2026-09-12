#!/usr/bin/env python3
"""一键前后端发布（2026-09-07 需求⑤：热更/网页版前后端一起更新）。

改动 tools/backend-src/（后端五件套 + www/ 前端）后跑这个脚本：
  1. build_web_function.py  汇组云端 otv-web 部署包
  2. tcb fn deploy           部署云端网页版（/web/ 即时生效）
  3. build_backend_zip.py    重建 App 内嵌 python-backend.zip（www 前端随包）
     → 再到后台「热更新」页点「上传最新版本」发布给 App 设备

用法: python tools/release_all.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(cmd, cwd, input_text=None):
    print("$", " ".join(cmd) if isinstance(cmd, list) else cmd, f"(cwd={cwd})")
    r = subprocess.run(cmd, cwd=cwd, input=input_text, encoding="utf-8",
                       capture_output=True, text=True, shell=False)
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-3000:] if len(out) > 3000 else out)
    return r.returncode == 0


def main():
    ok1 = run([PY, os.path.join(ROOT, "tools", "build_web_function.py")], ROOT)
    if not ok1:
        raise SystemExit("build_web_function 失败")
    # tcb 部署是交互式（选择 Update with merged config）——回车选默认
    ok2 = run(["tcb", "fn", "deploy", "otv-web", "--httpFn", "--dir", ".",
               "-e", "appletv-d5ge1bth794873f76", "--force"],
              os.path.join(ROOT, "cloudfunctions", "otv-web"), input_text="\n")
    if not ok2:
        raise SystemExit("tcb 部署 otv-web 失败（可手动: cd cloudfunctions/otv-web && tcb fn deploy otv-web --httpFn --dir . -e appletv-d5ge1bth794873f76 --force）")
    ok3 = run([PY, os.path.join(ROOT, "tools", "build_backend_zip.py")], ROOT)
    if not ok3:
        raise SystemExit("build_backend_zip 失败")
    print(
        "\n✅ 云端网页版已部署（/web/ 即时生效）\n"
        "✅ App 热更包已重建（android/app/src/main/assets/backend/python-backend.zip，含 www 前端）\n"
        "→ 到后台「热更新」页点「上传最新版本」把新包发布给 App 设备。"
    )


if __name__ == "__main__":
    main()
