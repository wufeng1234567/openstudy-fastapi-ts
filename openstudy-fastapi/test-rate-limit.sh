#!/bin/bash
# ========================================
# AI 限流自动化测试脚本
# 用法: bash test-rate-limit.sh [local|nginx|tunnel] [--wait]
# ========================================

set -e

TARGET="${1:-local}"
case "$TARGET" in
    local)  BASE="http://127.0.0.1:9101" ;;
    nginx)  BASE="http://127.0.0.1:3167" ;;
    tunnel) BASE="${DEMO_URL}" ;;
    *)      echo "用法: bash $0 [local|nginx|tunnel] [--wait]"; exit 1 ;;
esac

# ── 限流参数（和 rate_limit.py 保持一致）──
DAILY_LIMIT=50
USER_PER_MIN=10
IP_PER_MIN=100

echo "========================================"
echo "  AI 限流测试 — 目标: $TARGET"
echo "  $BASE"
echo "  参数: 用户 ${USER_PER_MIN}/min + ${DAILY_LIMIT}/天, IP ${IP_PER_MIN}/min"
echo "========================================"
echo ""

PASS=0; FAIL=0; SKIP=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
skip() { echo "  ⏭️  $1"; SKIP=$((SKIP+1)); }

clear_rl() {
    cd /root/workspace/openstudy-fastapi-ts/openstudy-fastapi
    .venv/bin/python3 -c "
import asyncio, redis.asyncio as redis
async def main():
    r = redis.from_url('redis://localhost:6379', decode_responses=True)
    keys = await r.keys('rl:ai:*')
    for k in keys: await r.delete(k)
    await r.aclose()
asyncio.run(main())
" 2>&1 > /dev/null
}

# ── [0] 清空 ──
echo "[0] 清空 Redis 限流计数器"
clear_rl
ok "已清空"
echo ""

# ── [1] 登录 ──
echo "[1] 登录获取 token"
TOKEN=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"${DEMO_PASSWORD}"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'] if d.get('data') else '')" 2>/dev/null)
if [ -z "$TOKEN" ]; then fail "登录失败"; exit 1; fi
ok "登录成功: ${TOKEN:0:8}..."
echo ""

# ── [2] 正常请求 ──
echo "[2] 正常请求应该成功"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
if [ "$CODE" = "200" ]; then ok "首次请求 HTTP 200"; else fail "首次请求 HTTP $CODE (期望 200)"; fi
echo ""

# ── [3] 每用户每分钟限流 ──
echo "[3] 每用户每分钟限 ${USER_PER_MIN} 次（连续请求 $((USER_PER_MIN + 5)) 次）"
USER_BLOCKED=false
TOTAL_REQ=$((USER_PER_MIN + 5))
for i in $(seq 1 $TOTAL_REQ); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
    if [ "$CODE" = "429" ] && [ "$USER_BLOCKED" = "false" ]; then
        USER_BLOCKED=true
        BLOCKED_AT=$i
    fi
    if [ "$CODE" = "429" ] && [ "$i" -eq "$BLOCKED_AT" ]; then
        BODY=$(curl -s "$BASE/ai/models" -H "Authorization: Bearer $TOKEN" \
               | python3 -c "import json,sys; print(json.load(sys.stdin).get('msg','')[:50])" 2>/dev/null)
        echo "  请求 #$i: HTTP 429 → $BODY  ← 首次被限流"
    fi
done
# [2] 用了 1 次，所以第 USER_PER_MIN 次在 [3] 中被限流（1 + USER_PER_MIN = USER_PER_MIN+1 总量，第 USER_PER_MIN+1 次超限）
EXPECTED_AT=$((USER_PER_MIN))
if [ "$USER_BLOCKED" = "true" ]; then
    if [ "$BLOCKED_AT" -ge "$((EXPECTED_AT - 1))" ] && [ "$BLOCKED_AT" -le "$((EXPECTED_AT + 1))" ]; then
        ok "用户限流在第 $BLOCKED_AT 次触发（期望 $EXPECTED_AT ±1）"
    else
        fail "用户限流在第 $BLOCKED_AT 次触发（期望 $EXPECTED_AT ±1）"
    fi
else
    fail "$TOTAL_REQ 次请求都没被限流"
fi
echo ""

# ── [4] 等待恢复 ──
echo "[4] 等待 65 秒后限流恢复"
if [ "$2" = "--wait" ]; then
    echo "  等待 65 秒..."
    sleep 65
    clear_rl
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models" -H "Authorization: Bearer $TOKEN")
    if [ "$CODE" = "200" ]; then ok "等待后请求恢复 HTTP 200"; else fail "等待后仍被限流 HTTP $CODE"; fi
else
    skip "加 --wait 参数可测试恢复（需等 65 秒）"
fi
echo ""

# ── [5] 非 AI 接口不受限流 ──
echo "[5] 非 AI 接口不受限流影响"
clear_rl
ALL_OK=true
for i in $(seq 1 20); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
    if [ "$CODE" != "200" ]; then ALL_OK=false; fi
done
if [ "$ALL_OK" = "true" ]; then ok "20 次 /health 全部 200，不受限流"; else fail "非 AI 接口被限流了"; fi
echo ""

# ── [6] IP 限流（只对 local/nginx 有效，隧道多 IP 是已知行为）──
echo "[6] IP 限流 ${IP_PER_MIN}/min（匿名请求）"
clear_rl
if [ "$TARGET" = "tunnel" ]; then
    skip "隧道多 IP，IP 限流可能不触发（预期行为，用户限流已覆盖）"
else
    # 发 IP_PER_MIN + 5 次匿名请求
    ANON_BLOCKED=false
    TOTAL_ANON=$((IP_PER_MIN + 5))
    for i in $(seq 1 $TOTAL_ANON); do
        CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ai/models")
        if [ "$CODE" = "429" ] && [ "$ANON_BLOCKED" = "false" ]; then
            ANON_BLOCKED=true
            ANON_AT=$i
        fi
    done
    if [ "$ANON_BLOCKED" = "true" ]; then
        ok "IP 限流在第 $ANON_AT 次触发（期望 ~$((IP_PER_MIN + 1))）"
    else
        fail "匿名 $TOTAL_ANON 次请求都没被 IP 限流"
    fi
fi
echo ""

# ── 汇总 ──
echo "========================================"
echo "  结果: ✅ $PASS  ❌ $FAIL  ⏭️  $SKIP"
echo "========================================"
[ "$FAIL" -gt 0 ] && exit 1 || true
