#!/usr/bin/env bash
# 公测版定稿监控 v2：
# 唤醒条件（任一满足即退出 0，后台任务退出会唤醒会话）：
#   A) docs 出现公测发布记录（README/测试记录 含 gongce 或「公测版…发布/versionCode」）→ 立即唤醒
#   B) 稳定信号：公测 APK 已存在 且 android/、apk/、docs/、tools/、internal/ 均无最近 8 分钟修改
#      （另一会话收尾完成、文件系统静止）
#   C) 目录异动：出现新的工程根目录（另一会话开始整理文件夹，可能移动 android/）
# 12 小时无信号退出 1（防僵尸；需重启监控）。
cd "D:/MyProjects/Apple TV"
mkdir -p tools/out
START=$(date +%s)
echo "WATCH_START $(date)" >> tools/out/public_release_detected.txt
while true; do
  # A) 文档发布记录
  if grep -qE "gongce|公测版.{0,20}(发布|versionCode)" docs/04-records/版本史.md docs/04-records/测试记录.md 2>/dev/null; then
    echo "SIGNAL=docs-release $(date)" >> tools/out/public_release_detected.txt
    echo "公测定稿：文档发布记录出现"
    exit 0
  fi
  # B) 稳定信号：公测 APK + 全项目静止 8 分钟（APK 按类别归档在 apk/公测TV、apk/公测移动）
  if find apk -maxdepth 2 -type f \( -name "*公测*" -o -iname "*gongce*" \) 2>/dev/null | grep -q .; then
    RECENT=$(find android apk docs tools internal -newermt "-8 minutes" -print -quit 2>/dev/null)
    if [ -z "$RECENT" ]; then
      echo "SIGNAL=stable $(date)" >> tools/out/public_release_detected.txt
      echo "公测定稿：APK 存在且项目静止 8 分钟"
      exit 0
    fi
  fi
  # C) 目录异动：本项目根出现内测/公测语义的新目录（另一会话整理文件夹）
  for d in 内测版 公测版 beta public internal/tv public/tv public/mobile; do
    if [ -e "$d" ] && [ "$d" != "internal/mobile" ]; then
      echo "SIGNAL=layout $d $(date)" >> tools/out/public_release_detected.txt
      echo "目录异动：$d 出现（另一会话在整理结构）"
      exit 0
    fi
  done
  # 12h 超时
  NOW=$(date +%s)
  if [ $((NOW-START)) -gt 43200 ]; then
    echo "WATCH_TIMEOUT $(date)" >> tools/out/public_release_detected.txt
    echo "监控 12h 超时未检测到公测定稿信号"
    exit 1
  fi
  sleep 180
done
