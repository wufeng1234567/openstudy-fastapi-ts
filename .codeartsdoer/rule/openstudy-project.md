# OpenStudy 项目开发规范（码道项目级规则）

> 存放位置：`./.codeartsdoer/rule/openstudy-project.md`（码道项目级规则目录，随仓库分发）

## 技术栈
- 后端：Python 3.11 + FastAPI + SQLAlchemy + PostgreSQL 16 + pgvector
- 前端：Vue 3 + TypeScript（strict）+ Vite
- 数据库脚本：`deploy/db-init/*.sql`，编号递增，不改历史文件

## 代码规范
- Python 遵循 PEP 8；公共函数写中文 docstring 并标注类型
- 金额、分数一律用 `Decimal`，禁止 `float`
- 数据库写操作放在事务内；删除必须处理关联表
- 前端禁止 `any`；接口返回类型必须定义；组件使用 `<script setup lang="ts">`

## 安全
- 用户输入统一走 `app/utils/html_sanitize.py`
- 列表接口必须分页并校验权限；越权返回 403，不返回 500
- 不把密钥、连接串写入代码或日志

## 开发方式
- 改代码前先 `grep` / `read` 定位，不凭猜测改 API
- 一次只解决一个问题，改完先跑相关探针
- 提交信息用中文，格式 `type: 简述`（feat/fix/docs/refactor/test/chore）
- 不自动 `git push`，除非明确要求
