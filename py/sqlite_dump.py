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


def dump_dbf(data):
    """dBase III/IV：头（版本/记录数/字段描述符）+ 记录数据"""
    if data[:1] not in (b"\x02", b"\x03", b"\x30", b"\x31", b"\x83", b"\x8b", b"\xF5"):
        return None
    if len(data) < 32:
        return None
    ver = data[0]
    import struct
    recs = struct.unpack("<I", data[4:8])[0]
    hlen = struct.unpack("<H", data[8:10])[0]
    rlen = struct.unpack("<H", data[10:12])[0]
    out = ["dBase 数据库（版本 0x%02X）" % ver,
           "记录: %d · 表头 %d bytes · 每条 %d bytes" % (recs, hlen, rlen)]
    # 字段描述符：32 bytes each，名字 11 + 类型 1 + ...
    fields = []
    pos = 32
    while pos + 32 <= min(hlen, len(data)) and data[pos] not in (0x0D, 0x00):
        name = data[pos:pos + 11].split(b"\x00")[0].decode("latin1", "replace")
        ftype = chr(data[pos + 11])
        flen = data[pos + 16]
        fields.append((name, ftype, flen))
        pos += 32
    out.append("字段: %s" % " / ".join("%s(%s,%d)" % (n, t, l) for n, t, l in fields[:24]))
    # 前 3 条记录
    rec_off = hlen
    shown = 0
    while shown < 3 and rec_off + rlen <= len(data) and recs > 0:
        flag = data[rec_off]
        vals = []
        fpos = rec_off + 1
        for name, ftype, flen in fields:
            raw = data[fpos:fpos + flen]
            if ftype in ("C", "M", "D"):
                v = raw.rstrip(b"\x00 \r\n").decode("latin1", "replace")
            elif ftype in ("N", "F", "L"):
                asc = raw.rstrip(b"\x00 ")
                try:
                    v = str(int(asc.decode("ascii")))
                except Exception:
                    v = str(int.from_bytes(raw, "little", signed=True) if raw else 0)
            else:
                v = str(int.from_bytes(raw, "little", signed=True) if raw else 0)
            vals.append("%s=%s" % (name, v[:36]))
            fpos += flen
        out.append("- %s %s" % ("[已删除]" if flag == 0x2A else "", " | ".join(vals)))
        rec_off += rlen
        shown += 1
    return "\n".join(out)


def dump_db(data, filename):
    fn = (filename or "").lower()
    if fn.endswith((".dbf",)):
        r = dump_dbf(data)
        if r:
            return r
    r = dump_sqlite(data)
    if r:
        return r
    return dump_dbf(data)
