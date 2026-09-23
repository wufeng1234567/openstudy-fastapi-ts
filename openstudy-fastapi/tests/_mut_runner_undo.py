# -*- coding: utf-8 -*-
"""临时变异跑手（用完即删）：在**镜像副本**里逐条摘掉 `del_flag` 过滤，看探针会不会红

⚠️ 为什么用镜像：直接改工作树会让 `--reload` 的后端给用户端发**坏代码**，而且别人读到的
md5 与运行结果对不上（本仓库 2026-09-21 实测过这个坑）。所以：复制一份 app/ 到镜像目录，
只在镜像里变异，真实工作树一个字节都不动。

用法：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_mut_runner_undo.py

判据：每个变异都必须让**指定的那一条**断言变红（其余尽量不动）—— 否则那条断言就是恒真的。
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.dirname(HERE)                     # .../openstudy-fastapi
PY = os.path.join(REAL, ".venv", "Scripts", "python.exe")
MIRROR = os.path.abspath(os.path.join(REAL, "..", "..", "..", ".undo_mirror_tmp"))
PROBE_REL = os.path.join("tests", "_probe_memory_undo.py")
SVC = os.path.join("app", "services", "ai", "memory_service.py")

EVICT_COUNT = """            .select_from(AiAgentMemory)
            .where(
                AiAgentMemory.user_id == user_id,
                AiAgentMemory.memory_type == memory_type,
                AiAgentMemory.del_flag == "0",
            )"""
EVICT_STALE = """            select(AiAgentMemory.id)
            .where(
                AiAgentMemory.user_id == user_id,
                AiAgentMemory.memory_type == memory_type,
                AiAgentMemory.del_flag == "0",
            )"""

#: (名字, 文件相对路径, 原文, 替换, 期望变红的断言 id)
MUTATIONS = [
    ("MUT-0 基线（不改任何代码）", None, None, None, set()),
    ("list_memories 去掉 del_flag", SVC,
     """    stmt = select(AiAgentMemory).where(
        AiAgentMemory.user_id == user_id,
        AiAgentMemory.del_flag == "0",
    )""",
     """    stmt = select(AiAgentMemory).where(
        AiAgentMemory.user_id == user_id,
    )""",
     {"P2"}),
    ("get_memory 去掉 del_flag", SVC,
     """            select(AiAgentMemory).where(
                AiAgentMemory.id == memory_id,
                AiAgentMemory.del_flag == "0",
            )""",
     """            select(AiAgentMemory).where(
                AiAgentMemory.id == memory_id,
            )""",
     {"P2"}),
    ("count_by_type 去掉 del_flag", SVC,
     """                AiAgentMemory.user_id == user_id,
                AiAgentMemory.del_flag == "0",
            )
            .group_by(AiAgentMemory.memory_type)""",
     """                AiAgentMemory.user_id == user_id,
            )
            .group_by(AiAgentMemory.memory_type)""",
     {"P3"}),
    ("_evict 的 count 去掉 del_flag（半变异：只动计数那一半）", SVC, EVICT_COUNT,
     EVICT_COUNT.replace('                AiAgentMemory.del_flag == "0",\n', ""),
     {"P9b"}),
    ("_evict 的 stale_ids 去掉 del_flag（半变异：只动候选那一半）", SVC, EVICT_STALE,
     EVICT_STALE.replace('                AiAgentMemory.del_flag == "0",\n', ""),
     {"P9c"}),
    ("list_deleted_memories 去掉 user_id（越权读闸门）", SVC,
     """        .where(
            AiAgentMemory.user_id == user_id,
            AiAgentMemory.del_flag == "2",
        )""",
     """        .where(
            AiAgentMemory.del_flag == "2",
        )""",
     {"P5"}),
    ("restore_memory 去掉 user_id（越权写闸门）", SVC,
     """        .where(
            AiAgentMemory.id == memory_id,
            AiAgentMemory.user_id == user_id,
        )
        .values(del_flag="0")""",
     """        .where(
            AiAgentMemory.id == memory_id,
        )
        .values(del_flag="0")""",
     {"P6", "P13"}),
    ("delete_memory 退回**物理删**（撤销需求本身）", SVC,
     """    result = await db.execute(
        update(AiAgentMemory)
        .where(
            AiAgentMemory.id == memory_id,
            AiAgentMemory.user_id == user_id,
            AiAgentMemory.del_flag == "0",
        )
        .values(del_flag="2")
    )""",
     """    result = await db.execute(
        delete(AiAgentMemory)
        .where(
            AiAgentMemory.id == memory_id,
            AiAgentMemory.user_id == user_id,
            AiAgentMemory.del_flag == "0",
        )
    )""",
     {"P2", "P5", "P7"}),
]


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def build_mirror():
    if os.path.isdir(MIRROR):
        shutil.rmtree(MIRROR)
    os.makedirs(os.path.join(MIRROR, "tests"), exist_ok=True)
    shutil.copytree(os.path.join(REAL, "app"), os.path.join(MIRROR, "app"))
    shutil.copy2(os.path.join(REAL, ".env"), os.path.join(MIRROR, ".env"))
    shutil.copy2(os.path.join(REAL, PROBE_REL), os.path.join(MIRROR, PROBE_REL))


def run_probe():
    p = subprocess.run([PY, PROBE_REL], cwd=MIRROR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (p.stdout or "") + (p.stderr or "")
    red = sorted(set(re.findall(r"\[FAIL\] (\S+)", out)))
    total = re.search(r"结果：(\d+)/(\d+) 通过", out)
    return p.returncode, red, (total.group(0) if total else "（没解析到结果行）"), out


def main():
    build_mirror()
    gold = {SVC: md5(os.path.join(REAL, SVC))}
    print(f"镜像 = {MIRROR}\n原始 md5 = {gold}\n")
    verdicts = []
    try:
        for name, rel, old, new, expect in MUTATIONS:
            target = os.path.join(MIRROR, rel) if rel else None
            if rel:
                shutil.copy2(os.path.join(REAL, rel), target)   # 先恢复原始
                assert md5(target) == gold[rel], f"{rel} 恢复后 md5 与原始不一致"
                src = open(target, encoding="utf-8").read()
                assert old in src, f"变异落点找不到（{name}）—— 别静默跳过"
                assert src.count(old) == 1, f"变异落点出现 {src.count(old)} 次（{name}）：不唯一"
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(src.replace(old, new))
            code, red, summary, out = run_probe()
            if rel:
                shutil.copy2(os.path.join(REAL, rel), target)   # 立刻恢复
                assert md5(target) == gold[rel], f"{rel} 恢复失败"
            hit = bool(expect & set(red)) if expect else (not red)
            extra = sorted(set(red) - expect)
            print(f"[{'OK  ' if hit else 'FAIL'}] {name}")
            print(f"         退码={code} {summary} 红={red or '无'}"
                  + (f" 期望={sorted(expect)}" if expect else "")
                  + (f" 顺带红={extra}" if extra else ""))
            verdicts.append((name, hit, code, red, sorted(expect)))
    finally:
        print(f"\n镜像是否已恢复：{all(md5(os.path.join(MIRROR, r)) == gold[r] for r in gold)}")
        # ⚠️ 跑完把镜像删掉：不留临时目录（想复查的话，重跑这个脚本就会重新建出来）
        shutil.rmtree(MIRROR, ignore_errors=True)
        print(f"镜像已删除：{MIRROR}")
    bad = [v for v in verdicts if not v[1]]
    print(f"\n变异矩阵：{len(verdicts) - len(bad)}/{len(verdicts)} 符合预期"
          + ("" if not bad else f"；不符：{[v[0] for v in bad]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
