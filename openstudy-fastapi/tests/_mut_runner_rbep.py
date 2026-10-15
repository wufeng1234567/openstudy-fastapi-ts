# -*- coding: utf-8 -*-
"""临时变异跑手（用完即删）：在**镜像副本**里逐条摘掉 2026-09-23 补的那几处，看探针会不会红

被测探针 = `tests/_probe_rollback_endpoint.py`（HTTP 层：turnId 透传 + 回退端点）。
每条变异对应一个真实缺陷形态：

  ①  `AgentExecuteRequest.turnId` **和**它的调用点一起摘掉 = 修复前的原状态
      （前端发的轮次 id 被 pydantic 静默丢掉 → 后端兜 auto_）
  ①b 半变异：**只**摘调用点（字段还在）→ 只该点亮 R4，用来隔离「字段声明」与「真的透传」两半
  ②  `/ai/agent/rollback` 路由改名 = 修复前「端点不存在」→ 调用落进 `catch_all` 的假 200
  ③  stream 调用点不再透传 turn_id → api 链路的账本归组键断掉

⚠️ 为什么用镜像：直接改工作树会让 `--reload` 的后端给用户端发**坏代码**，而且别人读到的
md5 与运行结果对不上（本仓库 2026-09-21 实测过这个坑）。所以复制一份 app/ 到镜像目录，
只在镜像里变异，真实工作树一个字节都不动；跑完删镜像。

用法：
    cd apps/fastapi-v2/openstudy-fastapi
    ./.venv/Scripts/python.exe tests/_mut_runner_rbep.py
"""
import hashlib
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.dirname(HERE)                     # .../openstudy-fastapi
PY = os.path.join(REAL, ".venv", "Scripts", "python.exe")
MIRROR = os.path.abspath(os.path.join(REAL, "..", "..", "..", ".rbep_mirror_tmp"))
PROBE_REL = os.path.join("tests", "_probe_rollback_endpoint.py")
AI = os.path.join("app", "api", "v1", "ai.py")

EXEC_FIELD = """    turnId: str = ""
    #: 写操作是否自动执行（前端开关透传）
    autoConfirm: bool = True"""
EXEC_FIELD_MUT = """    #: 写操作是否自动执行（前端开关透传）
    autoConfirm: bool = True"""

EXEC_FWD = """        # 回退账本的归组键：同一轮里的多次工具调用共用（见 AgentExecuteRequest.turnId）
        turn_id=req.turnId or "",
"""
EXEC_FWD_MUT = ""

ROUTE = '@router.post("/agent/rollback")'
ROUTE_MUT = '@router.post("/agent/rollback_mut")'

STREAM_FWD = """        # 回退账本的归组键：前端每轮生成，原样透传（见 AgentStreamRequest.turnId）
        turn_id=req.turnId or "",
"""
STREAM_FWD_MUT = ""

#: (名字, [(文件相对路径, 原文, 替换), ...], 期望变红的断言 id；edits 为空 = 基线)
MUTATIONS = [
    ("MUT-0 基线（不改任何代码）", [], set()),
    ("① 字段 + 调用点一起摘掉（修复前的原状态）", [(AI, EXEC_FIELD, EXEC_FIELD_MUT),
                                              (AI, EXEC_FWD, EXEC_FWD_MUT)],
     {"R1", "R4"}),
    ("①b 半变异：只摘调用点（字段还在）→ 只该点亮 R4", [(AI, EXEC_FWD, EXEC_FWD_MUT)],
     {"R4"}),
    ("② /ai/agent/rollback 路由改名（回到「端点不存在」的原缺陷）", [(AI, ROUTE, ROUTE_MUT)],
     {"R6", "R8", "R9", "R10", "R12"}),
    ("③ stream 调用点不再透传 turn_id（api 链路归组键断掉）", [(AI, STREAM_FWD, STREAM_FWD_MUT)],
     {"R13"}),
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
    gold = {AI: md5(os.path.join(REAL, AI))}
    print(f"镜像 = {MIRROR}\n原始 md5 = {gold}\n")
    verdicts = []
    try:
        for name, edits, expect in MUTATIONS:
            # 每轮先把镜像里的目标文件恢复成原始（前一条变异不许残留）
            for rel in {e[0] for e in edits} or gold.keys():
                shutil.copy2(os.path.join(REAL, rel), os.path.join(MIRROR, rel))
                assert md5(os.path.join(MIRROR, rel)) == gold[rel], f"{rel} 恢复后 md5 与原始不一致"
            for rel, old, new in edits:
                target = os.path.join(MIRROR, rel)
                src = open(target, encoding="utf-8").read()
                assert old in src, f"变异落点找不到（{name}）—— 别静默跳过"
                assert src.count(old) == 1, f"变异落点出现 {src.count(old)} 次（{name}）：不唯一"
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(src.replace(old, new))
            code, red, summary, out = run_probe()
            for rel in {e[0] for e in edits} or gold.keys():      # 立刻恢复
                shutil.copy2(os.path.join(REAL, rel), os.path.join(MIRROR, rel))
                assert md5(os.path.join(MIRROR, rel)) == gold[rel], f"{rel} 恢复失败"
            if "没解析到结果行" in summary:
                # 探针自己崩了 → 打印尾部，否则只剩「没测到」这种没法查的结论
                print(f"         ⚠️ 探针异常退出，尾部输出：\n"
                      + "\n".join("           " + ln for ln in out.strip().splitlines()[-10:]))
            hit = bool(expect & set(red)) if expect else (not red)
            missing = sorted(set(expect) - set(red))
            extra = sorted(set(red) - set(expect))
            print(f"[{'OK  ' if hit and not missing else 'FAIL'}] {name}")
            print(f"         退码={code} {summary} 红={red or '无'}"
                  + (f" 期望={sorted(expect)}" if expect else "")
                  + (f" 缺={missing}" if missing else "")
                  + (f" 顺带红={extra}" if extra else ""))
            verdicts.append((name, hit and not missing, code, red, sorted(expect)))
    finally:
        print(f"\n镜像是否已恢复：{all(md5(os.path.join(MIRROR, r)) == gold[r] for r in gold)}")
        shutil.rmtree(MIRROR, ignore_errors=True)
        print(f"镜像已删除：{MIRROR}")
    bad = [v for v in verdicts if not v[1]]
    print(f"\n变异矩阵：{len(verdicts) - len(bad)}/{len(verdicts)} 符合预期"
          + ("" if not bad else f"；不符：{[v[0] for v in bad]}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
