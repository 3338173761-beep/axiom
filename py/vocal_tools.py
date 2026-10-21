# -*- coding: utf-8 -*-
"""vocal_tools.py — 歌声合成工程引擎（零依赖）
覆盖：VocalSharp(.vspx XML)、Cadencii(.xvsq XML)、
NNSVS N-Editor(.nep zip+json)、VOX Factory(.vfp zip+json)、
Vogen(.vog zip+json)、KaraFun(.kfn zip 包)
"""

import re
import json
import zipfile
import io


def _zip_json_text(zf, hint, out):
    """从 zip 里找 json 并提取关键文本"""
    for n in zf.namelist():
        if n.lower().endswith(".json"):
            try:
                raw = zf.read(n)
                d = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                continue
            def walk(o, depth=0):
                if depth > 3:
                    return
                if isinstance(o, dict):
                    for k, v in o.items():
                        if isinstance(v, str) and len(v) > 1 and (depth >= 1 or k.lower() in ("name", "title", "projectname", "songname")):
                            out.append("%s: %s" % (k, v[:60]))
                        walk(v, depth + 1)
                elif isinstance(o, list):
                    for v in o[:6]:
                        walk(v, depth + 1)
            walk(d)
            return n
    return None


def parse_vspx(data):
    """VocalSharp：XML 工程"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "<vspx" not in text[:2000].lower() and "vocalSharp" not in text[:2000].lower() and "VSQX" not in text[:2000]:
        return None
    out = ["VocalSharp 工程（XML）"]
    m = re.search(r"<([a-zA-Z0-9_]+)[^>]*version=['\"]([^'\"]+)", text[:2000])
    if m:
        out.append("版本: " + m.group(2))
    notes = re.findall(r"<([a-zA-Z0-9_]*[Nn]ote[a-zA-Z0-9_]*)[^>]*>", text)
    if notes:
        out.append("音符标签: %d" % len(notes))
    m = re.search(r"<([a-zA-Z0-9_]*[Tt]rack[a-zA-Z0-9_]*)[^>]*>", text)
    if m:
        out.append("轨道标签: " + m.group(1))
    out.append("XML 规模: %d 字符" % len(text))
    return "\n".join(out)


def parse_xvsq(data):
    """Cadencii：XML 工程（VOCALOID 2 序列）"""
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return None
    if "<cadencii" not in text[:3000].lower() and "Cadencii" not in text[:3000]:
        return None
    out = ["Cadencii 工程（xvsq，VOCALOID2 序列 XML）"]
    notes = re.findall(r"<([a-zA-Z0-9_]*[Nn]ote[a-zA-Z0-9_]*)[^>]*>", text)
    out.append("音符标签: %d" % len(notes))
    n = re.findall(r"<([a-zA-Z0-9_]*[Pp]hrase[a-zA-Z0-9_]*)[^>]*>", text)
    out.append("乐句: %d" % len(n))
    m = re.search(r"<([a-zA-Z0-9_]*[Tt]rack[a-zA-Z0-9_]*)[^>]*>", text)
    if m:
        out.append("轨道: " + m.group(1))
    return "\n".join(out)


def parse_zip_vocal(data, hint):
    """nep/vfp/vog：zip + JSON 工程"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    names = zf.namelist()
    if not names:
        return None
    out = ["%s 工程（zip 容器）" % hint]
    out.append("内部文件: %d" % len(names))
    hit = _zip_json_text(zf, hint, out)
    if hit:
        out.append("元数据来源: " + hit)
    else:
        out.append("（未找到 JSON 元数据）")
    return "\n".join(out)


def parse_kfn(data):
    """KaraFun：zip 包（.kar 音频 + .kfn 歌词等）"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    names = zf.namelist()
    if not names:
        return None
    out = ["KaraFun 歌曲包（zip）"]
    out.append("内部文件: %d" % len(names))
    for n in names[:14]:
        out.append("  " + n)
    for n in names:
        if n.lower().endswith((".txt", ".lrc", ".kfn", ".json")):
            try:
                t = zf.read(n).decode("utf-8", "replace")[:200]
                out.append("--- %s ---" % n)
                out.append(t.strip()[:180])
            except Exception:
                pass
    return "\n".join(out)


def parse_vocal(data, filename):
    fn = (filename or "").lower()
    ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
    if ext == "vspx":
        r = parse_vspx(data)
        if r:
            return r
    if ext == "xvsq":
        r = parse_xvsq(data)
        if r:
            return r
    if ext == "nep":
        r = parse_zip_vocal(data, "NNSVS N-Editor")
        if r:
            return r
    if ext == "vfp":
        r = parse_zip_vocal(data, "VOX Factory")
        if r:
            return r
    if ext == "vog":
        r = parse_zip_vocal(data, "Vogen")
        if r:
            return r
    if ext == "kfn":
        r = parse_kfn(data)
        if r:
            return r
    # 魔数兜底：XML 家族 / zip 容器
    for parser in (parse_vspx, parse_xvsq, parse_kfn):
        try:
            r = parser(data)
        except Exception:
            continue
        if r is not None:
            return r
    try:
        r = parse_zip_vocal(data, ext or "工程")
        if r is not None:
            return r
    except Exception:
        pass
    if ext:
        return "该歌声合成工程格式（.%s）暂无解析器；大小 %d 字节。" % (ext, len(data))
    return "未知歌声合成工程二进制：%d 字节" % len(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            print(parse_vocal(f.read(), sys.argv[1]))
