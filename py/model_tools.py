# -*- coding: utf-8 -*-
"""model_tools — 3D 模型解析（零依赖）：
  obj / stl / ply / gltf / glb / dae / off
入口：parse_model(data, filename) -> str|None
"""
import re
import io
import json
import struct
import xml.etree.ElementTree as ET


def parse_obj(data):
    """Wavefront OBJ：顶点/纹理/面计数"""
    if not data[:8].lstrip().startswith((b"#", b"v", b"f", b"s", b"o", b"g", b"mtl", b"usemtl", b"vt", b"vn", b"l", b"p")):
        return None
    text = data.decode("utf-8", "replace")
    nv = len(re.findall(r"(?m)^v\s+\S", text))
    nvt = len(re.findall(r"(?m)^vt\s+\S", text))
    nvn = len(re.findall(r"(?m)^vn\s+\S", text))
    nf = len(re.findall(r"(?m)^f\s+\S", text))
    nmat = len(re.findall(r"(?m)^usemtl\s+(\S+)", text))
    matls = set(re.findall(r"(?m)^usemtl\s+(\S+)", text))
    if nv == 0 and nf == 0:
        return None
    return "\n".join([
        "OBJ 网格模型",
        "顶点: %d · 纹理坐标: %d · 法线: %d" % (nv, nvt, nvn),
        "面: %d · 材质组: %d%s" % (nf, nmat, ("（" + " / ".join(sorted(matls)[:6]) + "）" if matls else "")),
    ])


def parse_stl(data):
    """STL：二进制（80 字节头 + uint32 三角数）或 ASCII 'solid'"""
    if data[:5] == b"solid" and data[5:8] in (b" \r", b" \n", b"\r\n", b" \r\n"):
        text = data.decode("ascii", "replace")
        n = len(re.findall(r"(?m)^\s*facet normal", text))
        if n:
            return "STL ASCII 网格 · %d 个三角面" % n
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if n < 10000000:
            return "\n".join([
                "STL 二进制网格",
                "三角面: %d（预计 %d bytes 数据）" % (n, n * 50),
            ])
    return None


def parse_ply(data):
    """PLY：头部文本格式 + 元素计数（binary_little_endian 等）"""
    if data[:3] != b"ply":
        return None
    head_end = data.find(b"end_header")
    if head_end < 0:
        return None
    head = data[:head_end].decode("ascii", "replace")
    fmt = re.search(r"format\s+(\S+)", head)
    verts = re.search(r"element vertex (\d+)", head)
    faces = re.search(r"element face (\d+)", head)
    if not verts and not faces:
        return None
    return "\n".join([
        "PLY 多边形模型 · 格式 %s" % (fmt.group(1) if fmt else "?"),
        "顶点: %s · 面: %s" % (verts.group(1) if verts else "0", faces.group(1) if faces else "0"),
        "头部属性行: %d" % len([l for l in head.splitlines() if l.startswith("property")]),
    ])


def parse_gltf(data):
    """glTF：JSON 场景统计"""
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return None
    if not isinstance(obj, dict) or "asset" not in obj:
        return None
    def cnt(key):
        v = obj.get(key)
        return len(v) if isinstance(v, list) else 0
    scenes = obj.get("scenes") or []
    scene_names = "/".join(s.get("name", "scene%d" % i) for i, s in enumerate(scenes[:8]))
    return "\n".join([
        "glTF 三维场景",
        "场景: %s" % (scene_names or "(默认)"),
        "网格: %d · 节点: %d · 材质: %d · 动画: %d · 贴图: %d" % (
            cnt("meshes"), cnt("nodes"), cnt("materials"), cnt("animations"), cnt("textures")),
        "asset: %s" % json.dumps(obj.get("asset", {}), ensure_ascii=False)[:120],
    ])


def parse_glb(data):
    """GLB 二进制容器：12 字节头 + chunk（JSON 段）"""
    if len(data) < 12 or data[:4] != b"glTF":
        return None
    ver, length = struct.unpack("<II", data[4:12])
    if len(data) < length:
        length = len(data)
    out = ["GLB 二进制模型容器 (glTF v%d, %d bytes)" % (ver, length)]
    pos = 12
    idx = 0
    while pos + 8 <= length and idx < 8:
        clen, ctype = struct.unpack("<II", data[pos:pos + 8])
        pos += 8
        cname = {0x4E4F534A: "JSON", 0x004E4942: "BIN"}.get(ctype, "0x%08X" % ctype)
        out.append("chunk %d: %s（%d bytes）" % (idx, cname, clen))
        if ctype == 0x4E4F534A and pos + clen <= length:
            try:
                obj = json.loads(data[pos:pos + clen].decode("utf-8", "replace"))
                if isinstance(obj, dict):
                    out.append("网格: %d · 节点: %d · 材质: %d" % (
                        len(obj.get("meshes", [])), len(obj.get("nodes", [])), len(obj.get("materials", []))))
            except Exception:
                pass
        pos += clen
        idx += 1
    return "\n".join(out)


def parse_dae(data):
    """COLLADA DAE：XML 场景统计"""
    if not data.lstrip().startswith(b"<"):
        return None
    try:
        root = ET.fromstring(data.decode("utf-8", "replace"))
    except Exception:
        return None
    if not root.tag.endswith("COLLADA"):
        return None
    def tag(name):
        for e in root.iter():
            if e.tag.endswith(name):
                return e
        return None
    ngeo = len([e for e in root.iter() if e.tag.endswith("geometry")])
    nmat = len([e for e in root.iter() if e.tag.endswith("material")])
    nimg = len([e for e in root.iter() if e.tag.endswith("image")])
    nscene = len([e for e in root.iter() if e.tag.endswith("visual_scene")])
    unit = tag("unit")
    up = tag("up_axis")
    return "\n".join([
        "COLLADA 数字资产交换场景",
        "几何: %d · 材质: %d · 图像: %d · 场景: %d" % (ngeo, nmat, nimg, nscene),
        "单位: %s · 上轴: %s" % (
            (unit.get("meter") if unit is not None else "?"),
            (up.text if up is not None else "?")),
    ])


def parse_off(data):
    """OFF：顶点/面/边计数"""
    text = data.decode("utf-8", "replace")
    if not text.startswith("OFF"):
        return None
    parts = re.split(r"[\r\n]+", text.strip(), maxsplit=2)
    if len(parts) < 2:
        return None
    m = re.search(r"(\d+)\s+(\d+)\s+(\d+)", parts[1])
    if not m:
        return None
    return "OFF 网格 · 顶点 %s · 面 %s · 边 %s" % (m.group(1), m.group(2), m.group(3))


def parse_fbx(data):
    """Autodesk FBX：二进制（Kaydara FBX Binary）+ ASCII 两种"""
    if len(data) < 25:
        return None
    if data[:21] == b"Kaydara FBX Binary  \x00":
        ver = struct.unpack("<I", data[21:25])[0] if len(data) >= 25 else 0
        out = ["Autodesk FBX（二进制）"]
        out.append("版本: %d" % ver)
        out.append("文件大小: %d B" % len(data))
        return "\n".join(out)
    if data.startswith(b"FBXHeaderExtension:"):
        text = data.decode("latin1", "replace")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        out = ["Autodesk FBX（ASCII）"]
        out.append("行数: %d" % len(lines))
        found = []
        for l in lines:
            low = l.lower()
            if low.startswith("creator") or low.startswith("fbxversion"):
                found.append(l[:80])
        if found:
            out.append("元数据: " + " | ".join(found[:4]))
        return "\n".join(out)
    return None


def parse_lwo(data):
    """LightWave 3D 对象：FORM + LWOB/LWLO/LWSC，遍历块"""
    if len(data) < 12 or data[:4] != b"FORM":
        return None
    kind = data[8:12].decode("latin1", "replace")
    out = ["LightWave 3D 对象（%s）" % kind]
    chunks = []
    pos = 12
    while pos + 8 <= len(data) and len(chunks) < 20:
        c = data[pos:pos + 4].decode("latin1", "replace")
        ln = struct.unpack_from(">I", data, pos + 4)[0]
        if not (c.isprintable() and 4 <= ln <= 10000000):
            break
        chunks.append(c)
        pos += 8 + ln
        if pos > len(data):
            break
    out.append("块类型: " + ", ".join(chunks) if chunks else "无块")
    out.append("文件大小: %d B" % len(data))
    return "\n".join(out)


def parse_model(data, filename):
    fn = (filename or "").lower()
    for parser, exts in ((parse_obj, (".obj",)), (parse_stl, (".stl",)),
                         (parse_ply, (".ply",)), (parse_gltf, (".gltf",)),
                         (parse_glb, (".glb",)), (parse_dae, (".dae",)),
                         (parse_off, (".off",)), (parse_fbx, (".fbx",)),
                         (parse_lwo, (".lwo",))):
        if fn.endswith(exts):
            r = parser(data)
            if r:
                return r
    for parser in (parse_obj, parse_stl, parse_ply, parse_gltf, parse_glb, parse_dae, parse_off,
                   parse_fbx, parse_lwo):
        r = parser(data)
        if r:
            return r
    return None


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], "rb").read()
    print(parse_model(data, sys.argv[1]))
