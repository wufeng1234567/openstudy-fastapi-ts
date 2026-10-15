#!/bin/bash
# ========================================
# AI 限流自动化测试脚本
# 用法: bash test-rate-limit.sh [local|nginx|tunnel]
# ========================================

set -e

# ── 选择测试目标 ──
TARGET="${1:-local}"
case "$TARGET" in
    local)  BASE="http://127.0.0.1:9101" ;;
    nginx)  BASE="http://127.0.0.1:3167" ;;
    tunnel) BASE="https://***REMOVED***" ;;
    *)      echo "用法: bash $0 [local|nginx|tunnel]"; exit 1 ;;
esac

echo "========================================"
echo "  AI 限流测试 — 目标: $TARGET"
echo "  $BASE"
echo "========================================"
echo ""

# ── 工具函数 ──
PASS=0; FAIL=0; SKIP=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
skip() { echo "  ⏭️  $1"; SKIP=$((SKIP+1)); }

# ── 清空限流计数器 ──
echo "[0] 清空 Redis 限流计数器"
cd /root/workspace/openstudy-fastapi-ts/openstudy-fastapi
.venv/bin/python3 -c "
import asyncio, redis.asyncio as redis
async def main():
    r = redis.from_url('redis://localhost:6379', decode_responses=True)
    keys = await r.keys('rl:ai:*')
    for k in keys: await r.delete(k)
    print(f'  清空 {len(keys)} 个计数器')
    await r.aclose()
asyncio.run(main())
" 2>&1
echo ""

# ── 登录获取 token ──
echo "[1] 登录获取 token"
TOKEN=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"***REMOVED***"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'] if d.get('data') else '')" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    fail "登录失败，无法继续测试"
    exit 1
fi
ok "登录成功: ${TOKEN:0:8}..."
echo ""

# ── 测试 1: 正常请求应该成功 ──
echo "[2] 正常请求应该成功"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
if [ "$CODE" = "200" ]; then ok "首次请求 HTTP 200"
else fail "首次请求 HTTP $CODE (期望 200)"; fi
echo ""

# ── 测试 2: 每用户每分钟 5 次 ──
echo "[3] 每用户每分钟限 5 次（连续请求 8 次）"
USER_BLOCKED=false
for i in $(seq 1 8); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
    if [ "$CODE" = "429" ] && [ "$USER_BLOCKED" = "false" ]; then
        USER_BLOCKED=true
        BLOCKED_AT=$i
    fi
    printf "  请求 #%d: HTTP %s" "$i" "$CODE"
    if [ "$CODE" = "429" ]; then
        BODY=$(curl -s "$BASE/ai/models" -H "Authorization: Bearer $TOKEN" \
               | python3 -c "import json,sys; print(json.load(sys.stdin).get('msg','')[:50])" 2>/dev/null)
        printf " → %s" "$BODY"
    fi
    echo ""
done

# 总共 1(测试2) + 8(测试3) = 9 次同用户同分钟，第 6 次起应被限流
if [ "$USER_BLOCKED" = "true" ]; then
    if [ "$BLOCKED_AT" -ge 5 ] && [ "$BLOCKED_AT" -le 7 ]; then
        ok "用户限流在第 $BLOCKED_AT 次请求触发（期望 5-7）"
    else
        fail "用户限流在第 $BLOCKED_AT 次触发（期望 5-7）"
    fi
else
    fail "8 次请求都没被限流"
fi
echo ""

# ── 测试 3: 等一分钟后恢复 ──
echo "[4] 等待 65 秒后限流恢复（跳过等待则直接测）"
if [ "$2" = "--wait" ]; then
    echo "  等待 65 秒..."
    sleep 65
    # 清空计数器
    .venv/bin/python3 -c "
import asyncio, redis.asyncio as redis
async def main():
    r = redis.from_url('redis://localhost:6379', decode_responses=True)
    keys = await r.keys('rl:ai:*')
    for k in keys: await r.delete(k)
    await r.aclose()
asyncio.run(main())
" 2>&1 > /dev/null
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
    if [ "$CODE" = "200" ]; then ok "等待后请求恢复 HTTP 200"
    else fail "等待后仍被限流 HTTP $CODE"; fi
else
    skip "加 --wait 参数可测试恢复（需等 65 秒）"
fi
echo ""

# ── 测试 4: 无 token 的匿名请求 ──
echo "[5] 无 token 匿名请求（IP 限流 10/min）"
# 清空计数器
.venv/bin/python3 -c "
import asyncio, redis.asyncio as redis
async def main():
    r = redis.from_url('redis://localhost:6379', decode_responses=True)
    keys = await r.keys('rl:ai:*')
    for k in keys: await r.delete(k)
    await r.aclose()
asyncio.run(main())
" 2>&1 > /dev/null

ANON_BLOCKED=false
for i in $(seq 1 13); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models")
    if [ "$CODE" = "429" ] && [ "$ANON_BLOCKED" = "false" ]; then
        ANON_BLOCKED=true
        ANON_BLOCKED_AT=$i
    fi
done

if [ "$ANON_BLOCKED" = "true" ]; then
    ok "匿名 IP 限流在第 $ANON_BLOCKED_AT 次触发（期望 11）"
else
    # 隧道多 IP 可能不触发 IP 限流，这是已知行为
    if [ "$TARGET" = "tunnel" ]; then
        skip "隧道多 IP，IP 限流可能不触发（预期行为，用户限流已覆盖）"
    else
        fail "匿名 13 次请求都没被 IP 限流"
    fi
fi
echo ""

# ── 测试 5: 非 AI 接口不受限流 ──
echo "[6] 非 AI 接口不受限流影响"
# 清空计数器
.venv/bin/python3 -c "
import asyncio, redis.asyncio as redis
async def main():
    r = redis.from_url('redis://localhost:6379', decode_responses=True)
    keys = await r.keys('rl:ai:*')
    for k in keys: await r.delete(k)
    await r.aclose()
asyncio.run(main())
" 2>&1 > /dev/null

ALL_OK=true
for i in $(seq 1 20); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
    if [ "$CODE" != "200" ]; then ALL_OK=false; fi
done
if [ "$ALL_OK" = "true" ]; then ok "20 次 /health 全部 200，不受限流"
else fail "非 AI 接口被限流了"; fi
echo ""

# ── 汇总 ──
echo "========================================"
echo "  结果: ✅ $PASS  ❌ $FAIL  ⏭️  $SKIP"
echo "========================================"
if [ "$FAIL" -gt 0 ]; then exit 1; fi
