# -*- coding: utf-8 -*-
"""Axiom .NET 引擎：dnfile(元数据) + dncil(IL 反汇编) → .il 文本
纯 Python，可在 Pyodide(浏览器) 与本地运行。
"""
import struct

TOKEN_TABLES = {
    "Assembly": "0x20", "AssemblyRef": "0x23", "Event": "0x14", "Field": "0x04",
    "MemberRef": "0x0A", "MethodDef": "0x06", "ModuleRef": "0x1A", "Param": "0x08",
    "Property": "0x17", "TypeDef": "0x02", "TypeRef": "0x01", "TypeSpec": "0x1B",
    "GenericParam": "0x2A", "InterfaceImpl": "0x09", "MethodImpl": "0x19",
    "CustomAttribute": "0x0C", "DeclSecurity": "0x0E", "ManifestResource": "0x28",
    "Module": "0x00", "StandAloneSig": "0x11", "Constant": "0x0B",
}


def _token_name(pe, token):
    """token 整数 → 可读名称。"""
    try:
        t = int(token)
        table = (t >> 24) & 0xFF
        rid = t & 0xFFFFFF
        tbl_name = {0x02: "TypeDef", 0x0A: "MemberRef", 0x04: "Field", 0x06: "MethodDef",
                    0x01: "TypeRef", 0x70: "UserString", 0x1A: "ModuleRef", 0x17: "Property",
                    0x08: "Param", 0x14: "Event", 0x11: "StandAloneSig"}.get(table)
        if table == 0x70:
            us = pe.net.user_strings.get(rid)
            return "0x%08X \"%s\"" % (t, us) if us else "0x%08X" % t
        if tbl_name is None:
            return "0x%08X" % t
        rows = getattr(pe.net.mdtables, tbl_name, None)
        if rows is None or rid == 0 or rid > len(rows.rows):
            return "0x%08X" % t
        row = rows.rows[rid - 1]
        name = getattr(row, "Name", None)
        if name is not None:
            return "%s::%s" % (tbl_name, str(name))
        # MemberRef 有 Class 引用 → 尝试 TypeRef/TypeDef
        cls = getattr(row, "Class", None)
        if cls is not None:
            return "%s(0x%08X)" % (tbl_name, t)
        return "0x%08X" % t
    except Exception:
        return "0x%08X" % (int(token) if token is not None else 0)


def decompile_dotnet(data, filename="input.dll"):
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes
    import os, tempfile
    # dnfile 不支持内存加载，写临时文件（浏览器/本地通用）
    tmp = os.path.join(tempfile.gettempdir(), "axiom_dn_%s.dll" % filename.replace("\\", "_"))
    with open(tmp, "wb") as f:
        f.write(data)
    pe = dnfile.dnPE(tmp)
    out = []
    out.append("# .NET 程序集 · %s · %d 字节" % (filename, len(data)))
    md = pe.net.mdtables.MethodDef
    td = pe.net.mdtables.TypeDef
    out.append("")
    out.append("## 类型")
    for row in td.rows:
        try:
            name = str(row.Name) if row.Name is not None else "?"
        except Exception:
            name = "?"
        ns = ""
        try:
            ns = str(row.Namespace) if row.Namespace is not None else ""
        except Exception:
            ns = ""
        out.append("  .class %s.%s" % (ns, name) if ns else "  .class %s" % name)
    out.append("")
    out.append("## 方法 IL 反汇编")
    for i, row in enumerate(md.rows):
        rva = getattr(row, "Rva", None)
        if not rva:
            continue
        name = str(row.Name)
        foff = pe.get_offset_from_rva(rva)
        size = min(len(pe.__data__) - foff, 8192)
        raw = pe.__data__[foff:foff + size]
        out.append("")
        out.append(".method %s" % name)
        try:
            body = CilMethodBody(CilMethodBodyReaderBytes(raw))
            for insn in body.instructions:
                s = str(insn)
                # 增强 token 显示
                if "token(" in s:
                    try:
                        tok = int(s.split("token(")[1].split(")")[0], 16)
                        nm = _token_name(pe, tok)
                        out.append("    %s  ; %s" % (s, nm))
                        continue
                    except Exception:
                        pass
                out.append("    %s" % s)
        except Exception as e:
            out.append("    （方法体解析失败: %s）" % e)
    try:
        os.remove(tmp)
    except Exception:
        pass
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    with open(path, "rb") as f:
        print(decompile_dotnet(f.read(), path))
