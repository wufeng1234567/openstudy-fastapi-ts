# OpenStudy 踩坑记录

## 13. DevBridge 隧道 auth 缓存过期（环境重启后隧道 404）

**日期**：2026-10-18

**现象**：
- 新一天开机后，本地服务（PG/Redis/后端/Nginx）全部正常，但 DevBridge 隧道返回 404
- `db_auth_status` 报 `"Not logged in: api key is invalid or disabled"`
- `db_create` 报 `"Unauthorized: error code: 40100, authentication failed"`
- keyring 里的 key（`hwcloud:HW_DEVBRIDGE_API_KEY`）明明还在（57 字符，以 `devbridge_` 开头）

**根因**：
- **不是 key 真的过期了**，而是 DevBridge WebUI 服务（端口 13000）的 **auth 缓存状态过期**
- 环境重启后，WebUI 进程重新启动，但它的认证状态没有从 keyring 自动恢复
- key 本身仍然有效，只是 WebUI 不知道

**修复**：
- 用 keyring 里的 key 通过 CLI 重新登录，刷新 WebUI 缓存：
  ```bash
  DB_KEY=$(hwcloud keyring get HW_DEVBRIDGE_API_KEY)
  # 在沙箱内执行
  devbridge auth login --api-key="$DB_KEY"
  ```
- 登录成功后，`db_auth_status` 立即恢复 `"Logged in (Huawei Cloud IAM)"`
- 隧道 `***REMOVED***` 仍在服务端（没被删），直接 `db_host ***REMOVED***` 重新托管即可
- **地址不变**：`https://***REMOVED***`

**已写入 daily-start.sh 的自动修复**（第 267 行附近）：
- `db_init` 之后自动检查 `db_auth_status`
- 如果不是 "Logged in"，自动从 keyring 读 key 并 `devbridge auth login`
- 用户无需任何手动操作，无需去控制台创建新 key

**⚠️ 重要**：
- **不要**让用户去 https://devstation.connect.huaweicloud.com/space/devbridge/apikey 创建新 key
- key 一直在 keyring 里，只是 WebUI 缓存过期了
- 如果自动修复也失败（key 真的过期了），才需要去控制台重新生成
