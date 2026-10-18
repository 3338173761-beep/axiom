# -*- coding: utf-8 -*-
"""Axiom APK 引擎：解包 + AndroidManifest 解析 + classes.dex 反编译（smali）
纯 Python（zipfile + dalvik_smali + apkInspector.axml 可选）。
"""
import io, zipfile

def _try_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

def decompile_apk(data, filename="input.apk"):
    out = []
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = sorted(zf.infolist(), key=lambda i: i.filename)
    total = sum(i.file_size for i in infos)
    out.append("# APK 解包：%s · %d 个文件 · 解压后 %d 字节" % (filename, len(infos), total))
    # 文件清单
    out.append("")
    out.append("## 文件清单")
    for i in infos[:200]:
        out.append("%10d  %s" % (i.file_size, i.filename))
    if len(infos) > 200:
        out.append("... 其余 %d 个省略" % (len(infos) - 200))
    # AndroidManifest 解析（apkInspector 可选）
    try:
        manifest_bytes = zf.read("AndroidManifest.xml")
    except KeyError:
        manifest_bytes = None
    if manifest_bytes:
        axml = _try_import("apk_inspector.axml")
        if axml is None:
            axml = _try_import("apkinspector.axml")
        out.append("")
        out.append("## AndroidManifest.xml")
        try:
            parsed = axml.parse(manifest_bytes)
            # parsed 是 ResXMLTree 结构，转可读摘要
            out.append(_axml_summary(parsed))
        except Exception as e:
            out.append("（清单解析失败：%s）" % e)
    # DEX 反编译
    dex_names = [i.filename for i in infos if i.filename.endswith(".dex")]
    for dn in dex_names[:3]:
        try:
            dex_data = zf.read(dn)
            from dalvik_smali import decompile_dex
            out.append("")
            out.append("# ===== %s（%d 字节）=====" % (dn, len(dex_data)))
            out.append(decompile_dex(dex_data))
        except Exception as e:
            out.append("")
            out.append("# %s 反编译失败：%s" % (dn, e))
    # 其他可读文本资源（简要）
    txt_ext = (".txt", ".json", ".xml", ".properties", ".conf")
    out.append("")
    out.append("## 文本资源（前 10 个）")
    shown = 0
    for i in infos:
        if i.filename.endswith(txt_ext) and shown < 10:
            try:
                txt = zf.read(i).decode("utf-8", errors="replace")
                out.append("--- %s ---" % i.filename)
                out.append(txt[:1200])
                shown += 1
            except Exception:
                pass
    return "\n".join(out)

def _axml_summary(tree):
    """把 apkInspector 解析出的 AXML 树转成可读摘要。"""
    lines = []
    def walk(node, depth=0):
        pad = "  " * depth
        tag = getattr(node, "name", None) or getattr(node, "tag", None) or type(node).__name__
        lines.append("%s<%s>" % (pad, tag))
        # attributes
        attrs = getattr(node, "attributes", None) or getattr(node, "attrs", None) or []
        for a in attrs:
            aname = getattr(a, "name", None) or ""
            aval = getattr(a, "value", None) or getattr(a, "text", None) or ""
            lines.append("%s  %s=\"%s\"" % (pad, aname, aval))
        for c in getattr(node, "children", []) or []:
            walk(c, depth + 1)
    try:
        walk(tree)
    except Exception as e:
        return "（清单摘要失败：%s）" % e
    return "\n".join(lines)

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path and path.lower().endswith((".apk", ".aab", ".xapk")):
        with open(path, "rb") as f:
            print(decompile_apk(f.read(), path.split("\\")[-1].split("/")[-1]))
    else:
        print("用法: python apk_tool.py <file.apk>")
