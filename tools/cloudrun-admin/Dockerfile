# My TV 后台管理系统（腾讯云 CloudBase 云托管容器）
# 外网 HTTPS 访问 + 登录门禁（Cookie 会话）；凭据全部走环境变量，不进镜像层。
FROM python:3.12-slim

WORKDIR /app

# 补货（license_gen.py）需要 cryptography 签名；其余全标准库
RUN pip install --no-cache-dir cryptography

# 管理端代码（tools/ 下的四个文件，构建上下文 = tools/cloudrun-admin/，文件由部署脚本汇入）
COPY app/admin_server.py app/admin.html app/db_import.py app/license_gen.py /app/tools/

# 品牌字标（admin_server 按 ROOT.parent/android/... 只读引用）
COPY assets/my_tv_logo.png /app/android/app/src/main/res/drawable/my_tv_logo.png

# 补货批次输出目录（容器临时盘）
RUN mkdir -p /app/tools/out /app/tools/keys

ENV PORT=8080
EXPOSE 8080

CMD ["python", "/app/tools/admin_server.py"]
