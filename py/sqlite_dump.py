# -*- coding: utf-8 -*-
"""sqlite_dump — SQLite 数据库结构 + 数据 dump（Pyodide 内置 sqlite3，零依赖）
入口：dump_sqlite(data) -> str|None
"""
import sqlite3
import tempfile
import os


def dump_sqlite(data):
    if data[:16] != b"SQLite format 3\x00":
        return None
    ps = int.from_bytes(data[16:18], "big")
    vmajor = int.from_bytes(data[96:98], "big")
    vminor = int.from_bytes(data[98:100], "big")
    out = ["SQLite 数据库（文件格式 v%d.%d）  页大小 %d  文件 %d 字节" % (vmajor, vminor, ps, len(data))]
    fn = tempfile.mktemp(suffix=".db")
    try:
        with open(fn, "wb") as f:
            f.write(data)
        con = sqlite3.connect(fn)
        cur = con.cursor()
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type IN ('table','view','index') ORDER BY name")
        objs = cur.fetchall()
        out.append("对象: %d 个（表/视图/索引）" % len(objs))
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables[:14]:
            try:
                n = cur.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
                out.append("表 %s: %d 行" % (t, n))
                cur.execute('SELECT * FROM "%s" LIMIT 3' % t.replace('"', '""'))
                cols = [d[0] for d in cur.description]
                out.append("  列: " + ", ".join(cols))
                for row in cur.fetchall():
                    out.append("  " + " | ".join(str(c)[:48] for c in row))
            except Exception as e:
                out.append("  读取失败: %s" % e)
        con.close()
        os.remove(fn)
    except Exception as e:
        out.append("解析失败: %s" % e)
        try:
            os.remove(fn)
        except Exception:
            pass
    return "\n".join(out)
