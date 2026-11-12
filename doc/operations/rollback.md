# OpenStudy Rollback Runbook

> 当前状态：数据库迁移仍主要依赖 `init_db()` + `deploy/db-init/*.sql`，`alembic.ini` 指向的迁移目录尚未建立。以下流程是 P1 目标；在迁移补齐前，不要把它当作已验证的回滚能力。

## 1. 应用回滚（代码）

1. 记录当前 `git rev-parse HEAD` 和部署镜像 tag；
2. 在发布记录中确认上一稳定 commit；
3. 使用部署脚本切回上一镜像/commit；
4. 验证 `/health`、登录页、资料空间、练习页；
5. 把回滚原因、时间、影响范围写入 `doc/operations/release-log.md`。

## 2. 数据库回滚（迁移补齐前）

- 任何 schema 变更必须先备份：`backup-sql.sh`；
- 优先使用向后兼容变更（新增列/表），避免 rename/drop；
- 禁止直接在生产执行未经备份的 `ALTER/DROP`；
- 迁移补齐后，每个 migration 必须同时提供 `upgrade` 和可验证的 `downgrade`。

## 3. 发布前检查

```bat
scripts\verify-quality.bat
```

- 后端 compile/ruff/pytest 通过；
- 前端 build 通过；
- `git status` 干净；
- 环境变量/密钥未进入 Git；
- 有数据库备份和回滚点。

## 4. 事故记录

记录：时间、版本、现象、影响用户、根因、临时处置、永久修复、验证命令。不要只写“已修复”。
