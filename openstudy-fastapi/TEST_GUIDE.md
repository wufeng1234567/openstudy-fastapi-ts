# OpenStudy FastAPI 后端测试文档

## 前置条件

1. PostgreSQL 16 运行中 (Docker: pgsql, 端口 5432)
2. Redis 运行中 (Docker: redis-stack, 端口 6379)
3. 已创建 `openstudy` 数据库
4. 已运行建表脚本
5. FastAPI 服务运行在 `http://localhost:9000`

## 环境变量

```bash
# 设置基础 URL
BASE_URL=http://localhost:9000

# 设置 Token（登录后获取）
TOKEN=""
```

---

## 1. 基础接口

### 1.1 健康检查

```bash
curl -X GET "$BASE_URL/health" \
  -H "Content-Type: application/json"
```

**期望响应：**
```json
{"status": "ok"}
```

### 1.2 根路径

```bash
curl -X GET "$BASE_URL/" \
  -H "Content-Type: application/json"
```

**期望响应：**
```json
{
  "code": 200,
  "msg": "OpenStudy API is running",
  "data": {
    "version": "1.0.0",
    "docs": "/swagger-ui.html"
  }
}
```

### 1.3 Swagger 文档

```bash
# 浏览器访问
open http://localhost:9000/swagger-ui.html
```

---

## 2. 认证接口

### 2.1 用户注册

```bash
curl -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test123456",
    "nick_name": "测试用户"
  }'
```

**期望响应：**
```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "user_id": 2
  }
}
```

### 2.2 用户登录

```bash
curl -X POST "$BASE_URL/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

**期望响应：**
```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "token": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

**保存 Token：**
```bash
TOKEN="获取到的token"
```

### 2.3 获取用户信息

```bash
curl -X GET "$BASE_URL/getInfo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**期望响应：**
```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "user": {
      "userId": 1,
      "userName": "admin",
      "nickName": "管理员",
      "email": "",
      "phonenumber": "",
      "sex": "0",
      "avatar": "",
      "status": "0"
    },
    "roles": ["admin"],
    "permissions": ["*:*:*"]
  }
}
```

### 2.4 获取路由菜单

```bash
curl -X GET "$BASE_URL/getRouters" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3. 用户管理接口

### 3.1 查询用户列表

```bash
curl -X GET "$BASE_URL/system/user/list?pageNum=1&pageSize=10" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**带条件查询：**
```bash
curl -X GET "$BASE_URL/system/user/list?pageNum=1&pageSize=10&userName=admin&status=0" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 3.2 查询用户详情

```bash
curl -X GET "$BASE_URL/system/user/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 3.3 创建用户

```bash
curl -X POST "$BASE_URL/system/user" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_name": "user001",
    "nick_name": "用户001",
    "password": "123456",
    "email": "user001@example.com",
    "phonenumber": "13800138001",
    "sex": "0",
    "status": "0"
  }'
```

### 3.4 更新用户

```bash
curl -X PUT "$BASE_URL/system/user" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 2,
    "nick_name": "用户001-修改",
    "email": "user001_new@example.com"
  }'
```

### 3.5 删除用户

```bash
curl -X DELETE "$BASE_URL/system/user/2" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 3.6 重置密码

```bash
curl -X PUT "$BASE_URL/system/user/resetPwd" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 2,
    "password": "newpassword123"
  }'
```

---

## 4. 通知公告接口

### 4.1 查询公告列表

```bash
curl -X GET "$BASE_URL/system/notice/list?pageNum=1&pageSize=10" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**带条件查询：**
```bash
curl -X GET "$BASE_URL/system/notice/list?pageNum=1&pageSize=10&noticeType=1&status=0" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 4.2 查询公告详情

```bash
curl -X GET "$BASE_URL/system/notice/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 4.3 创建公告

```bash
curl -X POST "$BASE_URL/system/notice" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "notice_title": "系统更新通知",
    "notice_type": "1",
    "notice_content": "系统将于今晚进行维护更新，请提前保存数据。",
    "status": "0"
  }'
```

### 4.4 更新公告

```bash
curl -X PUT "$BASE_URL/system/notice" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "notice_id": 1,
    "notice_title": "系统更新通知-修改",
    "notice_content": "系统维护时间已调整，请注意。"
  }'
```

### 4.5 删除公告

```bash
curl -X DELETE "$BASE_URL/system/notice/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 5. 题库管理接口

### 5.1 查询题库列表

```bash
curl -X GET "$BASE_URL/questionBank/list?pageNum=1&pageSize=10" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**带条件查询：**
```bash
curl -X GET "$BASE_URL/questionBank/list?pageNum=1&pageSize=10&bankName=Python&status=0" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 5.2 查询题库详情

```bash
curl -X GET "$BASE_URL/questionBank/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 5.3 创建题库

```bash
curl -X POST "$BASE_URL/questionBank" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "bank_name": "Python基础题库",
    "bank_description": "Python基础知识练习题",
    "category": "编程语言",
    "status": "0"
  }'
```

### 5.4 更新题库

```bash
curl -X PUT "$BASE_URL/questionBank" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "bank_id": 1,
    "bank_name": "Python基础题库-修改",
    "bank_description": "更新后的描述"
  }'
```

### 5.5 删除题库

```bash
curl -X DELETE "$BASE_URL/questionBank/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. 题目管理接口

### 6.1 查询题目列表

```bash
curl -X GET "$BASE_URL/questionMain/list?pageNum=1&pageSize=10" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**带条件查询：**
```bash
curl -X GET "$BASE_URL/questionMain/list?pageNum=1&pageSize=10&bankId=1&questionType=single" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.2 查询题目详情

```bash
curl -X GET "$BASE_URL/questionMain/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.3 创建题目

```bash
curl -X POST "$BASE_URL/questionMain" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "bank_id": 1,
    "question_type": "single",
    "question_content": "Python中哪个关键字用于定义函数？",
    "question_answer": "B",
    "question_analysis": "def 是 Python 中定义函数的关键字",
    "difficulty": 1,
    "score": 1
  }'
```

### 6.4 删除题目

```bash
curl -X DELETE "$BASE_URL/questionMain/1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 7. AI 功能接口

### 7.1 查询 AI 提供商

```bash
curl -X GET "$BASE_URL/ai/providers" \
  -H "Content-Type: application/json"
```

**期望响应：**
```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "providers": ["zhipu", "deepseek", "siliconflow"],
    "models": {
      "zhipu": ["glm-4", "glm-4-plus", "glm-4v", "glm-3", "embedding-3"],
      "deepseek": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
      "siliconflow": ["Qwen/Qwen2.5-7B-Instruct", "..."]
    }
  }
}
```

### 7.2 AI 聊天

```bash
curl -X POST "$BASE_URL/ai/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [
      {"role": "user", "content": "你好，请介绍一下Python语言的特点"}
    ],
    "model": "glm-4-plus",
    "temperature": 0.7,
    "max_tokens": 1000
  }'
```

### 7.3 AI 流式聊天

```bash
curl -X POST "$BASE_URL/ai/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [
      {"role": "user", "content": "用简单的语言解释什么是机器学习"}
    ],
    "model": "glm-4-plus",
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

### 7.4 AI 出题

```bash
curl -X POST "$BASE_URL/ai/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "topic": "Python基础语法",
    "question_type": "single",
    "count": 3,
    "difficulty": 2,
    "model": "glm-4-plus"
  }'
```

**直接保存到题库：**
```bash
curl -X POST "$BASE_URL/ai/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "topic": "Python数据类型",
    "question_type": "single",
    "count": 5,
    "difficulty": 2,
    "bank_id": 1,
    "model": "glm-4-plus"
  }'
```

---

## 8. 错误场景测试

### 8.1 未登录访问

```bash
curl -X GET "$BASE_URL/system/user/list" \
  -H "Content-Type: application/json"
```

**期望响应：**
```json
{
  "code": 401,
  "msg": "未登录或登录已过期",
  "data": null
}
```

### 8.2 Token 过期

```bash
curl -X GET "$BASE_URL/system/user/list" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer expired-token"
```

### 8.3 创建重复用户名

```bash
curl -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "test123",
    "nick_name": "重复用户"
  }'
```

**期望响应：**
```json
{
  "code": 500,
  "msg": "用户名已存在",
  "data": null
}
```

### 8.4 查询不存在的资源

```bash
curl -X GET "$BASE_URL/questionBank/99999" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

**期望响应：**
```json
{
  "code": 500,
  "msg": "题库不存在",
  "data": null
}
```

---

## 11. 完整测试流程

### 流程一：用户注册 -> 登录 -> 创建题库 -> 创建题目

```bash
# 1. 注册
curl -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"testflow","password":"test123456","nick_name":"流程测试用户"}'

# 2. 登录
curl -X POST "$BASE_URL/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"testflow","password":"test123456"}'
# 保存返回的 token

# 3. 创建题库
curl -X POST "$BASE_URL/questionBank" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"bank_name":"测试题库","bank_description":"流程测试题库","category":"测试"}'

# 4. 创建题目
curl -X POST "$BASE_URL/questionMain" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"bank_id":1,"question_type":"single","question_content":"1+1=?","question_answer":"B","difficulty":1}'

# 5. 查询验证
curl -X GET "$BASE_URL/questionBank/1" \
  -H "Authorization: Bearer $TOKEN"

curl -X GET "$BASE_URL/questionMain/list?bankId=1" \
  -H "Authorization: Bearer $TOKEN"
```

### 流程二：AI 出题 -> 保存到题库

```bash
# 1. AI 出题并保存到题库
curl -X POST "$BASE_URL/ai/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"topic":"Python列表操作","question_type":"single","count":5,"difficulty":2,"bank_id":1}'

# 2. 查询题目验证
curl -X GET "$BASE_URL/questionMain/list?bankId=1&pageNum=1&pageSize=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 10. 自动化测试脚本

### test_all.sh

```bash
#!/bin/bash

BASE_URL="http://localhost:9000"
TOKEN=""

echo "========== 1. 健康检查 =========="
curl -s -X GET "$BASE_URL/health" | jq .

echo ""
echo "========== 2. 用户注册 =========="
curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"autotest","password":"test123456","nick_name":"自动测试"}' | jq .

echo ""
echo "========== 3. 用户登录 =========="
RESPONSE=$(curl -s -X POST "$BASE_URL/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')
echo $RESPONSE | jq .
TOKEN=$(echo $RESPONSE | jq -r '.data.token')

echo ""
echo "========== 4. 获取用户信息 =========="
curl -s -X GET "$BASE_URL/getInfo" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo ""
echo "========== 5. 创建题库 =========="
curl -s -X POST "$BASE_URL/questionBank" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"bank_name":"自动化测试题库","category":"测试"}' | jq .

echo ""
echo "========== 6. 查询题库列表 =========="
curl -s -X GET "$BASE_URL/questionBank/list?pageNum=1&pageSize=10" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo ""
echo "========== 7. 创建公告 =========="
curl -s -X POST "$BASE_URL/system/notice" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"notice_title":"测试公告","notice_type":"1","notice_content":"这是测试公告内容"}' | jq .

echo ""
echo "========== 8. 查询公告列表 =========="
curl -s -X GET "$BASE_URL/system/notice/list?pageNum=1&pageSize=10" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo ""
echo "========== 9. AI 出题 =========="
curl -s -X POST "$BASE_URL/ai/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"topic":"Python基础","question_type":"single","count":2,"difficulty":1}' | jq .

echo ""
echo "========== 测试完成 =========="
```

---

## 11. 注意事项

1. **数据库初始化**：首次运行前需要执行建表脚本
2. **AI API Key**：需要在 `.env` 中配置有效的 AI API Key
3. **Redis 连接**：确保 Redis 服务正常运行
4. **Token 有效期**：默认 30 分钟，过期后需要重新登录
5. **文件上传**：确保 `uploads` 目录存在且有写入权限

---

## 12. 常见问题

### Q: 登录返回 401？
A: 检查用户名密码是否正确，数据库是否已初始化。

### Q: AI 功能报错？
A: 检查 `.env` 中的 AI API Key 是否配置正确。

### Q: 文件上传失败？
A: 检查 `uploads` 目录权限，确保文件大小未超过限制。
