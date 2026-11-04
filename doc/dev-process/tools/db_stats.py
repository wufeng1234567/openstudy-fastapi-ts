"""从码道 opencode.db 统计开发数据（只读，不复制、不改库）。

用法：
    python db_stats.py
    python db_stats.py <opencode.db 路径>

原理：以 SQLite immutable 只读方式打开，避免被运行中的码道进程锁住。
"""
import sqlite3, json, collections, datetime, os, sys


def jd(s):
    try:
        return json.loads(s)
    except Exception:
        return {}


def connect_ro(path):
    path = os.path.abspath(path).replace('\\', '/')
    uri = f"file:{path}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        r'~/.codeartsdoer/cli-data/opencode.db')
    if not os.path.exists(p):
        raise SystemExit(f"找不到数据库：{p}")
    c = connect_ro(p)
    c.row_factory = sqlite3.Row

    sess = c.execute("select * from session order by time_created").fetchall()
    print(f"会话数: {len(sess)}")
    for r in sess:
        d = dict(r)
        t = d['time_created'] / 1000 if d['time_created'] else 0
        dt = datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M') if t else '?'
        kind = 'sub' if d['parent_id'] else 'root'
        print(f"  {d['id']} | {kind} | {dt} | {d['directory']}")

    roles = collections.Counter()
    for r in c.execute("select data from message"):
        roles[jd(r[0]).get('role') or jd(r[0]).get('type')] += 1
    print("\n消息角色:", dict(roles))

    ptypes = collections.Counter()
    tools = collections.Counter()
    perday = collections.Counter()
    files = set()
    times = []
    for r in c.execute("select time_created, data from part"):
        d = jd(r[1])
        ptypes[d.get('type')] += 1
        if r[0]:
            times.append(r[0])
        if d.get('type') == 'tool':
            tool = d.get('tool') or d.get('toolName') or '?'
            tools[tool] += 1
            if r[0]:
                perday[datetime.datetime.fromtimestamp(r[0] / 1000).strftime('%Y-%m-%d')] += 1
            inp = (d.get('state') or {}).get('input') or {}
            fp = inp.get('filePath') or inp.get('file_path')
            if fp and tool in ('edit', 'write'):
                files.add(fp)
    print("part 类型:", dict(ptypes))
    print("\n工具调用分布:")
    for k, v in tools.most_common():
        print(f"  {k:14s} {v}")
    print("工具调用合计:", sum(tools.values()))
    print("被编辑/写入的不同文件数:", len(files))
    print("按天工具调用:", dict(sorted(perday.items())))
    if times:
        print("时间跨度:", datetime.datetime.fromtimestamp(min(times) / 1000),
              "->", datetime.datetime.fromtimestamp(max(times) / 1000))


if __name__ == '__main__':
    main()
