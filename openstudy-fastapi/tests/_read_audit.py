"""从审计代理的 transcript 里取出「最后的助手正文」——它们的报告。

transcript 是 JSONL，每行一条消息。报告的形态是最后一条 role=assistant 且带文本的消息。
跑完删掉。
"""
import json
import pathlib
import sys

base = pathlib.Path(
    r"C:\Users\liu\.codebuddy\projects\d-OpenStudy\01a0ad39-186b-70ae-a917-e133f20db2ad\subagents"
)

targets = {
    "e2e-verifier": "agent-866f4139118a4899.jsonl",
    "flow-parity-auditor": "agent-bb68c46caab44a41.jsonl",
    "db-safety-auditor": "agent-c11bb16844df4e5f.jsonl",
}

for name, fn in targets.items():
    p = base / fn
    print("=" * 78)
    print(f"### {name}  ({fn})")
    print("=" * 78)
    if not p.exists():
        print("(transcript 不存在)")
        continue

    texts = []
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            # 各种可能的包装层都试一遍
            msg = rec.get("message") if isinstance(rec, dict) else None
            role = None
            content = None
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
            if role is None and isinstance(rec, dict):
                role = rec.get("role")
                content = rec.get("content")
            if role != "assistant":
                continue
            if isinstance(content, str):
                if content.strip():
                    texts.append(content)
            elif isinstance(content, list):
                # 块类型名不固定（input_text / output_text / text…），只要带 text 就收
                buf = [
                    (blk.get("text") or "")
                    for blk in content
                    if isinstance(blk, dict) and blk.get("text")
                ]
                if "".join(buf).strip():
                    texts.append("".join(buf))

    if not texts:
        print("(没找到助手正文)")
        continue
    print(texts[-1])
    print()
