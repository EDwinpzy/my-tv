#!/bin/bash
# 遥控器按键驱动：逐键独立注入（每键 0.55s 间隔），输出每键时间标记 + OptimalTV 焦点日志
# usage: focus_drive.sh <keycode>...   (UP=19 DOWN=20 LEFT=21 RIGHT=22 OK=23 BACK=4 MENU=82)
# 串口可用环境变量覆盖：SER=127.0.0.1:16384 focus_drive.sh 20 20 22
#   （MuMu 多实例 adb 端口会变：mumu-mcp preflight / acquire_instance 查当前端口）
ADB="${ADB:-/c/应用/MuMuPlayer/nx_main/adb.exe}"
SER="${SER:-127.0.0.1:16384}"
"$ADB" -s $SER shell logcat -c 2>/dev/null
i=0
for k in "$@"; do
  i=$((i+1))
  echo "=== key#$i $k @ $(date +%H:%M:%S)"
  "$ADB" -s $SER shell input keyevent "$k"
  sleep 0.55
done
echo "--- focus log ---"
"$ADB" -s $SER shell logcat -d -s OptimalTV:V | tail -120
