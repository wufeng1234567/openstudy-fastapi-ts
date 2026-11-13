# OpenStudy 部署与运维文档索引

现有部署材料已经较完整，本目录只做入口，不重复维护命令：

| 场景 | 文档 |
|---|---|
| Linux 服务器 / Windows Docker / 免 Docker 手动安装 / 公网访问 | [deploy/SKILL.md](../deploy/SKILL.md) |
| 部署经验与踩坑 | [deploy/DEPLOY-EXPERIENCE.md](../deploy/DEPLOY-EXPERIENCE.md) |
| 故障排查 | [deploy/TROUBLESHOOTING.md](../deploy/TROUBLESHOOTING.md) |
| 回滚 Runbook | [rollback.md](rollback.md) |
| 数据备份/恢复脚本 | [backup-sql.sh](../../backup-sql.sh)、[restore-sql.sh](../../restore-sql.sh) |

## 已知缺口（P1）

- 回滚 Runbook 已成文但尚未验证（依赖迁移版本化）；
- `alembic.ini` 指向的迁移目录不存在，当前 schema 依赖 `init_db()` + 手写 SQL；
- 数据库迁移必须补版本化与回滚验证后，才能把部署质量标为完整。
