-- Remove the retired ds-free / ds-free-nb web reverse-proxy configuration.
-- Safe to run repeatedly on an existing PostgreSQL database.

DELETE FROM public.sys_ai_config
WHERE provider IN ('deepseek-free', 'ds-free-nb');

ALTER TABLE public.sys_ai_config DROP COLUMN IF EXISTS web_phone;
ALTER TABLE public.sys_ai_config DROP COLUMN IF EXISTS web_password;
ALTER TABLE public.sys_ai_config DROP COLUMN IF EXISTS web_area_code;
