"""
DeepSeek 网页端反代客户端（provider = deepseek-free）

用途：不打开浏览器，用手机号 + 密码登录 chat.deepseek.com，把它私有的
聊天接口包装成 OpenAI 兼容调用，供 OpenStudy 的 AI 层使用。

================================ 重要说明 ================================
官方对脚本化调用有三道校验，本文件已按公开资料对齐协议形状，但仍可能被拒：

  1) TLS / HTTP2 指纹：用 curl_cffi 的 impersonate 模拟 Chrome，能过一部分。
  2) PoW：算法标识 `DeepSeekHashV1`，官方由前端下载的 WASM 模块计算：
         prefix   = f"{salt}_{expireAt}_"
         solve(challenge, prefix, difficulty) -> answer
         X-Ds-Pow-Response = base64(json({algorithm, challenge, salt, answer,
                                          signature, target_path}))
     纯 Python 无法保证与官方一致 —— 本文件把求解器做成可插拔：
         · NodeWasmPowSolver（推荐）：调用官方 wasm，算法一致
         · NaiveSha3PowSolver（兜底/诊断）：纯 Python 近似实现
     使用 Node 求解需要把官方 `sha3_wasm_bg.<hash>.wasm` 放到
     app/services/ai/pow_wasm/ 目录（获取方式见该目录 README）。
  3) 行为遥测：官方前端每次会话会上报十余种行为事件，缺失会被判定为机器人。
     本实现未伪造这些事件。

另外账号层面也有风控，异常调用可能导致账号被临时限制。
如果你的目标是稳定可用，请改用官方 API（app/services/ai/deepseek_client.py）。
==========================================================================
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, AsyncIterator, Optional, Dict, Any

from loguru import logger
from app.services.ai.base_client import BaseAiClient, ChatMessage, ChatResponse, TextBlock

# DeepSeek 网页端 API 基地址
BASE_URL = "https://chat.deepseek.com"

# 请求头模板（模拟 Chrome）
DEFAULT_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": BASE_URL,
    "referer": BASE_URL + "/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "x-client-version": "2.0.2",
    "x-client-platform": "web",
    "x-app-version": "2.0.2",
}

# wasm 与 node 求解脚本所在目录
POW_WASM_DIR = Path(__file__).parent / "pow_wasm"


class PowSolverError(Exception):
    """PoW 无法求解（缺 wasm / 缺 node / 算法不匹配等）"""


def _env_or_setting(name: str) -> Optional[str]:
    """先读环境变量，再读 settings（.env）。

    脚本直接跑时靠 os.environ；服务运行时 .env 由 pydantic-settings 装进 settings，
    但不会写回 os.environ，所以两处都要看。
    """
    v = os.environ.get(name)
    if v:
        return v
    try:
        from app.config import settings

        return getattr(settings, name, None) or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PoW 求解器
# ---------------------------------------------------------------------------


class BasePowSolver:
    """PoW 求解器接口"""

    name = "base"

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return self.name

    def solve(self, challenge: Dict[str, Any], target_path: str) -> Dict[str, Any]:
        """返回可直接 base64 的 answer 字典"""
        raise NotImplementedError


class NodeWasmPowSolver(BasePowSolver):
    """用 Node 跑官方 WASM 求解，算法与官方一致（推荐）

    依赖：
      · pow_wasm/sha3_wasm_bg.<hash>.wasm   官方 wasm 模块
      · pow_wasm/pow_solver.js              Node 调用脚本（本仓库自带）
      · 环境里有 node
    """

    name = "node-wasm"

    def __init__(self, node_bin: Optional[str] = None, timeout: float = 30.0):
        self.node_bin = node_bin or os.environ.get("POW_NODE_BIN") or "node"
        self.timeout = timeout

    def _wasm_file(self) -> Optional[Path]:
        if not POW_WASM_DIR.is_dir():
            return None
        files = sorted(POW_WASM_DIR.glob("*.wasm"))
        return files[0] if files else None

    @property
    def available(self) -> bool:
        return (
            shutil.which(self.node_bin) is not None
            and self._wasm_file() is not None
            and (POW_WASM_DIR / "pow_solver.js").is_file()
        )

    def describe(self) -> str:
        wasm = self._wasm_file()
        return f"node-wasm(node={self.node_bin}, wasm={wasm.name if wasm else '缺失'})"

    def solve(self, challenge: Dict[str, Any], target_path: str) -> Dict[str, Any]:
        wasm = self._wasm_file()
        script = POW_WASM_DIR / "pow_solver.js"
        if not wasm or not script.is_file():
            raise PowSolverError("pow_wasm 目录缺少 wasm 或 pow_solver.js")
        if shutil.which(self.node_bin) is None:
            raise PowSolverError(f"找不到 node 可执行文件: {self.node_bin}")

        payload = json.dumps(
            {
                "challenge": challenge.get("challenge", ""),
                "salt": challenge.get("salt", ""),
                "expireAt": challenge.get("expire_at", 0),
                "difficulty": challenge.get("difficulty", 3),
                "wasmPath": str(wasm),
            }
        )
        try:
            proc = subprocess.run(
                [self.node_bin, str(script)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as e:
            raise PowSolverError(f"node 求解超时: {e}")

        if proc.returncode != 0:
            raise PowSolverError(f"node 求解失败: {(proc.stderr or '').strip()[:300]}")

        try:
            out = json.loads((proc.stdout or "").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            raise PowSolverError(f"node 输出无法解析: {(proc.stdout or '')[:200]}")

        answer = out.get("answer")
        if answer in (None, 0, "0"):
            raise PowSolverError("wasm 未求出有效 answer（difficulty 或输入格式不符）")

        return {
            "algorithm": challenge.get("algorithm", "DeepSeekHashV1"),
            "challenge": challenge.get("challenge", ""),
            "salt": challenge.get("salt", ""),
            "answer": answer,
            "signature": challenge.get("signature", ""),
            "target_path": target_path,
        }


class NaiveSha3PowSolver(BasePowSolver):
    """纯 Python 兜底求解器（仅用于诊断，不保证与官方算法一致）

    思路：prefix = f"{salt}_{expire_at}_"，暴力枚举整数 answer，
    找 sha3_256(prefix + answer) 与 challenge 匹配的解。
    官方真实算法在 WASM 里，这里只是形状相同的近似，能否通过看运气。
    """

    name = "naive-sha3"

    def __init__(self, max_iter: int = 2_000_000):
        self.max_iter = max_iter

    # 候选的哈希输入布局（prefix = f"{salt}_{expireAt}_"，答案在 [0, difficulty) 内枚举）
    LAYOUTS = (
        "{salt}_{exp}_{i}",
        "{salt}_{exp_sec}_{i}",
        "{exp}_{salt}_{i}",
        "{salt}_{i}",
        "{i}_{salt}_{exp}",
    )

    def solve(self, challenge: Dict[str, Any], target_path: str) -> Dict[str, Any]:
        raw = (challenge.get("challenge") or "").strip().lower()
        salt = challenge.get("salt") or ""
        expire_at = challenge.get("expire_at") or 0
        try:
            expire_at = int(expire_at)
        except (TypeError, ValueError):
            expire_at = 0
        difficulty = challenge.get("difficulty") or 0
        try:
            limit = int(difficulty) or self.max_iter
        except (TypeError, ValueError):
            limit = self.max_iter
        limit = min(limit, self.max_iter)

        if not raw or not salt:
            raise PowSolverError(
                f"challenge 字段缺失（challenge={'有' if raw else '空'} salt={'有' if salt else '空'}）"
            )

        answer: Optional[int] = None
        used_layout = ""
        for layout in self.LAYOUTS:
            for i in range(limit):
                text = layout.format(
                    salt=salt, exp=expire_at, exp_sec=expire_at // 1000, i=i
                )
                if hashlib.sha3_256(text.encode()).hexdigest() == raw:
                    answer, used_layout = i, layout
                    break
            if answer is not None:
                break

        if answer is None:
            raise PowSolverError(
                f"naive-sha3 在 [0,{limit}) 内用 {len(self.LAYOUTS)} 种布局都没找到解"
                f"（difficulty={difficulty}）—— 说明哈希不是纯 SHA3-256，需要官方 wasm"
            )

        logger.info(f"[DeepSeekWeb] PoW 求解成功: layout={used_layout} answer={answer}")
        return {
            "algorithm": challenge.get("algorithm", "DeepSeekHashV1"),
            "challenge": raw,
            "salt": salt,
            "answer": answer,
            "signature": challenge.get("signature", ""),
            "target_path": target_path,
        }


def build_default_solver() -> BasePowSolver:
    """优先用 node-wasm，缺失时回退到 naive（并打印提示）"""
    node_solver = NodeWasmPowSolver()
    if node_solver.available:
        return node_solver
    return NaiveSha3PowSolver()


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class DeepSeekWebClient(BaseAiClient):
    """DeepSeek 网页端反代客户端"""

    def __init__(
        self,
        phone: str = None,
        password: str = None,
        area_code: str = "+86",
        solver: Optional[BasePowSolver] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        token: Optional[str] = None,
        cookie: Optional[str] = None,
    ):
        self._phone = phone
        self._password = password
        self._area_code = area_code or "+86"
        # 会话导入模式：token / cookie 由用户在浏览器里正常登录后取得，
        # 本客户端直接复用，不再走脚本登录（不涉及任何风控绕过）。
        self._token: Optional[str] = token or _env_or_setting("DEEPSEEK_WEB_TOKEN")
        self._cookie: Optional[str] = cookie or _env_or_setting("DEEPSEEK_WEB_COOKIE")
        self._session_id: Optional[str] = None
        self._headers: Dict[str, str] = DEFAULT_HEADERS.copy()
        if extra_headers:
            self._headers.update(extra_headers)

        # 浏览器会话材料导入：以下值都能从 chat.deepseek.com 的
        # localStorage / Application 面板里原样抄出来，属于用户自己的会话数据。
        #   · hif_dliq / hif_leim  → 官方前端随请求携带的动态头
        #   · smidV2               → 设备/会话标识
        # 这些是「复用自己浏览器的会话」，不是伪造。
        hif_dliq = _env_or_setting("DEEPSEEK_WEB_HIF_DLIQ")
        hif_leim = _env_or_setting("DEEPSEEK_WEB_HIF_LEIM")
        device_id = _env_or_setting("DEEPSEEK_WEB_DEVICE_ID")
        if hif_dliq:
            self._headers["x-hif-dliq"] = hif_dliq
        if hif_leim:
            self._headers["x-hif-leim"] = hif_leim
        if device_id:
            self._headers["x-ds-device-id"] = device_id
        self._last_login_time: Optional[float] = None
        self._token_valid_hours = 23  # token 约 24 小时有效，提前 1 小时刷新
        self._solver = solver or build_default_solver()
        # 诊断用：最近一次请求的原始响应，便于在 test 接口里回显
        self.last_diagnostics: Dict[str, Any] = {}
        if self._token:
            # 已有 token：立刻标记为「刚拿到」，让 _is_token_expired 返回 False
            self._headers["authorization"] = f"Bearer {self._token}"
            self._last_login_time = time.time()

    # ---- 元信息 ----

    @property
    def provider(self) -> str:
        return "deepseek-free"

    @property
    def supported_models(self) -> List[str]:
        # 只认领 deepseek-free；deepseek-chat 属于官方 API 客户端，不要在这里声明，
        # 否则 get_client_for_model 的前缀匹配会产生路由歧义。
        return ["deepseek-free"]

    @classmethod
    def from_config(cls, cfg, **kwargs) -> "DeepSeekWebClient":
        """从 sys_ai_config 行构造（后台配置的 ds-free 凭证走这里）"""
        return cls(
            phone=getattr(cfg, "web_phone", None),
            password=getattr(cfg, "web_password", None),
            area_code=getattr(cfg, "web_area_code", None) or "+86",
            **kwargs,
        )

    # ---- 基础 ----

    def _is_token_expired(self) -> bool:
        if not self._last_login_time or not self._token:
            return True
        return (time.time() - self._last_login_time) / 3600 >= self._token_valid_hours

    async def _ensure_token(self):
        if self._is_token_expired():
            ok = await self.login()
            if not ok:
                raise RuntimeError(
                    "DeepSeek 网页端登录失败，请检查手机号/密码，或查看日志中的诊断信息"
                )

    def _new_session(self):
        from curl_cffi.requests import AsyncSession

        session = AsyncSession(impersonate="chrome", timeout=60)
        # 会话导入模式：把浏览器里拿到的 cookie 带上（风控可能校验它）
        if self._cookie:
            session.headers["cookie"] = self._cookie
        return session

    # ---- 登录 ----

    async def login(self) -> bool:
        """手机号 + 密码登录，拿到 token 并建立会话

        登录会下发 Cookie（curl_cffi 的 session 自动带上），后续请求复用同一 session。
        """
        if not self._phone or not self._password:
            # 会话导入模式：有 token 就不需要账号密码
            if self._token and not self._is_token_expired():
                async with self._new_session() as session:
                    await self._create_session(session)
                logger.info(
                    f"[DeepSeekWeb] 使用导入的 token 会话，session_id={self._session_id}，"
                    f"PoW 求解器: {self._solver.describe()}"
                )
                return True
            logger.error("[DeepSeekWeb] 未配置手机号或密码，也没有可用 token，无法登录")
            return False

        # 已经有导入的合法 token → 直接复用，不做脚本登录
        if self._token and not self._is_token_expired():
            async with self._new_session() as session:
                await self._create_session(session)
            logger.info(
                f"[DeepSeekWeb] 使用导入的 token 会话，session_id={self._session_id}，"
                f"PoW 求解器: {self._solver.describe()}"
            )
            return True

        async with self._new_session() as session:
            try:
                resp = await session.post(
                    f"{BASE_URL}/api/v0/users/login",
                    json={
                        "mobile": str(self._phone).lstrip("+"),
                        "area_code": self._area_code,
                        "password": self._password,
                        "device_id": self._headers.get("x-ds-device-id", ""),
                        "os": "web",
                    },
                    headers=self._headers,
                )
            except Exception as e:
                logger.error(f"[DeepSeekWeb] 登录请求异常: {e}")
                self.last_diagnostics = {"stage": "login", "error": str(e)}
                return False

            self.last_diagnostics = {
                "stage": "login",
                "http_status": resp.status_code,
                "body": (resp.text or "")[:500],
            }

            if resp.status_code != 200:
                logger.error(
                    f"[DeepSeekWeb] 登录被拒 HTTP {resp.status_code}: {(resp.text or '')[:300]}"
                )
                return False

            try:
                data = resp.json()
            except Exception:
                logger.error(f"[DeepSeekWeb] 登录响应不是 JSON: {(resp.text or '')[:300]}")
                return False

            if data.get("code") != 0:
                logger.error(f"[DeepSeekWeb] 登录失败: {data}")
                return False

            biz = (data.get("data") or {})
            token = biz.get("token") or (biz.get("biz_data") or {}).get("token")
            if not token:
                # 业务错误在 data.biz_code 里（外层 code 恒为 0），单独给出可读提示
                biz_code = biz.get("biz_code")
                biz_msg = (biz.get("biz_msg") or "").strip()
                if biz_msg == "PASSWORD_OR_USER_NAME_IS_WRONG":
                    logger.error("[DeepSeekWeb] 登录失败：手机号或密码不正确")
                elif biz_msg == "RISK_DEVICE_DETECTED":
                    logger.error(
                        "[DeepSeekWeb] 登录被风控拦下：RISK_DEVICE_DETECTED ——"
                        "账号/密码已通过校验，但服务端把这次登录判定为「高风险设备」。\n"
                        "           这说明纯脚本登录已经过不了账号级风控，需要先在真实浏览器里\n"
                        "           完成一次设备验证（短信/滑块），本链路才能继续。\n"
                        "           继续反复重试会让账号风控等级升高，建议先停手。"
                    )
                else:
                    logger.error(
                        f"[DeepSeekWeb] 登录失败：biz_code={biz_code} biz_msg={biz_msg or '(空)'}"
                    )
                return False

            self._token = token
            self._headers["authorization"] = f"Bearer {token}"
            self._last_login_time = time.time()
            self.last_diagnostics["stage"] = "login-ok"

            await self._create_session(session)
            logger.info(
                f"[DeepSeekWeb] 登录成功，会话 ID: {self._session_id}，"
                f"PoW 求解器: {self._solver.describe()}"
            )
            return True

    async def _create_session(self, session) -> None:
        try:
            resp = await session.post(
                f"{BASE_URL}/api/v0/chat_session/create",
                json={},
                headers=self._headers,
            )
            body = (resp.text or "")[:400]
            self.last_diagnostics = {
                "stage": "create_session",
                "http_status": resp.status_code,
                "body": body,
            }
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    biz = data.get("data") or {}
                    biz_data = biz.get("biz_data") or {}
                    # 真实结构：data.biz_data.chat_session.id
                    self._session_id = (
                        (biz_data.get("chat_session") or {}).get("id")
                        or biz_data.get("id")
                        or biz.get("id")
                        or biz.get("chat_session_id")
                        or (biz.get("chat_session") or {}).get("id")
                    )
                    if self._session_id:
                        return
                    logger.warning(f"[DeepSeekWeb] 创建会话成功但没解析出 id: {body}")
                else:
                    logger.warning(f"[DeepSeekWeb] 创建会话失败: {body}")
            else:
                logger.warning(f"[DeepSeekWeb] 创建会话 HTTP {resp.status_code}: {body}")
        except Exception as e:
            logger.warning(f"[DeepSeekWeb] 创建会话异常: {e}")

    # ---- PoW ----

    async def _get_pow_challenge(self, session, target_path: str) -> Dict[str, Any]:
        resp = await session.post(
            f"{BASE_URL}/api/v0/chat/create_pow_challenge",
            json={"target_path": target_path},
            headers=self._headers,
        )
        if resp.status_code != 200:
            raise PowSolverError(
                f"获取 PoW challenge 失败 HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            )
        data = resp.json()
        if data.get("code") != 0:
            raise PowSolverError(f"获取 PoW challenge 失败: {data}")
        # 真实结构：data.biz_data.challenge
        biz_data = (data.get("data") or {}).get("biz_data") or {}
        return biz_data.get("challenge") or (data.get("data") or {}) or {}

    def _build_pow_header(self, challenge: Dict[str, Any], target_path: str) -> str:
        """求解并 base64 成 X-Ds-Pow-Response"""
        answer = self._solver.solve(challenge, target_path)
        raw = json.dumps(answer, separators=(",", ":"), ensure_ascii=False)
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    # ---- 聊天 ----

    async def _completion(self, content: str, stream: bool, target_path: str = "/api/v0/chat/completion"):
        """发一次补全请求，返回 (resp, session)。调用方负责解析并 close session。"""
        session = self._new_session()
        try:
            challenge = await self._get_pow_challenge(session, target_path)
            pow_header = self._build_pow_header(challenge, target_path)
        except PowSolverError as e:
            logger.error(f"[DeepSeekWeb] PoW 处理失败: {e}")
            self.last_diagnostics = {"stage": "pow", "error": str(e)}
            await session.close()
            raise

        headers = dict(self._headers)
        headers["x-ds-pow-response"] = pow_header

        resp = await session.post(
            f"{BASE_URL}{target_path}",
            json={
                "chat_session_id": self._session_id,
                # 官方当前要求字段名为 prompt（旧版叫 content），两个都带上更稳
                "prompt": content,
                "content": content,
                "chat_mode": "normal",
                "stream": stream,
                # 以下字段是从 422 报错里逐个补齐的官方前端字段
                "ref_file_ids": [],
                "parent_message_id": None,
                "model_type": None,
                "thinking_enabled": False,
                "search_enabled": False,
                "preempt": False,
            },
            headers=headers,
        )

        self.last_diagnostics = {
            "stage": "completion",
            "http_status": resp.status_code,
            "body": (resp.text or "")[:800],
        }

        if resp.status_code != 200:
            await session.close()
            raise RuntimeError(
                f"聊天请求被拒 HTTP {resp.status_code}: {(resp.text or '')[:300]}"
            )
        return resp, session

    @staticmethod
    def _iter_fragments(text: str):
        """解析 SSE 行，产出 (kind, content)，kind ∈ {reasoning, answer}"""
        for line in (text or "").split("\n"):
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            fragments = data.get("v")
            if isinstance(fragments, str):
                # 形如 {"p":"response/fragments/-1/content","o":"APPEND","v":"你好"}
                # 只认 content 路径，避免把 response/status 之类（如 "FINISHED"）当正文
                path = data.get("p") or ""
                if path and "content" not in path:
                    continue
                yield ("answer", fragments)
                continue
            if not isinstance(fragments, list):
                continue
            for frag in fragments:
                if not isinstance(frag, dict):
                    continue
                ftype = frag.get("type", "")
                fcontent = frag.get("content", "")
                if ftype == "THINK":
                    yield ("reasoning", fcontent)
                elif ftype == "RESPONSE":
                    yield ("answer", fcontent)

    async def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> ChatResponse:
        await self._ensure_token()
        content = self._assemble_content(messages)
        resp, session = await self._completion(content, stream=False)
        try:
            answer, thinking = "", ""
            for kind, text in self._iter_fragments(resp.text):
                if kind == "reasoning":
                    thinking += text
                else:
                    answer += text
        finally:
            await session.close()

        return ChatResponse(
            content=answer,
            usage=None,
            raw={"thinking": thinking, "response": answer},
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        include_reasoning: bool = False,
        **kwargs,
    ) -> AsyncIterator:
        """流式聊天，逐段产出 (kind, text)，kind 为 "reasoning" 或 "answer"

        网页端返回的是一次性响应体，这里解析后逐片吐出；对上层仍是流式协议。
        """
        await self._ensure_token()
        content = self._assemble_content(messages)
        resp, session = await self._completion(content, stream=True)
        try:
            for kind, text in self._iter_fragments(resp.text):
                if kind == "reasoning":
                    if include_reasoning:
                        yield ("reasoning", text)
                else:
                    yield ("answer", text)
        finally:
            await session.close()

    def _assemble_content(self, messages: List[ChatMessage]) -> str:
        """拼接消息：网页端没有 system role，需要把系统提示与历史对话并入 content"""
        parts: List[str] = []
        for msg in messages:
            if isinstance(msg.content, str):
                text = msg.content
            else:
                text = "\n".join(b.text for b in msg.content if isinstance(b, TextBlock))
            if not text:
                continue
            parts.append(f"Assistant: {text}" if msg.role == "assistant" else text)
        return "\n\n".join(parts)

    async def embeddings(self, texts: List[str], model: str = None) -> List[List[float]]:
        raise NotImplementedError("DeepSeek 网页端不支持 embeddings 接口")

    # ---- 连通性自检（供后台「测试连接」按钮调用）----

    async def self_test(self) -> Dict[str, Any]:
        """登录 → 建会话 → 发一句最短的话，返回各阶段结果

        无论成功失败都返回结构化信息，便于定位卡在哪一道关。
        """
        stages: List[Dict[str, Any]] = []

        ok = await self.login()
        stages.append(
            {
                "stage": "login",
                "ok": ok,
                "httpStatus": self.last_diagnostics.get("http_status"),
                "detail": "登录成功" if ok else (self.last_diagnostics.get("body") or "")[:300],
            }
        )
        if not ok:
            return {
                "ok": False,
                "solver": self._solver.describe(),
                "stages": stages,
                "detail": "登录失败（见 stages 里各阶段的原始响应）",
            }

        stages.append(
            {
                "stage": "session",
                "ok": bool(self._session_id),
                "detail": self._session_id or "未创建",
                # 附带 create_session 那一步的原始响应，便于定位
                "raw": self.last_diagnostics,
            }
        )

        try:
            resp, session = await self._completion("你好", stream=False)
            await session.close()
            reply = "".join(t for k, t in self._iter_fragments(resp.text) if k == "answer")
            stages.append(
                {"stage": "completion", "ok": bool(reply), "detail": reply[:200] or "响应为空"}
            )
            return {
                "ok": bool(reply),
                "solver": self._solver.describe(),
                "stages": stages,
                "detail": "ds-free 可用" if reply else "请求通过但未解析到内容",
            }
        except PowSolverError as e:
            stages.append({"stage": "pow", "ok": False, "detail": str(e)})
            return {
                "ok": False,
                "solver": self._solver.describe(),
                "stages": stages,
                "detail": f"PoW 阶段失败: {e}",
            }
        except Exception as e:
            stages.append({"stage": "completion", "ok": False, "detail": str(e)[:300]})
            return {
                "ok": False,
                "solver": self._solver.describe(),
                "stages": stages,
                "detail": f"聊天阶段失败: {e}",
            }


def register():
    """兼容占位：ds-free 已不再由后端注册客户端。

    当前架构：ds-free = 浏览器扩展方案（apps/deepseek-proxy 代发
    chat.deepseek.com 请求），后端不参与请求转发，所以这里**什么都不做**。

    本函数刻意保留为 no-op 空壳 —— 外部（含历史代码 / 部署脚本）若还在
    `from ...deepseek_web_client import register; register()`，也不会重新把
    反代客户端塞进 DynamicAI 路由表。

    ⚠️ 不要在这里恢复 `dynamic_ai.register_client(DeepSeekWebClient(...))`：
    `DeepSeekWebClient.supported_models` 认领的模型名就是 `deepseek-free`，
    一旦注册，`get_client_for_model("deepseek-free")` 会命中它，
    纯 HTTP 反代链路就会被重新启用（官方风控下 429/403，且账号有封禁风险）。
    """
    logger.debug("[DeepSeekWeb] register() 已废弃：ds-free 改由浏览器扩展实现，后端不注册反代客户端")
