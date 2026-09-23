# -*- coding: utf-8 -*-
"""变异对照跑手（fix-drop-be，2026-09-23）

只在**镜像副本** `D:\\OpenStudy\\.fixdrop_mirror_tmp` 里改文件，
**绝不动共享树**（9101 是 `--reload` 起的，就地改会把用户的浏览器跑到坏代码上）。

手法：替换 → 跑探针 → finally 整份写回 pristine → md5 比对确认已还原。
开跑前先断言「镜像里的两份被测文件 == 我预期的修复版 md5」，不是那份就拒绝开跑
（只断言还原是不够的）。

用法：
    cd /d/OpenStudy/.fixdrop_mirror_tmp
    <该仓库的 .venv python> _mut_runner.py
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys

MIRROR = os.path.dirname(os.path.abspath(__file__))
PRISTINE = os.path.join(MIRROR, "_pristine_app")
PY = r"D:\OpenStudy\apps\fastapi-v2\openstudy-fastapi\.venv\Scripts\python.exe"
PROBE = os.path.join(MIRROR, "tests", "_probe_drop_turn.py")
OUTDIR = os.path.join(MIRROR, "_mut_output")

AI = "app/api/v1/ai.py"
SVC = "app/services/ai/conversation_service.py"

#: 修复版（= 允许变异的那一版）的两份 md5
EXPECT = {
    AI: "985fbd72288d2057f6ee23538a18766f",
    SVC: "64a5dd9e8612b1be89d50995a25c264f",
}

COUNT_WHERE = (
    "                .where(\n"
    "                    AiChatMessage.user_id == uid,\n"
    "                    AiChatMessage.session_id == sid,\n"
    "                    AiChatMessage.turn_id == tid,\n"
    "                )\n"
)
COUNT_TAIL = (
    "                    AiChatMessage.turn_id == tid,\n"
    "                )\n"
    "            )\n"
    "            or 0\n"
)
COUNT_FULL = (
    "        matched = int(\n"
    "            await db.scalar(\n"
    "                select(func.count())\n"
    "                .select_from(AiChatMessage)\n"
    + COUNT_WHERE
    + "            )\n"
    "            or 0\n"
    "        )\n"
)
SID_GATE = (
    "    if not session_id:\n"
    "        # ⚠️ 这一句就是本次事故缺的那一句：前端拿不到会话 id 时发了空串，服务端\n"
    "        #    一个字没说、还回了个「成功」，前端于是把这一轮从本地 UI 摘掉了。\n"
    '        return error("缺少会话 id（sessionId），无法回退", code=400)\n'
)

MUTS = [
    (
        "M1", "matched 的 COUNT 也筛 del_flag='0'（退化成第二个 dropped）", SVC,
        COUNT_TAIL,
        COUNT_TAIL.replace(
            "                    AiChatMessage.turn_id == tid,\n",
            "                    AiChatMessage.turn_id == tid,\n"
            "                    AiChatMessage.del_flag == DEL_FLAG_UNDELETED,\n",
        ),
        "期望只亮 D5（matched 变成 0）—— 但 D1 也会亮（UPDATE 之后那两行已经是 '2'）",
    ),
    (
        "M2", "matched 的 COUNT 少了 user_id（越权读数）", SVC,
        COUNT_WHERE,
        COUNT_WHERE.replace("                    AiChatMessage.user_id == uid,\n", ""),
        "期望亮 D6 / D6b（别人的轮次 matched 变成 2）",
    ),
    (
        "M3", "matched 的 COUNT 少了 session_id", SVC,
        COUNT_WHERE,
        COUNT_WHERE.replace("                    AiChatMessage.session_id == sid,\n", ""),
        "期望亮 D11（同名轮次在两个会话里）与 D6b",
    ),
    (
        "M4", "matched 的 COUNT 少了 turn_id（数成「这个会话里有多少行」）", SVC,
        COUNT_WHERE,
        COUNT_WHERE.replace("                    AiChatMessage.turn_id == tid,\n", ""),
        "期望亮 D12（旧数据形态）以及 D1/D5/D6/D6b/D9b/D11 —— 这一条是「matched 必须按轮次定位」的总闸",
    ),
    (
        "M5", "matched = dropped（别名，退化成第二个 dropped）", SVC,
        COUNT_FULL, "        matched = dropped\n",
        "期望**只**亮 D5",
    ),
    (
        "M6", "端点删掉空 sessionId 闸门（回到「静默成功」）", AI,
        SID_GATE, "",
        "期望只亮 D13",
    ),
    (
        "M7", "UPDATE 不筛 del_flag（幂等被打破）", SVC,
        "                AiChatMessage.turn_id == tid,\n"
        "                AiChatMessage.del_flag == DEL_FLAG_UNDELETED,\n"
        "            )\n"
        "            .values(del_flag=DEL_FLAG_DELETED)\n",
        "                AiChatMessage.turn_id == tid,\n"
        "            )\n"
        "            .values(del_flag=DEL_FLAG_DELETED)\n",
        "期望亮 D5（dropped 变成 2）—— dropped 语义没被改坏的守卫",
    ),
    (
        # ⚠️ 这一条就是「修复前的响应形状」的等价变异（仓库里 HEAD 早于 drop-turn 特性，
        #    没有可用的 git 基线可回退，所以用单变量变异复刻修复前的形状）。
        "M8", "响应退回修复前的形状（只回 dropped，没有 matched）", AI,
        '    return success({"dropped": int(result["dropped"]), "matched": int(result["matched"])})\n',
        '    return success({"dropped": int(result["dropped"])})\n',
        "期望亮所有读 matched 的断言：D1/D5/D6/D6b/D9b/D11/D12",
    ),
    (
        "M9", "服务层空值闸门退回 int 0（修复前的形状）", SVC,
        '        return {"dropped": 0, "matched": 0}\n',
        "        return 0  # 修复前的形状\n",
        "期望亮 D8 / D14（同一个 return 语句，两层空值闸门共用）",
    ),
]


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def read(p):
    with open(p, "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    return raw.decode("utf-8").replace("\r\n", "\n"), crlf


def write(p, text, crlf):
    data = text.replace("\n", "\r\n") if crlf else text
    with open(p, "wb") as f:
        f.write(data.encode("utf-8"))


def run_probe(tag):
    out = os.path.join(OUTDIR, f"{tag}.txt")
    with open(out, "wb") as f:
        p = subprocess.run([PY, PROBE], cwd=MIRROR, stdout=f, stderr=subprocess.STDOUT)
    text = open(out, encoding="utf-8", errors="replace").read()
    red = re.findall(r"^\s*\[FAIL\]\s+(\S+)", text, re.M)
    banner = re.search(r"被测代码：app 包=(\S+)", text)
    md5s = re.findall(r"^\s+(\S+\.py) md5=(\w+)", text, re.M)
    return p.returncode, red, (banner.group(1) if banner else "?"), md5s, out


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    bad = []
    for rel, want in EXPECT.items():
        got = md5(os.path.join(MIRROR, rel))
        print(f"镜像 {rel} md5={got}（期望 {want}）{'OK' if got == want else '!! 不是修复版，拒绝开跑'}")
        if got != want:
            bad.append(rel)
    if bad:
        print("!! 镜像不是预期的修复版 → 拒绝开跑（只断言还原是不够的）")
        return 2
    if not os.path.isdir(PRISTINE):
        print(f"!! 缺 pristine 备份目录 {PRISTINE}")
        return 2

    # ---------- 0. 先跑一遍未变异的镜像（基线：必须全绿）----------
    rc, red, appdir, md5s, out = run_probe("M0-baseline")
    print(f"\n=== M0 未变异基线 ===\n  退出码={rc} 红={red or '（无）'} app={appdir}")
    print(f"  输出={out}")
    if rc != 0 or red:
        print("!! 基线不绿 → 后面的变异结论都不能用")
        return 2

    rows = []
    for tag, desc, rel, old, new, expect in MUTS:
        target = os.path.join(MIRROR, rel)
        # pristine 是 `app/` 整份的拷贝 → 去掉 rel 开头的 `app/` 再拼
        pristine = os.path.join(PRISTINE, rel.split("/", 1)[1])
        src, crlf = read(target)
        hits = src.count(old)
        if hits != 1:
            print(f"\n=== {tag} {desc} ===\n  !! 替换命中 {hits} 次（必须恰好 1）→ 跳过，不计入结论")
            rows.append((tag, desc, "SKIP(命中 %d)" % hits, expect))
            continue
        try:
            write(target, src.replace(old, new, 1), crlf)
            mutated_md5 = md5(target)
            rc, red, appdir, md5s, out = run_probe(tag)
        finally:
            shutil.copyfile(pristine, target)          # 整份写回
            restored = md5(target)
        print(f"\n=== {tag} {desc} ===\n  {rel} 变异后 md5={mutated_md5}；还原后 md5={restored}"
              f"{'  OK' if restored == EXPECT[rel] else '  !! 还原失败'}")
        print(f"  退出码={rc} 红={sorted(red) or '（无 —— 这条变异没被任何断言抓到）'}")
        print(f"  {expect}\n  输出={out}")
        print(f"  探针自报的 md5：{md5s}")
        rows.append((tag, desc, ", ".join(sorted(red)) or "（无）", expect))

    print("\n" + "=" * 78)
    print("变异表")
    print("=" * 78)
    for tag, desc, red, expect in rows:
        print(f"{tag:4s} {desc}\n     红={red}\n     预期={expect}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
