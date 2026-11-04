---
name: openstudy-release
description: OpenStudy 提交前预检。当用户要提交、发布、合入或跑回归时使用。依次执行后端编译检查、前端生产构建、关键探针，任一失败即停止并说明原因。
---

# OpenStudy 提交前预检

## 步骤（按顺序，失败即停）

1. 后端编译检查
   ```bash
   cd openstudy-fastapi
   .venv/Scripts/python.exe -m compileall app -q
   ```

2. 前端生产构建
   ```bash
   cd openstudy-vue3-ts
   npm run build:prod
   ```

3. 关键探针
   ```bash
   cd openstudy-fastapi
   .venv/Scripts/python.exe tests/_toolpref_probe.py
   ```
   再逐个运行 `tests/_probe*.py`，记录通过/失败数。

4. 输出汇总表：步骤 / 结果 / 耗时 / 备注。全绿才提示可以提交。

## 约束
- 只读执行，不修改源码，不自动提交
- 不安装新依赖，缺包如实报告
- 输出使用中文
