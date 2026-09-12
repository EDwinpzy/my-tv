#!/usr/bin/env python3
"""汇组 CloudRun 构建上下文（tools/cloudrun-admin/）并部署后台管理到腾讯云。

用法（部署前先填好环境变量，见 deploy.sh / 文档）：
  python build_context.py     # 仅汇组上下文（app/ + assets/ + Dockerfile）
部署：
  tools/cloudrun-admin/deploy.bat   # 调 CloudBase MCP / CLI 部署，或控制台上传本目录

镜像内容 = admin_server.py + admin.html + db_import.py + license_gen.py + 品牌字标；
敏感凭据（登录密码 / svc_import / 私钥）一律不进镜像，部署时以环境变量注入：
  OTV_ADMIN_USER / OTV_ADMIN_PASS   登录门禁（必填）
  OTV_AUTH_USER  / OTV_AUTH_PASS    svc_import 服务账号（必填）
  OTV_PRIV_KEY                       卡密签发私钥 PEM（可选：不设则云端补货禁用，
                                     仍可在本地 tools/admin_server.py 补货）
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
PROJ = TOOLS.parent

APP = HERE / "app"
ASSETS = HERE / "assets"


def main() -> None:
    if APP.exists():
        shutil.rmtree(APP)
    if ASSETS.exists():
        shutil.rmtree(ASSETS)
    APP.mkdir(parents=True)
    ASSETS.mkdir(parents=True)
    for name in ("admin_server.py", "admin.html", "db_import.py", "license_gen.py"):
        shutil.copy2(TOOLS / name, APP / name)
        print("app/", name)
    logo = PROJ / "android" / "app" / "src" / "main" / "res" / "drawable" / "my_tv_logo.png"
    shutil.copy2(logo, ASSETS / "my_tv_logo.png")
    print("assets/my_tv_logo.png")
    print("构建上下文就绪:", HERE)


if __name__ == "__main__":
    main()
