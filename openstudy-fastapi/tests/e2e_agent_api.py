# -*- coding: utf-8 -*-
"""
Agent（智能体）域接口回归测试 —— E2E，**进程内真实 HTTP**

为什么要有它：
    智能体的「模型 → 工具」多轮循环是本项目最容易回归的地方（前端丢参数、
    Ref 忘 .value、ORM 删父对象置空外键、工具结果回灌丢数据…都踩过）。
    以前这些验证都是一次性脚本、跑完就删，改一处就可能悄悄坏一处。
    本脚本把两条链路的关键行为固化成**一条命令可复跑**的回归测试。

覆盖两条链路的同一套行为：
    · api 付费链路：`POST /ai/agent/stream`（后端多轮工具循环）
    · ds-free 链路：`POST /ai/agent/execute`（前端循环的单步执行）
并在 HTTP 层验证：工具清单/鉴权、批量删除、分页、搜索扩范围、改名重名校验、
破坏性操作二次确认（同意 / 取消）、会话历史落库、时间线快照、
**笔记域（note_manage：分类兜底、可见性映射、逻辑删除、按 user_id 隔离）**。

为什么是「进程内」而不是真 HTTP 到 9101：
    本脚本要覆盖多轮工具循环，真模型调用既慢又**不确定**（不适合当回归测试）。
    于是用 `app.dependency_overrides` 换掉登录依赖、把
    `db_config.build_agent_llm` 换成**脚本化假 LLM** —— 其余（路由、参数解析、
    鉴权、落库、事件流、工具执行）**全部走真实代码**。
    因此：**不需要起后端进程，也不消耗 token**。

用法（只要 DB 可用）：
    cd openstudy-fastapi
    .venv/Scripts/python.exe tests/e2e_agent_api.py

退出码（**三态**，别把三者混成一个）：
    0 = 全绿；1 = 跑完了但有失败用例 / 中途崩了；2 = **根本没跑**（已有另一个实例在跑）。
    只有 0 才能当成「通过」。

⚠️ stdout 里还会出现 **`[SKIP] <用例id>`**：那表示这条用例**跑到了、但没测到东西**
   （Z2 的窗口为空 / 首次运行）。它在产物里的 `status` 仍是「通过」（空窗口不是失败），
   但**按通过条数统计的脚本请把它排除** —— 「没测到」不等于「验过了」。

⚠️ **同一时刻只允许一个进程跑本套件** —— 夹具名不带时间戳（`__e2e_agent__A/B/C/E`、
   `__e2e_agent_note__*`）且都写同一个真实用户，两个进程会**互删对方刚建的夹具**。
   所以脚本在任何 DB 操作**之前**抢一个单实例锁（`tests/.e2e_agent_api.lock`，见 `acquire_lock`）；
   抢不到就直接退 2，**不碰 DB、不写产物、不动 sidecar**。

产出：同目录 e2e_agent_api_result.json（用例表，可用于生成 Excel 报告）
    ⚠️ 该 json 带 `completed` 字段：`false` = 这一趟**没跑完**（崩了），里面的用例表是**残的**，
       别当成结果读。失败时另存一份 `_evidence/e2e_agent_api_result_<时间戳>_red.json`。
注意：会在库中创建 `__e2e_agent__` 前缀的临时题库与 `asst_e2e_` 前缀的会话，结束时清理；
笔记用例还会建一条 `__e2e_agent_note__` 前缀的分类与若干同前缀笔记，结束时**物理删**干净。

⚠️ 本脚本会**真的执行写操作**，而 Agent 的写操作会自动落长期记忆（`memory_hook`），
   所以结束时还要按标记物理清掉这些 `ai_agent_memory` 行 —— 否则每跑一次就往真实用户
   的记忆里塞十几条 `__e2e_agent__` 垃圾（见 `cleanup()`）。
"""
import asyncio
import datetime
import json
import os
import re
import socket
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_agent_api_result.json")

#: **红产物另存**目录。`OUT` 是单槽、每次跑都覆盖 —— 一次性的红被下一次绿盖掉之后，
#: 事后完全无法复核「它真的红过」（2026-09-19 就发生过：Z2 的首次红只留下一份被覆盖的 json）。
#: 所以失败时把同一份内容再存一份带时间戳的副本；**绿的时候什么都不写**（不留垃圾）。
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_evidence")

PREFIX = "__e2e_agent__"
BANK_A = PREFIX + "A"
BANK_B = PREFIX + "B"
BANK_C = PREFIX + "C"
BANK_E = PREFIX + "E"

#: 笔记用例的标记。笔记**用标题前缀**标记（没有题库那样的「名字唯一」约束，
#: 所以清理只能按标题前缀物理删，见 `cleanup()`）
NOTE_PREFIX = "__e2e_agent_note__"

#: N 组「他人 IDOR」夹具的标记前缀 —— 它属于**另一个用户**（uid_other），
#: 所以既不在 `bank_manage.list` 里（那只看当前用户），也不能按 uid 找；清理只能按标记前缀物理删。
#:
#: ⚠️ 提到模块级是**必需**的（不能只在 `main()` 里当局部变量）：`cleanup()` 是闭包，
#:    而它在 N 组**之前**就会被调用（预清理 + B 组开始时），那时局部变量还没赋值 → NameError。
OTHER_IDOR_MARK = PREFIX + "他人IDOR"

#: 记忆基线 sidecar：记下**上一次**跑开始时 `ai_agent_memory` 的最大 id。
#: 用途只有一个 —— 收尾的 Z2 用例检测「上一次跑崩了、留下**不含标记**的记忆行」这种孤儿。
#:
#: 为什么需要它（真实事故，2026-09-19）：一趟崩掉的跑留下 13 行记忆，其中 12 行内容含
#: `__e2e_agent__`，被 `cleanup()` 的标记网扫掉了；**剩下那一行**
#: 「已删除题目（ID=2081），题库现有 1 题」不含任何标记 → 标记网抓不到，而它又低于
#: 下一趟跑的基线（基线网也抓不到）→ 在库里藏了 50 分钟，靠人肉逐行核对才发现。
#:
#: ⚠️⚠️ **这里只检测、只报警，绝不自动删**。窗口 `(sidecar 基线, 本次基线]` 里的行也可能是
#:      **真实用户**在两次跑之间那几分钟里说的话 —— 按窗口自动删就是又一次
#:      「`clear_*` 删光真实数据」事故（同日已经出过一次：27 条真实记忆被一句
#:      `clear_memories()` 删光）。所以发现就让用例**变红**、把可疑行的
#:      id/user_id/类型/内容摘要/metadata 全打出来，由人决定删不删。
#:
#: ⚠️ 语义细节：这个基线**只在校验干净时推进**（见收尾的 Z2）。发现孤儿就不推进，
#:    于是下一趟跑会**继续报同一批**，直到人工处理掉 —— 否则「报一次就忘」，
#:    孤儿照样能藏（今天它就藏了 50 分钟）。人工清掉后窗内自动变 0，基线自愈。
BASELINE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".e2e_agent_mem_baseline"
)

#: **人工确认清单**（只读）：一行一个 `ai_agent_memory.id`，`#` 开头当注释。
#:
#: 为什么需要它：Z2 的窗口 `(上次基线, 本次基线]` 里会混进两类**数据上无法区分**的行 ——
#:   ① 上一趟跑崩了留下的**无标记孤儿**（该清）；
#:   ② **真实用户**在两次跑之间那几分钟里自己说的话（不该清，删了就是又一次
#:      「一句 `clear_memories()` 删光 27 条真实记忆」的事故，同日已经出过一次）。
#: 没有这个出口时，「让用例变绿」的唯一办法就是**把那些行删掉** —— 恰恰是我们最不想要的动作。
#:
#: ⚠️⚠️ 所以 ack 的语义是「**这行是真实数据，已人工确认过，别再报它**」，
#:     **不是**「允许删除」，更**不是**清理清单。
#: ⚠️ 这个文件**只读**：脚本从不创建、从不修改、从不删除它；文件不存在 = 空集
#:     （所以它不会自己冒出来，也不会被自动清理）。
ACK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".e2e_agent_mem_orphans_ack"
)

#: Z2 打印**明细**时最多列几行。
#:
#: ⚠️⚠️ **它只允许影响打印，绝不允许影响判定**（2026-09-19 修掉的缺陷 4 就是这条）。
#: 此前查询里写的是 `ORDER BY id LIMIT 20`，而 `fresh` 是在那 20 行上算的、`fresh` 空就推进基线：
#: 窗口里 25 行孤儿、前 20 行都登记进 ack 时，用例会**判绿并推进基线**，剩下的 5 行掉到新基线
#: 以下，标记网与基线网都再也抓不到 —— **孤儿越多越容易越过阈值、越看不见**。
#: 现在判定用全量 `count(*)`，明细全量取、只在这里截断，且截断必须把
#: 「还有 N 行未打印」写进 `actual`。
Z2_DETAIL_LIMIT = 20

#: **单实例锁**。同一套件**绝不允许两个进程同时跑**。
#:
#: 为什么必须有它（2026-09-19 事故，一晚报废好几批证据）：本套件的夹具名**不带时间戳**
#: （`__e2e_agent__A/B/C/E`、`__e2e_agent_note__*`），并且都写**同一个真实用户**
#: （`sys_user` 里第一个 user_id）。于是后跑的进程会把先跑的进程刚建好的夹具删掉 ——
#: 症状是：
#:   · `StaleDataError: UPDATE statement on table 'rag_document' expected to update 1 row(s);
#:     0 were matched.`（一方在插文档，另一方正在 cleanup）
#:   · `Z1 基线 id` 异常跳变、记忆条数与预期对不上
#: 看着像功能坏了，其实是两个进程互删。**连自己跟自己都不能并发。**
#:
#: 实现要点：
#:   · 用 `O_CREAT|O_EXCL` **原子创建**，不是「先判断 exists 再 create」（那有 TOCTOU 窗口）；
#:   · 拿不到锁时，如果锁**新鲜** → 判定为并发实例，什么也不做直接退 2；
#:   · 锁**陈旧**（mtime 超过 `LOCK_STALE_SECONDS`，通常是上一次崩了没走到 finally）→ 偷锁重抢，
#:     偷锁用 `os.rename`（原子，两个进程同时判「陈旧」也只有一个能 rename 成功），
#:     免得「两个进程都删同一个陈旧锁」把刚拿到锁的那个删掉。
LOCK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".e2e_agent_api.lock"
)

#: 锁的「新鲜」阈值（秒）。超过它视为陈旧锁（持有者已崩），可以偷。
LOCK_STALE_SECONDS = 600


def _lock_age_seconds():
    """锁文件的年龄（秒）；文件不存在/读不到 → None"""
    try:
        return time.time() - os.stat(LOCK_FILE).st_mtime
    except OSError:
        return None


def _lock_holder() -> str:
    """锁文件内容（写给并发者看：谁的 pid、什么时候开的）"""
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return " ".join(f.read().split())
    except OSError:
        return "(锁文件内容读不到)"


def _steal_stale_lock() -> None:
    """原子偷陈旧锁：rename 到本进程独有的名字。

    `os.rename` 只会成功一次 —— 两个进程同时判「这部分锁陈旧」时，只有一个能 rename 成功，
    所以不会出现「A 刚抢到锁、B 又把它删了」。失败（FileNotFoundError/FileExistsError）
    说明别人已经处理过，直接返回即可。
    """
    victim = f"{LOCK_FILE}.stale.{os.getpid()}"
    try:
        os.rename(LOCK_FILE, victim)
    except OSError:
        return
    try:
        os.remove(victim)
    except OSError:
        pass


def acquire_lock() -> bool:
    """抢单实例锁。抢到 → True；抢不到且锁新鲜 → 打印原因 + False（调用方退 2、什么都不做）"""
    payload = (
        f"pid={os.getpid()}\n"
        f"started={datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"host={socket.gethostname()}\n"
        f"script={os.path.abspath(__file__)}\n"
    )
    for _ in range(3):  # 陈旧锁要到下一轮才能抢；给几轮足够应付「别人也在偷」
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = _lock_age_seconds()
            if age is not None and age < LOCK_STALE_SECONDS:
                print(f"[LOCK] 已有另一个实例在跑：{LOCK_FILE}（锁龄 {int(age)}s"
                      f" < {LOCK_STALE_SECONDS}s，说明持有者还活着）")
                print(f"[LOCK] 持有者：{_lock_holder()}")
                print("[LOCK] 同一套件两个进程会互删固定名夹具（见脚本里 LOCK_FILE 的注释）"
                      " → 本次**什么都不做**（不碰 DB / 不写产物 / 不动 sidecar），退出码 2")
                return False
            print(f"[LOCK] 发现陈旧锁（锁龄 "
                  f"{'未知' if age is None else int(age)}s ≥ {LOCK_STALE_SECONDS}s，"
                  f"上一次大概是崩了没释放）→ 原子偷锁后重抢")
            _steal_stale_lock()
            continue
        except Exception as e:  # noqa: BLE001 - 建不了锁就没法保证不撞车
            print(f"[LOCK] 创建锁文件失败：{e!r} → 为安全起见不跑，退出码 2")
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
        except Exception as e:  # noqa: BLE001 - 写内容失败不影响锁的排他性
            print(f"[WARN] 写锁文件内容失败（不影响排他）：{e!r}")
        print(f"[LOCK] 已获得单实例锁 {LOCK_FILE}（pid={os.getpid()}）")
        return True
    print(f"[LOCK] 连续抢锁失败，判定为有并发实例（持有者：{_lock_holder()}）→ 退出码 2")
    return False


def _lock_pid(content: str):
    """取锁文件里的 **pid 字段**（整数）；取不到/不是整数 → None

    锁文件是 `acquire_lock()` 写的**多行 `key=value`**：`pid=` / `started=` / `host=` / `script=`。
    按行 `partition("=")` 解析（只切**第一个** `=`，所以 `script=D:\\…\\x.py` 不会被误切）。
    """
    for line in (content or "").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().lower() == "pid":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def release_lock() -> None:
    """释放锁。**只删自己那把** —— 锁被偷过/被别人重建时不许删（否则会放后面的人进来）"""
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        # ⚠️ **不许用「子串包含」判 pid**（缺陷 3，2026-09-20 修）：
        #    原写法是 `if f"pid={os.getpid()}" not in content: return` ——
        #    **自己的 pid 是别人 pid 的前缀**时它判真，于是会把**别人的锁**删掉
        #    （自己 1234、锁里是 12345 → `"pid=1234"` 是 `"pid=12345"` 的子串），
        #    删掉正在跑的那个实例的锁 = 放第二个实例进来 = 固定名夹具互删。
        #    这里改成解析出 pid **字段**再比整数。
        # 方向不对称是故意的：**读不出 pid 也一律不删** —— 宁可留一把陈旧锁让下一趟去偷
        # （`_steal_stale_lock` 是原子且只影响陈旧锁），也不能误删活锁。
        if _lock_pid(content) != os.getpid():
            return
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass
    except OSError as e:  # noqa: BLE001 - 释放失败不该盖掉退出码
        print(f"[WARN] 释放锁失败：{e!r}")


def _now_stamp() -> str:
    """带**毫秒**的时间戳。

    秒级粒度下同秒两次失败会互相覆盖（2026-09-19 实测：`..._221906_red.json` 与
    `..._221920_red.json` 之间还插进了一次同秒的失败，只有一份留下来），
    而红产物是事故的原始材料，被覆盖就等于证据消失。
    """
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)


def _result_payload(completed: bool, extra=None) -> dict:
    """产物 json 的**唯一**组装处（OUT 与 _evidence/ 里的副本形状必须一致）

    `completed` 是必需的：`main()` 中途抛异常时产物**不写**，磁盘上留的是**上一次**的
    产物（可能是绿的）→ 会造出「退出码 1 + 产物看起来全绿」这种会被误读的组合。
    有了这个字段，「全绿但 completed=false」一眼就能认出是崩溃残留。
    """
    payload = {
        "total": len(ROWS),
        "passed": len([r for r in ROWS if r["status"] == "通过"]),
        "rows": ROWS,
        "completed": bool(completed),
    }
    if extra:
        payload.update(extra)
    return payload


def _write_json(path: str, payload: dict) -> bool:
    """写产物 json（失败只 WARN —— 另存失败绝不能反过来盖掉退出码）"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 写产物失败 {path}: {e!r}")
        return False


def save_red_evidence() -> None:
    """失败时把同一份内容另存到 `_evidence/`（带毫秒时间戳）；**绿的时候什么都不写**"""
    path = os.path.join(
        EVIDENCE_DIR, f"e2e_agent_api_result_{_now_stamp()}_red.json"
    )
    if _write_json(path, _result_payload(True)):
        print("红产物另存:", path)


def save_crash_evidence(exc: BaseException) -> None:
    """崩溃路径的「未完成」证据：`completed=false` + traceback 摘要

    为什么要单独一份：崩溃时 `main()` 走不到写产物的那一步，`OUT` 里留的是**上一次**的
    结果；只看 `OUT` 会以为「跑过了、是绿的」。
    """
    extra = {
        "crashed": True,
        "error": repr(exc),
        "traceback": traceback.format_exc()[-4000:],
    }
    path = os.path.join(
        EVIDENCE_DIR, f"e2e_agent_api_result_{_now_stamp()}_crash.json"
    )
    _write_json(path, _result_payload(False, extra))
    print("崩溃证据另存:", path)
    # OUT 也标成未完成：否则「退出码 1 + 产物全绿」会被当成「只有零散用例失败」
    _write_json(OUT, _result_payload(False, extra))


def read_acked_ids() -> set:
    """读人工确认过的 id 集合（文件不存在/读不动 → 空集，绝不因此让用例失败）"""
    acked: set = set()
    try:
        with open(ACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                try:
                    acked.add(int(line))
                except ValueError:
                    continue  # 写错的行走不了就把整条用例搞红，忽略即可
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001 - 出口本身不该成为故障点
        print(f"  [WARN] ack 文件读取失败（按空集处理）: {e!r}")
    return acked


def read_prev_mem_baseline() -> int | None:
    """读上次记录的、**已验证干净**的记忆基线；文件缺失/损坏返回 None（首次运行）"""
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            value = int(json.load(f)["mem_baseline"])
        return value if value >= 0 else None
    except Exception:  # noqa: BLE001 - sidecar 坏了不该拖垮测试
        return None


def write_mem_baseline(value: int) -> None:
    """写 sidecar 基线（Z2 的窗口下界就是这个值）

    ⚠️ 这里**刻意不写「调用点有几处」**：那种数字写下来就会漂
    （本仓库已经因为「文档里的数字」返工过好几次 —— 比如某个「两处」其实是三处）。
    改这里时按**场景**逐个对照，别数个数：
      · **首次运行的 bootstrap** —— sidecar 不存在时把当前最大 id 写进去，
        这样万一这趟就崩了，下次跑仍能把它留下的行圈进「两次跑之间」的窗口；
      · **Z2 空窗口**（`prev >= cur`：两跑之间一行都没新增，或基线高于当前最大值）——
        窗口是空集 → 推进到当前最大 id。注意这属于**空转通过**（用例会自己说明「未检测」）；
      · **Z2 校验干净**（窗口里有行，但除已确认的外没有新孤儿、且明细与 `count(*)` 一致）→ 推进基线；
        反之（有新孤儿，或明细行数与 `count(*)` 不一致）→ **写回旧值把基线钉住**，
        让下次跑继续报同一批，直到人工处理或登记进 ack 文件。

    真正决定「推进还是钉住」的是调用点传进来的取值，本函数只负责落盘。
    """
    try:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump({"mem_baseline": int(value)}, f)
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] 写记忆基线 sidecar 失败（Z2 会退化）: {e!r}")


ROWS = []
_SESSION_IDS = []

#: 本脚本自造的**知识库** id（I11–I17 的检索夹具）。收尾时按这些**精确 id** 物理删
#: （外键顺序 qa → chunk → doc → kb）—— 库里还有用户的真实知识库，绝不能按无标记条件删。
_RAG_FIXTURE_KB_IDS = []

#: 每次假 LLM 被调用时收到的 messages（E 组用它检查「回灌给模型的内容」）
SEEN_ROUNDS = []


def T(cid, module, title, pre, steps, expected, ok, actual):
    ROWS.append({
        "cid": cid, "module": module, "title": title, "pre": pre,
        "steps": steps, "expected": expected, "actual": actual,
        "status": "通过" if ok else "失败",
    })
    print(("  [PASS] " if ok else "  [FAIL] ") + cid + " " + title + " -> " + str(actual))


def _tool_names(tools):
    """从 `registry.definitions()` 的输出里取出工具名集合

    `/ai/agent/tools` 的 `tools` 是 Function Calling 格式的数组
    （`[{"type":"function","function":{"name":...}}]`），不是名字数组。
    """
    names = set()
    for t in tools or []:
        name = ((t or {}).get("function") or {}).get("name")
        if name:
            names.add(name)
    return names


def _action_enum(tools, name):
    """某个工具 `parameters.properties.action.enum`（找不到 → None）

    A1 / P 组用它把「工具清单里的 action 枚举」与「工具类里声明的」逐项对齐 ——
    只断言「工具名在」是弱断言：`action` 少写一个值（或顺序/拼写漂了）
    模型照样看不到那个能力，而工具名一个都没少。
    """
    for t in tools or []:
        fn = ((t or {}).get("function") or {})
        if fn.get("name") == name:
            props = ((fn.get("parameters") or {}).get("properties") or {})
            return list((props.get("action") or {}).get("enum") or []) or None
    return None


#: **注册表里应当恰好有的工具**（A1 用它做集合相等断言）。
#:
#: ⚠️ 为什么是「精确集合」而不是 `>=`（2026-09-22 收紧）：原断言写的是
#:    `_tool_names(tools) >= {五个}` —— 那样**工具改名 / 注册漏一行 / 多注册一个**
#:    全都盖不住（多一个工具会让系统提示词变长、模型选错概率上升，正是本轮
#:    「5 个新工具合并成 5 个」那条裁决的反面）。断言期望集合相等，两头都能红。
#: ⚠️ 加工具时必须同时改这里 —— 这一条是**故意**的：工具清单是模型能力面，
#:    改它应当有人过一眼。
EXPECTED_TOOL_NAMES = {
    "bank_manage",
    "bank_share_manage",
    "knowledge_base_manage",
    "knowledge_search",
    "learning_stats",
    "memory_manage",
    "memory_search",
    "note_manage",
    "question_flag_manage",
    "question_manage",
}

#: 每个「按 action 枚举」的工具**声明的 action**（**实测**自注册表，不是抄文档）。
#:
#: 比对用**集合**（`set`）：枚举顺序不是契约，少一个 / 多一个 / 拼错才是
#: —— 那三种都会让模型看不到某个能力，而工具名一个都没少（弱断言盖不住）。
#: ⚠️ `note_manage` 有 `list_categories`、**没有** `delete_by_name`（笔记标题不唯一）。
EXPECTED_ACTION_ENUMS = {
    "bank_manage": {
        "list", "detail", "create", "update", "delete", "delete_by_name",
        "delete_many",
    },
    "bank_share_manage": {"list_shares", "share", "revoke", "receive", "copy"},
    "knowledge_base_manage": {
        "list", "create", "update", "delete", "list_documents", "delete_document",
    },
    "knowledge_search": {"search", "list"},
    "learning_stats": {
        "overview", "by_subject", "trend", "error_analysis", "growth",
    },
    "memory_manage": {"list_types", "forget", "clear"},
    "memory_search": {"search", "list"},
    "note_manage": {
        "list", "detail", "list_categories", "create", "update", "delete",
        "delete_many",
    },
    "question_flag_manage": {"list", "add", "master", "remove"},
    "question_manage": {
        "list", "detail", "search", "create", "batch_import", "update", "delete",
        "delete_many", "clear_questions",
    },
}


# ======================================================================
# 脚本化假 LLM：按轮次吐内容（第 N 轮 = SCRIPTS 里第 N 项）
# ======================================================================
class FakeChunk:
    def __init__(self, content="", tool_calls=None, reasoning=None):
        self.content = content
        self.tool_calls = tool_calls or []
        #: 深度思考正文。真实链路里它由 `langchain_reasoning_patch` 注入到
        #: `additional_kwargs["reasoning_content"]`（langchain-openai 默认会丢掉），
        #: 这里刻意**复刻同一个形状**，用来验 `loop.py` 会不会把它发成 thinking 事件。
        #: ⚠️ 别改成 `self.reasoning` —— 那样测的就不是真实字段名了。
        self.additional_kwargs = {"reasoning_content": reasoning} if reasoning else {}

    def __add__(self, other):
        r1 = (self.additional_kwargs or {}).get("reasoning_content") or ""
        r2 = (other.additional_kwargs or {}).get("reasoning_content") or ""
        return FakeChunk(
            (self.content or "") + (other.content or ""),
            (self.tool_calls or []) + (other.tool_calls or []),
            (r1 + r2) or None,
        )


class ScriptedLLM:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.i = 0

    def bind_tools(self, defs):
        return self

    async def astream(self, messages):
        SEEN_ROUNDS.append(list(messages))
        chunks = self.rounds[self.i] if self.i < len(self.rounds) else [FakeChunk("好的。")]
        self.i += 1
        for c in chunks:
            yield c


class FakeConfig:
    model = "e2e-fake"
    provider = "deepseek"


#: 待用脚本队列：每次 build_agent_llm 取一个
SCRIPTS = []


def script_tool_then_reply(tool_name, args, reply):
    """一轮工具调用 + 一轮最终回复"""
    SCRIPTS.append([
        [FakeChunk("", [{"name": tool_name, "args": args, "id": "c1"}])],
        [FakeChunk(reply)],
    ])


async def fake_build_agent_llm(db, provider=None, model=None, temperature=None, **kwargs):
    # **kwargs 兜住 db_config.build_agent_llm 后续新增的入参（如 user_id），
    # 否则签名不匹配 → TypeError: unexpected keyword argument。
    rounds = SCRIPTS.pop(0) if SCRIPTS else [[FakeChunk("好的。")]]
    return ScriptedLLM(rounds), FakeConfig()


def events_of(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line == "[DONE]":
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return out


def types_of(events):
    return [e.get("type") for e in events]


# ======================================================================
# 主流程
# ======================================================================
async def main():
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    from app.core.security import get_current_user
    from app.database import async_session_factory
    from app.main import app
    from app.services.ai import db_config
    from app.services.ai.agent import loop as agent_loop
    from sqlalchemy import delete, func, select, text

    async with async_session_factory() as db:
        uid = int(await db.scalar(text("SELECT user_id FROM sys_user ORDER BY user_id LIMIT 1")) or 0)
        # 上一次跑记录的基线（sidecar，可能是 None = 首次跑）。Z2 用它圈出「两次跑之间」
        # 新增的记忆行，从而发现上一次跑崩掉后留下的**无标记孤儿**（见 BASELINE_FILE 注释）。
        prev_mem_baseline = read_prev_mem_baseline()
        # 记忆基线：本脚本会**真的执行写操作**，`memory_hook` 会给当前用户落长期记忆。
        # 记下跑之前的最大 id，收尾时把之后新增的删掉（见 `cleanup()`）。
        mem_baseline = int(
            await db.scalar(text("SELECT COALESCE(MAX(id), 0) FROM ai_agent_memory")) or 0
        )
    # ⚠️ 只在**首次运行**（sidecar 不存在）时 bootstrap 一次：这样万一这趟就崩了，
    #    下次跑仍能把它留下的行圈进「两次跑之间」的窗口。之后基线**只在校验干净时推进**
    #    （见收尾 Z2）—— 有孤儿就不推进，让下次跑继续报，直到人工处理掉。
    if prev_mem_baseline is None:
        write_mem_baseline(mem_baseline)
    if not uid:
        # 库是空的 → **没跑到任何用例**，按退出码约定给 2（不是 0：「没跑」≠「通过」）
        print("找不到任何用户，无法测试")
        return 2

    db_config.build_agent_llm = fake_build_agent_llm
    fake_user = {"user_id": uid, "userName": "e2e-agent"}

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://e2e", timeout=60)
    client.headers.update({"Content-Type": "application/json"})

    def auth_on():
        app.dependency_overrides[get_current_user] = lambda: dict(fake_user)

    def auth_off():
        app.dependency_overrides.pop(get_current_user, None)

    async def preview_raw(tool, params, auto_confirm=None):
        """`POST /ai/agent/preview` 的**原样**调用（返回 (响应, body)）

        `auto_confirm` 不为 None 时带进请求体（v1 契约里它是**可选**字段：
        preview 与 execute 必须用**同一个** autoConfirm 值判定，否则
        「preview 发了票 / execute 说要票」这种组合会互相打架）。
        """
        body = {"tool": tool, "params": params, "userId": uid, "sessionId": ""}
        if auto_confirm is not None:
            body["autoConfirm"] = auto_confirm
        resp = await client.post("/ai/agent/preview", json=body)
        return resp, (resp.json() if isinstance(resp.json(), dict) else {})

    async def ticket_for(tool, params, auto_confirm=True):
        """取服务端确认票据（v1 契约：**只有确实需要确认时**才下发）

        需要确认的判定与执行侧同一个函数（`loop.needs_user_confirmation`）：
        破坏性操作恒需要；`autoConfirm=false` 时所有写操作需要。不需要确认时拿到的
        是 `None`（字段不出现），调用方照旧不带票据 —— 存量调用方零改动。
        """
        _resp, body = await preview_raw(tool, params, auto_confirm)
        return body.get("confirmTicket")

    async def execute_raw(tool, params, confirmed=True, auto_confirm=True, ticket=""):
        """**不带票据**（或带一张指定票据）的原始调用

        O 组用它验证「拒绝路径」与「重放 / 参数不匹配 / 越权票据」——
        这些用例要的正是**不**自动取票的行为。`ticket=""` 时请求体里没有该字段。
        """
        body = {
            "tool": tool, "params": params, "userId": uid,
            "autoConfirm": auto_confirm, "confirmed": confirmed,
        }
        if ticket:
            body["confirmTicket"] = ticket
        r = await client.post("/ai/agent/execute", json=body)
        return r.json() or {}

    async def execute(tool, params, confirmed=True, auto_confirm=True):
        """调 ds-free 的单步执行接口（**自动带上确认票据**）

        注意：`POST /ai/agent/execute` 直接返回 `ok()` / `fail()` **信封本身**
        （不再包一层 `success(data=…)`），所以这里直接取 `r.json()`。

        ⚠️ v1 契约（2026-09-21）：需要确认的操作（破坏性动作恒需要；
        `autoConfirm=false` 时所有写操作）必须在请求体里带一个**服务端签发的
        `confirmTicket`** —— `confirmed: true` 保留但**不再是充分条件**。
        所以这里先 `preview` 取票再执行（取不到票就不带该字段，存量行为不变）。
        要验「不带票据会被拒」请用 `execute_raw`。
        """
        ticket = await ticket_for(tool, params, auto_confirm)
        return await execute_raw(
            tool, params, confirmed=confirmed, auto_confirm=auto_confirm,
            ticket=ticket or "",
        )

    async def run_stream(body, approve=None):
        """跑一次 /ai/agent/stream；approve 不为 None 时遇到确认就调 /ai/agent/confirm"""
        task = asyncio.create_task(client.post("/ai/agent/stream", json=body))
        if approve is not None:
            for _ in range(400):
                ids = list(agent_loop._pending_confirms.keys())
                if ids:
                    await client.post("/ai/agent/confirm",
                                      json={"confirmId": ids[0], "approved": approve})
                    break
                await asyncio.sleep(0.05)
        resp = await task
        return events_of(resp.text)

    async def cleanup():
        # 删临时题库
        r = await execute("bank_manage", {"action": "list", "bank_name": PREFIX})
        for b in (r.get("banks") or []):
            await execute("bank_manage", {"action": "delete", "bank_id": b.get("bankId")})
        # 删临时会话
        for sid in list(_SESSION_IDS):
            await client.delete(f"/ai/sessions/{sid}", params={"userId": uid})
        # 笔记：**物理删**，不走工具的 delete（那是逻辑删除，会在库里留 del_flag='2' 残骸，
        # 测试数据不该有残骸）。先删笔记再删分类 —— note.category_id 有外键指向 note_category。
        #
        # ⚠️ 这里用 `LEFT(col, LENGTH(:p)) = :p` 做**精确前缀**匹配，**不要用 LIKE**：
        #    前缀里的 `_` 在 SQL LIKE 里是「匹配任意单字符」的通配符，
        #    `LIKE '__e2e_agent_note__%'` 会退化成「任意两字符 + e2e + 任意字符 + agent…」，
        #    等于用一条模糊模式去删用户的真数据。测试清理不该有这种爆炸半径。
        async with async_session_factory() as cdb:
            await cdb.execute(
                text("DELETE FROM note WHERE LEFT(title, LENGTH(:p)) = :p"),
                {"p": NOTE_PREFIX},
            )
            await cdb.execute(
                text("DELETE FROM note_category WHERE LEFT(name, LENGTH(:p)) = :p"),
                {"p": NOTE_PREFIX},
            )
            # 第四道网：N 组 / P 组的「他人 IDOR」夹具 —— 它属于**另一个用户**，
            # `bank_manage.list` 看不到它（那只列当前用户的题库），所以只能按标记前缀物理删。
            # ⚠️⚠️ 子查询里的列名必须**限定表名**：PG 会把不限定列名的 `bank_id` 解析成
            #     **外层** `question_main.bank_id`，条件退化成「只要存在同名题库」→
            #     试图删光整张 question_main（2026-09-19 差点真发生，被外键拦下）。
            #     这里写 `SELECT id FROM question_bank`（question_bank 的主键就叫 id）。
            #
            # ⚠️⚠️ **删除顺序是硬要求：子表 → question_main → question_bank**
            #     （2026-09-22 实测，被 P 组的夹具打红过一次）：这批外键在 PG 里
            #     **全是 `delete_rule=NO ACTION`，一条 ON DELETE CASCADE 都没有**：
            #       · `user_question_{error,favorite,marked}.question_id → question_main`
            #       · `user_question_*.bank_id / user_bank_favorite.bank_id /
            #          note_question_bank.question_bank_id → question_bank`
            #       · `question_sub.main_id / note_question.question_id → question_main`
            #     少删一层就是 `ForeignKeyViolationError`，而它会让**整段 cleanup 回滚**
            #     ——以前这里只删 question_main/question_bank 之所以没炸，是因为 N 组的
            #     夹具只有题、没有任何标记记录；P 组给「别人的题」加了三类标记记录之后
            #     立刻就炸了（现象：Z1 红、残留 39 条记忆，而 `finally` 里的
            #     `except Exception: pass` 把真正的异常**吞掉了**，日志里一个字都没有）。
            _idor_sub = (
                "SELECT id FROM question_bank "
                "WHERE LEFT(COALESCE(bank_name, ''), LENGTH(:p)) = :p"
            )
            for _tbl, _col in (
                ("user_question_error", "bank_id"),
                ("user_question_favorite", "bank_id"),
                ("user_question_marked", "bank_id"),
                ("user_bank_favorite", "bank_id"),
                ("note_question_bank", "question_bank_id"),
                ("bank_share", "bank_id"),
                ("bank_share_receive", "bank_id"),
            ):
                await cdb.execute(
                    text(f"DELETE FROM {_tbl} WHERE {_col} IN ({_idor_sub})"),
                    {"p": OTHER_IDOR_MARK},
                )
            await cdb.execute(
                text(
                    "DELETE FROM question_sub WHERE main_id IN "
                    "(SELECT id FROM question_main WHERE bank_id IN (" + _idor_sub + "))"
                ),
                {"p": OTHER_IDOR_MARK},
            )
            await cdb.execute(
                text(
                    "DELETE FROM note_question WHERE question_id IN "
                    "(SELECT id FROM question_main WHERE bank_id IN (" + _idor_sub + "))"
                ),
                {"p": OTHER_IDOR_MARK},
            )
            await cdb.execute(
                text(
                    "DELETE FROM question_main WHERE bank_id IN (" + _idor_sub + ")"
                ),
                {"p": OTHER_IDOR_MARK},
            )
            await cdb.execute(
                text(
                    "DELETE FROM question_bank "
                    "WHERE LEFT(COALESCE(bank_name, ''), LENGTH(:p)) = :p"
                ),
                {"p": OTHER_IDOR_MARK},
            )
            # 第三道网：I11–I17 造的**检索夹具知识库**，按**登记过的精确 id** 物理删
            # （外键顺序 qa → chunk → doc → kb）。
            # ⚠️ 库里还有用户的真实知识库（user 105 的「数据结构」「java」）——
            #    这里**只删本脚本登记过的 id**，绝不按无标记条件删、更不整表清。
            for kb_id_ in list(_RAG_FIXTURE_KB_IDS):
                for stmt in (
                    "DELETE FROM rag_qa_record WHERE kb_id = :k",
                    "DELETE FROM rag_document_chunk WHERE kb_id = :k",
                    "DELETE FROM rag_document WHERE kb_id = :k",
                    "DELETE FROM rag_knowledge_base WHERE id = :k",
                ):
                    await cdb.execute(text(stmt), {"k": kb_id_})
            _RAG_FIXTURE_KB_IDS.clear()
            # 长期记忆：Agent 每完成一次**写操作**都会自动落一条 `ai_agent_memory`
            # （见 `memory_hook` / `loop._execute_tool`）—— 上面这些建/删题库、建笔记、
            # 乃至 `cleanup()` 自己的删除动作，全都会留下记忆。不清理的话，跑一次测试
            # 就往真实用户的「记忆」里塞十几条垃圾，用户下次问「我上次建了什么题库」
            # 会被这些噪声带偏。
            #
            # 两道网，缺一不可：
            #   ① 按标记字面匹配 —— 能扫掉**历史遗留**（包括上一次跑崩了没清干净的），
            #      因为那时基线已经过去了、扫不到。
            #      用 `POSITION(标记 IN content)` 而不是 LIKE：标记里的 `_` 在 LIKE 里是
            #      「匹配任意单字符」的通配符，`LIKE '%__e2e_agent__%'` 会退化成一条模糊
            #      模式去匹配真实记忆。这里不按 user_id 过滤 —— G 组会以管理员身份替别人
            #      执行，行属于谁不确定；但「字面包含 __e2e_agent」只有本测试的数据能满足。
            #   ② 按**基线 id** —— 工具的 `message` 不一定带标记（实测
            #      「已删除题目（ID=1919），题库现有 1 题」就没有任何标记），只靠 ① 会漏。
            #      范围收在「本次跑之后 + 只会写到 uid」上，爆炸半径是「测试期间该用户的
            #      新增记忆」—— 本地回归场景下没有并发真实会话，可以接受。
            for marker in (PREFIX, NOTE_PREFIX):
                await cdb.execute(
                    text("DELETE FROM ai_agent_memory WHERE POSITION(:m IN content) > 0"),
                    {"m": marker},
                )
            await cdb.execute(
                text(
                    "DELETE FROM ai_agent_memory "
                    "WHERE user_id = :u AND id > :baseline"
                ),
                {"u": uid, "baseline": mem_baseline},
            )
            await cdb.commit()

    auth_on()
    try:
        # ================= A. 工具清单 / 鉴权 =================
        r = await client.get("/ai/agent/tools")
        data = r.json() or {}
        tools = data.get("tools") or []
        actions = data.get("actions") or {}
        # 先算好两个诊断量再进 f-string：**f-string 里的推导式不能跨相邻字面量**
        # （`f"{[x for x in ...` 换行写成两段相邻字符串会 SyntaxError）
        a1_names = _tool_names(tools)
        a1_extra = sorted(a1_names - EXPECTED_TOOL_NAMES)
        a1_missing = sorted(EXPECTED_TOOL_NAMES - a1_names)
        a1_enum_bad = [n for n, e in EXPECTED_ACTION_ENUMS.items()
                       if set(_action_enum(tools, n) or []) != e]
        a1_ro_in_actions = [n for n in ("knowledge_search", "memory_search") if n in actions]
        T("A1", "工具清单", "GET /ai/agent/tools 下发的工具集合与 action 枚举**一个不差**",
          "已登录", "GET /ai/agent/tools",
          "工具名集合 == 期望的 10 个（多一个 / 少一个 / 改名都判失败）；"
          "每个工具的 action 枚举 == 期望集合；"
          "bank_manage.destructive 含三个删除动作；note_manage.destructive 含两个删除动作；"
          "knowledge_search / memory_search 是只读的 → 不该出现在写/破坏性清单里",
          # ⚠️ 2026-09-22 **收紧**：原来写的是 `>= {五个}`（弱断言）——
          #    工具改名、注册漏一行、多注册一个它都能绿。而「工具数量变了」本身
          #    确实是回归（清单越长，模型选错概率越高，本轮刚把 3 个工具合并成 1 个）。
          #    所以改成**精确集合相等**：两头都能红。加工具时要同步改
          #    `EXPECTED_TOOL_NAMES`（故意的，工具清单是模型能力面）。
          _tool_names(tools) == EXPECTED_TOOL_NAMES
          # action 枚举也要逐项对齐：工具名还在、但少了个 action 同样等于能力没了
          and all(
              _action_enum(tools, n) is not None
              and set(_action_enum(tools, n)) == expected
              for n, expected in EXPECTED_ACTION_ENUMS.items()
          )
          and set(actions.get("bank_manage", {}).get("destructive") or [])
          == {"delete", "delete_by_name", "delete_many"}
          and set(actions.get("note_manage", {}).get("destructive") or [])
          == {"delete", "delete_many"}
          # note_manage 刻意没有 delete_by_name（笔记标题不唯一，按名删会删错），
          # 所以写入清单里也不该出现它
          and "delete_by_name" not in (actions.get("note_manage", {}).get("write") or [])
          # 只读检索工具不该进写清单 —— 进了的话前端会对每次检索弹确认卡片
          and "knowledge_search" not in actions
          and "memory_search" not in actions,
          f"tools={sorted(a1_names)} "
          f"多出来的={a1_extra} 少了的={a1_missing} 枚举对不上的={a1_enum_bad} "
          f"bank={actions.get('bank_manage')} note={actions.get('note_manage')} "
          f"readonlyInActions={a1_ro_in_actions}")

        # 鉴权：本项目把业务错误统一成 HTTP 200 + code，所以要同时看 status 与 body.code
        auth_off()
        r = await client.get("/ai/agent/tools")
        body = r.json() if isinstance(r.json(), dict) else {}
        code = body.get("code")
        T("A2", "鉴权", "未登录（无 token）访问被拒",
          "移除登录依赖覆盖后不带 token", "GET /ai/agent/tools",
          "HTTP 401/403 或 body.code=401/403",
          r.status_code in (401, 403) or code in (401, 403),
          f"status={r.status_code} code={code}")

        r = await client.post("/ai/agent/execute",
                              json={"tool": "bank_manage", "params": {"action": "list"}})
        body = r.json() if isinstance(r.json(), dict) else {}
        T("A3", "鉴权", "未登录不得调工具（写/执行入口）",
          "不带 token", "POST /ai/agent/execute",
          "HTTP 401/403 或 body.code=401/403",
          r.status_code in (401, 403) or body.get("code") in (401, 403),
          f"status={r.status_code} code={body.get('code')}")
        auth_on()

        await cleanup()  # 预清理历史残留

        # ================= B. ds-free 单步 /ai/agent/execute =================
        r = await execute("bank_manage", {"action": "create", "bank_name": BANK_A, "subject": "数学"})
        bid = (r.get("bank") or {}).get("bankId")
        T("B1", "ds-free 单步", "建题库",
          f"用户 {uid}", "execute bank_manage.create", "成功并返回 bankId",
          bool(r.get("success") and bid), f"bankId={bid}")

        qs = json.dumps([
            {"questionType": 1, "questionText": "E2E-Q1", "options": ["A", "B"], "answer": "0", "analysis": "普通解析"},
            {"questionType": 1, "questionText": "E2E-Q2", "options": ["A", "B"], "answer": "1", "analysis": "关键词：专有标记词"},
            {"questionType": 4, "questionText": "E2E-Q3", "answer": "42"},
            {"questionType": 5, "questionText": "E2E-Q4", "answer": "略"},
        ], ensure_ascii=False)
        r = await execute("question_manage", {"action": "batch_import", "bank_id": bid, "questions": qs})
        T("B2", "ds-free 单步", "批量导入 4 道题",
          f"bankId={bid}", "execute question_manage.batch_import", "imported=4, bankTotal=4",
          r.get("imported") == 4 and r.get("bankTotal") == 4,
          f"imported={r.get('imported')} total={r.get('bankTotal')}")

        r = await execute("question_manage", {"action": "list", "bank_id": bid, "limit": 2, "offset": 0})
        T("B3", "分页", "list 第一页 offset=0 limit=2",
          f"bankId={bid}", "execute question_manage.list", "count=2 total=4 hasMore=True",
          r.get("count") == 2 and r.get("total") == 4 and r.get("hasMore") is True,
          f"count={r.get('count')} total={r.get('total')} hasMore={r.get('hasMore')}")

        r = await execute("question_manage", {"action": "list", "bank_id": bid, "limit": 2, "offset": 2})
        T("B4", "分页", "list 第二页 offset=2",
          f"bankId={bid}", "execute question_manage.list", "count=2 hasMore=False",
          r.get("count") == 2 and r.get("hasMore") is False,
          f"count={r.get('count')} hasMore={r.get('hasMore')}")

        r = await execute("question_manage", {"action": "search", "question_text": "专有标记词"})
        hits = [q.get("questionText") for q in (r.get("questions") or [])]
        T("B5", "搜索扩范围", "关键词只出现在 analysis 里也能搜到",
          "E2E-Q2 的关键词只在解析里", "execute question_manage.search",
          "命中 E2E-Q2", "E2E-Q2" in hits, f"hits={hits}")

        # search 的分页字段必须和 list 一样齐 —— 只回一页而不报总量的话，
        # 卡片摘要会把「本次返回 20 条」说成「共 20 条」，用户也没法知道还有多少。
        r = await execute("question_manage", {
            "action": "search", "bank_id": bid, "question_text": "E2E-Q",
            "limit": 2, "offset": 0,
        })
        T("B5b", "搜索分页", "search 第一页 offset=0 limit=2",
          f"bankId={bid} 有 4 道 E2E-Q*", "execute question_manage.search",
          "count=2 total=4 hasMore=True",
          r.get("count") == 2 and r.get("total") == 4 and r.get("hasMore") is True,
          f"count={r.get('count')} total={r.get('total')} hasMore={r.get('hasMore')}")

        r = await execute("question_manage", {
            "action": "search", "bank_id": bid, "question_text": "E2E-Q",
            "limit": 2, "offset": 2,
        })
        T("B5c", "搜索分页", "search 第二页 offset=2",
          f"bankId={bid}", "execute question_manage.search",
          "count=2 total=4 hasMore=False",
          r.get("count") == 2 and r.get("total") == 4 and r.get("hasMore") is False,
          f"count={r.get('count')} total={r.get('total')} hasMore={r.get('hasMore')}")

        # 重名校验：建第二个库后，把 A 改成 B 的名字
        r = await execute("bank_manage", {"action": "create", "bank_name": BANK_B})
        r = await execute("bank_manage", {"action": "update", "bank_id": bid, "bank_name": BANK_B})
        T("B6", "改名重名校验", "改成已存在的题库名被拒",
          f"A={BANK_A} B={BANK_B}", "execute bank_manage.update(bank_name=B)",
          "success=False 且提示同名", r.get("success") is False and "同名" in str(r.get("error")),
          f"error={r.get('error')}")

        r = await execute("question_manage", {"action": "delete_many", "bank_id": bid, "question_indexes": [1, 3]})
        T("B7", "批量删题", "按题号批量删 1、3",
          f"bankId={bid}", "execute question_manage.delete_many", "deleted=2 bankTotal=2",
          r.get("deleted") == 2 and r.get("bankTotal") == 2,
          f"deleted={r.get('deleted')} total={r.get('bankTotal')}")

        # v1 契约（2026-09-21）改了这里的口径：`confirmed` 保留但**不再是充分条件** ——
        # 破坏性操作必须带服务端签发的 `confirmTicket`。所以这一条现在验**两遍**：
        #   · confirmed=False（老口径的「没确认」）→ 必须被拒；
        #   · confirmed=True（**旧实现的漏洞口径**：前端无条件填 true）→ 也必须被拒。
        # 两条一起断言才算锁住「票据才是授权」，只验前者的话「前端填 true 就能删」依然成立。
        #
        # ⚠️ 用**专用题库**（不是 BANK_A）：修复前 `confirmed=true` 会**真的把它删掉**，
        #    拿 BANK_A 当靶子的话 B9/B10 会因为「题库已经没了」而连带失败 ——
        #    那样红的**原因**就被说错了（看着像 clear_questions 坏了）。专用靶子还把
        #    「无副作用」也验了（旧实现下这一条正是红的：库里真的少了一个题库）。
        B8_BANK = PREFIX + "B8票"
        await execute("bank_manage", {"action": "create", "bank_name": B8_BANK})
        r_false = await execute_raw(
            "bank_manage", {"action": "delete_by_name", "bank_name": B8_BANK}, confirmed=False)
        r_true = await execute_raw(
            "bank_manage", {"action": "delete_by_name", "bank_name": B8_BANK}, confirmed=True)
        b8_left = [
            b.get("bankName")
            for b in ((await execute("bank_manage",
                                     {"action": "list", "bank_name": B8_BANK})).get("banks") or [])
        ]
        T("B8", "二次确认", "破坏性操作不带确认票据 → 被拦下且无副作用（confirmed=false/true 都拦）",
          f"专用靶子题库 {B8_BANK}（此后 B9/B10 用的是 BANK_A/BANK_B，不受本用例影响）",
          "execute bank_manage.delete_by_name ×2（不带 confirmTicket，confirmed 分别 false/true）"
          " → 再按名查该题库",
          "两条都 success=False 且 needsConfirm=True（票据缺失时仍给这个键，前端据此继续弹卡片）；"
          f"「{B8_BANK}」**仍然存在**（无副作用）",
          r_false.get("success") is False and r_false.get("needsConfirm") is True
          and r_true.get("success") is False and r_true.get("needsConfirm") is True
          and b8_left == [B8_BANK],
          f"confirmed=false: success={r_false.get('success')} "
          f"needsConfirm={r_false.get('needsConfirm')}；"
          f"confirmed=true: success={r_true.get('success')} "
          f"needsConfirm={r_true.get('needsConfirm')}；仍在={b8_left}")

        r = await execute("question_manage", {"action": "clear_questions", "bank_id": bid})
        T("B9", "清空题库", "clear_questions 清空题目（题库保留）",
          f"bankId={bid} 原有 2 题", "execute question_manage.clear_questions", "bankTotal=0",
          r.get("bankTotal") == 0, f"bankTotal={r.get('bankTotal')}")

        r = await execute("bank_manage", {"action": "delete_many", "bank_names": [BANK_A, BANK_B]})
        T("B10", "批量删库", "delete_many 按名批量删两个题库",
          f"{BANK_A}/{BANK_B}", "execute bank_manage.delete_many", "deleted=2",
          len(r.get("deleted") or []) == 2, f"deleted={len(r.get('deleted') or [])}")

        # ================= C. api 付费循环 /ai/agent/stream =================
        sid1 = f"asst_e2e_{int(time.time() * 1000)}_a"
        _SESSION_IDS.append(sid1)
        script_tool_then_reply("bank_manage", {"action": "create", "bank_name": BANK_C},
                               f"已创建题库「{BANK_C}」。")
        ev = await run_stream({
            "message": "帮我建一个题库", "sessionId": sid1, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        })
        ts = types_of(ev)
        T("C1", "api 付费循环", "一轮 create + 最终回复，事件序列完整",
          f"sessionId={sid1}", "POST /ai/agent/stream",
          "含 waiting/tool_start/tool_result/text/done 且以 done 收尾",
          all(t in ts for t in ("meta", "waiting", "tool_start", "tool_result", "text", "done"))
          and ts[-1] == "done", f"types={ts}")

        r = await execute("bank_manage", {"action": "list", "bank_name": BANK_C})
        T("C2", "api 付费循环", "工具真的执行了（题库建出来了）",
          f"{BANK_C}", "execute bank_manage.list", "能查到该题库",
          any(b.get("bankName") == BANK_C for b in (r.get("banks") or [])),
          f"banks={[b.get('bankName') for b in (r.get('banks') or [])]}")

        r = await client.get(f"/ai/conversation/{sid1}", params={"userId": uid})
        msgs = (r.json() or {}).get("data") or []
        roles = [m.get("role") for m in msgs]
        T("C3", "会话落库", "api 链路自动落库「提问 + 回复」",
          f"sessionId={sid1}", f"GET /ai/conversation/{sid1}", "角色含 user 与 assistant",
          "user" in roles and "assistant" in roles, f"roles={roles}")

        r = await client.get("/ai/sessions", params={"userId": uid})
        sids = [s.get("sessionId") for s in ((r.json() or {}).get("data") or [])]
        T("C4", "会话列表", "新会话出现在 /ai/sessions",
          f"sessionId={sid1}", "GET /ai/sessions", "列表含该会话",
          sid1 in sids, f"count={len(sids)}")

        # 破坏性：同意
        script_tool_then_reply("bank_manage", {"action": "delete_by_name", "bank_name": BANK_C},
                               "已按要求删除该题库。")
        ev = await run_stream({
            "message": f"删掉 {BANK_C}", "sessionId": sid1, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        }, approve=True)
        ts = types_of(ev)
        r = await execute("bank_manage", {"action": "list", "bank_name": BANK_C})
        gone = not any(b.get("bankName") == BANK_C for b in (r.get("banks") or []))
        T("C5", "二次确认(api)", "下发 tool_confirm → 调 /ai/agent/confirm 同意 → 真的删掉",
          f"{BANK_C} 存在", "stream(delete) + POST /ai/agent/confirm(true)",
          "事件含 tool_confirm/tool_confirm_resolved，且题库已删",
          "tool_confirm" in ts and "tool_confirm_resolved" in ts and gone,
          f"types={ts} gone={gone}")

        # 破坏性：取消
        await execute("bank_manage", {"action": "create", "bank_name": BANK_C})
        sid2 = f"asst_e2e_{int(time.time() * 1000)}_b"
        _SESSION_IDS.append(sid2)
        script_tool_then_reply("bank_manage", {"action": "delete_by_name", "bank_name": BANK_C},
                               "好的，那就不删了。")
        ev = await run_stream({
            "message": f"删掉 {BANK_C}", "sessionId": sid2, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        }, approve=False)
        r = await execute("bank_manage", {"action": "list", "bank_name": BANK_C})
        still = any(b.get("bankName") == BANK_C for b in (r.get("banks") or []))
        cancelled = any(e.get("type") == "tool_result" and "取消" in str(e.get("message")) for e in ev)
        T("C6", "二次确认(api)", "取消 → 不执行且回灌「用户已取消」",
          f"{BANK_C} 存在", "stream(delete) + POST /ai/agent/confirm(false)",
          "题库仍在 + 事件里有取消提示", still and cancelled,
          f"still={still} cancelled={cancelled}")

        # ================= D. 时间线快照 =================
        payload = [
            {"role": "user", "content": "我有什么题库"},
            {"role": "assistant", "type": "tool_result", "tool": "bank_manage",
             "action": "list", "status": "ok", "content": "查到 1 个题库",
             "params": {"action": "list"}, "data": {"success": True, "count": 1}},
            {"role": "assistant", "content": "你有 1 个题库。"},
        ]
        r = await client.put(f"/ai/conversation/{sid2}/agent-timeline",
                             json={"messages": payload}, params={"userId": uid})
        r = await client.get(f"/ai/conversation/{sid2}/agent-timeline", params={"userId": uid})
        got = ((r.json() or {}).get("data") or {}).get("messages") or []
        card_ok = len(got) == 3 and (got[1] or {}).get("type") == "tool_result" \
            and (got[1] or {}).get("status") == "ok"
        T("D1", "时间线快照", "PUT/GET agent-timeline round-trip（含卡片字段）",
          f"sessionId={sid2}", "PUT 再 GET", "3 条且卡片字段完整",
          card_ok, f"len={len(got)} card={(got[1] if len(got) > 1 else None)}")

        r = await client.get("/ai/conversation/asst_e2e_not_exist/agent-timeline", params={"userId": uid})
        got2 = ((r.json() or {}).get("data") or {}).get("messages")
        T("D2", "时间线快照", "没有快照时返回空数组（前端据此回退普通消息）",
          "不存在的会话", "GET agent-timeline", "messages == []",
          got2 == [], f"got={got2}")

        # ============ E. 回灌给模型的压缩结果必须保留「定位字段」============
        # 背景：模型看到的**不是** tool_result 的 data，而是 `guard.compress_result`
        # 的输出。早期它把 list / search 压成一串题干（`summary: "题干1；题干2…"`），
        # `questionId` / `sortOrder` 全丢 —— 于是模型遇到「删掉某某那道题」拿不到 ID，
        # 只能 search → list → list 一路翻，最后放弃并回头问用户。
        r = await execute("bank_manage", {"action": "create", "bank_name": BANK_E})
        # ⚠️ create 的结果把题库嵌在 `bank` 里（见 B1），不是顶层 bankId
        bank_e = (r.get("bank") or {}).get("bankId")
        qs_e = json.dumps([
            {"questionType": 1, "questionText": "E2E-E1 专有标记词", "options": ["A", "B"], "answer": "0"},
            {"questionType": 1, "questionText": "E2E-E2 干扰项", "options": ["A", "B"], "answer": "1"},
        ], ensure_ascii=False)
        await execute("question_manage",
                      {"action": "batch_import", "bank_id": bank_e, "questions": qs_e})

        SEEN_ROUNDS.clear()
        script_tool_then_reply(
            "question_manage",
            {"action": "search", "bank_id": bank_e, "question_text": "专有标记词"},
            "找到了。",
        )
        await run_stream({
            "message": "删掉专有标记词那道题", "sessionId": sid2, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        })
        # 第 0 轮是用户消息；工具结果是第 1 轮带上来的
        fed = "\n".join(str(getattr(m, "content", ""))
                        for rnd in SEEN_ROUNDS[1:] for m in rnd)
        T("E1", "压缩保 ID", "search 回灌给模型的结果里带 questionId / questionIndex",
          f"bankId={bank_e}", "scripted LLM 收到的 messages",
          "含 questionId 与 questionIndex（以及 total / hasMore）",
          all(k in fed for k in ('"questionId"', '"questionIndex"', '"total"', '"hasMore"')),
          "命中 " + ",".join(k for k in ('"questionId"', '"questionIndex"', '"total"', '"hasMore"') if k in fed))

        # 只有「拿到的 ID 真的能用」才算修好了 —— 用回灌里的 ID 去删
        m_id = re.search(r'"questionId":\s*(\d+)', fed)
        qid_e = int(m_id.group(1)) if m_id else 0
        r = await execute("question_manage",
                          {"action": "delete", "bank_id": bank_e, "question_id": qid_e})
        T("E2", "压缩保 ID", "用回灌里的 questionId 能真的删掉那道题",
          f"questionId={qid_e}", f"execute question_manage.delete(question_id={qid_e})",
          "success=True 且题库只剩 1 题",
          bool(r.get("success")) and r.get("bankTotal") == 1,
          f"success={r.get('success')} bankTotal={r.get('bankTotal')}")

        await execute("bank_manage", {"action": "delete", "bank_id": bank_e})

        # ================= I. L1 自动注入（记忆 → 系统提示词）=================
        # 断言契约：SystemMessage 里注入的记忆块，**必须等于** `build_memory_context`
        # 的产物。不要断言「刚建的题库名出现在里面」—— 注入只有 5 个名额、按
        # importance DESC 排，而本脚本跑过的删除动作 importance=8 会把新建的 7 挤掉，
        # 那种断言测的是「排序碰巧如何」而不是「注入了没有」。
        SEEN_ROUNDS.clear()
        script_tool_then_reply("bank_manage", {"action": "list"}, "好的。")
        await run_stream({
            "message": "我有哪些题库", "sessionId": sid2, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        })
        sys_text = str(getattr(SEEN_ROUNDS[0][0], "content", "")) if SEEN_ROUNDS else ""
        human_text = "\n".join(
            str(getattr(m, "content", ""))
            for m in (SEEN_ROUNDS[0][1:] if SEEN_ROUNDS else [])
        )

        from app.services.ai import memory_service
        from app.services.ai.agent import runtime_context

        async with async_session_factory() as cdb:
            expected = await memory_service.build_memory_context(
                cdb, uid, limit=runtime_context.MEMORY_LIMIT, lang="en"
            )
        T("I1", "L1 注入", "长期记忆摘要被注入 SystemMessage，内容与 build_memory_context 一致",
          "前序用例的写操作已触发 memory_hook 落记忆", "scripted LLM 第 0 轮收到的 SystemMessage",
          "SystemMessage 含 <user_memory> 块，且该块与 build_memory_context 的产物逐字一致",
          bool(expected) and "<user_memory>" in sys_text and expected in sys_text,
          f"期望块 {len(expected)} 字，注入命中={expected in sys_text if expected else False}")

        T("I2", "L1 注入", "注入的背景**只进 SystemMessage**，不混进用户消息",
          "同上", "对比 SystemMessage 与 HumanMessage",
          "HumanMessage 不含该记忆块",
          bool(expected) and expected not in human_text and "<user_memory>" not in human_text,
          f"human 含记忆块={expected in human_text if expected else 'n/a'}")

        # ds-free 链路要**自己拉**这段背景（它的提示词在前端拼），所以必须有个下发口子。
        # 这条锁住「前端能拿到与 api 链路同一份文本」—— 少了它两条链路上下文就漂移。
        r = await client.get("/ai/agent/context")
        body = r.json() or {}
        dl_ctx = body.get("context") if isinstance(body, dict) else None
        T("I3", "L1 注入", "GET /ai/agent/context 把同一份运行时背景下发给 ds-free",
          "已登录", "GET /ai/agent/context",
          "返回的 context 与 build_memory_context 的产物一致",
          isinstance(dl_ctx, str) and bool(expected) and expected in dl_ctx,
          f"len={len(dl_ctx) if isinstance(dl_ctx, str) else 'n/a'} "
          f"命中={expected in dl_ctx if isinstance(dl_ctx, str) and expected else False}")

        auth_off()
        r = await client.get("/ai/agent/context")
        body = r.json() if isinstance(r.json(), dict) else {}
        T("I4", "L1 注入", "未登录拿不到运行时背景（记忆是隐私）",
          "移除登录依赖覆盖后不带 token", "GET /ai/agent/context",
          "HTTP 401/403 或 body.code=401/403",
          r.status_code in (401, 403) or body.get("code") in (401, 403),
          f"status={r.status_code} code={body.get('code')}")
        auth_on()

        # 知识库清单同理：先建一个库，下一轮提示词里就该出现 <knowledge_bases>
        _kb_id = None
        try:
            from app.services.rag import rag_write_service as _rws
            async with async_session_factory() as cdb:
                _kb = await _rws.create_knowledge_base(
                    cdb, uid, name=f"{PREFIX}L1知识库", description="L1 注入用例"
                )
                _kb_id = _kb.id
            SEEN_ROUNDS.clear()
            script_tool_then_reply("bank_manage", {"action": "list"}, "好的。")
            await run_stream({
                "message": "我有哪些题库", "sessionId": sid2, "userId": uid,
                "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
            })
            sys_text2 = str(getattr(SEEN_ROUNDS[0][0], "content", "")) if SEEN_ROUNDS else ""
            T("I5", "L1 注入", "知识库清单被注入 SystemMessage（含 kbId，模型才能按库检索）",
              f"建知识库 {PREFIX}L1知识库（kbId={_kb_id}）", "scripted LLM 第 0 轮收到的 SystemMessage",
              "SystemMessage 含 <knowledge_bases> 与 [kbId=...] 与库名",
              "<knowledge_bases>" in sys_text2 and f"[kbId={_kb_id}]" in sys_text2
              and f"{PREFIX}L1知识库" in sys_text2,
              f"含<knowledge_bases>={'<knowledge_bases>' in sys_text2} "
              f"含kbId={f'[kbId={_kb_id}]' in sys_text2}")
        finally:
            # 逻辑删还不够 —— 必须物理删，否则 del_flag='2' 残骸会一直留着
            # （检索按 del_flag='0' 过滤，逻辑删的行检索不到，但它是实打实的垃圾数据）
            if _kb_id is not None:
                try:
                    async with async_session_factory() as cdb:
                        await cdb.execute(
                            text("DELETE FROM rag_knowledge_base WHERE id = :i"), {"i": _kb_id}
                        )
                        await cdb.commit()
                except Exception:  # noqa: BLE001
                    pass

        # ---- I6–I10：短期会话历史下发（ds-free 拿不到「本会话历史」的补丁）----
        # 背景：ds-free 的循环跑在前端，历史全靠 DS 网页自己的记忆 —— 那份记忆**不属于**
        # 任何一个 OpenStudy 会话（换会话不切、新会话不清），所以它完全看不到本会话的
        # 上下文。api 链路的历史注入点在 `loop.run_agent_stream`（`build_context_prompt`，
        # lang="en" → `<conversation_history>`）。要让两条链路历史口径一致，ds-free 必须
        # 拿到**同一份文本**，不能自己另拼一份。
        from app.services.ai import conversation_service as _conv2

        expected_hist = await _conv2.build_context_prompt(uid, sid2, lang="en")
        r = await client.get("/ai/agent/context", params={"sessionId": sid2})
        body = r.json() if isinstance(r.json(), dict) else {}
        hist = body.get("history")
        T("I6", "L1 注入", "带 sessionId 时下发该会话的短期历史（与 api 链路同一份文本）",
          f"sid2={sid2} 已跑过几轮问答（历史在库）",
          f"GET /ai/agent/context?sessionId={sid2}",
          "history 是 build_context_prompt(uid, sid2, lang='en') 的**原样产物**；"
          "非空且含 <conversation_history> 与用户提问原文",
          isinstance(hist, str) and bool(expected_hist) and hist == expected_hist
          and "<conversation_history>" in hist and "我有哪些题库" in hist,
          f"len={len(hist) if isinstance(hist, str) else 'n/a'} "
          f"逐字等于build_context_prompt={hist == expected_hist if isinstance(hist, str) else False}")

        # 不传 sessionId：必须给**空串**而不是缺字段 —— 前端（`fetchAgentContext`）判的是
        # `typeof data.context === 'string'`，缺字段会一路拼成 undefined 塞进提示词。
        # 同时锁住「context 字段一个字都不能变」：与上一条（带 sessionId）的 context
        # 逐字相同（两次调用之间没有任何写操作）。
        r = await client.get("/ai/agent/context")
        b2 = r.json() if isinstance(r.json(), dict) else {}
        ctx_no_sid = b2.get("context")
        T("I7", "L1 注入", "不传 sessionId → history 是空串，且 context 行为一个字没变",
          "紧接着上一条再调一次（中间无写操作，context 应当逐字相同）",
          "GET /ai/agent/context（不带 sessionId）",
          "history == ''；context 与带 sessionId 那次完全相同、仍非空",
          b2.get("history") == "" and isinstance(ctx_no_sid, str) and bool(ctx_no_sid)
          and ctx_no_sid == body.get("context"),
          f"history={b2.get('history')!r} "
          f"context相同={ctx_no_sid == body.get('context')} len={len(ctx_no_sid) if isinstance(ctx_no_sid, str) else 'n/a'}")

        # 越权红线：会话历史是私密数据 —— 拿到**别人的** sessionId 必须读不出他的历史。
        # 位置放在 I 组（G 组的 `auth_as` 定义在后面，这里直接换依赖覆盖）。
        async with async_session_factory() as cdb:
            uid_other = await cdb.scalar(
                text("SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1"),
                {"u": uid},
            )
        if uid_other:
            app.dependency_overrides[get_current_user] = lambda: {
                "user_id": uid_other, "userName": "e2e-agent",
            }
            try:
                r = await client.get("/ai/agent/context", params={"sessionId": sid2})
            finally:
                auth_on()  # 无论成败都要恢复登录态，否则后续用例都会被带偏
            b3 = r.json() if isinstance(r.json(), dict) else {}
            h3 = b3.get("history")
            T("I8", "越权防护", "拿别人的 sessionId 读不到他的历史（空串，且不报 500）",
              f"sid2={sid2} 属于 uid={uid}；以 uid={uid_other} 的登录态请求",
              f"GET /ai/agent/context?sessionId={sid2}",
              "HTTP 200 且 history == ''，不含对方的提问文本",
              r.status_code == 200 and h3 == "" and "我有哪些题库" not in str(h3),
              f"status={r.status_code} history={h3!r}")
        else:
            T("I8", "越权防护", "拿别人的 sessionId 读不到他的历史", "-", "-",
              "库里只有一个用户，跳过", False, "skip")

        # 未登录同理（沿用 I4 的口径）：连 sessionId 都不该被受理
        auth_off()
        r = await client.get("/ai/agent/context", params={"sessionId": sid2})
        b4 = r.json() if isinstance(r.json(), dict) else {}
        T("I9", "越权防护", "未登录不得凭 sessionId 拉历史（沿用 I4 口径）",
          "移除登录依赖覆盖后不带 token", f"GET /ai/agent/context?sessionId={sid2}",
          "HTTP 401/403 或 body.code=401/403",
          r.status_code in (401, 403) or b4.get("code") in (401, 403),
          f"status={r.status_code} code={b4.get('code')}")
        auth_on()

        # 失败**退化成空串、绝不抛**：历史下发是增强项，查库挂了不该让这次请求变 500。
        # 把 `build_context_prompt` 换成会抛的桩，验证端点里那个兜底分支真的在。
        # 注意补丁打在**模块对象**上：`app/api/v1/ai.py` 是 `from … import conversation_service`
        # 拿到的同一个模块实例，所以改属性就能生效（见 `_own_session_history`）。
        _boom_called = []

        async def _boom(*_a, **_kw):
            _boom_called.append(1)
            raise RuntimeError("模拟历史查询失败")

        _saved_bcp = _conv2.build_context_prompt
        try:
            _conv2.build_context_prompt = _boom
            r = await client.get("/ai/agent/context", params={"sessionId": sid2})
            b5 = r.json() if isinstance(r.json(), dict) else {}
        finally:
            _conv2.build_context_prompt = _saved_bcp
        T("I10", "L1 注入", "历史查询失败时退化成空串（HTTP 200，不抛、不影响 context）",
          "把 conversation_service.build_context_prompt 换成会抛的桩",
          f"GET /ai/agent/context?sessionId={sid2}",
          "桩确实被调到；HTTP 200 且 history == ''；context 照常非空",
          bool(_boom_called) and r.status_code == 200 and b5.get("history") == ""
          and bool(b5.get("context")),
          f"桩调用={len(_boom_called)} status={r.status_code} "
          f"history={b5.get('history')!r} context非空={bool(b5.get('context'))}")

        # ---- I11–I17：ds-free 走 **HTTP** 跑检索工具的护栏 ----
        # 缺口背景：ds-free 的检索走 `POST /ai/agent/execute`（前端循环 → 该接口 → 工具注册表），
        # 但此前**没有一条用例走过这条 HTTP 路径** —— `test_agent_rag_tools.py` 是
        # `registry.get(...)` **直调工具对象**（绕过 HTTP 层、绕过 `_execute_tool` 的 SAVEPOINT
        # 与 `memory_hook` 收口），本文件只在 A1 查了工具**清单**。
        # 也就是说这条链路回归了没人会红；这组用例就是补上它。
        #
        # 夹具：真建库 + 真写文档 + **真向量化**（与生产同一条 `embed_texts`）。
        # 名字带 PREFIX 标记**且带时间戳**：上一次跑崩留下的同名残骸不会撞 `RagConflict`。
        # ⚠️ 库里还有用户的**真实**知识库数据，所以收尾只按**自己拿到的 id** 精确物理删。
        from app.services.rag import rag_write_service as _rws9

        _kb9_name = f"{PREFIX}检索护栏{int(time.time() * 1000)}"
        # 夹具文档里埋一个**只有本文档有**的标记词：不限定 kb_ids 检索时（默认搜全部库），
        # 别的库（例如 `test_rag_pg.py` 的 `__rag_pg_test__*`）也会有「数据结构」类内容，
        # 用标记词才能保证「命中确实来自我建的库」这条断言是确定的。
        _tok9 = f"{PREFIX}独有标记词{int(time.time() * 1000)}"
        _doc9_text = (
            f"# 二叉搜索树（{PREFIX} 检索护栏夹具）\n\n"
            f"本段带有独占标记词 {_tok9}，只有本用例造的文档里才有它。\n"
            "二叉搜索树是一种有序的二叉树：左子树所有节点的值都小于根节点，右子树都大于根节点。\n"
            "查找、插入、删除的平均时间复杂度都是 O(log n)，最坏情况退化成链表变成 O(n)。\n"
            "红黑树与 AVL 树是它的自平衡变体，用来保证最坏情况下的对数复杂度。\n"
        )
        _kb9_id = None
        _mem9_id = None
        try:
            async with async_session_factory() as cdb:
                _kb9 = await _rws9.create_knowledge_base(
                    cdb, uid, _kb9_name, description="I11–I17 检索护栏夹具"
                )
                _kb9_id = _kb9.id
                _RAG_FIXTURE_KB_IDS.append(_kb9_id)
                _doc9 = await _rws9.create_document(
                    cdb, uid, _kb9_id,
                    file_name=f"{PREFIX}护栏数据结构.txt",
                    raw_content=_doc9_text, file_type="txt",
                )
                from app.services.rag.chunker import chunk_text as _chunk9
                from app.services.rag.embedding import embed_texts as _embed9

                _contents9 = [ck.content for ck in _chunk9(_doc9_text)]
                # 真向量化（SiliconFlow）：这一步挂了说明环境不可用，用例应当显式失败而不是空跑
                _vecs9 = await _embed9(_contents9)
                await _rws9.replace_chunks(cdb, _doc9, _contents9, _vecs9)

            # 一条**带标记**的记忆：memory_search 的正向命中要有东西可命中，
            # 而它自己是只读工具、不会产生记忆。收尾按精确 id 删（cleanup 里还有标记网兜底）。
            from app.services.ai import memory_service as _mem9

            _mem9_token = f"{PREFIX}护栏记忆标记{int(time.time() * 1000)}"
            async with async_session_factory() as cdb:
                _mem9_row = await _mem9.save_memory(
                    cdb, uid, f"{_mem9_token} 用于验证 ds-free 链路能检索到历史记忆"
                )
                _mem9_id = _mem9_row.id

            # --- I11：knowledge_search.list（HTTP）---
            r = await execute("knowledge_search", {"action": "list"})
            _kbs9 = r.get("knowledgeBases") or []
            T("I11", "ds-free 检索护栏", "HTTP 跑 knowledge_search.list：返回形状 + 中文回执",
              f"已真建库 {_kb9_name}（kbId={_kb9_id}）",
              "POST /ai/agent/execute {tool: knowledge_search, params: {action: list}}",
              "success=True；count == len(knowledgeBases)；列表含自己建的 kbId；"
              "message 是中文「你有 N 个知识库」",
              bool(r.get("success")) and isinstance(_kbs9, list)
              and r.get("count") == len(_kbs9)
              and any(k.get("kbId") == _kb9_id for k in _kbs9)
              and str(r.get("message") or "").startswith("你有"),
              f"count={r.get('count')} 含自己建库="
              f"{any(k.get('kbId') == _kb9_id for k in _kbs9)} message={r.get('message')}")

            # --- I12：knowledge_search.search（HTTP，真向量化后要能检索到）---
            # ⚠️ 这里**限定 kb_ids** 检索：不带 kb_ids 时工具会搜**该用户的全部知识库**
            #    （见 `resolve_knowledge_bases`），而库里还有别的测试夹具库与用户真实库
            #    （例如 `__rag_pg_test__*`、用户 105 的「数据结构」）—— 那种情况下
            #    「每条命中的 kbId 都是我建的库」这条断言本来就不成立（不是实现问题，是断言写错）。
            #    搜全部库的行为由 I18 单独覆盖。
            r = await execute(
                "knowledge_search",
                {"action": "search", "query": "二叉搜索树的时间复杂度", "kb_ids": [_kb9_id]},
            )
            _hits9 = r.get("hits") or []
            _loc9_ok = bool(_hits9) and all(
                h.get("chunkId") is not None and h.get("docId") is not None
                and h.get("chunkIndex") is not None and bool(h.get("source"))
                and h.get("kbId") == _kb9_id
                for h in _hits9
            )
            T("I12", "ds-free 检索护栏",
              "HTTP 跑 knowledge_search.search（限定 kb_ids）：真向量化后能检索到 + 定位字段齐",
              "真建库 + 真写文档 + 真 embedding，kb_ids 限定到自己建的库",
              "POST /ai/agent/execute {tool: knowledge_search, params: {action: search, "
              "query: 二叉搜索树的时间复杂度, kb_ids: [<自己建的>]}}",
              "success=True；count>0；每条命中都来自该库且带 source / chunkId / docId / "
              "chunkIndex / kbId；正文含「二叉搜索树」",
              bool(r.get("success")) and (r.get("count") or 0) > 0 and _loc9_ok
              and any("二叉搜索树" in (h.get("content") or "") for h in _hits9),
              f"count={r.get('count')} 定位字段齐={_loc9_ok} "
              f"首条={str({k: _hits9[0].get(k) for k in ('chunkId', 'docId', 'chunkIndex', 'kbId', 'source')})[:130] if _hits9 else 'n/a'}")

            # --- I13：kbId 不存在/不属于自己 → fail 信封 + hint（自纠依据）---
            r = await execute(
                "knowledge_search",
                {"action": "search", "query": "二叉搜索树", "kb_ids": [99999999]},
            )
            T("I13", "ds-free 检索护栏", "kbId 不存在/不属于自己 → fail 信封 + hint",
              "kb_ids=[99999999]（不存在）",
              "POST /ai/agent/execute knowledge_search.search",
              "success=False；有 error；hint 指向 action=list（模型据此自纠，而不是原地重试）",
              r.get("success") is False and bool(r.get("error"))
              and "list" in str(r.get("hint")),
              f"error={r.get('error')} hint={r.get('hint')}")

            # --- I14：缺 query → fail 信封 + hint ---
            r = await execute("knowledge_search", {"action": "search"})
            T("I14", "ds-free 检索护栏", "search 缺 query → fail 信封 + hint",
              "不传 query", "POST /ai/agent/execute knowledge_search.search",
              "success=False；error 提到 query；hint 非空",
              r.get("success") is False and "query" in str(r.get("error"))
              and bool(r.get("hint")),
              f"error={r.get('error')} hint={r.get('hint')}")

            # --- I15：memory_search.list（HTTP）---
            r = await execute("memory_search", {"action": "list", "limit": 5})
            _mems9 = r.get("memories") or []
            _mshape9_ok = bool(_mems9) and all(
                m.get("memoryId") is not None and bool(m.get("memoryType"))
                and bool(m.get("content")) and m.get("importance") is not None
                and "createTime" in m
                for m in _mems9
            )
            T("I15", "ds-free 检索护栏",
              "HTTP 跑 memory_search.list：返回形状 + limit 生效 + 中文回执",
              "用户已有历史记忆（含本用例刚写的那条标记记忆）",
              "POST /ai/agent/execute {tool: memory_search, params: {action: list, limit: 5}}",
              "success=True；count == len(memories) 且 ≤ limit；每条含 memoryId / memoryType / "
              "content / importance / createTime；message 是中文「找到 N 条历史记忆」",
              bool(r.get("success")) and _mshape9_ok
              and r.get("count") == len(_mems9) and len(_mems9) <= 5
              and "条历史记忆" in str(r.get("message")),
              f"count={r.get('count')} 形状齐={_mshape9_ok} message={r.get('message')}")

            # --- I16：memory_search.search（HTTP，要搜得到刚写的那条标记记忆）---
            r = await execute("memory_search", {"action": "search", "query": _mem9_token})
            _found9 = r.get("memories") or []
            T("I16", "ds-free 检索护栏", "HTTP 跑 memory_search.search：能搜到指定关键词的记忆",
              f"已写入带标记记忆（memoryId={_mem9_id}，关键词 {_mem9_token}）",
              "POST /ai/agent/execute {tool: memory_search, params: {action: search, query: <标记>}}",
              "success=True；count≥1；命中内容含该关键词；中文回执里带关键词",
              bool(r.get("success")) and (r.get("count") or 0) >= 1
              and any(_mem9_token in (m.get("content") or "") for m in _found9)
              and _mem9_token in str(r.get("message")),
              f"count={r.get('count')} 命中标记="
              f"{any(_mem9_token in (m.get('content') or '') for m in _found9)} "
              f"message={r.get('message')}")

            # --- I17：只读工具**不弹二次确认**（`write_operation=False` 的实际效果）---
            # 为什么要带「对照」：只断言「只读工具没弹确认」是空跑 —— 得同时证明
            # 「autoConfirm=false 这个开关真的会拦写操作」，两条合起来才说明
            # 前端不会因为一次检索就弹卡片、也不会漏弹一次删除。
            r_ks = await execute(
                "knowledge_search", {"action": "search", "query": "二叉搜索树"},
                auto_confirm=False, confirmed=False,
            )
            r_ms = await execute(
                "memory_search", {"action": "list", "limit": 3},
                auto_confirm=False, confirmed=False,
            )
            # 对照项：写操作在同一个开关下必须被拦（用 note_manage.create 且**不传参数**，
            # 确认门挡在工具执行之前，所以不会写任何数据）。
            # ⚠️ 这里刻意用 `execute_raw`（**不带票据**）：v1 契约下
            #    「autoConfirm=false 的写操作」属于「需要确认」，缺票据就该被拦门挡住。
            #    换回 `execute` 的话会自动取票，这条就变成在验「带票能创建」—— 测错东西了。
            r_wr = await execute_raw(
                "note_manage", {"action": "create"},
                auto_confirm=False, confirmed=False,
            )
            T("I17", "ds-free 检索护栏",
              "只读工具在 autoConfirm=false 下也不弹确认（对照：写操作会被拦）",
              "三个调用都带 autoConfirm=false 且 confirmed=false",
              "execute knowledge_search.search / memory_search.list / note_manage.create",
              "两个只读工具 success=True 且无 needsConfirm；写操作 success=False 且 "
              "needsConfirm=True（证明这个开关真的在拦，用例不是空跑）",
              r_ks.get("success") is True and "needsConfirm" not in r_ks
              and r_ms.get("success") is True and "needsConfirm" not in r_ms
              and r_wr.get("success") is False and r_wr.get("needsConfirm") is True,
              f"knowledge_search={r_ks.get('success')} needsConfirm={'needsConfirm' in r_ks} "
              f"memory_search={r_ms.get('success')} "
              f"写操作={r_wr.get('success')} needsConfirm={r_wr.get('needsConfirm')}")

            # --- I18：**不带 kb_ids** 的检索 = 搜该用户的全部知识库（默认行为）---
            # 与 I12 是两条不同的路径：I12 只看自己那个库，I18 覆盖「跨库检索」。
            # 用夹具里的**独占标记词**提问，保证命中来自我建的库，不受其它夹具库/真实库影响。
            r = await execute("knowledge_search", {"action": "search", "query": _tok9})
            _hits18 = r.get("hits") or []
            _loc18_ok = bool(_hits18) and all(
                h.get("chunkId") is not None and h.get("docId") is not None
                and h.get("chunkIndex") is not None and bool(h.get("source"))
                and h.get("kbId") is not None
                for h in _hits18
            )
            T("I18", "ds-free 检索护栏",
              "HTTP 跑 knowledge_search.search（不带 kb_ids）：跨全部知识库检索",
              f"用夹具独占标记词 {_tok9} 提问（只有本用例造的文档含它）",
              "POST /ai/agent/execute {tool: knowledge_search, params: {action: search, query: <独占标记词>}}",
              "success=True；count≥1 且至少一条命中来自自己建的库、内容含标记词；"
              "每条命中都带定位字段；knowledgeBases 列出本次检索范围；note 非空",
              bool(r.get("success")) and (r.get("count") or 0) >= 1
              and any(_tok9 in (h.get("content") or "") and h.get("kbId") == _kb9_id
                      for h in _hits18)
              and _loc18_ok and bool(r.get("knowledgeBases")) and bool(r.get("note")),
              f"count={r.get('count')} 命中标记="
              f"{any(_tok9 in (h.get('content') or '') for h in _hits18)} 定位字段齐={_loc18_ok} "
              f"knowledgeBases={len(r.get('knowledgeBases') or [])} note={'非空' if r.get('note') else '空'}")
        finally:
            # 精确物理删自己造的夹具（外键顺序：qa → chunk → doc → kb）。
            # 不要用 `delete_knowledge_base()`（那是逻辑删，会留 del_flag='2' 残骸）。
            if _kb9_id is not None:
                try:
                    async with async_session_factory() as cdb:
                        for stmt in (
                            "DELETE FROM rag_qa_record WHERE kb_id = :k",
                            "DELETE FROM rag_document_chunk WHERE kb_id = :k",
                            "DELETE FROM rag_document WHERE kb_id = :k",
                            "DELETE FROM rag_knowledge_base WHERE id = :k",
                        ):
                            await cdb.execute(text(stmt), {"k": _kb9_id})
                        await cdb.commit()
                except Exception:  # noqa: BLE001 - 收尾失败不该盖住用例结果
                    pass
            if _mem9_id is not None:
                try:
                    async with async_session_factory() as cdb:
                        await cdb.execute(
                            text("DELETE FROM ai_agent_memory WHERE id = :i"), {"i": _mem9_id}
                        )
                        await cdb.commit()
                except Exception:  # noqa: BLE001
                    pass

        # ================= F. 笔记（note_manage）=================
        # 背景：`note.category_id` 是 NOT NULL 且分类按用户隔离，而工具**没有**「建分类」动作
        # （分类是用户在笔记页自己建的），所以这里直接造一个测试分类当夹具。
        async with async_session_factory() as cdb:
            await cdb.execute(
                text("INSERT INTO note_category (user_id, name, order_num) VALUES (:u, :n, 99)"),
                {"u": uid, "n": NOTE_PREFIX + "分类"},
            )
            await cdb.commit()
            cat_id = await cdb.scalar(
                text("SELECT id FROM note_category WHERE user_id=:u AND name=:n"),
                {"u": uid, "n": NOTE_PREFIX + "分类"},
            )

        # F1 建笔记（显式分类名）
        # 正文两份都给：`markdown_content`（富文本）与 `content`（纯文本）是**各自独立**的列，
        # 只给其中一份时另一份就是 NULL —— 不是 bug，但用例要把两条都验到。
        r = await execute("note_manage", {
            "action": "create",
            "title": NOTE_PREFIX + "牛顿定律",
            "markdown_content": "# 牛顿三定律\n\n第一定律：惯性定律。",
            "content": "牛顿三定律纯文本版：惯性、F=ma、作用力与反作用力。",
            "tags": ["物理", "复习", "物理"],
            "category_name": NOTE_PREFIX + "分类",
        })
        note_id = (r.get("note") or {}).get("noteId")
        note = r.get("note") or {}
        T("F1", "笔记", "create 建笔记（落指定分类）",
          f"分类「{NOTE_PREFIX}分类」已存在", "execute note_manage.create",
          "success=True；categoryId=测试分类；tags 去重为「物理,复习」；createTime 可读（refresh 到位）",
          bool(r.get("success")) and note.get("categoryId") == cat_id
          and note.get("tags") == "物理,复习" and bool(note.get("createTime")),
          f"noteId={note_id} categoryId={note.get('categoryId')} "
          f"tags={note.get('tags')} createTime={note.get('createTime')}")

        # F2 可见性映射：笔记 1=公开（**与题库 0=公开相反**）
        r = await execute("note_manage", {
            "action": "create", "title": NOTE_PREFIX + "公开笔记",
            "content": "这是一篇公开笔记", "is_public": 1,
            "category_name": NOTE_PREFIX + "分类",
        })
        pub = r.get("note") or {}
        T("F2", "笔记", "is_public=1 → 「公开」（笔记与题库的语义相反）",
          "笔记 is_public 是 1=公开/0=私密；题库是 0=公开/1=私密",
          "execute note_manage.create(is_public=1)",
          "返回值 visibility=公开，且**不含 isPublic**（避免被前端题库枚举渲染成反的）",
          pub.get("visibility") == "公开" and "isPublic" not in pub,
          f"visibility={pub.get('visibility')} 含isPublic={'isPublic' in pub}")

        # F3 缺标题 / 缺正文都要拦下并给 hint
        r = await execute("note_manage", {"action": "create", "content": "只有正文"})
        T("F3", "笔记", "create 缺 title 被拦下并给 hint",
          "-", "execute note_manage.create(无 title)",
          "success=False 且有 hint", not r.get("success") and bool(r.get("hint")),
          f"error={r.get('error')} hint={r.get('hint')}")

        # F4 分类名写错 → 失败，且 hint 里列出真实分类名（模型据此自纠）
        r = await execute("note_manage", {
            "action": "create", "title": NOTE_PREFIX + "错分类",
            "content": "x", "category_name": "根本不存在的分类",
        })
        T("F4", "笔记", "分类名写错时 hint 列出真实分类名（自纠环能闭上）",
          "-", "execute note_manage.create(category_name=不存在)",
          f"success=False 且 hint 含「{NOTE_PREFIX}分类」",
          not r.get("success") and NOTE_PREFIX + "分类" in str(r.get("hint")),
          f"error={r.get('error')} hint={r.get('hint')}")

        # F5 按正文关键词搜到（不只标题）
        r = await execute("note_manage", {"action": "list", "keyword": "惯性定律"})
        hits = [n.get("noteId") for n in (r.get("notes") or [])]
        T("F5", "笔记", "list 能按**正文**关键词命中（不只标题）",
          f"noteId={note_id} 的正文含「惯性定律」", "execute note_manage.list(keyword=惯性定律)",
          "命中该 noteId；且返回 total",
          note_id in hits and isinstance(r.get("total"), int),
          f"hits={hits} count={r.get('count')} total={r.get('total')}")

        # F6 详情带完整正文
        r = await execute("note_manage", {"action": "detail", "note_id": note_id})
        d = r.get("note") or {}
        T("F6", "笔记", "detail 返回完整正文（markdown + 纯文本）",
          f"noteId={note_id}", "execute note_manage.detail",
          "markdownContent 与 content 都非空",
          bool(r.get("success")) and bool(d.get("markdownContent")) and bool(d.get("content")),
          f"markdown={str(d.get('markdownContent'))[:20]!r} content={str(d.get('content'))[:20]!r}")

        # F7 更新：改标题 + 状态
        r = await execute("note_manage", {
            "action": "update", "note_id": note_id,
            "title": NOTE_PREFIX + "牛顿定律-改", "status": "published",
        })
        T("F7", "笔记", "update 改标题/状态并回报 changed",
          f"noteId={note_id}", "execute note_manage.update",
          "success=True；changed 含 title、status；statusText=已发布",
          bool(r.get("success")) and {"title", "status"} <= set(r.get("changed") or [])
          and (r.get("note") or {}).get("statusText") == "已发布",
          f"changed={r.get('changed')} statusText={(r.get('note') or {}).get('statusText')}")

        # F8 数据隔离：换一个 userId 调同一接口 —— 现在应当被**越权防护拦下（HTTP 403）**，
        #    而不是靠工具自己过滤。详见 G 组（越权专项）。
        #    注：这个用例之所以能构造出来，是因为 `/ai/agent/execute` 允许请求体带 userId；
        #    加固后「带别人的 userId」会直接被 `resolve_user_scope` 拒绝。
        async with async_session_factory() as cdb:
            uid2 = await cdb.scalar(
                text("SELECT user_id FROM sys_user WHERE user_id <> :u ORDER BY user_id LIMIT 1"),
                {"u": uid},
            )
        if uid2:
            r2 = await client.post("/ai/agent/execute", json={
                "tool": "note_manage", "params": {"action": "detail", "note_id": note_id},
                "userId": uid2, "autoConfirm": True, "confirmed": True,
            })
            body2 = r2.json() or {}
            T("F8", "笔记", "换个 userId 拿不到别人的笔记（越权防护拦下）",
              f"noteId={note_id} 属于 uid={uid}", f"execute note_manage.detail(userId={uid2})",
              "HTTP 403 且 success=False",
              r2.status_code == 403 and not body2.get("success"),
              f"status={r2.status_code} success={body2.get('success')} error={body2.get('error')}")
        else:
            T("F8", "笔记", "工具按 user_id 过滤", "-", "-", "库里只有一个用户，跳过", False, "skip")

        # F9 删除是逻辑删除，且 detail 立刻查不到
        r = await execute("note_manage", {"action": "delete", "note_id": note_id})
        r2 = await execute("note_manage", {"action": "detail", "note_id": note_id})
        async with async_session_factory() as cdb:
            del_flag = await cdb.scalar(
                text("SELECT del_flag FROM note WHERE note_id=:n"), {"n": note_id}
            )
        T("F9", "笔记", "delete 是逻辑删除（del_flag=2）且随即查不到",
          f"noteId={note_id}", "execute note_manage.delete → detail → 直接查 del_flag",
          "delete 成功；detail 失败；库里 del_flag='2'",
          bool(r.get("success")) and not r2.get("success") and del_flag == "2",
          f"delete={r.get('success')} detail={r2.get('success')} del_flag={del_flag}")

        # F10 刻意没有 delete_by_name（笔记标题不唯一，按名删会删错）
        # 注意拦在**参数校验层**（schema 的 action 枚举），比进到工具里更早，
        # 所以 hint 是通用的「action 只能是 …」而不是工具自己写的那句。
        r = await execute("note_manage", {"action": "delete_by_name", "title": "任意"})
        T("F10", "笔记", "delete_by_name 被拒（笔记标题不唯一，刻意不做）",
          "-", "execute note_manage.delete_by_name",
          "success=False，且 hint 列出合法 action（含 list，供模型改道先查 id）",
          not r.get("success") and "list" in str(r.get("hint")),
          f"error={r.get('error')} hint={r.get('hint')}")

        # ================= G. 越权防护（userId 只能是自己）=================
        # 背景：这批接口原来统一写 `user_id = userId or current_user["user_id"]`，
        # 于是**任何登录用户传别人的 userId 就能以他人身份读写**（水平越权 / IDOR）。
        # 加固后统一走 `security.resolve_user_scope`。
        #
        # 本组重点验**四个响应族各自的错误形状** —— 形状搞错比不修更糟：
        #   ① /agent/execute      → HTTP 403 + `fail()` 信封（**必须带 success 字段**，
        #                           否则前端 `result.success !== false` 会判成成功，
        #                           界面上出现一张数据为空的绿色成功卡片）
        #   ② SSE 流（assistant/agent stream）→ HTTP 403（前端判 `response.ok`）
        #   ③ 会话/时间线        → HTTP 200 + body.code=403（本仓库 `error()` 的形状）

        def auth_as(user_id, roles=None):
            """把登录态临时换成指定用户（roles 可选，用来测管理员放行）"""
            who = {"user_id": user_id, "userName": "e2e-agent"}
            if roles is not None:
                who["roles"] = roles
            app.dependency_overrides[get_current_user] = lambda: dict(who)

        auth_as(uid)  # 显式声明：下面测的都是「普通用户」

        if uid2:
            # --- ① /ai/agent/execute：403 + fail 信封 ---
            r = await client.post("/ai/agent/execute", json={
                "tool": "bank_manage", "params": {"action": "list"},
                "userId": uid2, "autoConfirm": True, "confirmed": True,
            })
            b = r.json() or {}
            T("G1", "越权防护", "execute 传别人 userId → 403 且是 fail 信封（带 success，不会被判成成功）",
              f"登录 uid={uid}，请求体 userId={uid2}", "POST /ai/agent/execute",
              "HTTP 403；body.success 是 **False**（不是缺字段）；body 有 error",
              r.status_code == 403 and b.get("success") is False and bool(b.get("error")),
              f"status={r.status_code} success={b.get('success')!r} error={b.get('error')}")

            # --- ② SSE 流：HTTP 403 ---
            r = await client.post("/ai/agent/stream", json={
                "message": "越权探测", "userId": uid2,
            })
            T("G2", "越权防护", "agent/stream 传别人 userId → HTTP 403（前端判 response.ok）",
              f"登录 uid={uid}，body userId={uid2}", "POST /ai/agent/stream",
              "HTTP 403", r.status_code == 403, f"status={r.status_code}")

            r = await client.get("/ai/assistant/stream",
                                 params={"message": "越权探测", "userId": uid2})
            T("G3", "越权防护", "assistant/stream 传别人 userId → HTTP 403",
              f"登录 uid={uid}，query userId={uid2}", "GET /ai/assistant/stream",
              "HTTP 403", r.status_code == 403, f"status={r.status_code}")

            # --- ③ 会话/时间线：HTTP 200 + body.code=403 ---
            r = await client.get("/ai/sessions", params={"userId": uid2})
            b = r.json() or {}
            T("G4", "越权防护", "GET /ai/sessions 传别人 userId → body.code=403",
              f"登录 uid={uid}，query userId={uid2}", "GET /ai/sessions",
              "HTTP 200 且 body.code=403（本仓库 error() 形状）",
              b.get("code") == 403, f"status={r.status_code} body={str(b)[:110]}")

            r = await client.get("/ai/conversation/probe-session", params={"userId": uid2})
            b = r.json() or {}
            T("G5", "越权防护", "读别人的会话历史 → body.code=403",
              f"登录 uid={uid}，query userId={uid2}", "GET /ai/conversation/{sid}",
              "HTTP 200 且 body.code=403",
              b.get("code") == 403, f"status={r.status_code} body={str(b)[:110]}")

            r = await client.delete("/ai/sessions/probe-session", params={"userId": uid2})
            b = r.json() or {}
            T("G6", "越权防护", "删别人的会话 → body.code=403",
              f"登录 uid={uid}，query userId={uid2}", "DELETE /ai/sessions/{sid}",
              "HTTP 200 且 body.code=403",
              b.get("code") == 403, f"status={r.status_code} body={str(b)[:110]}")

        # --- 不误伤：空值仍用登录态（保留原 `or` 语义），传自己放行 ---
        r = await client.get("/ai/sessions")
        b = r.json() or {}
        T("G7", "越权防护", "不传 userId → 用登录态，正常工作（不误伤）",
          f"登录 uid={uid}", "GET /ai/sessions",
          "body.code=200", b.get("code") == 200, f"body.code={b.get('code')}")

        r = await client.get("/ai/sessions", params={"userId": 0})
        b = r.json() or {}
        T("G8", "越权防护", "传 userId=0（约定表示「没指定」）→ 仍用登录态",
          f"登录 uid={uid}", "GET /ai/sessions?userId=0",
          "body.code=200（若这里 403 说明改过头了，会打断传 0 的调用方）",
          b.get("code") == 200, f"body.code={b.get('code')}")

        r = await client.get("/ai/sessions", params={"userId": uid})
        b = r.json() or {}
        T("G9", "越权防护", "传自己的 userId → 放行",
          f"登录 uid={uid}", f"GET /ai/sessions?userId={uid}",
          "body.code=200", b.get("code") == 200, f"body.code={b.get('code')}")

        # --- 管理员逃生口：加固不该把管理员一起关掉 ---
        if uid2:
            auth_as(uid, roles=["admin"])
            r = await client.get("/ai/sessions", params={"userId": uid2})
            b = r.json() or {}
            T("G10", "越权防护", "管理员传别人 userId → 放行（逃生口没被一起关掉）",
              f"roles=['admin']，登录 uid={uid}，query userId={uid2}", "GET /ai/sessions",
              "body.code=200", b.get("code") == 200, f"body.code={b.get('code')}")
            auth_as(uid)  # 恢复普通用户，免得影响收尾的 cleanup

        # ================= H. 深度思考链路 =================
        # 背景：`thinking` 事件类型一直写在 loop.py 的契约表里，但**从没被 emit 过**；
        # 而且 `build_agent_llm` 主动发 `{"thinking":{"type":"disabled"}}`，在**上游**
        # 就把 reasoning_content 掐掉了（实测 disabled→0 字 / 不传→66 字）。
        # 更隐蔽的是 langchain-openai 的白名单转换会丢弃该字段（见
        # `app/services/ai/langchain_reasoning_patch.py`），所以「后端忘了读」只是表象。
        #
        # 本组锁死四条不变量：
        #   ① 思考要能下发（否则卡片永不出现 = 用户报的 bug）
        #   ② 思考必须排在正文/工具调用**之前**（否则 UI 上会错位到答案后面）
        #   ③ 思考**不能**混进最终回答（会污染回复、还会被写进聊天记录）
        #   ④ 上游不给思考时不许报错、更不许凭空造

        def _txt(evs, t):
            return "".join(e.get("content") or "" for e in evs if e.get("type") == t)

        # --- H1：无工具的一轮，思考要下发且不混入回答 ---
        SCRIPTS.append([
            [FakeChunk("", reasoning="我先想想怎么回答。"), FakeChunk("你好！我是学习助手。")],
        ])
        ev = await run_stream({"message": "你好", "userId": uid})
        ts = types_of(ev)
        think, ans = _txt(ev, "thinking"), _txt(ev, "text")
        T("H1", "深度思考", "思考正文下发成 thinking 事件，且不混入回答",
          "假 LLM 吐 reasoning_content + 正文", "POST /ai/agent/stream",
          "含 thinking 事件；思考=「我先想想怎么回答。」；回答不含思考正文",
          "thinking" in ts and think == "我先想想怎么回答。"
          and think not in ans and ans == "你好！我是学习助手。",
          f"types={ts} thinking={think!r} answer={ans!r}")

        # --- H2：同一分片里既有思考又有正文 → 思考必须在前 ---
        SCRIPTS.append([[FakeChunk("这是正文。", reasoning="这是思考。")]])
        ev = await run_stream({"message": "同一分片", "userId": uid})
        ts = types_of(ev)
        i_t, i_x = (ts.index("thinking") if "thinking" in ts else -1), \
                   (ts.index("text") if "text" in ts else -1)
        T("H2", "深度思考", "同一分片的思考排在正文之前（否则 UI 会错位）",
          "一个分片同时带 reasoning 和 content", "POST /ai/agent/stream",
          "thinking 事件的下标 < text 事件的下标",
          0 <= i_t < i_x, f"types={ts} thinking@{i_t} text@{i_x}")

        # --- H3：工具轮 —— 每轮的思考都要在该轮正文/工具调用之前，且不污染回答 ---
        SCRIPTS.append([
            [FakeChunk("", [{"name": "bank_manage", "args": {"action": "list"}, "id": "c1"}],
                       reasoning="先查题库。")],
            [FakeChunk("查完了，你还没有题库。", reasoning="整理结果。")],
        ])
        ev = await run_stream({"message": "列出题库", "userId": uid})
        ts = types_of(ev)
        thinks = [(i, e.get("content")) for i, e in enumerate(ev) if e.get("type") == "thinking"]
        i_tool = ts.index("tool_start") if "tool_start" in ts else -1
        i_text = ts.index("text") if "text" in ts else -1
        ans = _txt(ev, "text")
        T("H3", "深度思考", "工具轮每轮都发思考，且分别早于该轮的工具调用/正文",
          "第1轮思考后调工具，第2轮思考后回复", "POST /ai/agent/stream",
          "2 个 thinking；第1个在 tool_start 前；第2个在 text 前；回答不含思考",
          len(thinks) == 2 and i_tool >= 0 and i_text >= 0
          and thinks[0][0] < i_tool and thinks[1][0] < i_text
          and "先查题库。" not in ans and "整理结果。" not in ans,
          f"thinks={thinks} tool@{i_tool} text@{i_text} answer={ans!r}")

        # --- H4：上游不返回思考 → 不报错、不凭空造 thinking ---
        SCRIPTS.append([[FakeChunk("没有思考也能回答。")]])
        ev = await run_stream({"message": "不支持思考的模型", "userId": uid})
        ts, ans = types_of(ev), _txt(ev, "text")
        errs = [e.get("message") for e in ev if e.get("type") == "error"]
        T("H4", "深度思考", "上游不支持思考时不报错、不凭空造 thinking 事件",
          "假 LLM 只吐正文、无 reasoning_content", "POST /ai/agent/stream",
          "无 thinking、无 error；回答正常返回（UI 已容忍整场没有 thinking）",
          "thinking" not in ts and not errs and ans == "没有思考也能回答。",
          f"types={ts} errors={errs} answer={ans!r}")

        # --- H5：补丁自检（含「上游结构变了要优雅降级」）---
        import langchain_openai.chat_models.base as _lc_base
        from app.services.ai import langchain_reasoning_patch as _rp

        marker = getattr(_rp, "_MARKER", "_openstudy_reasoning_patched")
        patched = bool(getattr(_lc_base._convert_delta_to_message_chunk, marker, False))
        T("H5", "深度思考", "reasoning 注入补丁已装上（否则思考字段会被 langchain 丢掉）",
          "import app.services.ai.db_config 触发安装", "检查模块级函数标记",
          "INSTALLED=True 且 _convert_delta_to_message_chunk 带补丁标记",
          _rp.INSTALLED and patched, f"INSTALLED={_rp.INSTALLED} marker={patched}")

        # --- H6：langchain 结构变了（函数消失）必须优雅降级，不能把启动搞崩 ---
        _saved = _lc_base._convert_delta_to_message_chunk
        degraded = False
        try:
            del _lc_base._convert_delta_to_message_chunk
            _rp.INSTALLED = False
            degraded = (_rp.install() is False) and (_rp.INSTALLED is False)
        except Exception as e:  # noqa: BLE001
            print("    降级测试异常:", repr(e))
        finally:
            _lc_base._convert_delta_to_message_chunk = _saved
            _rp.install()  # 恢复（已带标记 → 幂等，不会二次包装）
        _restored = bool(getattr(_lc_base._convert_delta_to_message_chunk, marker, False))
        T("H6", "深度思考", "langchain 内部函数消失时补丁优雅降级（退化成无思考，不抛异常）",
          "临时删掉 _convert_delta_to_message_chunk 再 install()", "调用 install()",
          "返回 False 且 INSTALLED=False，不抛异常；随后能恢复",
          degraded and _restored,
          f"degraded={degraded} 已恢复={_restored}")

        # --- H7/H8：`metrics` 事件的形状、配对与 `steps` 口径 ---
        # 为什么补：ds-free 侧已有等价护栏（`tests/df_cases.mjs` 的 metrics 组：每个 metrics
        # 事件必须含 6 个字段、`firstTokenMs === null` **当且仅当** `firstTokenSamples === 0`、
        # 吐过正文的那轮 `firstTokenSamples === 1` 且 `rounds > samples`），而 api 侧
        # H1–H6 全是「事件类型存在性 + 相对下标」—— **一处都不碰 metrics 字段**。
        # 于是「后端哪天把 `firstTokenSamples` 删掉」不会有任何用例变红。判据照 ds-free 那份抄。
        def _metrics_evs(evs):
            return [e for e in evs if e.get("type") == "metrics"]

        _M_FIELDS = ("rounds", "steps", "llmMs", "toolMs", "firstTokenMs", "firstTokenSamples")

        SCRIPTS.append([
            [FakeChunk("", [{"name": "bank_manage", "args": {"action": "list"}, "id": "c1"}])],
            [FakeChunk("这是最终回复。")],
        ])
        ev = await run_stream({"message": "指标形状", "userId": uid})
        mevs = _metrics_evs(ev)
        missing = [(i, sorted(set(_M_FIELDS) - set(m))) for i, m in enumerate(mevs)
                   if set(_M_FIELDS) - set(m)]
        # 严格配对：有样本 ⟺ 有平均值。少一边就会出现「显示了 — 但样本数是 1」
        # 或「有毫秒值却权重为 0」这种前后端汇总算错的情况。
        paired = all(
            (m.get("firstTokenMs") is None) == (m.get("firstTokenSamples") == 0)
            for m in mevs
        )
        last = mevs[-1] if mevs else {}
        snapshot = {k: last.get(k) for k in _M_FIELDS}
        T("H7", "执行统计", "metrics 事件字段齐全，且 firstTokenMs 与 firstTokenSamples 严格配对",
          "一轮工具调用（只吐 tool_calls、无正文）+ 一轮正文",
          "POST /ai/agent/stream，收集所有 type=metrics 的事件",
          "每个 metrics 事件都含 rounds/steps/llmMs/toolMs/firstTokenMs/firstTokenSamples；"
          "firstTokenMs 为 null ⟺ firstTokenSamples == 0；"
          "末个事件（吐过正文那轮）firstTokenSamples == 1 且 rounds > samples"
          "（只吐 tool_calls 的轮不进样本，所以 rounds 会大于样本数）",
          bool(mevs) and not missing and paired
          and last.get("firstTokenSamples") == 1
          and isinstance(last.get("firstTokenMs"), int)
          and int(last.get("rounds") or 0) > int(last.get("firstTokenSamples") or 0),
          f"metrics {len(mevs)} 个；缺字段{missing}；配对={paired}；末个={snapshot}；"
          f"rounds={[m.get('rounds') for m in mevs]} "
          f"samples={[m.get('firstTokenSamples') for m in mevs]} "
          f"firstTokenMs={[m.get('firstTokenMs') for m in mevs]}")

        # `steps` 的唯一定义是「**模型本轮请求的工具调用条目数**，在遍历工具前一次加完」。
        # 若把它写成遍历体内的 `+= 1`，下面这条路径就会少算：同一 `tool:args` 连续重复触发
        # 死循环保护 → 该轮遍历**在中途 `break`** → 它后面的条目不再被计数。
        # 这里刻意让「被 break 跳过的那一条」是一个**本来会正常执行**的调用
        # （`bank_manage list`）：它一旦被执行就会多出一个 `tool_result`，
        # 所以「steps == 5」与「tool_result 恰好 1 个」两条一起断言 ——
        # 前者锁计数口径，后者证明那一条**确实**没执行（不是因为工具不存在而被跳过）。
        _same = {"action": "list", "bank_name": PREFIX}
        SCRIPTS.append([
            [FakeChunk("", [{"name": "bank_manage", "args": _same, "id": "r1c1"}])],
            [FakeChunk("", [{"name": "bank_manage", "args": _same, "id": "r2c1"}])],
            [FakeChunk("", [{"name": "bank_manage", "args": _same, "id": "r3c1"}])],
            [FakeChunk("", [{"name": "bank_manage", "args": _same, "id": "r4c1"},
                            {"name": "bank_manage", "args": _same, "id": "r4c2"}])],
        ])
        ev = await run_stream({"message": "反复列出题库", "userId": uid})
        mevs = _metrics_evs(ev)
        ts8 = types_of(ev)
        steps_last = (mevs[-1] if mevs else {}).get("steps")
        n_tool_result = ts8.count("tool_result")
        stopped = any(
            "重复调用" in str(e.get("message") or "")
            for e in ev
            if e.get("type") == "warning"
        )
        T("H8", "执行统计", "steps 在遍历工具前一次加完：被止损 break 跳过的条目也要算",
          "连续 4 轮调用同一 tool:args（第 4 轮一次给 2 个条目）→ 触发死循环保护",
          "POST /ai/agent/stream → 收集 metrics 事件 + tool_result 事件",
          "第 4 轮遍历**中途 break**（能查到『重复调用』warning）；"
          "steps == 5（1+1+1+2，含被 break 跳过的那一条）；"
          "tool_result 恰好 1 个（被跳过的那条确实没执行）",
          stopped and steps_last == 5 and n_tool_result == 1,
          f"死循环告警={stopped} 末个 steps={steps_last} tool_result 数={n_tool_result} "
          f"steps 序列={[m.get('steps') for m in mevs]}")

        # ================= K. 检索工具走真实 HTTP（ds-free 链路的回归护栏）=========
        # 为什么单开一组：ds-free 的知识库 / 记忆检索走的是 **HTTP `POST /ai/agent/execute`**
        # （前端循环 → 该接口 → 工具注册表 → `_execute_tool` 的 SAVEPOINT + `memory_hook` 收口）。
        # 但此前这条路径**没有任何用例**：`tests/test_agent_rag_tools.py` 是
        # `registry.get('knowledge_search')` **直调工具对象**（绕过 HTTP 层、绕过收口、绕过回灌），
        # 本文件此前也只在 A1 查过工具清单 —— 也就是说这条链路以后回归了，没有任何用例会红。
        #
        # 夹具是**真的**：HTTP 建库 → HTTP 传文档 → 后台流水线**真调 embedding** 向量化完成
        # （轮询 `/rag/document/status` 到 status=5），再走 HTTP 让工具自己检索。
        # 收尾只删本组**带标记**造的数据，并硬断言「真实用户已有的 rag 行一条都没少」（K12）。
        #
        # ⚠️ 库里有用户的真实知识库（不是测试专用库），所以下面所有删除都按
        #    `LEFT(name, LENGTH(:prefix)) = :prefix` 精确前缀（**不能用 LIKE** —— `_` 是通配符）。
        from app.models.rag import (
            DOC_VECTORIZED,
            RagDocument,
            RagDocumentChunk,
            RagKnowledgeBase,
            RagQaRecord,
        )

        KB_MARK = PREFIX  # `__e2e_agent__`
        KB_NAME = f"{KB_MARK}K组知识库{int(time.time() * 1000)}"
        KB_DOC = f"{KB_MARK}K组资料.txt"
        # 关键词那一路（jieba 分词 → content_tokens → tsvector）必须真命中，才锁得住
        # `hasKeywordAgreement`：正文与查询词里都要有**别的文档不可能出现**的词 ——
        # 一个人造 ASCII 标记 + 一个中文专有词。
        KB_TOKEN = "ZETAKTOKEN"
        KB_TOPIC = "欧拉回路"
        KB_TEXT = (
            f"# {KB_TOPIC}\n\n"
            f"{KB_TOPIC}的充要条件：连通图里奇度顶点数为 0 或 2。\n"
            f"本段带一个只属于回归用例的标记：{KB_TOKEN}。\n"
        )

        async def _k_scalar(sql: str, **params):
            async with async_session_factory() as db:
                return await db.scalar(text(sql), params)

        async def _k_rag_ids() -> dict:
            """三张表的全部 id —— 用来做「一条都不许少」的对照快照"""
            async with async_session_factory() as db:
                out = {}
                for key, model in (("kb", RagKnowledgeBase), ("doc", RagDocument),
                                   ("chunk", RagDocumentChunk)):
                    out[key] = {r[0] for r in (await db.execute(select(model.id))).all()}
                return out

        async def _k_marked_ids() -> dict:
            """当前库里**带本测试标记**的 rag 行 id（kb + 它的 doc + 它的 chunk）

            为什么需要它：K12 要断言「`_k_cleanup()` 没有误删**别人的**行」，可是
            「少掉的 id」里**必然**包含本组自己刚造的那几行（K1 建的库、K2 传的文档与分块）——
            它们就是被自己的清理删掉的，属于**应该少**。历史遗留的标记残骸同理
            （上一次跑崩了没清干净，标记网本就该扫掉，见 `_k_cleanup` docstring）。
            所以判定前必须把「带标记的行」整块剔出去，否则 `not missing` **恒假**、
            这条用例永远不可能通过 —— 那是断言写错，不是实现有问题。
            """
            async with async_session_factory() as db:
                kb_ids = {
                    r[0]
                    for r in (
                        await db.execute(
                            select(RagKnowledgeBase.id).where(
                                func.left(RagKnowledgeBase.name, len(KB_MARK)) == KB_MARK
                            )
                        )
                    ).all()
                }
                doc_ids = set()
                if kb_ids:
                    doc_ids = {
                        r[0]
                        for r in (
                            await db.execute(
                                select(RagDocument.id).where(RagDocument.kb_id.in_(kb_ids))
                            )
                        ).all()
                    }
                chunk_ids = set()
                if doc_ids:
                    chunk_ids = {
                        r[0]
                        for r in (
                            await db.execute(
                                select(RagDocumentChunk.id).where(
                                    RagDocumentChunk.doc_id.in_(doc_ids)
                                )
                            )
                        ).all()
                    }
                return {"kb": kb_ids, "doc": doc_ids, "chunk": chunk_ids}

        async def _k_cleanup() -> int:
            """物理删本组按标记造的 RAG 数据（子 → 父），返回删掉的知识库数

            前缀用 `LEFT(col, LENGTH(:p)) = :p`，**不是 LIKE**（前缀里的 `_` 是通配符，
            会删到真实用户的数据）。删除顺序照 `rag_document_chunk → rag_document →
            rag_qa_record → rag_knowledge_base`（与 e2e_rag_api.py 的清理同口径）。
            """
            async with async_session_factory() as db:
                kb_ids = [
                    r[0]
                    for r in (
                        await db.execute(
                            select(RagKnowledgeBase.id).where(
                                func.left(RagKnowledgeBase.name, len(KB_MARK)) == KB_MARK
                            )
                        )
                    ).all()
                ]
                if kb_ids:
                    doc_ids = [
                        r[0]
                        for r in (
                            await db.execute(
                                select(RagDocument.id).where(
                                    RagDocument.kb_id.in_(kb_ids)
                                )
                            )
                        ).all()
                    ]
                    if doc_ids:
                        await db.execute(
                            delete(RagDocumentChunk).where(
                                RagDocumentChunk.doc_id.in_(doc_ids)
                            )
                        )
                        await db.execute(
                            delete(RagDocument).where(RagDocument.id.in_(doc_ids))
                        )
                    await db.execute(
                        delete(RagQaRecord).where(RagQaRecord.kb_id.in_(kb_ids))
                    )
                    await db.execute(
                        delete(RagKnowledgeBase).where(RagKnowledgeBase.id.in_(kb_ids))
                    )
                await db.commit()
                return len(kb_ids)

        rag_snapshot = await _k_rag_ids()  # 建库之前：此刻的 rag 行全是「真实用户的」
        k_mem_baseline = int(
            await _k_scalar("SELECT COALESCE(MAX(id), 0) FROM ai_agent_memory") or 0
        )
        kb_id = None
        doc_id = None
        hits: list = []

        try:
            # --- K1 真建库（HTTP）---
            r = await client.post(
                "/rag/knowledgeBase",
                json={"name": KB_NAME, "description": f"{KB_MARK}K 组检索护栏用例"},
            )
            kb_body = r.json() or {}
            kb_id = ((kb_body.get("data") or {}) if isinstance(kb_body, dict) else {}).get(
                "kbId"
            )
            T("K1", "检索(HTTP)", "HTTP 建知识库（检索夹具的前置，走 /rag/knowledgeBase）",
              f"登录 uid={uid}", "POST /rag/knowledgeBase",
              "body.code=200 且返回 kbId、name 与提交的一致",
              kb_body.get("code") == 200 and isinstance(kb_id, int)
              and (kb_body.get("data") or {}).get("name") == KB_NAME,
              f"code={kb_body.get('code')} kbId={kb_id}")

            # --- K2 真传文档 + 真向量化（HTTP，后台流水线要真调 embedding）---
            st = {}
            if kb_id:
                r = await client.post(
                    "/rag/document/uploadText",
                    json={"kbId": kb_id, "fileName": KB_DOC, "content": KB_TEXT},
                )
                doc_id = ((r.json() or {}).get("data") or {}).get("docId")
                for _ in range(180):  # 最长 ~90s，与 e2e_rag_api 的轮询同口径
                    st = (
                        (await client.get(f"/rag/document/status/{doc_id}")).json() or {}
                    ).get("data") or {}
                    if st.get("done"):
                        break
                    await asyncio.sleep(0.5)
            T("K2", "检索(HTTP)", "HTTP 传文档后后台流水线真跑完（status=5 已向量化）",
              f"kbId={kb_id}", "POST /rag/document/uploadText → GET /rag/document/status",
              "轮询到 done=True、status=5（已向量化）、chunkCount≥1（否则检索不可能有结果）",
              isinstance(doc_id, int) and st.get("status") == DOC_VECTORIZED
              and int(st.get("chunkCount") or 0) >= 1,
              f"docId={doc_id} status={st.get('status')} "
              f"chunkCount={st.get('chunkCount')} error={st.get('errorMsg')}")

            # --- K3 knowledge_search.list 走 HTTP ---
            r = await execute("knowledge_search", {"action": "list"})
            kbs = r.get("knowledgeBases") or []
            mine = [k for k in kbs if k.get("kbId") == kb_id]
            T("K3", "检索(HTTP)", "knowledge_search.list 经 /ai/agent/execute 返回真实清单",
              f"本组已建库 kbId={kb_id}", "execute knowledge_search.list",
              "success=True；count 等于清单长度；清单里含本组知识库（kbId + name）",
              bool(r.get("success")) and r.get("count") == len(kbs) and bool(mine)
              and mine[0].get("name") == KB_NAME,
              f"success={r.get('success')} count={r.get('count')} 命中本组库={bool(mine)}")

            # --- K4 knowledge_search.search：真检索到 + 全套定位字段 ---
            # 定位字段（kbId/chunkId/docId/chunkIndex/source）是模型引用出处的唯一依据：
            # 少一个，模型就没法说清「这条出自哪个库的哪篇文档第几段」。
            r = await execute(
                "knowledge_search",
                {"action": "search", "query": f"{KB_TOPIC} {KB_TOKEN}", "kb_ids": [kb_id]},
            )
            hits = r.get("hits") or []
            need = ("chunkId", "docId", "docName", "chunkIndex", "kbId", "source", "content")
            T("K4", "检索(HTTP)", "knowledge_search.search 真检索到，且命中带全套定位字段",
              f"kbId={kb_id} 已向量化，查询词含正文里的专有词",
              "execute knowledge_search.search(kb_ids=[本组库])",
              "success=True 且命中；每条命中 kbId/chunkId/docId/docName/chunkIndex/source/content "
              "都在；kbId 就是本组库；正文里能找到标记词",
              bool(r.get("success")) and bool(hits)
              and all(all(h.get(k) is not None for k in need) for h in hits)
              and all(h.get("kbId") == kb_id for h in hits)
              and KB_TOKEN in json.dumps(hits, ensure_ascii=False),
              f"count={r.get('count')} recalled={r.get('recalled')} "
              f"source={hits[0].get('source') if hits else None!r} "
              f"kbId={hits[0].get('kbId') if hits else None}")

            # --- K5 两路原始分都要在（锁 `hasKeywordAgreement` 恒 False 那个回归）---
            T("K5", "检索(HTTP)", "关键词那一路真命中：hasKeywordAgreement=True 且两路原始分都在",
              "查询词与正文共享专有词，jieba 分词后 tsvector 能对上",
              "execute knowledge_search.search（同 K4 的返回）",
              "hasKeywordAgreement 为 True；每条命中都带 keywordScore/vectorScore 键，"
              "且至少一条关键词分非空、至少一条向量分非空（= 两路都真的跑了）",
              r.get("hasKeywordAgreement") is True
              and all("keywordScore" in h and "vectorScore" in h for h in hits)
              and any(h.get("keywordScore") is not None for h in hits)
              and any(h.get("vectorScore") is not None for h in hits),
              f"agreement={r.get('hasKeywordAgreement')} "
              f"kw={[h.get('keywordScore') for h in hits]} "
              f"vec={[h.get('vectorScore') for h in hits]}")

            # --- K6 命中能追溯回源文档（分块真带向量）---
            chunks = []
            if doc_id:
                r = await client.get(f"/rag/document/chunks/{doc_id}")
                chunks = (r.json() or {}).get("data") or []
            hit_ids = {h.get("chunkId") for h in hits}
            traced = [c for c in chunks if c.get("chunkId") in hit_ids]
            T("K6", "检索(HTTP)", "命中的 chunkId 能追回源文档，且该分块真的带向量",
              f"docId={doc_id}", f"GET /rag/document/chunks/{doc_id}",
              "命中的 chunkId 都能在该文档的分块清单里找到，且这些分块 vectorized=True",
              bool(hit_ids) and hit_ids <= {c.get("chunkId") for c in chunks}
              and bool(traced) and all(c.get("vectorized") for c in traced),
              f"命中 {len(hit_ids)} 个 chunkId / 文档分块 {len(chunks)} 条；"
              f"对上 {len(traced)} 条，全部带向量="
              f"{all(c.get('vectorized') for c in traced) if traced else False}")

            # --- K7 越权面：换用户走同一条 HTTP 路径，拿不到别人的库与记忆 ---
            if uid_other:
                app.dependency_overrides[get_current_user] = lambda: {
                    "user_id": uid_other, "userName": "e2e-agent",
                }
                try:
                    r_ks = await client.post("/ai/agent/execute", json={
                        "tool": "knowledge_search",
                        "params": {"action": "search", "query": KB_TOKEN, "kb_ids": [kb_id]},
                    })
                    r_ms = await client.post("/ai/agent/execute", json={
                        "tool": "memory_search", "params": {"action": "list"},
                    })
                finally:
                    auth_on()
                b_ks = r_ks.json() if isinstance(r_ks.json(), dict) else {}
                b_ms = r_ms.json() if isinstance(r_ms.json(), dict) else {}
                dumped = json.dumps([b_ks, b_ms], ensure_ascii=False)
                T("K7", "越权(HTTP)", "换用户走 execute 检索：拿不到别人的知识库与记忆",
                  f"kbId={kb_id} 属于 uid={uid}；以 uid={uid_other} 的身份请求",
                  "execute knowledge_search.search(别人的 kb_ids) + memory_search.list",
                  "知识库那条 success=False 且有 hint（不区分「不存在」与「不是你的」）；"
                  "两条响应正文里都不出现对方的标记词",
                  b_ks.get("success") is False and bool(b_ks.get("hint"))
                  and KB_TOKEN not in dumped and KB_MARK not in dumped,
                  f"ks.success={b_ks.get('success')} "
                  f"ks.error={str(b_ks.get('error'))[:40]!r} "
                  f"泄漏标记={KB_TOKEN in dumped or KB_MARK in dumped}")
            else:
                T("K7", "越权(HTTP)", "换用户走 execute 检索拿不到别人的数据", "-", "-",
                  "库里只有一个用户，跳过", False, "skip")

            # --- K8 memory_search.list 走 HTTP ---
            r = await execute("memory_search", {"action": "list", "limit": 5})
            mems = r.get("memories") or []
            T("K8", "检索(HTTP)", "memory_search.list 经 HTTP 返回记忆清单（形状 + 中文回执）",
              "本脚本前序用例的写操作已触发 memory_hook 落记忆",
              "execute memory_search.list",
              "success=True；返回非空；每条含 memoryId/memoryType/content/importance；"
              "message 是中文人话回执",
              bool(r.get("success")) and bool(mems)
              and all({"memoryId", "memoryType", "content", "importance"} <= set(m) for m in mems)
              and isinstance(r.get("message"), str) and "记忆" in r.get("message"),
              f"success={r.get('success')} count={r.get('count')} message={r.get('message')!r}")

            # --- K9 memory_search.search 真按关键词过滤 ---
            r = await execute("memory_search", {"action": "search", "query": "题库", "limit": 10})
            mems = r.get("memories") or []
            T("K9", "检索(HTTP)", "memory_search.search 真按关键词过滤（返回正文都含该词）",
              "query=题库（前序用例建的题库写操作会落记忆）",
              "execute memory_search.search(query=题库)",
              "success=True；count≥1；每条 content 都含该关键词；message 提到该词",
              bool(r.get("success")) and len(mems) >= 1
              and all("题库" in (m.get("content") or "") for m in mems)
              and "题库" in str(r.get("message")),
              f"success={r.get('success')} count={r.get('count')} message={r.get('message')!r}")

            # --- K10 只读工具不该要求二次确认（write_operation=False 的实际效果）---
            # 关键在 autoConfirm=False：这个开关下**写操作**会被拦（needsConfirm），
            # 只读工具必须照跑 —— 这就是「前端不给检索弹确认卡片」的服务端依据。
            r_ks = await execute("knowledge_search", {"action": "list"}, auto_confirm=False)
            r_ms = await execute("memory_search", {"action": "list"}, auto_confirm=False)
            tools_body = (await client.get("/ai/agent/tools")).json() or {}
            actions = tools_body.get("actions") or {}
            in_actions = [n for n in ("knowledge_search", "memory_search") if n in actions]
            T("K10", "只读工具", "autoConfirm=False 下两个检索工具仍直接执行（不弹二次确认）",
              "关掉自动执行（写操作此时必须要求确认）",
              "execute knowledge_search/memory_search(autoConfirm=False) + GET /ai/agent/tools",
              "两条都 success=True 且响应里没有 needsConfirm；actions 里也没有这两个工具",
              bool(r_ks.get("success")) and bool(r_ms.get("success"))
              and "needsConfirm" not in r_ks and "needsConfirm" not in r_ms
              and not in_actions,
              f"ks.success={r_ks.get('success')} ms.success={r_ms.get('success')} "
              f"needsConfirm={'needsConfirm' in r_ks or 'needsConfirm' in r_ms} "
              f"出现在actions={in_actions}")

            # --- K11 非法参数走 fail() 信封 + hint（自纠闭环的依据）---
            bad_kb = await execute("knowledge_search",
                                   {"action": "search", "query": "x", "kb_ids": [999999999]})
            no_q = await execute("knowledge_search", {"action": "search"})
            bad_action = await execute("memory_search", {"action": "explode"})
            T("K11", "自纠闭环", "不存在的 kbId / 缺 query / 非法 action 都 fail 且带 hint",
              "不存在或不属于自己的 kbId 不区分（避免探测他人资源是否存在）",
              "execute 三次非法调用",
              "三条都 success=False 且 hint 非空；kb 那条 hint 指向 list（先确认归属）；"
              "非法 action 那条 hint 列出合法枚举",
              all(x.get("success") is False and bool(x.get("hint"))
                  for x in (bad_kb, no_q, bad_action))
              and "list" in str(bad_kb.get("hint"))
              and "search" in str(bad_action.get("hint")),
              f"bad_kb={str(bad_kb.get('hint'))[:36]!r} no_q={str(no_q.get('hint'))[:24]!r} "
              f"bad_action={str(bad_action.get('hint'))[:36]!r}")
        finally:
            # 清本组造的数据（标记前缀，物理删）；清理后立刻做「没误删」的硬断言。
            # ⚠️ 对照窗口刻意取**清理前后紧邻的两次快照**（毫秒级），而不是拿 K 组开始时的快照：
            #    后者只有几秒的窗口，但用户可能正在页面上自己删知识库 / 别的 e2e 在跑，
            #    那种「少了的 id」与本组的清理无关，会把这条断言变成噪声。窗口收窄后，
            #    这条仍然精确回答「**我的清理**有没有删掉非本组标记的行」。
            pre_clean = await _k_rag_ids()
            # 带标记的 id（含本组刚建的那几行）—— 它们被删是应该的，判定时要整块剔除，
            # 否则 `not missing` 恒假（详见 `_k_marked_ids` 的 docstring）。
            marked_pre = await _k_marked_ids()
            removed = await _k_cleanup()
            rag_after = await _k_rag_ids()
            missing = {
                k: sorted(set(v) - marked_pre[k] - rag_after[k])
                for k, v in pre_clean.items()
                if set(v) - marked_pre[k] - rag_after[k]
            }
            # 反向也要查：标记行**必须真的被删掉**（否则「清理」等于没生效，残骸只会越积越多）。
            own_left = sorted(
                (marked_pre["kb"] & rag_after["kb"])
                | (marked_pre["doc"] & rag_after["doc"])
                | (marked_pre["chunk"] & rag_after["chunk"])
            )
            left = int(
                await _k_scalar(
                    "SELECT count(*) FROM rag_knowledge_base "
                    "WHERE LEFT(COALESCE(name, ''), LENGTH(:p)) = :p",
                    p=KB_MARK,
                )
                or 0
            )
            # 只读工具**不该**留下记忆：按工具名核查（POSITION 而非 LIKE，与仓库既有口径一致），
            # 并限定在 K 组开始之后新增的行 —— 并发跑别的用例不会让它假红。
            read_memories = int(
                await _k_scalar(
                    "SELECT count(*) FROM ai_agent_memory WHERE user_id = :u AND id > :b "
                    "AND (POSITION('knowledge_search' IN content) > 0 "
                    "OR POSITION('memory_search' IN content) > 0)",
                    u=uid, b=k_mem_baseline,
                )
                or 0
            )
            T("K12", "收尾", "只删自己造的：清理窗口内真实用户的 rag 行一条没少、检索没落记忆",
              f"清理前快照 kb={len(pre_clean['kb'])}/doc={len(pre_clean['doc'])}/"
              f"chunk={len(pre_clean['chunk'])}（含本组库；建库前的真实行数 "
              f"{len(rag_snapshot['kb'])}/{len(rag_snapshot['doc'])}/{len(rag_snapshot['chunk'])}）",
              "按标记前缀物理删 → 紧邻前后两次快照按 id 回比 + 数残留 + 查记忆表",
              "本组标记库残留 0；标记行（kb/doc/chunk）真被删掉；"
              "清理窗口内除**带标记的行**外一个 id 都没少；"
              "记忆表里没有新增的检索类记忆",
              left == 0 and not own_left and not missing and read_memories == 0,
              f"删掉本组知识库 {removed} 个；残留={left}；"
              f"误删的 id={missing or '无'}；标记行漏删={own_left or '无'}；"
              f"检索类新记忆={read_memories}")

        # ================= M. 知识库屏蔽闸门（per-KB `disabled`）=========
        # 需求（用户原话）：「要支持知识库屏蔽功能 —— 比如用户不想把那个知识库给 llm
        # 查看，可以进行屏蔽」。屏蔽 = **一道闸门**：被屏蔽的库在**所有模型可见路径**上
        # 消失（L1 提示词清单 / knowledge_search.list / 点名检索 / /rag/search），
        # 但在**管理列表**里必须照样看得见 —— 否则用户自己的开关就关不回去了。
        #
        # ⚠️ 本组刻意**不传文档、不向量化、不点 query**：闸门收口在「解析出哪些库」
        #    那一步（`resolve_knowledge_bases` / `list_knowledge_bases`），判定点用
        #    纯 DB 读 + 纯 HTTP 就能验；而任何真正走到 `embed_query` 的调用都要花钱
        #    （硅基流动）。所以本组**只验判定点**，`knowledge_search.search` 与
        #    `/rag/search` 这两条 HTTP 级用例本次**未跑**（NOT RUN，等 team-lead 放行）。
        #
        # 夹具：两个**空**知识库（不传文档 → 零 embedding）。M_A 会被屏蔽，M_B 作对照
        # —— 对照组是必须的：只有「M_A 不出现」而没对照组时，那条断言可能恒真
        # （比如接口整体挂了、或者清单为空），那就等于没测。
        from app.models.rag import RagKnowledgeBase as _M_KB
        from app.services.rag import rag_write_service as _m_rws
        from app.services.rag.rag_write_service import _kb_brief as _m_brief

        M_MARK = f"{PREFIX}M组"          # 清理用的**精确前缀**（不用 LIKE：`_` 是通配符）
        M_A_NAME = f"{M_MARK}屏蔽{int(time.time() * 1000)}"
        M_B_NAME = f"{M_MARK}对照{int(time.time() * 1000)}"

        def _is_int01(v) -> bool:
            """必须是**整数** 0/1 —— 布尔不算（JSON 的 `true` 在 Python 里 `== 1` 成立，
            但 `el-switch` 是**严格相等**，true 与 1 在它眼里是两个值）。"""
            return isinstance(v, int) and not isinstance(v, bool) and v in (0, 1)

        async def _m_scalar(sql: str, **params):
            async with async_session_factory() as db:
                return await db.scalar(text(sql), params)

        async def _m_unmarked() -> dict:
            """**不带本套件标记**的知识库 `{id: disabled}` —— 全是真实用户的数据

            ⚠️ **刻意不按 user_id 过滤**：本套件的 uid 是 `sys_user` 里第一个用户
            （实测 = 1 / admin），而用户的**真实**知识库属于另一个 user_id（实测 3 个，
            user_id=105）。按 uid 过滤的话这个集合恒为空集，M9 那条「一行没少」
            就会**恒真** —— 看着绿，其实什么都没测（这正是本仓库最忌讳的假绿）。
            """
            async with async_session_factory() as db:
                rows = (
                    await db.execute(
                        text(
                            "SELECT id, disabled FROM rag_knowledge_base "
                            "WHERE LEFT(COALESCE(name, ''), LENGTH(:p)) <> :p"
                        ),
                        {"p": PREFIX},
                    )
                ).all()
            return {r[0]: r[1] for r in rows}

        async def _m_put(payload: dict, kb_id=None):
            resp = await client.put(f"/rag/knowledgeBase/{kb_id or m_a}", json=payload)
            return resp, (resp.json() or {})

        async def _m_detail(kb_id: int) -> dict:
            return ((await client.get(f"/rag/knowledgeBase/{kb_id}")).json() or {}).get(
                "data"
            ) or {}

        async def _m_list() -> list:
            return ((await client.get("/rag/knowledgeBase/list")).json() or {}).get(
                "data"
            ) or []

        async def _m_ctx() -> str:
            return ((await client.get("/ai/agent/context")).json() or {}).get("context") or ""

        def _m_ctx_total(ctx: str):
            """/ai/agent/context 里报的库数（`You have N in total.`）

            ⚠️ 为什么断言**这个数**而不是「名字在不在」：名字那条路会被
            `runtime_context.MAX_KB_LISTED`（10 条上限）截断 —— 库一多，
            「不在里面」就可能是被截掉的，断言就假绿了。计数是**不受上限影响**的那一路。
            """
            m = re.search(r"You have (\d+) in total", ctx)
            return int(m.group(1)) if m else None

        m_a = m_b = None
        m_before = await _m_unmarked()
        try:
            # --- M0 建夹具：两个空知识库（HTTP，零 embedding）---
            body_a = (await client.post("/rag/knowledgeBase", json={"name": M_A_NAME})).json() or {}
            m_a = (body_a.get("data") or {}).get("kbId")
            body_b = (await client.post("/rag/knowledgeBase", json={"name": M_B_NAME})).json() or {}
            m_b = (body_b.get("data") or {}).get("kbId")
            _RAG_FIXTURE_KB_IDS.extend(i for i in (m_a, m_b) if isinstance(i, int))
            T("M0", "屏蔽闸门", "建两个空知识库作夹具（不传文档 → 零 embedding）",
              f"登录 uid={uid}", "POST /rag/knowledgeBase ×2",
              "两次 code=200 且返回不同 kbId；**创建响应里也带 disabled（整数 0）** —— "
              "少这一处，前端把新建库塞进本地列表时那一行就会绑到 undefined",
              isinstance(m_a, int) and isinstance(m_b, int) and m_a != m_b
              and _is_int01((body_a.get("data") or {}).get("disabled"))
              and (body_a.get("data") or {}).get("disabled") == 0,
              f"kbId={m_a}/{m_b} 创建回显disabled={(body_a.get('data') or {}).get('disabled')!r}")

            # --- M1 写路径：PUT {disabled:1} 之后**库里真的变了**（重读，不只看 200）---
            # R3：只看 PUT 的 200 是假闸门 —— 字段名写错（pydantic extra='ignore'
            # 会静默丢字段）、handler 忘了透传、服务层守卫写成 `if x:`（0 被当成没传）
            # 这几种情况下 PUT 全都回 200，而库里一个字节没变。
            r_put, put_body = await _m_put({"disabled": 1})
            put_data = put_body.get("data") or {}
            detail1 = await _m_detail(m_a)
            rows1 = await _m_list()
            listed1 = [k for k in rows1 if k.get("kbId") == m_a]
            _listed1_disabled = listed1[0].get("disabled") if listed1 else None
            T("M1", "屏蔽闸门", "PUT {disabled:1} 后**库里真的变了**（重读详情 + 重读列表）",
              f"M_A(kbId={m_a}) 新建、disabled=0",
              "PUT /rag/knowledgeBase/{id} {disabled:1} → GET 详情 + GET list",
              "HTTP 200 且 body.code=200；回显 / 详情 / 列表三处 disabled 都是**整数 1**；"
              "只传 disabled 时 name 未被清空（说明写入守卫是 `is not None` 口径）",
              r_put.status_code == 200 and put_body.get("code") == 200
              and _is_int01(put_data.get("disabled")) and put_data.get("disabled") == 1
              and _is_int01(detail1.get("disabled")) and detail1.get("disabled") == 1
              and detail1.get("name") == M_A_NAME
              and bool(listed1) and listed1[0].get("disabled") == 1,
              f"status={r_put.status_code} code={put_body.get('code')} "
              f"回显={put_data.get('disabled')!r} 详情={detail1.get('disabled')!r} "
              f"列表={_listed1_disabled!r} name保持={detail1.get('name') == M_A_NAME}")
            # ⚠️ 上面那个值先算好再进 f-string：`{x!r if c else 'n/a'}` 在本机
            #    Python 3.11 下是**语法错误**（f-string 的 `!r` 转换后面必须直接就是 `}`，
            #    不能再跟 `if/else`；实测 `f"{d.get('k')!r if d else 'n/a'}"` →
            #    `SyntaxError: f-string: expecting '}'`）。不是格式问题，是编译不过。

            # --- M2 管理列表**必须**还看得见被屏蔽的库（否则开关关不回去）---
            rows = await _m_list()
            mine = [k for k in rows if k.get("kbId") == m_a]
            bad_rows = [k.get("kbId") for k in rows if not _is_int01(k.get("disabled"))]
            T("M2", "屏蔽闸门", "管理列表仍含被屏蔽的库，且**每一行**都带整数 0/1 的 disabled",
              f"M_A(kbId={m_a}) 已屏蔽；列表共 {len(rows)} 行（含用户对真实库）",
              "GET /rag/knowledgeBase/list",
              "列表含 M_A；**所有行**都有 disabled 且为整数 0/1。缺键 / null / 字符串都会让"
              "前端 el-switch 在**挂载时** emit 一次写库（那等于替用户改数据）",
              bool(mine) and mine[0].get("disabled") == 1 and bool(rows) and not bad_rows,
              f"含M_A={bool(mine)} 行数={len(rows)} 非法行={bad_rows or '无'}")

            # --- M3 字段名写错 → 422，而不是「静默 200 + 库里没变」；正常字段仍 200 ---
            # 反向（正常改名仍 200）必须**同一条用例里**一起验：只验 422 的话，
            # 把 extra 写成 `forbid` 之外的东西（比如整个模型写错）也能过。
            # ⚠️ 改名挑对照组 M_B，不动被屏蔽的 M_A —— M4/M7 要靠 M_A_NAME 做「不出现」断言，
            #    改掉它的名字会让那两条断言退化成恒真。
            r_bad, _ = await _m_put({"blocked": True})
            detail_bad = await _m_detail(m_a)
            M_B_NAME_NEW = f"{M_B_NAME}改"
            r_ren, _ = await _m_put({"name": M_B_NAME_NEW}, kb_id=m_b)
            detail_ren = await _m_detail(m_b)
            M_B_NAME = M_B_NAME_NEW  # 后续用例（M4/M5）的对照组断言跟着用新名字
            T("M3", "屏蔽闸门", "字段名写错（blocked）→ 422 且库没被动；正常改名仍 200",
              "PUT 一个**未声明**字段 blocked（前后端字段名对不上的真实形态）"
              " + PUT 一个**声明过的** name",
              "PUT /rag/knowledgeBase/{id} {blocked: true} 与 {name: ...}",
              "写错那条 HTTP **422**（`model_config extra='forbid'`；**绝不能**是 200 —— 200 "
              "意味着字段被 pydantic 静默丢弃、库里没写、UI 却显示已屏蔽）；改名那条仍 200、"
              "名字真的变了、且**没有**顺手清掉 disabled（写入守卫是 `is not None` 口径）",
              r_bad.status_code == 422 and _is_int01(detail_bad.get("disabled"))
              and detail_bad.get("disabled") == 1
              and r_ren.status_code == 200
              and detail_ren.get("name") == M_B_NAME
              and _is_int01(detail_ren.get("disabled"))
              and detail_ren.get("disabled") == 0,
              f"写错status={r_bad.status_code} 复查M_A disabled={detail_bad.get('disabled')!r}；"
              f"改名status={r_ren.status_code} name={detail_ren.get('name')!r} "
              f"disabled={detail_ren.get('disabled')!r}")

            # --- M4 L1 运行时背景（GET /ai/agent/context）：被屏蔽的库不出现 ---
            ctx1 = await _m_ctx()
            alive_cnt = int(await _m_scalar(
                "SELECT count(*) FROM rag_knowledge_base WHERE user_id = :u AND del_flag = '0'",
                u=uid) or 0)
            enabled_cnt = int(await _m_scalar(
                "SELECT count(*) FROM rag_knowledge_base WHERE user_id = :u "
                "AND del_flag = '0' AND disabled = 0", u=uid) or 0)
            T("M4", "屏蔽闸门", "L1 运行时背景下发给模型时不含被屏蔽的库（名字/kbId/计数三路）",
              f"M_A 已屏蔽；uid={uid} 未删库 {alive_cnt} 个、其中启用 {enabled_cnt} 个",
              "GET /ai/agent/context（纯 HTTP，不调模型）",
              "context 不含 M_A 的名字与 `kbId=`；提示词报的库数 == **启用中**的库数"
              "（!= 未删库总数）—— 计数是唯一不受 10 条上限截断的那一路；"
              "对照组 M_B 的名字必须**出现**（否则「不出现」可能恒真）",
              M_A_NAME not in ctx1 and f"kbId={m_a}" not in ctx1
              and _m_ctx_total(ctx1) == enabled_cnt and M_B_NAME in ctx1
              and enabled_cnt < alive_cnt,
              f"含M_A名={M_A_NAME in ctx1} 含M_A的kbId={f'kbId={m_a}' in ctx1} "
              f"提示词库数={_m_ctx_total(ctx1)} 启用={enabled_cnt} 未删={alive_cnt} "
              f"对照M_B出现={M_B_NAME in ctx1}")

            # --- M5 knowledge_search.list：模型那份清单里没有它 ---
            r = await execute("knowledge_search", {"action": "list"})
            kbs = r.get("knowledgeBases") or []
            T("M5", "屏蔽闸门", "knowledge_search.list 不含被屏蔽的库，且回灌载荷里没有 disabled 键",
              f"M_A(kbId={m_a}) 已屏蔽、M_B(kbId={m_b}) 启用",
              "POST /ai/agent/execute {tool: knowledge_search, params: {action: list}}"
              "（**不传 query** → 不会走到 embed_query，零成本）",
              "success=True；清单里没有 M_A 的 kbId；**每一行都没有 disabled 键**（已剥掉："
              "剩下的行全是启用中的，这个字段对模型零信息量、只费 token）；对照组 M_B 在里面",
              bool(r.get("success")) and all(k.get("kbId") != m_a for k in kbs)
              and all("disabled" not in k for k in kbs) and bool(kbs)
              and any(k.get("kbId") == m_b for k in kbs),
              f"success={r.get('success')} 条数={len(kbs)} "
              f"含M_A={any(k.get('kbId') == m_a for k in kbs)} "
              f"含M_B={any(k.get('kbId') == m_b for k in kbs)} "
              f"带disabled键={len([k for k in kbs if 'disabled' in k])}")

            # --- M6 判定点（纯 DB 读）：默认分支 + 显式分支，且**不抛错** ---
            async with async_session_factory() as cdb:
                raised = None
                ids_default: set = set()
                ids_named: list = []
                try:
                    ids_default = {
                        k.id for k in await _m_rws.resolve_knowledge_bases(cdb, uid)
                    }
                    ids_named = [
                        k.id
                        for k in await _m_rws.resolve_knowledge_bases(cdb, uid, [m_a, m_b])
                    ]
                except Exception as e:  # noqa: BLE001 - 抛错本身就是这条用例的判据
                    raised = repr(e)
            T("M6", "屏蔽闸门", "resolve_knowledge_bases：两个分支都排除被屏蔽的库，且静默丢弃不抛错",
              f"M_A(kbId={m_a}) 已屏蔽、M_B(kbId={m_b}) 启用",
              "直调 rag_write_service.resolve_knowledge_bases（纯 SELECT，零成本）",
              "默认分支（不点名）含 M_B、不含 M_A；显式分支 [M_A, M_B] 只返回 [M_B]；"
              "**不抛异常** —— 抛 RagNotFound 会被包成 404，前端随即弹出两条没有信息量的"
              "报错（本地 errorCode 表优先于后端文案），把用户的主动动作呈现成错误",
              raised is None and m_a not in ids_default and m_b in ids_default
              and ids_named == [m_b],
              f"抛错={raised} 默认分支含M_A={m_a in ids_default} 含M_B={m_b in ids_default} "
              f"显式分支={ids_named}")

            # --- M7 开关必须能关回去（disabled=0 不能被当成「没传」而静默无效）---
            r_put2, put2_body = await _m_put({"disabled": 0})
            detail2 = await _m_detail(m_a)
            ctx2 = await _m_ctx()
            async with async_session_factory() as cdb:
                named2 = [k.id for k in await _m_rws.resolve_knowledge_bases(cdb, uid, [m_a])]
            T("M7", "屏蔽闸门", "PUT {disabled:0} 真的取消屏蔽（0 不能被当成「没传」）",
              f"M_A(kbId={m_a}) 当前 disabled=1",
              "PUT {disabled:0} → GET 详情 + GET /ai/agent/context + resolve([M_A])",
              "HTTP 200；回显与详情的 disabled 都是整数 **0**；context 里出现 M_A 的名字且"
              "库数回到未删总数；显式点名 [M_A] 解析出 1 个库（证明 M6 的空不是恒空）",
              r_put2.status_code == 200
              and _is_int01((put2_body.get("data") or {}).get("disabled"))
              and (put2_body.get("data") or {}).get("disabled") == 0
              and _is_int01(detail2.get("disabled")) and detail2.get("disabled") == 0
              and M_A_NAME in ctx2 and _m_ctx_total(ctx2) == alive_cnt
              and named2 == [m_a],
              f"status={r_put2.status_code} 回显={(put2_body.get('data') or {}).get('disabled')!r} "
              f"详情={detail2.get('disabled')!r} context含M_A={M_A_NAME in ctx2} "
              f"提示词库数={_m_ctx_total(ctx2)}/{alive_cnt} 显式解析={named2}")

            # --- M8 文案：全被屏蔽 ≠ 一个都没有（D8）---
            # 这两种情况的处置**完全不同**（去关屏蔽开关 vs 去上传资料），说成同一句会让用户
            # 以为自己的资料丢了 —— 而这是用户自己刚做的动作。
            await _m_put({"disabled": 1})
            await _m_put({"disabled": 1}, kb_id=m_b)
            r_all = await execute("knowledge_search", {"action": "list"})
            msg_all = str(r_all.get("message") or "")
            T("M8", "屏蔽闸门", "全部被屏蔽时的话术不再说「你还没有知识库」（D8）",
              f"M_A/M_B 两个库都置为 disabled=1（uid={uid} 名下已无启用库）",
              "execute knowledge_search.list（不传 query → 零成本）",
              "success=True、count=0；message 里能看到「屏蔽」；**不能**出现「你还没有知识库」"
              "（那是在说用户没有资料，而事实是他自己刚把它们屏蔽了）",
              bool(r_all.get("success")) and (r_all.get("count") or 0) == 0
              and "屏蔽" in msg_all and "还没有" not in msg_all,
              f"count={r_all.get('count')} message={msg_all!r}")

            # --- M9 读侧一律下发整数 0/1（**纯内存**构造，不落库、零成本）---
            probe_out = []
            for raw in (None, "", 0, 1, 2, "0", "1"):
                obj = _M_KB(user_id=uid, name="内存夹具")
                obj.disabled = raw
                probe_out.append((repr(raw), _m_brief(obj).get("disabled")))
            T("M9", "屏蔽闸门", "读侧永远下发整数 0/1（null / 空串 / 字符串 / 越界值都漏不出去）",
              "纯内存构造 RagKnowledgeBase（**不写库**），逐个值过 `_kb_brief`",
              "把 None / '' / 0 / 1 / 2 / '0' / '1' 分别塞进 disabled 再序列化",
              "每个值都得到整数 0 或 1；键恒定存在、绝不为 None / 字符串；非零一律归一成 1"
              "（与闸门 `disabled == 0` 同向 ⇒ UI 显示与检索闸门不可能给出相反结论）",
              all(_is_int01(v) for _, v in probe_out)
              and [v for _, v in probe_out] == [0, 0, 0, 1, 1, 0, 1],
              f"取值→下发：{probe_out}")
        finally:
            # 物理删本组两个夹具（**精确 id**，外键顺序 qa → chunk → doc → kb）。
            # 库里还有用户的真实知识库，绝不按无标记条件删、更不整表清。
            async with async_session_factory() as cdb:
                for _k in [i for i in (m_a, m_b) if isinstance(i, int)]:
                    for _stmt in (
                        "DELETE FROM rag_qa_record WHERE kb_id = :k",
                        "DELETE FROM rag_document_chunk WHERE kb_id = :k",
                        "DELETE FROM rag_document WHERE kb_id = :k",
                        "DELETE FROM rag_knowledge_base WHERE id = :k",
                    ):
                        await cdb.execute(text(_stmt), {"k": _k})
                await cdb.commit()
            left = int(await _m_scalar(
                "SELECT count(*) FROM rag_knowledge_base "
                "WHERE LEFT(COALESCE(name, ''), LENGTH(:p)) = :p", p=M_MARK) or 0)
            m_after = await _m_unmarked()
            changed = sorted(set(m_before.items()) - set(m_after.items()))
            T("M10", "收尾", "只删自己造的：本组夹具残留 0，真实用户（无标记）的库一行没少/没被改",
              f"建夹具前全库无标记知识库 {len(m_before)} 个（**不按 uid 过滤**：本套件 uid "
              f"是 admin，真实库属于另一个用户，按 uid 过滤会让这条断言恒真）",
              "按精确 id 物理删 → 数残留 + 前后两次「无标记行」的 (id, disabled) 回比",
              "本组标记库残留 0；**没有一条**无标记行消失或改变（新增的真实行不算变动）；"
              "清理只按标记走，无标记的行是用户数据，一行不许动",
              left == 0 and not changed,
              f"残留={left} 无标记行 {len(m_before)}→{len(m_after)} 变动={changed or '无'}")

        # ================= L. 确认卡片的预演端点（POST /ai/agent/preview）=========
        # 为什么需要它：api 付费链路的确认卡片由**后端**弹（`run_agent_stream` 的
        # `tool_confirm` 事件里带 `preview`），ds-free 的循环与卡片都在**前端** ——
        # 它只能自己来取这一份。拿不到的话两条链路的卡片不对等：付费链路说
        # 「将删除题库「X」，含 23 道题」，免费链路只显示一句 action 名。
        #
        # 本组锁的是这个端点的**四条约定**：只读（绝不执行工具）、失败不阻断、
        # 越权形状与 `/agent/execute` 一致（403 + fail 信封）、参数归一化与 execute 同源。
        L_BANK = PREFIX + "L"
        r = await execute("bank_manage",
                          {"action": "create", "bank_name": L_BANK, "subject": "语文"})
        l_bank_id = (r.get("bank") or {}).get("bankId")

        async def preview(tool_name, params, user_id=None):
            body = {"tool": tool_name, "params": params, "sessionId": sid2}
            if user_id is not None:
                body["userId"] = user_id
            resp = await client.post("/ai/agent/preview", json=body)
            return resp, (resp.json() if isinstance(resp.json(), dict) else {})

        r, b = await preview("bank_manage", {"action": "delete", "bank_id": l_bank_id})
        pv = b.get("preview") or {}
        # ⚠️ 这里**特意不**断言 `ownedByCurrentUser`：它不是能直接展示给用户的文案，而是
        #    一个未经加工的布尔值 —— 确认卡片对没有中文标签的键是**原样打印**
        #    （`AgentConfirmCard/index.vue` 的 `PREVIEW_LABELS[k] || k`），于是卡片上会多出
        #    一行 `ownedByCurrentUser  true`，正是那个组件注释里批评的「给用户看 JSON」。
        #    补中文标签也解决不了（值仍是 `true`/`false`），所以这个键**已从 preview() 里删掉**。
        #    别为了「信息更全」把它加回来：卡片能说清「删的是哪个库」就够，归属由工具自己判。
        T("L1", "确认预演", "需要确认的操作返回非空 preview（卡片才说得出「删的是哪个」）",
          f"题库 {L_BANK}（bankId={l_bank_id}）", "POST /ai/agent/preview",
          "HTTP 200；preview.bankName 就是该题库名、subject 与建库时一致、totalQuestions 是整数"
          "（与 loop 里 tool_confirm 带的 preview 同一份）",
          r.status_code == 200 and pv.get("bankName") == L_BANK
          and pv.get("subject") == "语文"
          and isinstance(pv.get("totalQuestions"), int),
          f"status={r.status_code} preview={str(pv)[:120]}")

        r, b = await preview("bank_manage", {"action": "list"})
        T("L2", "确认预演", "不需要确认的操作返回 preview == {}（不白算、也不报错）",
          "list 不在 _WRITE_ACTIONS 里", "POST /ai/agent/preview(action=list)",
          "HTTP 200 且 preview 是空对象（与循环里 if tool.needs_confirmation(params) 同口径）",
          r.status_code == 200 and b.get("preview") == {},
          f"status={r.status_code} preview={b.get('preview')!r}")

        if uid_other:
            r, b = await preview("bank_manage",
                                 {"action": "delete", "bank_id": l_bank_id}, user_id=uid_other)
            T("L3", "越权(预演)", "传别人的 userId → 403 + fail 信封（带 success，不会被判成成功）",
              f"登录 uid={uid}，请求体 userId={uid_other}", "POST /ai/agent/preview",
              "HTTP 403；body.success 是 **False** 且有 error（形状同 /ai/agent/execute）",
              r.status_code == 403 and b.get("success") is False and bool(b.get("error")),
              f"status={r.status_code} success={b.get('success')!r} error={str(b.get('error'))[:40]!r}")
        else:
            T("L3", "越权(预演)", "传别人的 userId 被拒", "-", "-",
              "库里只有一个用户，跳过", False, "skip")

        r, b = await preview("no_such_tool", {})
        T("L4", "确认预演", "未知工具 → fail 信封（HTTP 200，不是 500）",
          "传一个不存在的工具名", "POST /ai/agent/preview",
          "HTTP 200；success=False；hint 列出可用工具（模型/前端据此改道）",
          r.status_code == 200 and b.get("success") is False
          and "bank_manage" in str(b.get("hint")),
          f"status={r.status_code} success={b.get('success')} hint={str(b.get('hint'))[:60]!r}")

        r, b = await preview("bank_manage", {"action": "explode"})
        T("L5", "确认预演", "非法 action → fail 信封 + hint 列出合法枚举（自纠依据）",
          "action 不在 schema 枚举里", "POST /ai/agent/preview(action=explode)",
          "HTTP 200；success=False；hint 里能看到 delete 等合法值",
          r.status_code == 200 and b.get("success") is False
          and "delete" in str(b.get("hint")),
          f"status={r.status_code} error={str(b.get('error'))[:40]!r} "
          f"hint={str(b.get('hint'))[:60]!r}")

        # 只读性：预演**绝不能写库**。只断言「题库还在」是不够的 —— 「还在」挡不住「被改过」，
        # 所以这里取**整行快照**（逐列）前后对比 + 该库题目数不变。
        # ⚠️ 对比窗口只覆盖预演那一次调用，且对象是本组自建的题库（别人不可能碰），
        #    所以并发跑别的用例/用户在页面上操作都不会让它假红。
        async def _l_bank_row(bid):
            async with async_session_factory() as db:
                row = (
                    await db.execute(
                        text(
                            "SELECT id, bank_name, subject, total_questions, status, user_id, "
                            "is_public FROM question_bank WHERE id = :b"
                        ),
                        {"b": bid},
                    )
                ).first()
                return tuple(row) if row else None

        async def _l_bank_questions(bid):
            async with async_session_factory() as db:
                return int(
                    await db.scalar(
                        text("SELECT count(*) FROM question_main WHERE bank_id = :b"),
                        {"b": bid},
                    )
                    or 0
                )

        row_before = await _l_bank_row(l_bank_id)
        q_before = await _l_bank_questions(l_bank_id)
        await preview("bank_manage", {"action": "delete", "bank_id": l_bank_id})  # 破坏性动作
        row_after = await _l_bank_row(l_bank_id)
        q_after = await _l_bank_questions(l_bank_id)
        T("L6", "确认预演", "预演绝不写库：整行逐列不变、题目数不变（不只是「还在」）",
          f"bankId={l_bank_id}（题库 {L_BANK}）",
          "取整行快照 → POST /ai/agent/preview(delete) → 再取整行快照",
          "两次快照完全一致（含 subject/total_questions/status/is_public/user_id）；"
          "该库题目数不变；行仍存在",
          row_before is not None and row_before == row_after and q_before == q_after,
          f"行逐列一致={row_before == row_after} 题目数 {q_before}→{q_after} 行={row_after}")

        # 失败不阻断（红线）：让 preview() 抛异常，端点必须 200 + 空 preview。
        # 理由：拿不到预览只是卡片信息少一点；这里报错把前端卡住，就变成「用户删不掉东西了」。
        from app.services.ai.agent.loop import ensure_tools_loaded
        from app.services.ai.agent.registry import registry as _registry

        ensure_tools_loaded()
        _tool_inst = _registry.get("bank_manage")
        _saved_preview = _tool_inst.preview

        async def _boom_preview(*_a, **_kw):
            raise RuntimeError("模拟 preview 失败")

        try:
            _tool_inst.preview = _boom_preview
            r, b = await preview("bank_manage", {"action": "delete", "bank_id": l_bank_id})
        finally:
            _tool_inst.preview = _saved_preview
        T("L7", "确认预演", "preview() 抛异常时只降级为空 preview（HTTP 200，不阻断确认流程）",
          "把 bank_manage.preview 换成会抛的桩", "POST /ai/agent/preview",
          "HTTP 200 且 preview == {}（前端照常弹卡片，只是信息少一点）",
          r.status_code == 200 and b.get("preview") == {},
          f"status={r.status_code} preview={b.get('preview')!r} success={b.get('success')}")

        # 参数归一化必须与 execute 同源：否则「预览描述的」和「实际执行的」不是同一组参数
        r, b = await preview("bank_manage",
                             {"action": "delete", "bank_id": str(l_bank_id)})
        pv = b.get("preview") or {}
        T("L8", "确认预演", "参数归一化与 execute 同源（字符串 id 也能反查）",
          f'bank_id 传字符串 "{l_bank_id}"', "POST /ai/agent/preview",
          "preview.bankName 仍是本题库名 —— 说明 ExecutionGuard.normalize_params 真的跑了",
          pv.get("bankName") == L_BANK, f"preview={str(pv)[:100]}")

        # 缺 bank_id：走的是与 `/agent/execute` **同一套**跨字段校验（`ExecutionGuard.validate_params`
        # 对 bank_manage 的 detail/update/delete 强制要 bank_id）→ fail 信封 + 指路 hint。
        # 这条顺带锁住「预演与执行共用同一套参数校验」——两边漂移的话，卡片描述和执行就不是一回事。
        r, b = await preview("bank_manage", {"action": "delete"})
        T("L9", "确认预演", "缺 bank_id → fail 信封 + hint 指路（与 execute 同一套校验）",
          "delete 不带 bank_id（bank_manage 的跨字段前置校验）", "POST /ai/agent/preview",
          "HTTP 200；success=False；hint 指向 bank_id 或「先 list 查」",
          r.status_code == 200 and b.get("success") is False
          and ("bank_id" in str(b.get("hint")) or "list" in str(b.get("hint"))),
          f"status={r.status_code} success={b.get('success')} "
          f"error={str(b.get('error'))[:40]!r} hint={str(b.get('hint'))[:60]!r}")

        # --- L10：按名删除的卡片必须显示**真实**题库名（不能空白、也不能回显模型给的名字）---
        # 背景：`bank_manage.delete_by_name` 的卡片此前**完全空白** —— 用户被要求确认
        # 「删除题库」，却看不到要删的是哪一个。补的方式是**只读反查**出真实题库。
        # 两条一起锁：
        #   ① 真名 → 卡片上就是库里那个名字（连 subject 一起给，信息量够用户判断）
        #   ② 假名 → 明说没找到，且**不含**模型传进来的那个字符串 ——
        #      回显的话卡片会显示一个**并不存在**的题库名，用户确认的是 A、实际删的是 B
        #      （或什么都没删），那比没有预览更危险。
        r, b = await preview("bank_manage", {"action": "delete_by_name", "bank_name": L_BANK})
        pv = b.get("preview") or {}
        fake_bank = L_BANK + "_并不存在"
        _r2, _b2 = await preview("bank_manage",
                                 {"action": "delete_by_name", "bank_name": fake_bank})
        pv2 = _b2.get("preview") or {}
        T("L10", "确认预演", "按名删除的卡片给**真实**题库名；名字对不上就明说（不回显模型字符串）",
          f"题库「{L_BANK}」（真）/ 「{fake_bank}」（假）",
          "POST /ai/agent/preview(delete_by_name)",
          "真名 → preview.bankName 就是库里那个名字，且带 subject；"
          "假名 → bankName 说明没找到，且整份 preview 里**不含**模型传进来的那个名字",
          pv.get("bankName") == L_BANK and bool(pv.get("subject"))
          and "没有找到" in str(pv2.get("bankName"))
          and fake_bank not in json.dumps(pv2, ensure_ascii=False),
          f"真名 preview={str(pv)[:90]}；假名 preview={str(pv2)[:90]}")

        # --- L11：批量删库的卡片给出 count + sample（照 note_manage._preview_delete 的样板）---
        r, b = await preview("bank_manage", {"action": "delete_many", "bank_ids": [l_bank_id]})
        pv = b.get("preview") or {}
        T("L11", "确认预演", "批量删库的卡片给出 count + sample（题库名）",
          f"bank_ids=[{l_bank_id}]（题库 {L_BANK}）", "POST /ai/agent/preview(delete_many)",
          "preview.count == 1；sample 里就是该题库名（用户看清要删哪几个）",
          pv.get("count") == 1 and pv.get("sample") == [L_BANK],
          f"preview={str(pv)[:120]}")

        # --- L12：清空题库的卡片要说清「清哪个库、清多少题」---
        n_real = await _l_bank_questions(l_bank_id)
        r, b = await preview("question_manage",
                             {"action": "clear_questions", "bank_id": l_bank_id})
        pv = b.get("preview") or {}
        fake_name = "并不存在的库__e2e__"
        _r2, _b2 = await preview("question_manage",
                                 {"action": "clear_questions", "bank_name": fake_name})
        pv2 = _b2.get("preview") or {}
        T("L12", "确认预演", "清空题库的卡片显示真实题库名 + 影响题数；查不到就说题库不存在",
          f"bankId={l_bank_id}（{L_BANK}，库里实测 {n_real} 题）/ 「{fake_name}」（假名）",
          "POST /ai/agent/preview(clear_questions)",
          "bank_id 版：bankName == 真实题库名，且 count == 库里该库真实题目数（同一条 SQL 口径）；"
          "假名版：bankName 明说没找到，且不回显模型给的字符串",
          pv.get("bankName") == L_BANK and pv.get("count") == n_real
          and "没有找到" in str(pv2.get("bankName"))
          and fake_name not in json.dumps(pv2, ensure_ascii=False),
          f"preview={str(pv)[:110]} 库里题目数={n_real}；假名 preview={str(pv2)[:90]}")

        # --- L13：笔记更新的「将修改」是**中文人话**，且重复项去重 ---
        # 背景：之前拼的是**参数名**（`title、tags、is_public`），前端把它直接打在卡片上
        # （`PREVIEW_LABELS.willChange` =「将修改」）—— 等于给用户看 schema。
        # `content` 与 `markdown_content` 都映射成「正文」，必须去重成一个。
        r = await execute("note_manage", {
            "action": "create", "title": NOTE_PREFIX + "L预览",
            "markdown_content": "预览用例用正文",
            "category_name": NOTE_PREFIX + "分类",
        })
        l_note_id = (r.get("note") or {}).get("noteId")
        _r, _b = await preview("note_manage", {
            "action": "update", "note_id": l_note_id,
            "title": "改个标题", "content": "纯文本", "markdown_content": "# md",
            "tags": ["a"], "is_public": 1, "status": "draft",
            "category_name": NOTE_PREFIX + "分类",
        })
        pv = _b.get("preview") or {}
        wc = str(pv.get("willChange") or "")
        T("L13", "确认预演", "笔记更新卡片的「将修改」是中文人话（不是字段名），重复项去重",
          f"noteId={l_note_id}，一次给 title/content/markdown_content/tags/is_public/status/category",
          "POST /ai/agent/preview(note_manage.update)",
          "willChange 全是中文白名单词；content 与 markdown_content 都是「正文」→ 只出现一次",
          wc == "标题、正文、标签、可见性、状态、分类",
          f"willChange={wc!r} preview={str(pv)[:110]}")

        # --- L14：`count > len(sample)` 的**截断分支**（此前运行时从未被覆盖）---
        # 为什么单开一条：前端的 `AgentConfirmCard` 里那句
        #   `const total = k === 'sample' && typeof p.count === 'number' ? p.count : items.length`
        # **只有 `count > len(sample)` 时才有意义**，而上面所有预览夹具都是
        # `count == len(sample)`（P4/P5/P6/P14）或走 `hasSample=false` 那条分支（P8/P9）。
        # 也就是说：把 `count` 发成**字符串**、或者干脆不发精确总数，卡片会让「共 N 条」整句消失，
        # 而**旧夹具照样全绿**（零报错、静默）—— fe-ui-1 已离线实测过这个渲染后果。
        # ⚠️ 断言里用**工具自己的** `_PREVIEW_SAMPLE` 而不是写死 5：这样既防漂，
        #    又能自己检查「这个夹具真的超过了截断阈值」（否则截断分支根本没被走到）。
        from app.services.ai.agent.tools.question_manage import (
            _PREVIEW_SAMPLE as _QM_SAMPLE,
        )

        _qs = json.dumps([
            {"questionType": 1, "questionText": f"{PREFIX}截断题{i}",
             "options": ["A", "B"], "answer": "0"}
            for i in range(1, 9)
        ], ensure_ascii=False)
        _imp = await execute("question_manage",
                             {"action": "batch_import", "bank_id": l_bank_id, "questions": _qs})
        _lst = await execute("question_manage",
                             {"action": "list", "bank_id": l_bank_id, "limit": 20})
        _qids = [q.get("questionId") for q in (_lst.get("questions") or [])]
        _r14, _b14 = await preview("question_manage",
                                   {"action": "delete_many", "bank_id": l_bank_id,
                                    "question_ids": _qids})
        pv14 = _b14.get("preview") or {}
        _c14 = pv14.get("count")
        _n_sample = len(pv14.get("sample") or [])
        T("L14", "确认预演", "批量删题的预览：count 是**精确总数**且是 int，sample 按 _PREVIEW_SAMPLE 截断",
          f"题库 {L_BANK} 里 batch_import 8 道题（imported={_imp.get('imported')}），"
          f"再对 {len(_qids)} 个 questionId 打 delete_many 预览",
          "execute batch_import ×1 → execute list 取 questionId → POST /ai/agent/preview(delete_many)",
          "type(count) is int（**严格**：不是字符串也不是 bool —— `'8'` 会让卡片上「共 N 条」整句消失）；"
          f"count == 8（精确总数，不是 len(sample)）；len(sample) == {_QM_SAMPLE}"
          f"（截断真的发生，即 count({8}) > _PREVIEW_SAMPLE({_QM_SAMPLE})）",
          type(_c14) is int and _c14 == 8 and _n_sample == _QM_SAMPLE and _c14 > _QM_SAMPLE,
          f"count={_c14!r} type={type(_c14).__name__} len(sample)={_n_sample} "
          f"_PREVIEW_SAMPLE={_QM_SAMPLE} sample[:2]={str(pv14.get('sample'))[:70]}")

        # ================= N. 按主键 id 的越权（水平越权 / IDOR）=================
        # 背景（本轮主线缺陷，实测）：Agent 工具的用户隔离**只做在「按名字 / 列表」那一路**，
        # 「按主键 id」那一路直接 `ctx.db.get(Model, id)` —— 于是**别人的 id** 能读也能改：
        #   · `question_manage._resolve_question` 的 `question_id` 分支无归属校验，
        #     而 `_detail` / `_update` / `_delete` 三条路**共用**它；
        #   · `bank_manage._resolve_bank` 的 `bank_id` 分支同样无校验（`_detail` 能读到别人的题库）、
        #     `bank_manage.preview()` 的只读反查也照给别人的题库名。
        # 「按名字」那一路是**有**校验的 —— 所以「换个名字问」的用例（F8 / K7）**盖不住**这个洞。
        #
        # 夹具：**本用例自己造**一条属于**另一个用户**的题库 + 题目（名字带 PREFIX 标记），
        # 收尾按**精确 id** 物理删。⚠️ 绝不拿真实用户的数据当靶子：本组打的是「改 / 删」
        # 两个动作，打到真数据上收不回来（本仓库出过 `clear_*` 删光真实数据的事故）。
        N_OTHER_MARK = OTHER_IDOR_MARK
        N_OTHER_BANK = N_OTHER_MARK + "库"
        N_OTHER_Q = N_OTHER_MARK + "题干"
        N_TAMPER = N_OTHER_MARK + "被篡改"
        n_bank = n_q = None
        try:
            if not uid_other:
                # 库里只有一个用户 → 本组**没测到东西**（不是「没问题」）
                for _cid in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N10", "N11"):
                    T(_cid, "越权(id)", "拿别人的 question_id / bank_id 被拒", "-", "-",
                      "库里只有一个用户，跳过", False, "skip")
            else:
                async with async_session_factory() as cdb:
                    await cdb.execute(text(
                        "INSERT INTO question_bank (bank_name, subject, description, "
                        "total_questions, status, user_id, is_public) "
                        "VALUES (:n, :s, :d, 1, '0', :u, 0)"
                    ), {"n": N_OTHER_BANK, "s": "越权夹具", "d": N_OTHER_MARK + "夹具",
                        "u": uid_other})
                    n_bank = await cdb.scalar(text(
                        "SELECT id FROM question_bank WHERE bank_name = :n AND user_id = :u "
                        "ORDER BY id DESC LIMIT 1"
                    ), {"n": N_OTHER_BANK, "u": uid_other})
                    await cdb.execute(text(
                        "INSERT INTO question_main (bank_id, question_type, difficulty, "
                        "question_text, answer, has_sub_questions, sort_order, score, status) "
                        "VALUES (:b, 1, 1, :t, '0', 0, 1, 0, '0')"
                    ), {"b": int(n_bank or 0), "t": N_OTHER_Q})
                    n_q = await cdb.scalar(text(
                        "SELECT id FROM question_main WHERE bank_id = :b AND question_text = :t "
                        "ORDER BY id DESC LIMIT 1"
                    ), {"b": int(n_bank or 0), "t": N_OTHER_Q})
                    await cdb.commit()
                n_bank = int(n_bank) if n_bank else None
                n_q = int(n_q) if n_q else None

                async def _n_scalar(sql, **params):
                    async with async_session_factory() as cdb:
                        return await cdb.scalar(text(sql), params)

                # --- N1 读别人的题 ---
                r = await execute("question_manage", {"action": "detail", "question_id": n_q})
                dumped = json.dumps(r, ensure_ascii=False)
                T("N1", "越权(id)", "question_manage.detail 拿别人的 question_id → 被拒且不泄漏题干",
                  f"question_id={n_q} 属于 uid={uid_other}；以 uid={uid} 登录态调用",
                  "POST /ai/agent/execute {tool: question_manage, params: {action: detail, "
                  "question_id: <别人的>}}",
                  "success=False；有 error 与 hint；响应里**不含**题干标记"
                  "（不能把别人的题目内容读出来）",
                  r.get("success") is False and bool(r.get("error")) and bool(r.get("hint"))
                  and N_OTHER_Q not in dumped,
                  f"success={r.get('success')} error={str(r.get('error'))[:44]!r} "
                  f"hint={str(r.get('hint'))[:30]!r} 泄漏题干={N_OTHER_Q in dumped}")

                # --- N2 改别人的题（必须无副作用）---
                r = await execute("question_manage", {
                    "action": "update", "question_id": n_q, "question_text": N_TAMPER,
                })
                after = await _n_scalar(
                    "SELECT question_text FROM question_main WHERE id = :i", i=n_q)
                T("N2", "越权(id)", "question_manage.update 拿别人的 question_id → 被拒且题干没被改",
                  f"question_id={n_q} 属于 uid={uid_other}",
                  "execute question_manage.update(question_id=<别人的>, question_text=<篡改>) "
                  "→ 直接查库回读该行",
                  "success=False；有 hint；库里题干**仍是原值**（不是「报错了但还是改了」）",
                  r.get("success") is False and bool(r.get("hint")) and after == N_OTHER_Q,
                  f"success={r.get('success')} 库里题干={str(after)[:40]!r}")

                # --- N3 删别人的题 ---
                r = await execute("question_manage", {"action": "delete", "question_id": n_q})
                left_q = int(await _n_scalar(
                    "SELECT count(*) FROM question_main WHERE id = :i", i=n_q) or 0)
                T("N3", "越权(id)", "question_manage.delete 拿别人的 question_id → 被拒且题目还在",
                  f"question_id={n_q} 属于 uid={uid_other}",
                  "execute question_manage.delete(question_id=<别人的>) → 数该行是否还在",
                  "success=False；有 error 与 hint；库里该行**仍然存在**（物理删一旦执行收不回来）",
                  r.get("success") is False and bool(r.get("error")) and bool(r.get("hint"))
                  and left_q == 1,
                  f"success={r.get('success')} error={str(r.get('error'))[:44]!r} 仍在={left_q == 1}")

                # --- N4 读别人的题库 ---
                r = await execute("bank_manage", {"action": "detail", "bank_id": n_bank})
                dumped = json.dumps(r, ensure_ascii=False)
                T("N4", "越权(id)", "bank_manage.detail 拿别人的 bank_id → 被拒且不泄漏题库信息",
                  f"bank_id={n_bank} 属于 uid={uid_other}",
                  "execute bank_manage.detail(bank_id=<别人的>)",
                  "success=False；有 error 与 hint；响应里**不含**该题库名",
                  r.get("success") is False and bool(r.get("error")) and bool(r.get("hint"))
                  and N_OTHER_BANK not in dumped,
                  f"success={r.get('success')} error={str(r.get('error'))[:44]!r} "
                  f"泄漏题库名={N_OTHER_BANK in dumped}")

                # --- N5 改别人的题库 ---
                r = await execute("bank_manage", {
                    "action": "update", "bank_id": n_bank, "subject": N_TAMPER,
                })
                after_sub = await _n_scalar(
                    "SELECT subject FROM question_bank WHERE id = :i", i=n_bank)
                T("N5", "越权(id)", "bank_manage.update 拿别人的 bank_id → 被拒且题库没被改",
                  f"bank_id={n_bank} 属于 uid={uid_other}",
                  "execute bank_manage.update(bank_id=<别人的>, subject=<篡改>) → 回读 subject",
                  "success=False；有 error 与 hint；库里 subject **仍是原值**「越权夹具」",
                  r.get("success") is False and bool(r.get("hint"))
                  and after_sub == "越权夹具",
                  f"success={r.get('success')} 库里 subject={after_sub!r}")

                # --- N6 删别人的题库 ---
                r = await execute("bank_manage", {"action": "delete", "bank_id": n_bank})
                left_b = int(await _n_scalar(
                    "SELECT count(*) FROM question_bank WHERE id = :i", i=n_bank) or 0)
                T("N6", "越权(id)", "bank_manage.delete 拿别人的 bank_id → 被拒且题库还在",
                  f"bank_id={n_bank} 属于 uid={uid_other}",
                  "execute bank_manage.delete(bank_id=<别人的>) → 数该行是否还在",
                  "success=False；库里该行**仍然存在**"
                  "（服务端这一路必须挡；不能只靠前端不点那个按钮）",
                  r.get("success") is False and bool(r.get("error")) and left_b == 1,
                  f"success={r.get('success')} error={str(r.get('error'))[:44]!r} 仍在={left_b == 1}")

                # --- N7 预演（只读反查）同样要挡 ---
                # 只读反查给不给别人的题库名，是**信息泄漏**：确认卡片会把别人的题库名打到用户脸上。
                _r7, _b7 = await preview("bank_manage", {"action": "delete", "bank_id": n_bank})
                pv7 = _b7.get("preview") or {}
                T("N7", "越权(id)", "bank_manage 预览按别人的 bank_id 反查 → 不给信息",
                  f"bank_id={n_bank} 属于 uid={uid_other}",
                  "POST /ai/agent/preview {action: delete, bank_id: <别人的>}",
                  "preview 是空对象（不给别人的题库名 / 科目 / 题数），且不报 500",
                  _r7.status_code == 200 and pv7 == {},
                  f"status={_r7.status_code} preview={str(pv7)[:90]}")

                # --- N8 对照：自己的 id 仍然照常可用（证明上面的拒绝不是「一刀切挡死」）---
                _r8a = await execute("bank_manage", {"action": "detail", "bank_id": l_bank_id})
                _r8b = await execute("question_manage",
                                     {"action": "detail", "question_id": (_qids or [None])[0]})
                T("N8", "越权(id)", "对照：自己的 bank_id / question_id 仍然读得到（不是一刀切）",
                  f"自己的 bankId={l_bank_id} / questionId={(_qids or [None])[0]}",
                  "execute bank_manage.detail + question_manage.detail（都是自己的 id）",
                  "两条都 success=True；题库名 / 题干真的返回了",
                  _r8a.get("success") is True
                  and ((_r8a.get("bank") or {}).get("bankName") == L_BANK)
                  and _r8b.get("success") is True
                  and bool((_r8b.get("question") or {}).get("questionText")),
                  f"bank.success={_r8a.get('success')} "
                  f"bankName={(_r8a.get('bank') or {}).get('bankName')!r} "
                  f"question.success={_r8b.get('success')}")

                # --- N10 别人的 bank_id 走 **question_manage**（另一份解析实现）也要挡 ---
                # N4–N7 打的是 `bank_manage` 那一份 `_resolve_bank`；这里打的是
                # `question_manage._resolve_bank` —— 同一个洞里**两条各自独立**的实现。
                # 两份实现的口径一旦漂开，洞就从没挡住的那一份复发（这正是本轮缺陷的形态：
                # 「按名字」那路有校验、「按 id」那路没有，而用例只照了有校验的那一条）。
                r = await execute("question_manage", {"action": "list", "bank_id": n_bank})
                dumped = json.dumps(r, ensure_ascii=False)
                r2 = await execute("question_manage", {
                    "action": "detail", "bank_id": n_bank, "question_index": 1})
                dumped2 = json.dumps(r2, ensure_ascii=False)
                T("N10", "越权(id)",
                  "question_manage 拿别人的 bank_id（list / 按题号 detail）→ 被拒且不泄漏",
                  f"bank_id={n_bank} 属于 uid={uid_other}",
                  "execute question_manage.list(bank_id=<别人的>) + "
                  ".detail(question_index=1, bank_id=<别人的>)",
                  "两条都 success=False；有 error / hint；响应里**不含**别人的题库名与题干",
                  r.get("success") is False and bool(r.get("error")) and bool(r.get("hint"))
                  and N_OTHER_BANK not in dumped and N_OTHER_Q not in dumped
                  and r2.get("success") is False and bool(r2.get("error"))
                  and N_OTHER_BANK not in dumped2 and N_OTHER_Q not in dumped2,
                  f"list.success={r.get('success')} 泄漏库名={N_OTHER_BANK in dumped} "
                  f"泄漏题干={N_OTHER_Q in dumped} | detail.success={r2.get('success')} "
                  f"泄漏库名={N_OTHER_BANK in dumped2} 泄漏题干={N_OTHER_Q in dumped2}")

                # --- N11 清空别人的题库（批量物理删）→ 被拒且一道没少 ---
                # 与 N3 同一个理由，但走的是**另一个动作**（`clear_questions` 一次删光整库）：
                # 一旦闸门破了，爆炸半径是「整库题目被物理删」，比删单题大得多。
                before_n = int(await _n_scalar(
                    "SELECT count(*) FROM question_main WHERE bank_id = :b", b=n_bank) or 0)
                r = await execute("question_manage",
                                  {"action": "clear_questions", "bank_id": n_bank})
                after_n = int(await _n_scalar(
                    "SELECT count(*) FROM question_main WHERE bank_id = :b", b=n_bank) or 0)
                T("N11", "越权(id)",
                  "question_manage.clear_questions 拿别人的 bank_id → 被拒且一道没少",
                  f"bank_id={n_bank} 属于 uid={uid_other}（本组夹具，题数 {before_n}）",
                  "execute question_manage.clear_questions(bank_id=<别人的>) → 回数该库题数",
                  "success=False；有 error / hint；别人题库的题数**不变**",
                  before_n > 0 and after_n == before_n
                  and r.get("success") is False and bool(r.get("error")) and bool(r.get("hint")),
                  f"before={before_n} after={after_n} success={r.get('success')} "
                  f"error={str(r.get('error'))[:44]!r}")
        finally:
            # 精确物理删本组的「他人」夹具（子 → 父）。库里还有真实用户的题库，
            # 所以只按**本组登记的 id** 删，绝不按无标记条件删、更不整表清。
            if n_bank or n_q:
                try:
                    async with async_session_factory() as cdb:
                        if n_q:
                            await cdb.execute(
                                text("DELETE FROM question_main WHERE id = :i"), {"i": n_q})
                        if n_bank:
                            await cdb.execute(
                                text("DELETE FROM question_bank WHERE id = :i"), {"i": n_bank})
                        await cdb.commit()
                except Exception:  # noqa: BLE001 - 收尾失败不该盖住用例结果
                    pass
            async with async_session_factory() as cdb:
                left_n = int(await cdb.scalar(text(
                    "SELECT count(*) FROM question_bank "
                    "WHERE LEFT(COALESCE(bank_name, ''), LENGTH(:p)) = :p"
                ), {"p": N_OTHER_MARK}) or 0)
            T("N9", "收尾", "本组「他人」夹具残留 0（清理只按自己登记的 id / 标记前缀走）",
              f"标记前缀 {N_OTHER_MARK}（本组自己造的，属于 uid={uid_other}）",
              "按精确 id 物理删 → 按标记前缀数残留",
              "残留 0 行", left_n == 0, f"残留={left_n}")

        # ================= O. 服务端确认票据（confirmTicket，契约 v1）=================
        # 背景（用户裁决，2026-09-21）：ds-free 链路的破坏性操作此前**只靠前端弹卡片** ——
        # `/ai/agent/execute` 直接信任请求体里的 `confirmed: true`，而前端 `executeTool`
        # 是**无条件**填 true 的。也就是说「用户确认」这件事在服务端**根本不存在**：
        # 一个 HTTP 客户端带上 true 就能删库。前端弹卡片是**体验**，不是**授权**。
        #
        # 现在的形状：需要确认的操作 → preview 下发**签名票据** → execute 必须带回来 →
        # 服务端校验（签名 / uid / tool+paramsHash / 未过期 / **一次性**）→ 全过才执行。
        # `confirmed` 字段保留，但**不再是充分条件**。
        #
        # 本组同时锁「票据真的生效」（O3/O10 正向）与「少了/错了就不执行」（O4–O8 反向）——
        # 只锁反向的话，把票据校验写成「一律拒绝」也能全绿。
        from app.services.ai.agent import confirm_ticket as _ct
        from app.services.ai.agent.guard import params_hash as _params_hash

        O_MARK = PREFIX + "O"
        o_a, o_b, o_c = O_MARK + "A", O_MARK + "B", O_MARK + "C"
        o_d, o_e = O_MARK + "D", O_MARK + "E"

        async def _o_bank_id(name):
            r_ = await execute("bank_manage",
                               {"action": "list", "bank_name": name})
            for b_ in (r_.get("banks") or []):
                if b_.get("bankName") == name:
                    return b_.get("bankId")
            return None

        async def _o_create(name):
            await execute("bank_manage", {"action": "create", "bank_name": name})
            return await _o_bank_id(name)

        oa_id = await _o_create(o_a)
        ob_id = await _o_create(o_b)
        oc_id = await _o_create(o_c)

        # --- O1 preview 在「确实需要确认」时下发票据（且原有 preview 行为不变）---
        _r1, _b1 = await preview_raw("bank_manage", {"action": "delete", "bank_id": oa_id})
        t1 = _b1.get("confirmTicket")
        pv1 = _b1.get("preview") or {}
        T("O1", "确认票据", "preview 对破坏性操作下发 confirmTicket（且 preview 内容一字不变）",
          f"题库 {o_a}（bankId={oa_id}）；delete 是破坏性动作",
          "POST /ai/agent/preview {action: delete, bank_id: <自己的>}",
          "HTTP 200；confirmTicket 是**非空字符串**（`payload.signature` 两段）；"
          "preview.bankName 仍是该题库名（新增字段不影响原有形状）",
          _r1.status_code == 200 and isinstance(t1, str) and bool(t1) and t1.count(".") == 1
          and pv1.get("bankName") == o_a,
          f"status={_r1.status_code} ticket长度={len(t1) if isinstance(t1, str) else 'n/a'} "
          f"preview={str(pv1)[:70]}")

        # --- O2 不需要确认的操作**不出现**该字段（存量调用方零改动）---
        _r2, _b2 = await preview_raw("bank_manage", {"action": "list"})
        T("O2", "确认票据", "不需要确认的操作不下发票据（字段不出现，存量调用方零改动）",
          "list 不在写 / 破坏性清单里", "POST /ai/agent/preview {action: list}",
          "HTTP 200；body 里**没有** confirmTicket 键（不是空串、不是 null）；preview == {}",
          _r2.status_code == 200 and "confirmTicket" not in _b2 and _b2.get("preview") == {},
          f"status={_r2.status_code} 有该键={'confirmTicket' in _b2} preview={_b2.get('preview')!r}")

        # --- O3 正向：带票据就能真的执行（否则整条链路是死的）---
        r3 = await execute_raw("bank_manage", {"action": "delete", "bank_id": oa_id}, ticket=t1)
        gone_a = (await _o_bank_id(o_a)) is None
        T("O3", "确认票据", "带票据执行破坏性操作 → 真的执行了（正向对照，证明票据不是「一律拒绝」）",
          f"用 O1 取到的票据删题库 {o_a}", "execute bank_manage.delete(bank_id=..., confirmTicket=<O1>)",
          "success=True；随后按名查不到该题库（真删了）",
          r3.get("success") is True and gone_a,
          f"success={r3.get('success')} 已删={gone_a} error={str(r3.get('error'))[:40]!r}")

        # --- O4 反向：不带票据 → 不执行（`confirmed: true` 不再是充分条件）---
        # 这里直接手工 POST 而不走 `execute_raw`，因为要同时断言 **HTTP 200** ——
        # 这是「业务级拒绝」不是「越权」，前端判的是 `success !== false`（不是 response.ok）。
        _r4 = await client.post("/ai/agent/execute", json={
            "tool": "bank_manage", "params": {"action": "delete", "bank_id": ob_id},
            "userId": uid, "autoConfirm": True, "confirmed": True,
        })
        r4 = _r4.json() or {}
        still_b = (await _o_bank_id(o_b)) is not None
        T("O4", "确认票据", "不带票据的破坏性操作 → 被拒且无副作用（confirmed=true 也不例外）",
          f"题库 {o_b}（bankId={ob_id}）存在；请求体带 confirmed=true 但**不带** confirmTicket",
          "POST /ai/agent/execute {action: delete, confirmed: true}（无票据）→ 再按名查该题库",
          "HTTP 200（业务级拒绝，不是 403）；success=False；error 提到确认票据；hint 非空；"
          "needsConfirm=True（前端据此继续弹卡片）；题库**仍然存在**",
          _r4.status_code == 200 and r4.get("success") is False
          and "确认票据" in str(r4.get("error")) and bool(r4.get("hint"))
          and r4.get("needsConfirm") is True and still_b,
          f"status={_r4.status_code} success={r4.get('success')} "
          f"error={str(r4.get('error'))[:40]!r} needsConfirm={r4.get('needsConfirm')} 仍在={still_b}")

        # --- O5 一次性：同一张票据重放 → 拒绝 ---
        r5 = await execute_raw("bank_manage", {"action": "delete", "bank_id": oa_id}, ticket=t1)
        T("O5", "确认票据", "票据**一次性**：同一张票重放 → 被拒（不是走到工具才发现题库没了）",
          "复用 O3 已经用过的同一张票据（同一 tool + 同一参数）",
          "execute bank_manage.delete(bank_id=<O3 删过的>) + 同一张 confirmTicket",
          "success=False 且 error 提到**确认票据**（说明拦在票据闸门，"
          "而不是走到工具后报「题库不存在」）",
          r5.get("success") is False and "确认票据" in str(r5.get("error")),
          f"success={r5.get('success')} error={str(r5.get('error'))[:52]!r}")

        # --- O6 参数绑定：票据只对「它签发时那组参数」有效 ---
        t2 = await ticket_for("bank_manage", {"action": "delete", "bank_id": ob_id})
        r6 = await execute_raw("bank_manage", {"action": "delete", "bank_id": oc_id}, ticket=t2)
        still_c = (await _o_bank_id(o_c)) is not None
        T("O6", "确认票据", "票据与参数绑定：拿 A 的票删 B → 被拒且 B 没被删",
          f"票据是为 bank_id={ob_id}（{o_b}）签发的，却拿去删 bank_id={oc_id}（{o_c}）",
          "preview(delete, O_B) 取票 → execute(delete, O_C) 带上它",
          "success=False；error 提到确认票据；O_C **仍然存在**（paramsHash 对不上就该拦死）",
          r6.get("success") is False and "确认票据" in str(r6.get("error")) and still_c,
          f"success={r6.get('success')} error={str(r6.get('error'))[:40]!r} O_C仍在={still_c}")

        # --- O7 归属绑定：别人 uid 的票据在本 uid 下无效（**先证明票本身是好的**）---
        if uid_other:
            h_b = _params_hash({"action": "delete", "bank_id": ob_id})
            t3 = _ct.issue(uid_other, "bank_manage", h_b)
            unit3 = _ct.verify(t3, uid_other, "bank_manage", h_b)  # 单元级：票本身有效
            r7 = await execute_raw("bank_manage", {"action": "delete", "bank_id": ob_id}, ticket=t3)
            still_b7 = (await _o_bank_id(o_b)) is not None
            T("O7", "确认票据", "票据与 uid 绑定：别人的有效票据在本 uid 下被拒",
              f"票据 payload.uid={uid_other}，本请求登录态 uid={uid}；题库 {o_b} 属于 uid",
              "confirm_ticket.issue(uid=<别人>) → verify（单元级，应为有效）→ execute 带该票",
              "单元级 verify 返回有效（证明票**本身**没问题，拒绝不是因为格式坏）；"
              "HTTP 那一趟 success=False 且 error 提到确认票据；题库仍在",
              unit3[0] is True and r7.get("success") is False
              and "确认票据" in str(r7.get("error")) and still_b7,
              f"单元verify={unit3} http.success={r7.get('success')} "
              f"error={str(r7.get('error'))[:40]!r} 仍在={still_b7}")
        else:
            T("O7", "确认票据", "票据与 uid 绑定", "-", "-", "库里只有一个用户，跳过", False, "skip")

        # --- O8 过期 / 篡改 ---
        h_c = _params_hash({"action": "delete", "bank_id": oc_id})
        t_exp = _ct.issue(uid, "bank_manage", h_c, ttl=-1)
        unit_exp = _ct.verify(t_exp, uid, "bank_manage", h_c)
        r8a = await execute_raw("bank_manage", {"action": "delete", "bank_id": oc_id}, ticket=t_exp)
        body_c, _sig_c = t_exp.split(".", 1)
        t_tamper = body_c[:-1] + ("A" if body_c[-1] != "A" else "B") + "." + _sig_c
        unit_tamper = _ct.verify(t_tamper, uid, "bank_manage", h_c)
        r8b = await execute_raw("bank_manage", {"action": "delete", "bank_id": oc_id},
                                ticket=t_tamper)
        still_c8 = (await _o_bank_id(o_c)) is not None
        T("O8", "确认票据", "过期票据 / 被篡改的签名 → 都拒绝（且单元级 verify 也说无效）",
          f"给 bank_id={oc_id} 签两张废票：ttl=-1（已过期）、payload 末尾被改一个字符",
          "confirm_ticket.verify ×2（单元级） + execute ×2（HTTP）",
          "单元级两次都返回无效；HTTP 两次都 success=False 且 error 提到确认票据；题库仍在",
          unit_exp[0] is False and unit_tamper[0] is False
          and r8a.get("success") is False and "确认票据" in str(r8a.get("error"))
          and r8b.get("success") is False and "确认票据" in str(r8b.get("error"))
          and still_c8,
          f"单元exp={unit_exp} 单元tamper={unit_tamper} "
          f"http.exp={r8a.get('success')} http.tamper={r8b.get('success')} 仍在={still_c8}")

        # --- O9 autoConfirm=false：**所有写操作**都要确认（不只破坏性）---
        # 这条同时锁住 preview 的 autoConfirm 透传：客户端必须能把同一个开关值给 preview，
        # 否则「execute 说要票、preview 却按 autoConfirm=true 判成不需要」→ 死锁（根本拿不到票）。
        t_d = await ticket_for("bank_manage", {"action": "create", "bank_name": o_d},
                               auto_confirm=False)
        r9a = await execute_raw("bank_manage", {"action": "create", "bank_name": o_d},
                                auto_confirm=False, confirmed=False, ticket=t_d or "")
        created_d = (await _o_bank_id(o_d)) is not None
        r9b = await execute_raw("bank_manage", {"action": "create", "bank_name": o_e},
                                auto_confirm=False, confirmed=True)
        created_e = (await _o_bank_id(o_e)) is not None
        T("O9", "确认票据", "autoConfirm=false：非破坏性写操作也要票据（有票执行 / 无票拒绝）",
          f"两个 create（{o_d} / {o_e}）都带 autoConfirm=false；{o_d} 带票、{o_e} 不带票",
          "preview(autoConfirm=false) 取票 → execute ×2",
          "不带票的那次：success=False 且 error 提到确认票据、**题库没建出来**；"
          "带票的那次：success=True 且题库真的建出来了（票据是「授权」而不是「一律拒绝」）",
          isinstance(t_d, str) and bool(t_d) and r9a.get("success") is True and created_d
          and r9b.get("success") is False and "确认票据" in str(r9b.get("error"))
          and not created_e,
          f"票={'有' if t_d else '无'} 带票create={r9a.get('success')}(建出={created_d}) "
          f"无票create={r9b.get('success')}(建出={created_e}) "
          f"error={str(r9b.get('error'))[:36]!r}")

        # ================= P. 本轮新增的五组工具（#4 验收）=================
        # 背景（2026-09-22，api-tools 交付后后端冻结）：本轮给 Agent 加了五组能力 ——
        #   `question_flag_manage`（错题本 / 收藏 / 斩题**三合一**，用 flag_type 区分）、
        #   `memory_manage`（长期记忆管理）、`learning_stats`（学习统计，**只读**）、
        #   `knowledge_base_manage`（知识库管理）、`bank_share_manage`（分享 / 领取 / 复制）。
        #
        # 本组锁四件事（缺一个都会留下「看着有、其实不敢用」的能力）：
        #   ① **注册可见性**：工具出现在 `/ai/agent/tools` 与 `meta` 事件里，action 枚举与实现一致；
        #      **只读工具一条都不许进 `actions` 的写 / 破坏性清单**（进了前端每次检索都弹确认卡片）
        #   ② **越权**：每个工具每个 action 在「自己的 userId + **别人的**资源 id」下必须失败，
        #      且**无副作用**（别人的记录 / 知识库 / 分享 / 记忆一行都没被动）
        #   ③ **确认语义**：破坏性 action 不带服务端票据必须被拒，且**没有副作用**
        #      （正向对照也要有：带票据真的执行 —— 否则「一律拒绝」也能全绿）
        #   ④ **隔离**：list / search 只回自己的数据（别人的夹具一条都不许出现）
        #   ⑤ **联动**（P25）：新工具造出来的状态要能被旧工具正常处理 ——
        #      「先加标记、再让助手删掉这道题」实测曾经 FK violation（见 `_purge_questions`）
        #
        # 夹具（**全部自己造 + 打标记**，绝不拿真实用户数据当靶子）：
        #   · **自己的**题库 / 题目 / 知识库 / 分享 / 标记记录：走工具建，名字带 `PREFIX`
        #     → 收尾的 `cleanup()` 按名 / 按登记 id 删掉；
        #   · **另一个用户的**题库/题目/三类记录/分享/记忆/知识库/文档：直接插库，名字与内容
        #     一律带 `OTHER_IDOR_MARK` / `PREFIX` 标记（沿用 N 组那几道清理网），
        #     本组结束时再按**登记的精确 id**物理删一遍。
        #   · ⚠️ 别人的题库刻意建成**私密**（`is_public=1`）：题库表里 `0` **才是公开**，
        #     公开库里的题本来就该看得见 —— 拿公开库当靶子会得到一个「假红 / 假绿」。
        P_MARK = PREFIX + "P"
        p_own_bank = P_MARK + "自己的库"
        p_own_q = P_MARK + "自己的题干"
        p_own_kb = P_MARK + "自己的知识库"
        p_own_kb2 = P_MARK + "自己的知识库2"
        p_own_mem_text = PREFIX + "P自己造的待忘记忆"
        P_OTH_MARK = OTHER_IDOR_MARK + "P"
        p_oth_bank = P_OTH_MARK + "私密库"
        p_oth_q = P_OTH_MARK + "题干"
        p_oth_kb = P_OTH_MARK + "他人知识库"
        p_oth_doc = P_OTH_MARK + "他人文档.txt"
        p_oth_mem_text = PREFIX + "P他人的记忆（不许被别人读到 / 删掉）"
        p_oth_tok = PREFIX + "P_share_token"
        p_oth_code = "P9E2E1"  # 6 位分享码（share_code 是 String(12)）

        P_NEW_TOOLS_SET = {
            "question_flag_manage", "memory_manage", "learning_stats",
            "knowledge_base_manage", "bank_share_manage",
        }
        #: 只读工具：不进 `actions`，执行时也不需要确认（`write_operation = False`）
        P_READONLY_TOOLS = ("learning_stats", "knowledge_search", "memory_search")
        P_STATS_ACTIONS = ("overview", "by_subject", "trend", "error_analysis", "growth")
        #: 写 / 破坏性清单的期望值（**实测**自工具类，不是抄文档）
        P_EXPECTED_WD = {
            "question_flag_manage": ({"add", "master", "remove"}, {"remove"}),
            "memory_manage": ({"forget", "clear"}, {"forget", "clear"}),
            "knowledge_base_manage": (
                {"create", "update", "delete", "delete_document"},
                {"delete", "delete_document"},
            ),
            "bank_share_manage": (
                {"share", "revoke", "receive", "copy"}, {"revoke"},
            ),
        }
        #: 三类标记记录的表 / 主键列 / 状态列（**字面量**，不接受任何外部输入拼进 SQL）
        P_KIND_SQL = {
            "error": ("user_question_error", "error_id", "status"),
            "favorite": ("user_question_favorite", "favorite_id", "favorite_status"),
            "marked": ("user_question_marked", "marked_id", "marked_status"),
        }

        async def p_scalar(sql, **params):
            async with async_session_factory() as cdb:
                return await cdb.scalar(text(sql), params)

        async def p_row(sql, **params):
            async with async_session_factory() as cdb:
                return (await cdb.execute(text(sql), params)).first()

        async def p_exec(sql, **params):
            async with async_session_factory() as cdb:
                await cdb.execute(text(sql), params)
                await cdb.commit()

        async def p_count(sql, **params):
            return int(await p_scalar(sql, **params) or 0)

        def p_skip(cid, module, reason="库里只有一个用户：本组需要「别人的资源」，跳过"):
            T(cid, module, "(需要第二个用户的夹具)", "-", "-", reason, False, "skip")

        # 本组夹具登记的精确 id（收尾按它们物理删）
        p_own_kb_ids = []
        p_oth = {}

        # 「别人的真实数据一条没少」的观察基线（**只读采样**，收尾回比；
        # 规则里那条「读真实用户数据必须断言行数不变」就是它）。
        p_watch_tables = (
            ("question_bank", "user_id"),
            ("bank_share", "owner_id"),
            ("ai_agent_memory", "user_id"),
            ("rag_knowledge_base", "user_id"),
            ("user_question_error", "user_id"),
            ("user_question_favorite", "user_id"),
            ("user_question_marked", "user_id"),
        )
        p_watch_before = {}

        # ---- 自己的夹具（全部走工具，与本套件既有夹具同一套清理网）----
        _r = await execute("bank_manage",
                           {"action": "create", "bank_name": p_own_bank, "subject": "P组夹具"})
        p_own_bank_id = (_r.get("bank") or {}).get("bankId")
        _r = await execute("question_manage",
                           {"action": "create", "bank_id": p_own_bank_id,
                            "question_text": p_own_q})
        p_own_qid = _r.get("questionId")

        _r = await execute("knowledge_base_manage", {"action": "create", "name": p_own_kb})
        p_own_kb_id = _r.get("kbId")
        if p_own_kb_id:
            p_own_kb_ids.append(int(p_own_kb_id))
        _r = await execute("knowledge_base_manage", {"action": "create", "name": p_own_kb2})
        p_own_kb2_id = _r.get("kbId")
        if p_own_kb2_id:
            p_own_kb_ids.append(int(p_own_kb2_id))
        # 收尾的 `cleanup()` 按**登记的精确 id** 物理删（外键顺序 qa → chunk → doc → kb）。
        # ⚠️ 必须登记：`delete_knowledge_base` 是**逻辑删**（del_flag='2'），
        #    不物理删就会在库里留残骸，下一轮再建同名库还会撞「已存在」。
        _RAG_FIXTURE_KB_IDS.extend(p_own_kb_ids)

        _r = await execute("bank_share_manage", {"action": "share", "bank_id": p_own_bank_id})
        p_own_share_id = _r.get("shareId")

        # ---- 「另一个用户」的夹具（直接插库：不消耗模型 / 不跑 embedding）----
        if uid_other:
            for _t, _c in p_watch_tables:
                p_watch_before[_t] = await p_count(
                    f"SELECT count(*) FROM {_t} WHERE {_c} = :u", u=uid_other)
            async with async_session_factory() as cdb:
                await cdb.execute(text(
                    "INSERT INTO question_bank (bank_name, subject, description, "
                    "total_questions, status, user_id, is_public) "
                    "VALUES (:n, :s, :d, 1, '0', :u, 1)"
                ), {"n": p_oth_bank, "s": "越权夹具",
                    "d": P_OTH_MARK + "夹具（私密：is_public=1）", "u": uid_other})
                o_bank = await cdb.scalar(text(
                    "SELECT id FROM question_bank WHERE bank_name = :n AND user_id = :u "
                    "ORDER BY id DESC LIMIT 1"), {"n": p_oth_bank, "u": uid_other})
                o_bank = int(o_bank)
                await cdb.execute(text(
                    "INSERT INTO question_main (bank_id, question_type, difficulty, "
                    "question_text, answer, has_sub_questions, sort_order, score, status) "
                    "VALUES (:b, 1, 1, :t, '0', 0, 1, 0, '0')"
                ), {"b": o_bank, "t": p_oth_q})
                o_q = await cdb.scalar(text(
                    "SELECT id FROM question_main WHERE bank_id = :b AND question_text = :t "
                    "ORDER BY id DESC LIMIT 1"), {"b": o_bank, "t": p_oth_q})
                o_q = int(o_q)
                # 三类标记记录（各一条）：用来验「按 id 定位」有没有带 user_id。
                # 错题的 error_count 刻意给 9999 —— 只要某处漏了 user_id 过滤，
                # 它就会窜到 uid 的「错得最多 TOP5」第一名（隔离用例据此变红）。
                # ⚠️ 这三张表的 ORM `default=0` **不是** server_default（实测 PG：
                #    review_count / error_times / is_starred… 都是 NOT NULL 无默认值），
                #    直接插库必须把它们全列出来，否则 NotNullViolation。
                await cdb.execute(text(
                    "INSERT INTO user_question_error (user_id, question_id, bank_id, "
                    "error_count, review_count, status, is_mastered) "
                    "VALUES (:u, :q, :b, 9999, 0, 1, 0)"
                ), {"u": uid_other, "q": o_q, "b": o_bank})
                o_err = await cdb.scalar(text(
                    "SELECT error_id FROM user_question_error WHERE user_id = :u "
                    "AND question_id = :q ORDER BY error_id DESC LIMIT 1"),
                    {"u": uid_other, "q": o_q})
                await cdb.execute(text(
                    "INSERT INTO user_question_favorite (user_id, question_id, bank_id, "
                    "error_times, correct_times, review_count, is_starred, favorite_status) "
                    "VALUES (:u, :q, :b, 0, 0, 0, 0, 1)"
                ), {"u": uid_other, "q": o_q, "b": o_bank})
                o_fav = await cdb.scalar(text(
                    "SELECT favorite_id FROM user_question_favorite WHERE user_id = :u "
                    "AND question_id = :q ORDER BY favorite_id DESC LIMIT 1"),
                    {"u": uid_other, "q": o_q})
                await cdb.execute(text(
                    "INSERT INTO user_question_marked (user_id, question_id, bank_id, "
                    "marked_type, error_times_before_mark, correct_times_before_mark, "
                    "review_count, is_mastered, marked_status) "
                    "VALUES (:u, :q, :b, 1, 0, 0, 0, 0, 1)"
                ), {"u": uid_other, "q": o_q, "b": o_bank})
                o_mrk = await cdb.scalar(text(
                    "SELECT marked_id FROM user_question_marked WHERE user_id = :u "
                    "AND question_id = :q ORDER BY marked_id DESC LIMIT 1"),
                    {"u": uid_other, "q": o_q})
                # 别人发出的一条分享（`share_id` 是全局自增 → 只按 id 取就能撤销别人的分享）
                await cdb.execute(text(
                    "INSERT INTO bank_share (bank_id, owner_id, share_token, share_code, "
                    "permission, message, receive_count, status) "
                    "VALUES (:b, :u, :t, :c, 'read', :msg, 0, '0')"
                ), {"b": o_bank, "u": uid_other, "t": p_oth_tok, "c": p_oth_code,
                    "msg": P_OTH_MARK + "夹具分享"})
                o_share = await cdb.scalar(text(
                    "SELECT id FROM bank_share WHERE share_token = :t"),
                    {"t": p_oth_tok})
                # 别人的一条长期记忆（memory_manage.forget 不许删到它）
                await cdb.execute(text(
                    "INSERT INTO ai_agent_memory (user_id, memory_type, content, importance) "
                    "VALUES (:u, 'episodic', :c, 5)"
                ), {"u": uid_other, "c": p_oth_mem_text})
                o_mem = await cdb.scalar(text(
                    "SELECT id FROM ai_agent_memory WHERE user_id = :u AND content = :c "
                    "ORDER BY id DESC LIMIT 1"), {"u": uid_other, "c": p_oth_mem_text})
                # 别人的知识库 + 文档（**不建 chunk**：零 embedding，不花钱）
                await cdb.execute(text(
                    "INSERT INTO rag_knowledge_base (user_id, name, description, "
                    "embedding_model, embedding_dim, chunk_size, chunk_overlap, "
                    "doc_count, chunk_count, status, del_flag, disabled) "
                    "VALUES (:u, :n, :d, :m, 1024, 800, 100, 1, 0, '0', '0', 0)"
                ), {"u": uid_other, "n": p_oth_kb, "d": P_OTH_MARK + "夹具",
                    "m": "BAAI/bge-m3"})
                o_kb = await cdb.scalar(text(
                    "SELECT id FROM rag_knowledge_base WHERE user_id = :u AND name = :n "
                    "ORDER BY id DESC LIMIT 1"), {"u": uid_other, "n": p_oth_kb})
                await cdb.execute(text(
                    "INSERT INTO rag_document (kb_id, user_id, file_name, file_type, "
                    "file_size, chunk_count, status) "
                    "VALUES (:k, :u, :n, 'txt', 12, 0, 1)"
                ), {"k": int(o_kb), "u": uid_other, "n": p_oth_doc})
                o_doc = await cdb.scalar(text(
                    "SELECT id FROM rag_document WHERE kb_id = :k AND file_name = :n "
                    "ORDER BY id DESC LIMIT 1"), {"k": int(o_kb), "n": p_oth_doc})
                await cdb.commit()
            p_oth = {
                "bank": o_bank, "q": o_q, "err": int(o_err), "fav": int(o_fav),
                "mrk": int(o_mrk), "share": int(o_share), "mem": int(o_mem),
                "kb": int(o_kb), "doc": int(o_doc),
            }
            _RAG_FIXTURE_KB_IDS.append(p_oth["kb"])

        # ---- ① 注册可见性 ----
        _rp = await client.get("/ai/agent/tools")
        _pb = _rp.json() or {}
        p_tools = _pb.get("tools") or []
        p_actions = _pb.get("actions") or {}
        p_payload_names = _tool_names(p_tools)
        # 「启用中」= payload 里 disabled == 0 的那一份（meta 事件只广播它们）
        p_enabled = {
            ((t or {}).get("function") or {}).get("name")
            for t in p_tools if not (t or {}).get("disabled")
        }
        p_disabled = p_payload_names - p_enabled
        # f-string 里的推导式**不能跨相邻字面量**（写成两段相邻字符串会 SyntaxError）→ 先算好
        p1_enum_bad = [n for n in sorted(P_NEW_TOOLS_SET)
                       if n in EXPECTED_ACTION_ENUMS
                       and set(_action_enum(p_tools, n) or []) != EXPECTED_ACTION_ENUMS[n]]
        p1_qfm_required = next(
            (((t.get("function") or {}).get("parameters") or {}).get("required") or []
             for t in p_tools
             if ((t.get("function") or {}).get("name")) == "question_flag_manage"), [])

        T("P1", "新工具注册", "GET /ai/agent/tools 下发 5 个新工具，且 action 枚举与实现逐个一致",
          "已登录；新工具 = question_flag_manage / memory_manage / learning_stats / "
          "knowledge_base_manage / bank_share_manage",
          "GET /ai/agent/tools → 按名字取 parameters.properties.action.enum 逐个比对",
          "5 个新工具都在 tools 里；每个的 action 枚举集合 == 期望集合；"
          "question_flag_manage 的 required 含 flag_type（漏了会静默写错表）",
          P_NEW_TOOLS_SET <= p_payload_names
          and all(set(_action_enum(p_tools, n) or []) == e
                  for n, e in EXPECTED_ACTION_ENUMS.items() if n in P_NEW_TOOLS_SET)
          and "flag_type" in p1_qfm_required,
          f"缺失={sorted(P_NEW_TOOLS_SET - p_payload_names)} 枚举对不上的={p1_enum_bad} "
          f"flag_type必填={'flag_type' in p1_qfm_required} "
          f"全部工具数={len(p_payload_names)}")

        p_sid = f"asst_e2e_{int(time.time() * 1000)}_p"
        _SESSION_IDS.append(p_sid)
        # 脚本队列：本套件每组都是「push 一个、pop 一个」，所以这里非空说明有组漏消费；
        # 打印出来（而不是默默 clear）——否则本组会拿到别人剩的脚本、断言看着莫名其妙地红。
        if SCRIPTS:
            print(f"  [WARN] P 组开始前 SCRIPTS 队列残留 {len(SCRIPTS)} 条（会被本组误用）")
        SCRIPTS.clear()
        SCRIPTS.append([[FakeChunk("我这一轮不需要工具。")]])
        ev_p = await run_stream({
            "message": "你能做什么？", "sessionId": p_sid, "userId": uid,
            "provider": "deepseek", "model": "deepseek-flash", "autoConfirm": True,
        })
        p_meta = next((e for e in ev_p if e.get("type") == "meta"), {})
        p_meta_tools = p_meta.get("tools") or []
        p_meta_names = {t.get("name") for t in p_meta_tools}
        T("P2", "新工具注册", "meta 事件把新工具广播给前端（且只广播**启用中**的工具）",
          f"sessionId={p_sid}；payload 里 disabled!=0 的工具={sorted(p_disabled) or '无'}",
          "POST /ai/agent/stream → 取 meta.tools[].name",
          "meta.tools 的名字集合 == payload 里 disabled==0 的那一份；"
          "新工具只要没被屏蔽就必须在 meta 里（前端工具条靠它渲染）；每条描述非空",
          p_meta_names == p_enabled
          and (P_NEW_TOOLS_SET - p_disabled) <= p_meta_names
          and all((t.get("description") or "").strip() for t in p_meta_tools),
          f"meta={sorted(p_meta_names)} enabled={sorted(p_enabled)} "
          f"新工具缺失={sorted((P_NEW_TOOLS_SET - p_disabled) - p_meta_names)}")

        p_ro_in_actions = [n for n in P_READONLY_TOOLS if n in p_actions]
        p_stats_actions_leaked = sorted(
            set(P_STATS_ACTIONS)  # ⚠️ 必须显式 set()：tuple & set 会 TypeError
            & {a for v in p_actions.values() for k in ("write", "destructive")
               for a in (v.get(k) or [])}
        )
        T("P3", "新工具注册", "只读工具不进 actions 的写 / 破坏性清单（否则每次检索都弹确认卡片）",
          "learning_stats 全 5 个 action / knowledge_search / memory_search 都是只读的",
          "GET /ai/agent/tools → actions",
          "三个只读工具都不在 actions 的键里；learning_stats 的 5 个 action 名"
          "不出现在**任何**工具的 write / destructive 清单里",
          not p_ro_in_actions and not p_stats_actions_leaked,
          f"只读出现在的={p_ro_in_actions} 统计 action 泄漏={p_stats_actions_leaked}")

        p_wd_actual = {}
        for _n, (_w, _d) in P_EXPECTED_WD.items():
            _v = p_actions.get(_n) or {}
            p_wd_actual[_n] = (sorted(_v.get("write") or []), sorted(_v.get("destructive") or []))
        T("P4", "新工具注册", "4 个有新工具（按 action 判定）不误报也不漏报 write/destructive",
          "expect：question_flag_manage 只有 remove 破坏性（master 保留记录）；"
          "memory_manage 两个 action 都破坏性；knowledge_base_manage 删库/删文档；"
          "bank_share_manage 只有 revoke",
          "GET /ai/agent/tools → actions[<tool>] 与期望集合逐个比对",
          "四个工具的 write / destructive 集合与期望**完全相等**（集合比较，顺序不是契约）",
          all(set(p_wd_actual[n][0]) == w and set(p_wd_actual[n][1]) == d
              for n, (w, d) in P_EXPECTED_WD.items()),
          f"实际={p_wd_actual}")

        p_stats_res = {}
        for _a in P_STATS_ACTIONS:
            # autoConfirm=false + **不带票据**：只读工具必须照常执行，且不该给 needsConfirm
            p_stats_res[_a] = await execute_raw(
                "learning_stats", {"action": _a}, auto_confirm=False, confirmed=False)
        T("P5", "新工具注册", "learning_stats 是只读的：autoConfirm=false 且无票据也照常执行",
          "5 个 action 全部走 /ai/agent/execute（不带 confirmTicket）",
          "execute_raw(learning_stats, autoConfirm=false) ×5",
          "5 个都 success=True 且**不带** needsConfirm（只有写/破坏性操作才要确认）；"
          "每个都有非空 message（给用户看的人话回执）",
          all(v.get("success") is True and v.get("needsConfirm") is not True
              and bool(v.get("message")) for v in p_stats_res.values()),
          # ⚠️ 这里用**列表**推导式：f-string 里的裸生成器表达式会被求值成 `<generator object …>`
          #    （实测），`actual` 就变成一行没用的 repr —— 而这行正是失败时人要读的证据。
          f"逐个={[(a, v.get('success'), v.get('needsConfirm')) for a, v in p_stats_res.items()]}")

        # ---- ② 参数校验 / 自纠（三条 api-tools 自测过的红点）----
        r6 = await execute_raw("question_flag_manage", {"action": "list"})
        T("P6", "新工具参数校验", "缺必填 flag_type → 参数校验层就拦下（不是执行到一半才发现）",
          "question_flag_manage 的 flag_type 是 required（不给默认值 —— 否则会静默写进错题本）",
          "execute_raw(question_flag_manage, {action: list})（不带 flag_type）",
          "success=False；error 以「参数校验失败」开头；validationErrors 含「缺少必填参数 flag_type」；"
          "hint 非空（模型据此补参数）",
          r6.get("success") is False and "参数校验失败" in str(r6.get("error"))
          and any("flag_type" in str(e) for e in (r6.get("validationErrors") or []))
          and bool(r6.get("hint")),
          f"error={str(r6.get('error'))[:60]!r} validationErrors={r6.get('validationErrors')}")

        r7 = await execute_raw("question_flag_manage",
                               {"action": "master", "flag_type": "favorite", "record_id": 1})
        T("P7", "新工具参数校验", "flag_type=favorite + master → 拒绝（收藏不支持「标记已掌握」）",
          "master 只对错题本有意义（favorite / marked 都没有这个 action）",
          "execute_raw(question_flag_manage, {action: master, flag_type: favorite})",
          "success=False；error 明说**不支持**；hint 点明 master 只对错题本 + 列出该 flag_type 的合法 action",
          r7.get("success") is False and "不支持" in str(r7.get("error"))
          and "master" in str(r7.get("hint")),
          f"error={str(r7.get('error'))[:46]!r} hint={str(r7.get('hint'))[:70]!r}")

        r8 = await execute_raw("question_flag_manage",
                               {"action": "list", "flag_type": "error", "error_id": 1})
        T("P8", "新工具参数校验", "旧参数名 error_id → 「不支持的参数」+ hint 列出全部合法参数",
          "入参统一成了 record_id（旧的三工具版本用的是 error_id / favorite_id / marked_id）",
          "execute_raw(question_flag_manage, {action: list, flag_type: error, error_id: 1})",
          "success=False；error 含「不支持的参数 error_id」；hint 从 schema 生成、含 record_id 等合法键",
          r8.get("success") is False and "不支持的参数 error_id" in str(r8.get("error"))
          and all(k in str(r8.get("hint"))
                  for k in ("record_id", "flag_type", "question_id", "keyword")),
          f"error={str(r8.get('error'))[:60]!r} hint={str(r8.get('hint'))[:90]!r}")

        # ---- ③ 越权：自己的 userId + 别人的资源 id ----
        if not p_oth:
            # 需要「别人的资源」才谈得上的用例（越权 / 隔离 / 收尾回比）——
            # 没有第二个用户时它们是**没测到东西**，不是「没问题」（与 N 组同一口径）
            for _c, _m in (("P9", "新工具越权"), ("P10", "新工具越权"), ("P11", "新工具越权"),
                           ("P12", "新工具越权"), ("P13", "新工具越权"), ("P14", "新工具越权"),
                           ("P15", "新工具越权"), ("P19", "新工具隔离"), ("P20", "新工具隔离"),
                           ("P21", "新工具隔离"), ("P22", "新工具隔离"), ("P23", "新工具隔离"),
                           ("P26", "新工具收尾")):
                p_skip(_c, _m)
        else:
            # --- P9 用别人的 record_id 删三类记录 ---
            p_res9 = {}
            for _k, (_tbl, _idc, _sc) in P_KIND_SQL.items():
                _rid = p_oth[{"error": "err", "favorite": "fav", "marked": "mrk"}[_k]]
                p_res9[_k] = await execute("question_flag_manage",
                                           {"action": "remove", "flag_type": _k,
                                            "record_id": _rid})
                p_res9[_k + "_left"] = await p_count(
                    f"SELECT count(*) FROM {_tbl} WHERE {_idc} = :i", i=_rid)
            T("P9", "新工具越权", "remove 拿别人的 errorId / favoriteId / markedId → 全被拒且一条没删",
              f"三条记录的 id 来自 uid={uid_other}（本组的他人夹具），本请求登录态 uid={uid}",
              "execute(question_flag_manage, {action: remove, flag_type: <三种>, record_id: <别人的>})"
              "（走 execute ⇒ preview 会给票，所以拦下的**不是**票据闸门）",
              "三次都 success=False；error 里**不含**「确认票据」（证明拦在归属校验，不是票据）；"
              "三条记录在库里都还在",
              all(p_res9[_k].get("success") is False
                  and "确认票据" not in str(p_res9[_k].get("error"))
                  and bool(p_res9[_k].get("hint")) for _k in P_KIND_SQL)
              and all(p_res9[_k + "_left"] == 1 for _k in P_KIND_SQL),
              f"逐个={ {k: (v.get('success'), str(v.get('error'))[:26]) for k, v in p_res9.items() if not k.endswith('_left')} } "
              f"仍在={ {k: p_res9[k + '_left'] for k in P_KIND_SQL} }")

            # --- P10 用别人的 errorId 标「已掌握」（不是删除 → 但同样要带 user_id）---
            r10 = await execute("question_flag_manage",
                                {"action": "master", "flag_type": "error",
                                 "record_id": p_oth["err"]})
            _row10 = await p_row(
                "SELECT is_mastered, status FROM user_question_error WHERE error_id = :i",
                i=p_oth["err"])
            T("P10", "新工具越权", "master 拿别人的 errorId → 被拒且记录没被改成「已掌握」",
              f"error_id={p_oth['err']} 属于 uid={uid_other}",
              "execute(question_flag_manage, {action: master, flag_type: error, record_id: <别人的>})"
              " → 回读该行 is_mastered / status",
              "success=False 且有 hint；库里该行仍是 (is_mastered=0, status=1)（没被改）",
              r10.get("success") is False and bool(r10.get("hint"))
              and _row10 is not None and tuple(_row10) == (0, 1),
              f"success={r10.get('success')} error={str(r10.get('error'))[:34]!r} "
              f"库里(is_mastered,status)={tuple(_row10) if _row10 else None}")

            # --- P11 把别人私密题库里的题加进自己的标记 ---
            p_res11 = {}
            for _k in P_KIND_SQL:
                p_res11[_k] = await execute("question_flag_manage",
                                            {"action": "add", "flag_type": _k,
                                             "question_id": p_oth["q"]})
            p_added_own = await p_count(
                "SELECT (SELECT count(*) FROM user_question_error WHERE user_id = :u AND question_id = :q)"
                " + (SELECT count(*) FROM user_question_favorite WHERE user_id = :u AND question_id = :q)"
                " + (SELECT count(*) FROM user_question_marked WHERE user_id = :u AND question_id = :q)",
                u=uid, q=p_oth["q"])
            T("P11", "新工具越权", "add 别人**私密**题库里的题 ×3 → 全被拒且自己名下没造出记录",
              f"question_id={p_oth['q']} 在 uid={uid_other} 的私密库「{p_oth_bank}」里（is_public=1）",
              "execute(question_flag_manage, {action: add, flag_type: <三种>, question_id: <别人的>})"
              " → 数 uid 名下指向该题的记录",
              "三次都 success=False（可见性闸门）；uid 名下指向该题的记录数 == 0"
              "（不然就是「借自己的账号读别人的题」）",
              all(v.get("success") is False and bool(v.get("hint")) for v in p_res11.values())
              and p_added_own == 0,
              f"逐个={ {k: (v.get('success'), str(v.get('error'))[:26]) for k, v in p_res11.items()} } "
              f"自己名下新增={p_added_own}")

            # --- P12 knowledge_base_manage：4 个按 id 的 action 全部要判归属 ---
            p_res12 = {}
            p_res12["update"] = await execute("knowledge_base_manage", {
                "action": "update", "kb_id": p_oth["kb"], "name": P_OTH_MARK + "被改名"})
            p_res12["delete"] = await execute("knowledge_base_manage", {
                "action": "delete", "kb_id": p_oth["kb"]})
            p_res12["list_documents"] = await execute("knowledge_base_manage", {
                "action": "list_documents", "kb_id": p_oth["kb"]})
            p_res12["delete_document"] = await execute("knowledge_base_manage", {
                "action": "delete_document", "doc_id": p_oth["doc"]})
            _kb12 = await p_row(
                "SELECT name, del_flag FROM rag_knowledge_base WHERE id = :i", i=p_oth["kb"])
            _doc12 = await p_count("SELECT count(*) FROM rag_document WHERE id = :i",
                                   i=p_oth["doc"])
            T("P12", "新工具越权", "knowledge_base_manage 用别人的 kbId / docId → 4 个 action 全被拒",
              f"kb_id={p_oth['kb']} / doc_id={p_oth['doc']} 属于 uid={uid_other}",
              "execute(knowledge_base_manage, update/delete/list_documents 用别人的 kb_id；"
              "delete_document 用别人的 doc_id)（delete/delete_document 的票由 preview 正常下发）",
              "四个都 success=False 且 error 不含「确认票据」（拦在归属，不是票据）；"
              "库里该知识库名未变、del_flag 仍 '0'，文档仍在",
              all(v.get("success") is False and "确认票据" not in str(v.get("error"))
                  for v in p_res12.values())
              and _kb12 is not None and tuple(_kb12) == (p_oth_kb, "0") and _doc12 == 1,
              f"逐个={ {k: (v.get('success'), str(v.get('error'))[:24]) for k, v in p_res12.items()} } "
              f"库里(name,del_flag)={tuple(_kb12) if _kb12 else None} 文档数={_doc12}")

            # --- P13 bank_share_manage：share / copy 用别人的银行、revoke 用别人的分享 ---
            p_res13 = {}
            p_res13["share"] = await execute("bank_share_manage",
                                             {"action": "share", "bank_id": p_oth["bank"]})
            p_res13["copy"] = await execute("bank_share_manage",
                                            {"action": "copy", "bank_id": p_oth["bank"]})
            p_res13["revoke"] = await execute("bank_share_manage",
                                              {"action": "revoke", "share_id": p_oth["share"]})
            _share13 = await p_scalar("SELECT status FROM bank_share WHERE id = :i",
                                      i=p_oth["share"])
            _copy13 = await p_count(
                "SELECT count(*) FROM question_bank WHERE user_id = :u AND bank_name = :n",
                u=uid, n=p_oth_bank + "（副本）")
            T("P13", "新工具越权", "bank_share_manage：分享/复制别人的题库、撤销别人的分享 → 全被拒",
              f"bank_id={p_oth['bank']}（别人的私密库）、share_id={p_oth['share']}（别人发出的分享）",
              "execute(bank_share_manage, share/copy 用别人的 bank_id；revoke 用别人的 share_id)\n"
              "→ 回读那条分享的 status / 数 uid 名下有没有「（副本）」出现",
              "三个都 success=False；那条分享仍是 '0'（有效）；uid 名下没有多出一个副本题库",
              all(v.get("success") is False for v in p_res13.values())
              and _share13 == "0" and _copy13 == 0,
              f"逐个={ {k: (v.get('success'), str(v.get('error'))[:26]) for k, v in p_res13.items()} } "
              f"分享status={_share13!r} 副本数={_copy13}")

            # --- P14 memory_manage.forget 拿别人的 memory_id ---
            r14 = await execute("memory_manage",
                                {"action": "forget", "memory_id": p_oth["mem"]})
            _mem14 = await p_count("SELECT count(*) FROM ai_agent_memory WHERE id = :i",
                                   i=p_oth["mem"])
            T("P14", "新工具越权", "memory_manage.forget 拿别人的 memory_id → 被拒且那条记忆还在",
              f"memory_id={p_oth['mem']} 属于 uid={uid_other}",
              "execute(memory_manage, {action: forget, memory_id: <别人的>})（票由 preview 正常下发）"
              " → 数该行是否还在",
              "success=False；error 不含「确认票据」；库里的记忆条数仍是 1（删记忆不可恢复）",
              r14.get("success") is False and "确认票据" not in str(r14.get("error"))
              and _mem14 == 1,
              f"success={r14.get('success')} error={str(r14.get('error'))[:34]!r} 仍在={_mem14}")

            # --- P15 正向对照：同样的工具，**自己的**资源全都可用（不是一刀切拒绝）---
            p_pos = {}
            p_pos["own_add"] = await execute("question_flag_manage",
                                             {"action": "add", "flag_type": "error",
                                              "question_id": p_own_qid})
            _own_rid = p_pos["own_add"].get("errorId")
            # add 之后**必须**在活跃列表里（这一步才是「自己的记录读得到」的正向对照）
            p_pos["list_after_add"] = await execute("question_flag_manage",
                                                   {"action": "list", "flag_type": "error"})
            _ids_after_add = [q.get("errorId") for q in (p_pos["list_after_add"].get("errors") or [])]
            p_pos["own_master"] = await execute("question_flag_manage",
                                                {"action": "master", "flag_type": "error",
                                                 "record_id": _own_rid})
            # master 的语义是「**离开活跃列表**但**记录保留**」（status=0, is_mastered=1）——
            # 所以这里两条都要断言：列表里没了 **且** 行还在。少了后半句，
            # 「master 其实把行删了」也会绿；少了前半句，就该问「那它到底改了什么」。
            p_pos["list_after_master"] = await execute("question_flag_manage",
                                                      {"action": "list", "flag_type": "error"})
            _ids_after_master = [q.get("errorId")
                                for q in (p_pos["list_after_master"].get("errors") or [])]
            _own_row = await p_row(
                "SELECT is_mastered, status FROM user_question_error WHERE error_id = :i",
                i=_own_rid)
            _own_kb_names = [kb.get("name") for kb in (
                (await execute("knowledge_base_manage", {"action": "list"})).get("knowledgeBases") or [])]
            _own_share_ids = [s.get("shareId") for s in (
                (await execute("bank_share_manage", {"action": "list_shares"})).get("shares") or [])]
            T("P15", "新工具越权", "对照：自己的资源在同样这些工具下都可用（不是一刀切挡死）",
              f"自己的题库 {p_own_bank} / 自己的知识库 {p_own_kb} / 自己的分享 #{p_own_share_id}",
              "add(error) 自己的题 → list（应看得到）→ master 它 → 再 list（应看不到但行还在）"
              "；再 list 自己的知识库 / 自己的分享",
              "add / master 都 success=True；add 后自己的记录 id **在** list 里；"
              "master 后**不在** list 里但库里那行仍在且 (is_mastered=1, status=0)"
              "（master ≠ 删除）；自己的知识库名与 shareId 都在各自的列表里",
              p_pos["own_add"].get("success") is True
              and p_pos["own_master"].get("success") is True
              and _own_rid in _ids_after_add
              and _own_rid not in _ids_after_master
              and _own_row is not None and tuple(_own_row) == (1, 0)
              and p_own_kb in _own_kb_names and p_own_share_id in _own_share_ids,
              f"add={p_pos['own_add'].get('success')} master={p_pos['own_master'].get('success')} "
              f"add后在列表={_own_rid in _ids_after_add} master后在列表={_own_rid in _ids_after_master} "
              f"库里(is_mastered,status)={tuple(_own_row) if _own_row else None} "
              f"自己的库在列表里={p_own_kb in _own_kb_names} "
              f"自己的分享在列表里={p_own_share_id in _own_share_ids}")

        # ---- ④ 确认语义：破坏性 action 不带票据必须被拒且无副作用（正向对照也要有）----
        _rf = await execute("question_flag_manage",
                            {"action": "add", "flag_type": "favorite",
                             "question_id": p_own_qid})
        p_fav_id = _rf.get("favoriteId")
        r16a = await execute_raw("question_flag_manage",
                                 {"action": "remove", "flag_type": "favorite",
                                  "record_id": p_fav_id}, confirmed=True)
        _left16a = await p_count(
            "SELECT count(*) FROM user_question_favorite WHERE favorite_id = :i", i=p_fav_id)
        r16b = await execute("question_flag_manage",
                             {"action": "remove", "flag_type": "favorite",
                              "record_id": p_fav_id})
        _left16b = await p_count(
            "SELECT count(*) FROM user_question_favorite WHERE favorite_id = :i", i=p_fav_id)
        T("P16", "新工具确认", "remove 不带票据 → 被拒且一条没删；带票据 → 真的删（正向对照）",
          f"自己的收藏记录 favoriteId={p_fav_id}（PREFIX 夹具，不是真实数据）",
          "execute_raw(remove, confirmed=true, **不带 confirmTicket**) → 数该行；"
          "再 execute(remove, 自动取票) → 再数",
          "不带票那次：success=False、error 提到确认票据、needsConfirm=True，"
          "且该行**仍在**；带票那次：success=True 且该行真的没了",
          r16a.get("success") is False and "确认票据" in str(r16a.get("error"))
          and r16a.get("needsConfirm") is True and _left16a == 1
          and r16b.get("success") is True and _left16b == 0,
          f"无票: success={r16a.get('success')} needsConfirm={r16a.get('needsConfirm')} 仍在={_left16a}；"
          f"有票: success={r16b.get('success')} 仍在={_left16b}")

        r17a = await execute_raw("knowledge_base_manage",
                                 {"action": "delete", "kb_id": p_own_kb2_id}, confirmed=True)
        _kb17a = await p_count(
            "SELECT count(*) FROM rag_knowledge_base WHERE id = :i AND del_flag = '0'",
            i=p_own_kb2_id)
        r17b = await execute("knowledge_base_manage",
                             {"action": "delete", "kb_id": p_own_kb2_id})
        _kb17b = await p_count(
            "SELECT count(*) FROM rag_knowledge_base WHERE id = :i AND del_flag = '0'",
            i=p_own_kb2_id)
        T("P17", "新工具确认", "知识库 delete 不带票据 → 被拒且库还在；带票据 → 真的删（逻辑删）",
          f"自己刚建的空知识库 kbId={p_own_kb2_id}（零文档 → 零 embedding）",
          "execute_raw(delete, confirmed=true, 无票据) → 回读 del_flag；再 execute(delete) → 回读",
          "不带票那次：success=False、error 提到确认票据、needsConfirm=True，"
          "库里 del_flag 仍是 '0'；带票那次：success=True 且 del_flag 变成 '2'",
          r17a.get("success") is False and "确认票据" in str(r17a.get("error"))
          and r17a.get("needsConfirm") is True and _kb17a == 1
          and r17b.get("success") is True and _kb17b == 0,
          f"无票: success={r17a.get('success')} del_flag0计数={_kb17a}；"
          f"有票: success={r17b.get('success')} del_flag0计数={_kb17b}")

        await p_exec(
            "INSERT INTO ai_agent_memory (user_id, memory_type, content, importance) "
            "VALUES (:u, 'episodic', :c, 5)", u=uid, c=p_own_mem_text)
        p_own_mem_id = await p_scalar(
            "SELECT id FROM ai_agent_memory WHERE user_id = :u AND content = :c "
            "ORDER BY id DESC LIMIT 1", u=uid, c=p_own_mem_text)
        r18a = await execute_raw("memory_manage",
                                 {"action": "forget", "memory_id": p_own_mem_id}, confirmed=True)
        _mem18a = await p_count("SELECT count(*) FROM ai_agent_memory "
                                "WHERE id = :i AND del_flag = '0'", i=p_own_mem_id)
        r18b = await execute("memory_manage",
                             {"action": "forget", "memory_id": p_own_mem_id})
        # ⚠️ 2026-09-22 起删记忆是**逻辑删**（用户裁决「写操作可撤销 / 用户端删除全部逻辑删除」），
        #    所以这里从「数物理行」改成三句一起数：活跃 0 条 + **行还在** + del_flag='2'。
        #    原断言是 `count(*) == 0`（物理删时代的口径）—— 那个口径下「可恢复」这个需求
        #    根本无法成立（行都没了），留着它等于让套件把新需求判成红。
        _mem18b = await p_count("SELECT count(*) FROM ai_agent_memory "
                                "WHERE id = :i AND del_flag = '0'", i=p_own_mem_id)
        _mem18b_row = await p_count("SELECT count(*) FROM ai_agent_memory WHERE id = :i",
                                    i=p_own_mem_id)
        _mem18b_flag = await p_scalar("SELECT del_flag FROM ai_agent_memory WHERE id = :i",
                                      i=p_own_mem_id)
        T("P18", "新工具确认", "记忆 forget 不带票据 → 被拒且记忆还在；带票据 → 真的删（逻辑删，可恢复）",
          f"自己插的一条带标记记忆 memoryId={p_own_mem_id}（绝不拿真实记忆当靶子）",
          "execute_raw(forget, confirmed=true, 无票据) → 数该行（活跃口径）；再 execute(forget)"
          " → 活跃条数 + 物理行数 + del_flag 三样一起回读",
          "不带票那次：success=False、error 提到确认票据、needsConfirm=True，该行仍是**活跃**的；"
          "带票那次：success=True、deleted=1，活跃条数变 0，但**行还在**且 del_flag='2'"
          "（逻辑删 → 「最近删除」里能恢复）",
          r18a.get("success") is False and "确认票据" in str(r18a.get("error"))
          and r18a.get("needsConfirm") is True and _mem18a == 1
          and r18b.get("success") is True and r18b.get("deleted") == 1
          and _mem18b == 0 and _mem18b_row == 1 and _mem18b_flag == "2",
          f"无票: success={r18a.get('success')} 活跃={_mem18a}；"
          f"有票: success={r18b.get('success')} deleted={r18b.get('deleted')} "
          f"活跃={_mem18b} 行还在={_mem18b_row} del_flag={_mem18b_flag!r}")

        # ---- ⑤ 隔离：list / search 只回自己的数据 ----
        # ⚠️ 只有「有第二个用户」时才有意义：**没有别人的数据**就没有「隔离」可谈
        #    （此时上面已经按 skip 记过这几条，别在这里又报一次 FAIL）。
        if p_oth:
            p_iso = {}
            p_iso_totals_ok = True
            p_iso_own_hit = {}
            for _k, (_tbl, _idc, _sc) in P_KIND_SQL.items():
                # 先保证自己有一条第 _k 类记录（add 是幂等的：已存在则恢复，不重复插行）。
                # 这一步同时是**正向对照**：少了它，「列表里没有别人的数据」可能是「列表恒空」。
                await execute("question_flag_manage",
                              {"action": "add", "flag_type": _k, "question_id": p_own_qid})
                _rl = await execute("question_flag_manage", {"action": "list", "flag_type": _k})
                p_iso[_k] = _rl
                _uid_cnt = await p_count(
                    f"SELECT count(*) FROM {_tbl} WHERE user_id = :u AND {_sc} = 1", u=uid)
                p_iso_totals_ok = p_iso_totals_ok and _rl.get("total") == _uid_cnt
                p_iso_own_hit[_k] = p_own_q in json.dumps(_rl, ensure_ascii=False)
            T("P19", "新工具隔离", "三类 list 只回自己的记录：别人的夹具一条都不出现",
              f"别人的三类记录都指向题干「{p_oth_q}」（错题 error_count=9999，漏过滤就窜到最前；"
              f"自己的记录指向「{p_own_q}」）",
              "execute(question_flag_manage, {action: list, flag_type: <三种>})",
              "三个 list 的返回里都**不含**别人的题干；**都含**自己的题干（不是恒空列表）；"
              "total == 按 uid 在库里数出来的活跃条数（口径对不上说明过滤写错了）",
              all(p_oth_q not in json.dumps(v, ensure_ascii=False) for v in p_iso.values())
              and all(p_iso_own_hit.values())
              and p_iso_totals_ok,
              f"泄漏={ {k: (p_oth_q in json.dumps(v, ensure_ascii=False)) for k, v in p_iso.items()} } "
              f"自己那条在列表里={p_iso_own_hit} total对得上={p_iso_totals_ok}")

            _r20 = await execute("knowledge_base_manage", {"action": "list"})
            _kb_names20 = [kb.get("name") for kb in (_r20.get("knowledgeBases") or [])]
            p_own_kb_present = p_own_kb in _kb_names20
            _disabled_ok20 = all(isinstance(kb.get("disabled"), int)
                                 and not isinstance(kb.get("disabled"), bool)
                                 for kb in (_r20.get("knowledgeBases") or []))
            T("P20", "新工具隔离", "knowledge_base_manage.list 只回自己的库（管理列表口径）",
              f"自己的「{p_own_kb}」属于 uid；别人的「{p_oth_kb}」属于 uid={uid_other}",
              "execute(knowledge_base_manage, {action: list})",
              "列表里含自己的库名；**不含**别人的库名；count == len(knowledgeBases)；"
              "每项的 disabled 是**整数** 0/1（前端开关是受控的，拿到 null 会当场翻转并回写）",
              p_own_kb_present and p_oth_kb not in _kb_names20
              and _r20.get("count") == len(_kb_names20) and _disabled_ok20,
              f"自己的在={p_own_kb_present} 别人的在={p_oth_kb in _kb_names20} "
              f"count={_r20.get('count')}/{len(_kb_names20)} disabled都是整数={_disabled_ok20}")

            _r21 = await execute("bank_share_manage", {"action": "list_shares"})
            _shares21 = _r21.get("shares") or []
            _ids21 = [s.get("shareId") for s in _shares21]
            _codes21 = [s.get("shareCode") for s in _shares21]
            T("P21", "新工具隔离", "list_shares 只回自己发出的分享",
              f"别人的分享 #{p_oth['share']}（分享码 {p_oth_code}）属于 uid={uid_other}",
              "execute(bank_share_manage, {action: list_shares})",
              "列表里不含别人的 shareId / shareCode；含自己那条 shareId；"
              "count == len(shares) 且 total 是整数",
              p_oth["share"] not in _ids21 and p_oth_code not in _codes21
              and p_own_share_id in _ids21 and _r21.get("count") == len(_shares21)
              and isinstance(_r21.get("total"), int),
              f"别人的在里面={p_oth['share'] in _ids21} 自己的在={p_own_share_id in _ids21} "
              f"count={_r21.get('count')} total={_r21.get('total')}")

            _r22 = await execute("memory_manage", {"action": "list_types"})
            _items22 = _r22.get("memoryTypes") or []
            p_mem22_ok = True
            p_mem22_detail = {}
            for _it in _items22:
                _t22 = _it.get("memoryType")
                # ⚠️ 两处 SQL 都带 `del_flag = '0'`：工具侧从 2026-09-22 起只数**活跃**记忆
                #    （逻辑删的行不算），SQL 不跟着筛就会把 P18 刚软删的那条算成差异 → 假红。
                _uid22 = await p_count(
                    "SELECT count(*) FROM ai_agent_memory WHERE user_id = :u AND memory_type = :t"
                    " AND del_flag = '0'",
                    u=uid, t=_t22)
                _all22 = await p_count(
                    "SELECT count(*) FROM ai_agent_memory WHERE memory_type = :t"
                    " AND del_flag = '0'", t=_t22)
                p_mem22_detail[_t22] = (_it.get("count"), _uid22, _all22)
                p_mem22_ok = p_mem22_ok and _it.get("count") == _uid22
            # 对照：别人的记忆确实存在（全局计数 > uid 计数）→ 上面那条断言**能**分辨
            p_mem22_ctrl = any(u_c < a_c for (_c, u_c, a_c) in p_mem22_detail.values())
            T("P22", "新工具隔离", "list_types 的计数按「当前用户」数：与库里 uid 的行数逐类相等",
              "别人的夹具记忆（含标记）属于 uid_other，全局计数必然 > uid 计数",
              "execute(memory_manage, {action: list_types}) → 逐类与 SQL count 比对",
              "每一类的 count == 库里 uid 该类**活跃**（del_flag='0'）的行数；且存在某一类「全局 > uid」"
              "（证明夹具在、这条断言**能**分辨全局与按人过滤）",
              p_mem22_ok and p_mem22_ctrl,
              f"(工具count, uid库内, 全局)={p_mem22_detail} 对照(全局>uid)={p_mem22_ctrl}")

            _r23 = await execute("learning_stats", {"action": "error_analysis"})
            _dumped23 = json.dumps(_r23, ensure_ascii=False)
            _uid23 = await p_count(
                "SELECT count(*) FROM user_question_error WHERE user_id = :u", u=uid)
            _all23 = await p_count("SELECT count(*) FROM user_question_error")
            T("P23", "新工具隔离", "learning_stats 的数字按「当前用户」算：不含别人的错题",
              f"别人的夹具错题 error_count=9999 指向「{p_oth_q}」→ 漏过滤就会出现在 uid 的 TOP5",
              "execute(learning_stats, {action: error_analysis}) → 与 SQL 计数比对",
              "返回里**不含**别人的题干；totalErrors == 库里 uid 的错题行数；"
              "且全局错题数 > uid 错题数（证明夹具在、断言能分辨）",
              p_oth_q not in _dumped23 and _r23.get("totalErrors") == _uid23
              and _all23 > _uid23 and _r23.get("success") is True,
              f"泄漏={p_oth_q in _dumped23} totalErrors={_r23.get('totalErrors')} "
              f"uid库内={_uid23} 全局={_all23}")

        # ---- ⑤b 联动（跨工具）：**被标记的题也要能删**（本轮实测出来的 FK 缺陷）----
        # 背景：`question_manage._purge_questions` 只显式删了 `question_sub` / `note_question`，
        # 漏了 `user_question_{error,favorite,marked}` —— 而这三张表到 `question_main` 的外键
        # 在 PG 里是 `delete_rule=NO ACTION`（**没有** ON DELETE CASCADE，2026-09-22 实测）。
        # 于是「先收藏/加入错题本，再让助手删掉这道题」会直接
        # `ForeignKeyViolationError: … violates foreign key constraint
        #  "user_question_favorite_question_id_fkey"`，用户看到「工具执行异常：IntegrityError…」，
        # 而且**题删不掉**。这条路径本轮之前走不到（没有工具能造出「已被标记的题」），
        # `question_flag_manage` 上线后就是一步普通操作。
        # 修前的原始响应与 md5 存档：tests/_evidence/p_group_flag_delete_before_fix_20260922.txt
        p_del_bank = P_MARK + "联动库"
        _r = await execute("bank_manage",
                           {"action": "create", "bank_name": p_del_bank, "subject": "P组夹具"})
        p_del_bank_id = (_r.get("bank") or {}).get("bankId")
        _r = await execute("question_manage",
                           {"action": "create", "bank_id": p_del_bank_id,
                            "question_text": P_MARK + "联动题干"})
        p_del_qid = _r.get("questionId")
        for _k in P_KIND_SQL:
            await execute("question_flag_manage",
                          {"action": "add", "flag_type": _k, "question_id": p_del_qid})
        _marked_before = {
            _k: await p_count(f"SELECT count(*) FROM {_t} WHERE question_id = :q", q=p_del_qid)
            for _k, (_t, _i, _s) in P_KIND_SQL.items()
        }
        _rd = await execute("question_manage",
                            {"action": "delete", "question_id": p_del_qid})
        _q25_left = await p_count("SELECT count(*) FROM question_main WHERE id = :q",
                                  q=p_del_qid)
        _rec25_left = 0
        for _k, (_t, _i, _s) in P_KIND_SQL.items():
            _rec25_left += await p_count(f"SELECT count(*) FROM {_t} WHERE question_id = :q",
                                         q=p_del_qid)
        T("P25", "新工具联动", "被标记（错题 / 收藏 / 斩题）的题也能删掉：不再 FK violation",
          f"自建题库 {p_del_bank} + 一道题；先 add 三种标记（= 三条指向该题的外键），再删该题",
          "execute(question_flag_manage add ×3) → execute(question_manage delete) → 回读题目与标记行",
          "delete success=True；题目真的没了；三类标记记录**一并清掉**（不留孤儿行）。"
          "修前实测：success=False + 'IntegrityError … user_question_favorite_question_id_fkey' + 题还在",
          _rd.get("success") is True and _q25_left == 0 and _rec25_left == 0
          and all(v == 1 for v in _marked_before.values()),
          f"delete.success={_rd.get('success')} error={str(_rd.get('error'))[:70]!r} "
          f"题目残留={_q25_left} 标记残留={_rec25_left} 标记加进去的条数={_marked_before}")

        # ---- ⑥ 收尾：按登记的精确 id 物理删本组夹具，然后**回比** ----
        try:
            async with async_session_factory() as cdb:
                # 自己的三类标记记录（按 question_id 精确定位自己的夹具题 —— 不是按无标记条件删）
                for _k, (_tbl, _idc, _sc) in P_KIND_SQL.items():
                    await cdb.execute(
                        text(f"DELETE FROM {_tbl} WHERE user_id = :u AND question_id = :q"),
                        {"u": uid, "q": p_own_qid})
                # 自己的两个知识库（逻辑删过的也一并物理删）
                for _kid in p_own_kb_ids:
                    for _stmt in (
                        "DELETE FROM rag_qa_record WHERE kb_id = :k",
                        "DELETE FROM rag_document_chunk WHERE kb_id = :k",
                        "DELETE FROM rag_document WHERE kb_id = :k",
                        "DELETE FROM rag_knowledge_base WHERE id = :k",
                    ):
                        await cdb.execute(text(_stmt), {"k": _kid})
                # 自己的那条待忘记忆（正常已被工具删掉；这里兜底）
                await cdb.execute(
                    text("DELETE FROM ai_agent_memory WHERE user_id = :u AND content = :c"),
                    {"u": uid, "c": p_own_mem_text})
                # 自己发出的那条分享。⚠️ 库里的 `delete_banks` **会**连带清 `bank_share`
                # （bank_id 是同一个），但那是 `cleanup()` 删题库时的事 ——
                # 而 P26 的残留断言在 cleanup() **之前**跑，所以这里自己先删掉，
                # 免得把「收尾没做完」当成「已经干净了」。
                if p_own_share_id:
                    await cdb.execute(
                        text("DELETE FROM bank_share WHERE id = :i"),
                        {"i": int(p_own_share_id)})
                if p_oth:
                    await cdb.execute(
                        text("DELETE FROM ai_agent_memory WHERE id = :i"), {"i": p_oth["mem"]})
                    await cdb.execute(
                        text("DELETE FROM bank_share WHERE id = :i"), {"i": p_oth["share"]})
                    for _tbl in ("user_question_error", "user_question_favorite",
                                 "user_question_marked"):
                        await cdb.execute(
                            text(f"DELETE FROM {_tbl} WHERE user_id = :u AND question_id = :q"),
                            {"u": uid_other, "q": p_oth["q"]})
                    await cdb.execute(
                        text("DELETE FROM rag_document WHERE id = :i"), {"i": p_oth["doc"]})
                    await cdb.execute(
                        text("DELETE FROM rag_document_chunk WHERE kb_id = :k"), {"k": p_oth["kb"]})
                    await cdb.execute(
                        text("DELETE FROM rag_knowledge_base WHERE id = :i"), {"i": p_oth["kb"]})
                    await cdb.execute(
                        text("DELETE FROM question_main WHERE id = :i"), {"i": p_oth["q"]})
                    await cdb.execute(
                        text("DELETE FROM question_bank WHERE id = :i"), {"i": p_oth["bank"]})
                await cdb.commit()
        except Exception as _e:  # noqa: BLE001 - 收尾失败不该盖住用例结果（下面的断言会兜住）
            print(f"  [WARN] P 组夹具清理失败：{_e!r}")

        _left_own = await p_count(
            "SELECT (SELECT count(*) FROM user_question_error WHERE user_id = :u AND question_id = :q)"
            " + (SELECT count(*) FROM user_question_favorite WHERE user_id = :u AND question_id = :q)"
            " + (SELECT count(*) FROM user_question_marked WHERE user_id = :u AND question_id = :q)",
            u=uid, q=p_own_qid)
        _left_oth_bank = await p_count(
            "SELECT count(*) FROM question_bank "
            "WHERE LEFT(COALESCE(bank_name, ''), LENGTH(:p)) = :p", p=P_OTH_MARK)
        _left_oth_mem = await p_count(
            "SELECT count(*) FROM ai_agent_memory WHERE POSITION(:m IN content) > 0",
            m=p_oth_mem_text)
        _left_own_mem = await p_count(
            "SELECT count(*) FROM ai_agent_memory WHERE POSITION(:m IN content) > 0",
            m=p_own_mem_text)
        _left_own_share = await p_count(
            "SELECT count(*) FROM bank_share WHERE id = :i", i=int(p_own_share_id or 0))
        if p_oth:
            p_watch_after = {
                _t: await p_count(f"SELECT count(*) FROM {_t} WHERE {_c} = :u", u=uid_other)
                for _t, _c in p_watch_tables
            }
            p_watch_ok = p_watch_after == p_watch_before
            _watch_detail = {t: (p_watch_before[t], p_watch_after[t])
                             for t in p_watch_before if p_watch_before[t] != p_watch_after[t]}
            T("P26", "新工具收尾", "本组夹具残留 0，且另一个用户的真实行数**一条没少**",
              f"别人的观察表：{', '.join(t for t, _ in p_watch_tables)}（跑前只读采样）",
              "按登记的精确 id / 自己的夹具 question_id 物理删 → 残留计数 + 逐表回比行数",
              "自己的三类记录 0；自己的分享 0；他人题库标记残留 0；两条夹具记忆残留 0；"
              "另一用户的 7 张表跑前跑后计数完全相等"
              "（不能只打印「看着没问题」—— 删多了要能红）",
              _left_own == 0 and _left_own_share == 0 and _left_oth_bank == 0
              and _left_oth_mem == 0 and _left_own_mem == 0 and p_watch_ok,
              f"自己记录残留={_left_own} 自己分享残留={_left_own_share} "
              f"他人题库残留={_left_oth_bank} "
              f"记忆残留(他人={_left_oth_mem}/自己={_left_own_mem}) "
              f"别人行数变化={_watch_detail or '无'}")
        else:
            # 没有第二个用户时 P26 已经在上面的 skip 分支里报过「没测到东西」了 ——
            # 别在这里再补一条看着像「通过」的行。
            pass

        await cleanup()
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        T("XX", "执行", "脚本异常", "-", "-", "-", False, repr(e))
    finally:
        # 无论如何都清一遍临时数据（中途异常时尤其重要）
        try:
            await cleanup()
        except Exception:  # noqa: BLE001
            pass
        # 清理结果**要断言，不能只打印**：Agent 的写操作会自动落长期记忆，
        # 漏清一次就往真实用户记忆里塞十几条垃圾，而且下次跑时「基线」已经过去、
        # 只会越积越多。把它变成一条会红的用例，才有人管。
        try:
            async with async_session_factory() as db:
                left = int(
                    await db.scalar(
                        text("SELECT count(*) FROM ai_agent_memory WHERE id > :b"), {"b": mem_baseline}
                    )
                    or 0
                )
            T("Z1", "收尾", "测试数据清理", "跑完自动清理", "清理后统计记忆表",
              "基线之后无新增记忆（测试不污染真实用户的长期记忆）",
              left == 0, f"基线 id={mem_baseline} 之后残留 {left} 条")
        except Exception as e:  # noqa: BLE001
            T("Z1", "收尾", "测试数据清理", "-", "-", "-", False, f"复核失败: {e!r}")

        # Z2：两次跑之间不许有「无标记孤儿」——**只检测、只报警，绝不自动删**（见 BASELINE_FILE）
        # 为什么单开一条：Z1 只看得见「本次基线之后」的行。上一次跑崩掉留下的行，
        # 其 id **低于**本次基线，Z1 永远看不见；而标记网又只认内容里的 `__e2e_agent__`，
        # 「已删除题目（ID=2081），题库现有 1 题」这种行两网都漏 —— 实测藏了 50 分钟。
        # 窗口取 `(上次基线, 本次基线]`，即「两次跑之间新增的行」：本次跑自己的行都在
        # 本次基线**之上**，不会混进来。
        try:
            if prev_mem_baseline is None:
                # 首次运行同样**没测到东西**（基线刚写下去，Z2 的窗口还没生效）——
                # 与下面「空窗口」是同一类，所以同样要在 stdout 留一行 [SKIP]（见 B-4 的理由）。
                print("[SKIP] Z2 首次运行（sidecar 不存在）：本次只写入基线，Z2 的检测从下次跑起生效"
                      " —— **未检测，不算验证通过**")
                T("Z2", "收尾", "两次跑之间没有无标记的记忆孤儿（上趟崩了留下的）",
                  "sidecar 记录的上次基线", "查 (上次基线, 本次基线] 区间内不含标记的记忆行",
                  "首次运行（sidecar 不存在）：本次基线已写入，从下次跑起生效",
                  True, f"首次运行，已写入基线 id={mem_baseline}")
            elif prev_mem_baseline >= mem_baseline:
                # 空窗口：两跑之间**一行都没新增**（prev == cur），或者 sidecar 的基线比当前最大 id
                # 还大（prev > cur，一般是人工清过行 / 换过库）→ 区间都是空集，孤儿必然是 0。
                # ⚠️ 这种绿是**空转通过**，不是「验过了」—— 必须自己说出来，否则
                #    一次恒真的绿会被当成证据（2026-09-19 chain-verifier 抓到的就是这个）。
                write_mem_baseline(mem_baseline)
                acked_ids_now = read_acked_ids()
                # ⚠️ **计数诚实化**（B-4）：这条用例的 `status` 仍是「通过」（空窗口不是失败，已拍板），
                # 但「按通过条数统计」的脚本会把它算成**验过了** —— 而它其实**什么都没测**。
                # 所以额外在 stdout 留一行显眼的 `[SKIP]`：人眼扫日志与按条数统计的脚本都能区分开。
                print(f"[SKIP] Z2 空转通过：窗口 (sidecar {prev_mem_baseline}, 本次基线 {mem_baseline}] "
                      "为空 → **本次跑没有新增记忆，未检测**，不算验证通过"
                      "（按条数统计请把这一条排除）")
                T("Z2", "收尾", "两次跑之间没有无标记的记忆孤儿（上趟崩了留下的）",
                  f"sidecar 基线 id={prev_mem_baseline}，本次基线 id={mem_baseline}"
                  f"（{'相等' if prev_mem_baseline == mem_baseline else '基线高于当前最大值'}）",
                  "查 (上次基线, 本次基线] 区间内「内容不含 __e2e_agent__ 标记」的记忆行",
                  "窗口为空 → 本用例**空转通过**（没测到东西，不算验证通过）",
                  True,
                  f"窗口为空（本次跑无新增记忆，未检测）"
                  + (f"；ack 文件登记 {len(acked_ids_now)} 个 id" if acked_ids_now else ""))
            else:
                acked_ids = read_acked_ids()
                # ⚠️⚠️ **判定一律用全量，`LIMIT` 只许限制打印**（缺陷 4，2026-09-19 修）。
                #
                # 此前这里写的是 `ORDER BY id LIMIT 20`，而 `fresh` 是在**那 20 行**上算的、
                # `fresh` 空就推进基线 —— 于是「窗口里 25 行孤儿、前 20 行都登记进 ack」时，
                # 用例会**判绿并推进基线**，剩下的 5 行掉到新基线以下，标记网与基线网都再也抓不到。
                # **孤儿越多越容易越过阈值、越看不见**，这是最坏的一种假绿。
                #
                # 现在四条一起：
                #   ① 判定基数用**不带 LIMIT** 的 `count(*)`；
                #   ② 明细也**全量取**（判定与打印必须同源，不能一个全量一个局部，否则两边结论不同）；
                #   ③ 打印时按 `Z2_DETAIL_LIMIT` 截断，**截断了就必须写出「还有 N 行未打印」**；
                #   ④ 取到的行数与 `count(*)` 不等 → **直接判红**（那正是「有人又给查询加了 LIMIT /
                #      过滤」的指纹；另一种可能是窗口内的行被并发进程改了，文案里两种都提到）。
                # ⚠️⚠️ **判定窗口按 `user_id` 过滤 —— 只看 e2e 自己那个 uid**（B-1b，2026-09-20 修）。
                #
                # 为什么：Z2 要抓的是「**测试跑崩后留在库里**的无标记行」，而本套件**只写 `uid`
                # 这一个用户**（`uid` = sys_user 里第一个 user_id）。不加过滤的话，
                # **真实用户在界面上的每一次 Agent 操作**都会落进窗口、被判成孤儿 → 红 → 而且因为
                # 「有 fresh 就钉住基线」它还会**一直红**。这不是偶发假阳性，是**结构性假阳性**。
                # 实例（2026-09-20 10:18）：用户自己在浏览器里建了「Java知识题库」并导入 30 题，
                # 落下的 3 条 episodic 记忆（user_id=105）正好把这条用例顶红 —— 而它们**不属于本套件、
                # 也不该被本套件判**（无标记行 = 用户的真实数据，一行都不许删，更不该「登记掉」）。
                # ⚠️ **信息不能丢**：其他 user 在窗口内的新行**另行列出条数**（信息性、不参与判定），
                #    且**只列用户/类型/条数、不打印正文** —— 正文是用户自己的记忆内容。
                _win = {"prev": prev_mem_baseline, "cur": mem_baseline,
                        "m1": PREFIX, "m2": NOTE_PREFIX, "uid": uid}
                async with async_session_factory() as db:
                    total_orphans = int(
                        await db.scalar(
                            text(
                                "SELECT count(*) FROM ai_agent_memory "
                                "WHERE id > :prev AND id <= :cur AND user_id = :uid "
                                "AND POSITION(:m1 IN content) = 0 "
                                "AND POSITION(:m2 IN content) = 0"
                            ),
                            _win,
                        )
                        or 0
                    )
                    orphan_rows = (
                        await db.execute(
                            text(
                                "SELECT id, user_id, memory_type, content, metadata, create_time "
                                "FROM ai_agent_memory "
                                "WHERE id > :prev AND id <= :cur AND user_id = :uid "
                                "AND POSITION(:m1 IN content) = 0 "
                                "AND POSITION(:m2 IN content) = 0 "
                                "ORDER BY id"
                            ),
                            _win,
                        )
                    ).all()
                    # 信息性（**不参与判定**）：窗口内**其他 user** 的新行，按 (user, 类型) 汇总条数。
                    # 不取正文：那是用户自己的数据，不往测试产物里抄。
                    other_rows = (
                        await db.execute(
                            text(
                                "SELECT user_id, memory_type, count(*) FROM ai_agent_memory "
                                "WHERE id > :prev AND id <= :cur AND user_id <> :uid "
                                "GROUP BY user_id, memory_type ORDER BY user_id, memory_type"
                            ),
                            _win,
                        )
                    ).all()
                    # ack 文件里登记过、但库里已经没有的 id：提示人工可以清掉那一行登记，
                    # 但**脚本绝不自己去改这个文件**（它是人的决定，不是程序的状态）。
                    existing = {
                        r[0]
                        for r in (
                            await db.execute(
                                text("SELECT id FROM ai_agent_memory WHERE id <= :cur"),
                                {"cur": mem_baseline},
                            )
                        ).all()
                    }
                acked = [r for r in orphan_rows if r[0] in acked_ids]
                fresh = [r for r in orphan_rows if r[0] not in acked_ids]
                stale_acked = sorted(acked_ids - existing)
                # 信息性（**不进判定**）：窗口内其他 user 的新行汇总
                other_new = sum(int(r[2]) for r in other_rows)
                other_desc = "、".join(f"user={r[0]} {r[1]}×{r[2]}" for r in other_rows)
                # 行数与 count(*) 不等 = 判定与明细不同源，不许静默
                fetch_short = total_orphans != len(orphan_rows)
                unprinted = max(len(fresh) - Z2_DETAIL_LIMIT, 0)
                shown = fresh[:Z2_DETAIL_LIMIT]

                def _fmt(rows) -> str:
                    # create_time 是人工判断唯一能用的线索：那几分钟我用没用界面
                    return " | ".join(
                        f"#{r[0]} user={r[1]} {r[2]} at={r[5]} content={str(r[3])[:50]!r} "
                        f"metadata={str(r[4])[:80]}"
                        for r in rows
                    )

                # 干净（除了已确认的）→ 推进基线；有**未确认**的 → 红 + **钉住旧基线**
                # （下次跑继续报同一批，直到人工处理或登记进 ack）。
                # `fetch_short` 也要钉住：判定与明细不一致时推进基线 = 把没看清的部分永久埋掉。
                write_mem_baseline(
                    mem_baseline if (not fresh and not fetch_short) else prev_mem_baseline
                )
                tail = (
                    f"；ack 文件里 {len(stale_acked)} 个 id 已不存在，可清理登记"
                    f"（{stale_acked}）"
                    if stale_acked
                    else ""
                )
                T("Z2", "收尾", "两次跑之间没有无标记的记忆孤儿（上趟崩了留下的）",
                  f"sidecar 记录的上次基线 id={prev_mem_baseline}，本次基线 id={mem_baseline}"
                  + (f"，ack 文件登记 {len(acked_ids)} 个 id" if acked_ids else ""),
                  "查 (上次基线, 本次基线] 区间内「内容不含 __e2e_agent__ 标记」、"
                  "**且属于本套件自己那个 uid** 的记忆行，"
                  "再按 ack 文件分成「已人工确认」与「新孤儿」。"
                  "**判定用全量 count(*)，明细全量取、只在打印时截断**；"
                  "其他 user 的新行只列条数（信息性，不参与判定）",
                  "新孤儿 0 行。>0 说明上一趟跑崩了、留下**无标记**的孤儿（标记网+基线网都抓不到），"
                  "或者真实用户在这几分钟里自己写了记忆 —— 两者数据上分不清，需要人工判断："
                  "是真数据就登进 ack 文件（`tests/.e2e_agent_mem_orphans_ack`，只读、"
                  "语义是「已确认」**不是「允许删除」**），是无标记孤儿才手工清理。"
                  f"明细超过 {Z2_DETAIL_LIMIT} 行时必须在 actual 里写出未打印行数",
                  not fresh and not fetch_short,
                  f"新孤儿 {len(fresh)} 行（uid={uid} 全量 {total_orphans} 行，判定不看 LIMIT）"
                  f" / 已确认 {len(acked)} 行"
                  + (f"；新孤儿明细（前 {len(shown)} 条）：{_fmt(shown)}" if shown else "")
                  + (
                      f"；**还有 {unprinted} 行未打印**"
                      f"（明细打印上限 {Z2_DETAIL_LIMIT}，判定用的是全量）"
                      if unprinted
                      else ""
                  )
                  + (
                      f"；⚠️ count(*)={total_orphans} 但只取到 {len(orphan_rows)} 行 —— "
                      "查询疑似被加了 LIMIT/过滤，或窗口内的行被并发进程改动"
                      if fetch_short
                      else ""
                  )
                  + (
                      f"；**其他 user 在窗口内的新行 {other_new} 行（{other_desc}）"
                      "—— 信息性、不参与判定**（无标记行是用户的真实数据，不是测试孤儿；"
                      f"本套件只写 uid={uid}）"
                      if other_new
                      else ""
                  )
                  + tail)
        except Exception as e:  # noqa: BLE001
            T("Z2", "收尾", "两次跑之间没有无标记的记忆孤儿（上趟崩了留下的）",
              "-", "-", "-", False, f"复核失败: {e!r}")
        await client.aclose()
        # ⚠️ 必须显式释放连接池：本脚本直接用 app 的全局 `engine`（不止一次），
        #    不 dispose 的话，asyncio.run() 关掉事件循环后 GC 才去收拾这些连接，
        #    于是进程退出时刷一屏 `RuntimeError: greenlet is being finalized` +
        #    `non-checked-in connection` 的吓人噪音（实际不影响用例结果，但会掩盖真问题）。
        try:
            from app.database import engine as _engine

            await _engine.dispose()
        except Exception:  # noqa: BLE001
            pass

    passed = len([r for r in ROWS if r["status"] == "通过"])
    print(f"\n{passed}/{len(ROWS)} 通过")
    # ⚠️ `completed=True`：走到这里说明**用例表是完整的**（中途崩溃走不到这行，
    #    那条路径由守卫里的 `save_crash_evidence` 落 `completed=false`）。
    if _write_json(OUT, _result_payload(True)):
        print("产出:", OUT)

    # **红产物另存 + 退出码**都收在 `main()` 尾部（不要再散落到模块级 —— 模块级代码在
    # `import` 时就会执行，那是 2026-09-19 埋下的雷：`import` 本模块会满跑一遍、
    # 连 DB、写产物、动 sidecar）。
    # 为什么退出码必须传出去：本套件此前只 `print` 失败、退出码恒为 0，而
    # `scripts/test-fastapi-v2.bat` 在它后面就是 `if errorlevel 1 goto :failed` ——
    # 那条防线**永远不触发**（套件红着，总脚本照样报「全部通过」）。
    # 另外四套（`e2e_rag_api.py` / `test_rag_pg.py` / `test_context_memory.py` /
    # `test_agent_rag_tools.py`）都是 `raise SystemExit(asyncio.run(run()))`，这里对齐它们。
    red = [r for r in ROWS if r["status"] != "通过"]
    if red:
        save_red_evidence()
    return 1 if red else 0


if __name__ == "__main__":
    # ⚠️ 单实例锁必须在**任何 DB 操作之前**拿到：本套件的夹具名不带时间戳、且都写同一个
    #    真实用户，两个进程会互删对方刚建的夹具（详见 LOCK_FILE 上方注释）。
    #    抢不到锁 → 打印原因 + 退 2 + **什么都不做**（不碰 DB、不写产物、不动 sidecar）。
    if not acquire_lock():
        raise SystemExit(2)
    try:
        _code = asyncio.run(main())
    except BaseException as _e:  # noqa: BLE001 - 崩溃路径也要落证据，否则会留下「绿产物 + 退出码 1」
        save_crash_evidence(_e)
        traceback.print_exc()
        raise SystemExit(1)
    else:
        # `main()` 每条路径都 return 了 0/1/2；万一将来有人加了裸 `return`，
        # 这里**不许**把 None 当成 0（那就是又一次「没跑说成通过」），按失败处理。
        raise SystemExit(1 if _code is None else int(_code))
    finally:
        release_lock()
