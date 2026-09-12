#!/usr/bin/env python3
"""把 license_gen.py 批次目录导入 CloudBase PG（v1.17 运维工具）

鉴权：svc_import 服务账号 signin 换 2 小时 access_token 后调 import_licenses RPC
（SECURITY DEFINER + 函数内 auth.uid() 白名单，仅 svc_import 可执行）。
凭据存 tools/keys/svc_import_*.txt，属敏感文件，不入仓库不进会话正文。

用法:
  python db_import.py out/20260902-monthly-100

批次目录需含 cards.csv（note 来源）与 tickets.jsonl（票据原文），由 license_gen.py 生成。
"""
import argparse
import csv
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
KEYS = ROOT / "keys"
# 请求目标硬编码为本项目 CloudBase 环境的 PG HTTP API 网关（https + 域名白名单，防 SSRF）
ALLOWED_HOST = "appletv-d5ge1bth794873f76.api.tcloudbasegateway.com"
BASE = f"https://{ALLOWED_HOST}"
PUBKEY_FILE = KEYS / "publishable_key.txt"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "重定向被拒绝", headers, fp)


def check_url(url: str):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname != ALLOWED_HOST or u.port is not None:
        raise ValueError(f"目标 URL 不在白名单内: {url}")


def signin() -> str:
    # v1.20 云端形态（HTTP 云函数/容器）：优先环境变量注入的 svc_import 凭据，
    # 本地形态回退 keys/ 文件（不入仓库不入镜像层）
    import os
    user = os.environ.get("OTV_AUTH_USER") or (KEYS / "svc_import_user.txt").read_text(encoding="utf-8").strip()
    pw = os.environ.get("OTV_AUTH_PASS") or (KEYS / "svc_import_pass.txt").read_text(encoding="utf-8").strip()
    url = BASE + "/auth/v1/signin"
    check_url(url)
    req = urllib.request.Request(
        url, data=json.dumps({"username": user, "password": pw}).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as r:
        out = json.loads(r.read().decode("utf-8"))
    tok = out.get("access_token")
    if not tok:
        sys.exit(f"signin 未返回 access_token: {list(out.keys())}")
    return tok


def main():
    p = argparse.ArgumentParser(description="导入卡密批次到 CloudBase PG")
    p.add_argument("dir", help="license_gen.py 输出的批次目录")
    args = p.parse_args()

    d = pathlib.Path(args.dir)
    if not (d / "tickets.jsonl").exists():
        sys.exit(f"找不到 {d}/tickets.jsonl")

    tickets = [json.loads(ln) for ln in (d / "tickets.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    with (d / "cards.csv").open(encoding="utf-8-sig", newline="") as f:
        cards = list(csv.DictReader(f))
    if len(tickets) != len(cards):
        sys.exit(f"cards.csv({len(cards)}) 与 tickets.jsonl({len(tickets)}) 行数不一致")

    rows = [{"code": t["code"], "plan": t["plan"], "days": t["days"],
             "note": c.get("note", ""), "ticket": t}
            for t, c in zip(tickets, cards)]

    tok = signin()
    url = BASE + "/v1/rdb/rest/rpc/import_licenses"
    check_url(url)
    req = urllib.request.Request(
        url,
        data=json.dumps({"p_rows": rows}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + tok},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=60) as r:
            print(f"{d.name}: HTTP {r.status} → {r.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8')[:500]}")


if __name__ == "__main__":
    main()
