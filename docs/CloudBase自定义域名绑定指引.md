# CloudBase 自定义域名绑定指引（移除「风险提醒」中间页）

> 目标：把网页版从默认域名迁移到自有已备案域名，消除 QQ/X5 内核浏览器（MuMu、微信内置浏览器等）对 `*.tcloudbase.com` 默认域的安全拦截页。
> 实测结论（2026-09-09）：拦截发生在**浏览器侧 URL 安全校验**，服务器无法移除（curl 直连任意 UA 均返回正常页面），唯一解法是绑定干净的自定义域名。

## 当前线上状态（2026-09-09 实测）

- 环境：`appletv-d5ge1bth794873f76`（上海，个人版，**2026-10-09 到期，需留意续期**）
- 已绑域名：仅默认域 + 通配 `*`，未绑任何自定义域名
- 通配域承载 5 条路由（全部 `WEB_SCF` 类型，路径透传关、鉴权关）：

| 路由 | 上游云函数 |
|---|---|
| /activate | activate |
| /admin | otv-admin |
| /hotupdate | hotupdate |
| /iptv | iptv |
| /web | otv-web |

## 前置硬性条件（只有你能提供）

1. **一个你拥有的域名**（本机无腾讯云 API 密钥，无法代查账户资产；工程配置内也未出现过自有域名）。
2. **域名已 ICP 备案**——`tcb domains add` 强制校验，未备案会被拒绝。无备案域名需先完成备案（约 1-3 周，腾讯云控制台可提交）。
3. SSL 证书：优先试免传 `--certid`（自动申请免费证书）；失败再在控制台证书管理上传证书后传 ID。

## 绑定步骤（拿到域名后依次执行）

```bash
# 0) CLI 已登录（本机 cloudbase 3.8.1 凭证有效）
cloudbase login

# 1) 绑定域名到 HTTP 访问服务（假设域名为 tv.example.com）
cloudbase domains add tv.example.com -e appletv-d5ge1bth794873f76

# 2) 查 DNS 配置值：读输出里的 CName 列，到域名 DNS 服务商添加该 CNAME 记录
cloudbase domains ls -e appletv-d5ge1bth794873f76

# 3) 等解析生效后，把 5 条路由原样绑到新域名（路径透传/鉴权保持与现网一致）
cloudbase routes add -e appletv-d5ge1bth794873f76 --data '{
  "domain": "tv.example.com",
  "routes": [
    {"path": "/activate",  "upstreamResourceType": "WEB_SCF", "upstreamResourceName": "activate"},
    {"path": "/admin",     "upstreamResourceType": "WEB_SCF", "upstreamResourceName": "otv-admin"},
    {"path": "/hotupdate", "upstreamResourceType": "WEB_SCF", "upstreamResourceName": "hotupdate"},
    {"path": "/iptv",      "upstreamResourceType": "WEB_SCF", "upstreamResourceName": "iptv"},
    {"path": "/web",       "upstreamResourceType": "WEB_SCF", "upstreamResourceName": "otv-web"}
  ]
}'

# 4) 验证（应返回 My TV 页面 HTML）
curl -s https://tv.example.com/web/ | head -c 200

# 5) 在此前触发风险页的浏览器（MuMu 内置浏览器/微信）打开 https://tv.example.com/web/ 复验拦截消失

# 6)（可选）旧默认域下线：确认新域稳定后再删通配路由，避免 App 内置的默认域地址立即失效
#    cloudbase routes delete '*' -e appletv-d5ge1bth794873f76   # 谨慎：App/激活链接可能仍指向默认域
```

## 注意

- **App 端不依赖该域名**：Android 内嵌后端不走 `service.tcloudbase.com`，绑域只影响网页版与后台管理入口。
- 后台 `/admin` 绑到自有域后，建议保持强口令（域名越干净，被扫描的概率越高）。
- 环境个人版 **2026-10-09 到期**，到期前需在控制台续期，否则域名绑定与全部云函数一起下线。
