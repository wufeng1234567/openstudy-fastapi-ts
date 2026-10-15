# OpenStudy 数据库部署

PostgreSQL 16（需 `vector` + `pg_trgm` 扩展）。

## 一键导入

```bash
# 1) 建库（库名可自定义，默认 openstudy_v2_pgsql）
createdb openstudy_v2_pgsql

# 2) 导入结构 + 种子 + 演示数据
psql -U root -d openstudy_v2_pgsql -f openstudy_v2_pgsql_deploy.sql

# 3) 回到 openstudy-fastapi，配置 .env 里的 PG_*，启动后端
#    首次启动时 ORM 会做增量校验；本 SQL 已含全部表结构，通常无需再建。
```

> Docker 部署 PostgreSQL 时，可用：`docker cp openstudy_v2_pgsql_deploy.sql pgsql:/tmp/ && docker exec pgsql psql -U root -d openstudy_v2_pgsql -f /tmp/openstudy_v2_pgsql_deploy.sql`

## 文件说明

| 文件 | 内容 |
| --- | --- |
| `openstudy_v2_pgsql_deploy.sql` | 完整部署：建表结构 + 部门/角色/菜单/参数 + 演示数据 |

## 演示账号

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin123` | 超级管理员 |
| `demo`  | `admin123` | 普通用户 |

⚠️ **首次登录后请立即修改密码。**

## 已清洗内容（重要）

- `sys_ai_config.api_key`：真实 Key 已全部移除，替换为占位符 `YOUR_API_KEY_HERE`。
  部署后在「系统管理 → AI 模型配置」里填写你自己的 Key。
- 真实用户、题库、题目、笔记、RAG 文档等业务数据：已删除，仅保留少量演示数据。
- 系统参数中的默认初始密码（`sys.user.initPassword = 123456`）为 RuoYi 内置默认值，可按需修改。

## 模型配置

导入后 `sys_ai_config` 含三条：

| config_id | provider | model | 说明 |
| --- | --- | --- | --- |
| 1 | `deepseek` | `deepseek-flash` | 默认对话模型（占位 Key） |
| 2 | `deepseek` | `deepseek-v4-pro` | 高级模型（占位 Key） |
| 3 | `ds-free-nb` | `ds-free-nb` | 本机 DS 网页无头桥（需先启动 `startup-scripts/ds-bridge`） |
