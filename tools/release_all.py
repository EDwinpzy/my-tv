#!/usr/bin/env python3
"""构建本地前后端交付物，并按显式参数执行网页版部署。

改动 tools/backend-src/（后端五件套 + www/ 前端）后默认只做本地构建：
  1. build_web_function.py  汇组云端 otv-web 部署包
  2. build_backend_zip.py    重建 App 内嵌 python-backend.zip（www 前端随包）

得到用户明确确认后，才使用 `--deploy` 部署云端网页版；热更新包上传/发布
仍必须在后台单独操作，不由本脚本自动推送。

用法: python tools/release_all.py
部署: python tools/release_all.py --deploy
"""
import argparse
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
    parser = argparse.ArgumentParser(description="Build local deliverables; deploy only with explicit --deploy")
    parser.add_argument("--deploy", action="store_true",
                        help="deploy otv-web after the user has explicitly approved the exact scope")
    args = parser.parse_args()

    ok1 = run([PY, os.path.join(ROOT, "tools", "build_web_function.py")], ROOT)
    if not ok1:
        raise SystemExit("build_web_function 失败")

    # 先完成全部本地交付物构建，再考虑任何外部动作。
    ok3 = run([PY, os.path.join(ROOT, "tools", "build_backend_zip.py")], ROOT)
    if not ok3:
        raise SystemExit("build_backend_zip 失败")

    if args.deploy:
        # tcb 部署是交互式（选择 Update with merged config）——回车选默认。
        ok2 = run(["tcb", "fn", "deploy", "otv-web", "--httpFn", "--dir", ".",
                   "-e", "appletv-d5ge1bth794873f76", "--force"],
                  os.path.join(ROOT, "cloudfunctions", "otv-web"), input_text="\n")
        if not ok2:
            raise SystemExit("tcb 部署 otv-web 失败（可手动: cd cloudfunctions/otv-web && tcb fn deploy otv-web --httpFn --dir . -e appletv-d5ge1bth794873f76 --force）")
    if args.deploy:
        print("\n✅ 本地交付物已构建\n✅ 云端网页版已部署（/web/ 即时生效）\n"
              "✅ App 热更包已重建（android/app/src/main/assets/backend/python-backend.zip，含 www 前端）\n"
              "→ App 热更新仍需到后台手动上传并发布。")
    else:
        print("\n✅ 本地交付物已构建\n"
              "✅ 云端网页版部署包已生成（未部署）\n"
              "✅ App 热更包已重建（android/app/src/main/assets/backend/python-backend.zip，含 www 前端）\n"
              "⏸ 未执行部署、上传或推送；获得用户明确确认后再运行 --deploy，并在后台发布热更新。")


if __name__ == "__main__":
    main()
