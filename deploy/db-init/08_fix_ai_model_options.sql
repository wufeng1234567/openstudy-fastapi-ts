-- ============================================================
-- 修正 DeepSeek 官方模型的「推理强度 / 上下文长度」默认值（幂等，可重复执行）
-- ------------------------------------------------------------
-- 背景（2026-10）：
--   1. 官方 `GET /models` 元数据确认：deepseek-flash 与 deepseek-v4-pro 的
--      effort 档位都只有 low / high / max（默认 high），没有 medium。
--   2. 官方没有「上下文档位」这个入参 —— 两个模型窗口都是 1M。
--      `sys_ai_config.context_length` 存的是**应用层喂多少历史进去的预算**，
--      合法值为 `200k`（基础，默认）/ `1m`（完整）。旧值 `32k`/`128k` 已废弃。
--
-- 用法：psql -U root -d openstudy_v2_pgsql -f 08_fix_ai_model_options.sql
-- 只动 sys_ai_config 里 provider='deepseek' 的**系统行**（user_id IS NULL），
-- 不碰用户自己添加的模型。
-- ============================================================

-- 1. 官方模型的推理强度：清掉无效的 medium（官方不接受），统一收敛到 high
UPDATE public.sys_ai_config
SET reasoning_effort = 'high'
WHERE provider = 'deepseek'
  AND user_id IS NULL
  AND (reasoning_effort IS NULL OR lower(reasoning_effort) NOT IN ('low', 'high', 'max'));

-- 2. 官方模型的上下文档位：空值 / 旧值（32k、128k 等）→ 默认 200k
UPDATE public.sys_ai_config
SET context_length = '200k'
WHERE provider = 'deepseek'
  AND user_id IS NULL
  AND (context_length IS NULL OR lower(context_length) NOT IN ('200k', '1m'));

-- 3. 校验
SELECT config_id, provider, model, thinking_mode, reasoning_effort, context_length
FROM public.sys_ai_config
WHERE provider = 'deepseek'
ORDER BY config_id;
