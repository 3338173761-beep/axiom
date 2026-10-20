# -*- coding: utf-8 -*-
"""Axiom 综合归档引擎：tar/zip/gz/bz2/xz/lzma/zst/br/lz4/uue/ar/cpio/deb 浏览器内解包
纯 Python + 标准库（Pyodide 内置 gzip/bz2/lzma/tarfile/zipfile；zstd/brotli/lz4 可选包）
输出格式与 sevenz.py 一致：清单 + 文本预览
"""
import io, os, sys, tarfile, zipfile, gzip, bz2, lzma


def _uudecode(data):
    """自研 uuencode 解码（不依赖标准库 uu 模块，Pyodide/3.12 均可）"""
    lines = data.splitlines()
    out = bytearray()
    in_body = False
    for line in lines:
        if not in_body:
            if line.startswith(b"begin "):
                in_body = True
            continue
        if line.startswith(b"end"):
            break
        if not line:
            continue
        count = (line[0] - 32) & 0x3f
        if count == 0:
            continue
        vals = []
        for c in line[1:]:
            vals.append((c - 32) & 0x3f)
        i = 0
        while count > 0 and i + 3 < len(vals):
            out.append((vals[i] << 2) | (vals[i + 1] >> 4))
            if count > 1:
                out.append(((vals[i + 1] & 0x0f) << 4) | (vals[i + 2] >> 2))
            if count > 2:
                out.append(((vals[i + 2] & 0x03) << 6) | vals[i + 3])
            count -= 3
            i += 4
    return bytes(out)


def _fmt_size(n):
    if n < 1024: return "%d B" % n
    if n < 1024 * 1024: return "%.1f KB" % (n / 1024)
    return "%.1f MB" % (n / 1024 / 1024)


def _preview(data, maxlen=400):
    try:
        t = data.decode("utf-8", errors="replace")
    except Exception:
        return ""
    t = t.replace("\x00", "").strip()
    if not t or not any(ch.isalpha() for ch in t):
        return ""
    return t[:maxlen]


def _list_result(files, name):
    """files: [(relpath, data_bytes)]"""
    lines = ["归档解包完成：共 %d 个文件（%s）" % (len(files), name)]
    total = 0
    for rel, d in files:
        lines.append("- %s (%s)" % (rel, _fmt_size(len(d))))
        total += len(d)
    lines.append("（解出总大小 %s）" % _fmt_size(total))
    lines.append("")
    lines.append("===== 文本预览 =====")
    shown = 0
    for rel, d in files:
        if shown >= 8: break
        if d and _preview(d):
            lines.append("\n--- %s ---\n%s" % (rel, _preview(d)))
            shown += 1
    return "\n".join(lines)


# ---------- tar ----------
def _tar(data, name):
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except Exception as e:
        return "tar 解析失败：%s" % e
    files = []
    try:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                files.append((m.name, f.read() if f else b""))
            elif m.isdir():
                files.append((m.name.rstrip("/") + "/", b""))
    except Exception as e:
        return "tar 解包失败：%s" % e
    finally:
        tf.close()
    return _list_result(files, name)


# ---------- zip ----------
def _zip(data, name):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as e:
        return "zip 解析失败：%s" % e
    files = []
    try:
        for m in zf.infolist():
            if m.is_dir():
                files.append((m.filename.rstrip("/") + "/", b""))
            else:
                try:
                    files.append((m.filename, zf.read(m)))
                except Exception:
                    files.append((m.filename + " [读取失败]", b""))
    except Exception as e:
        return "zip 解包失败：%s" % e
    finally:
        zf.close()
    return _list_result(files, name)


# ---------- 单文件压缩 ----------
def _single(data, decompress_fn, name, label):
    try:
        out = decompress_fn(data)
    except Exception as e:
        return "%s 解压失败：%s" % (label, e)
    files = [(name.rsplit(".", 1)[0] if "." in name else name + ".out", out)]
    return _list_result(files, name)


def _zstd(data, name):
    try:
        import zstandard
        out = zstandard.ZstdDecompressor().decompress(data, max_output_size=0x40000000)
    except Exception as e:
        return "ZSTD 解压失败（需要 zstandard 包）：%s" % e
    return _list_result([(name.rsplit(".", 1)[0], out)], name)


def _brotli(data, name):
    try:
        import brotli
        out = brotli.decompress(data)
    except Exception as e:
        return "Brotli 解压失败（需要 brotli 包）：%s" % e
    return _list_result([(name.rsplit(".", 1)[0], out)], name)


def _lz4(data, name):
    try:
        import lz4.frame
        out = lz4.frame.decompress(data)
    except Exception as e:
        return "LZ4 解压失败（需要 lz4 包）：%s" % e
    return _list_result([(name.rsplit(".", 1)[0], out)], name)


# ---------- uu ----------
def _uue(data, name):
    try:
        out = _uudecode(data)
        if not out:
            return "uue 解码结果为空"
    except Exception as e:
        return "uue 解码失败：%s" % e
    return _list_result([(name.rsplit(".", 1)[0] + ".out", out)], name)


# ---------- ar（Unix 归档） ----------
def _ar(data, name):
    if not data.startswith(b"!<arch>\n"):
        return "ar 头无效"
    pos = 8
    files = []
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        fname = hdr[:16].decode("ascii", errors="replace").rstrip()
        fsize = hdr[48:58].decode("ascii", errors="replace").strip()
        try:
            size = int(fsize)
        except ValueError:
            break
        body = data[pos + 60:pos + 60 + size]
        if fname.endswith("/"):
            fname = fname.rstrip("/")
        files.append((fname, body))
        pos += 60 + size
        if pos < len(data) and data[pos] in (b"\n"[0], b"\x0a"[0]):
            pos += 1
    return _list_result(files, name)


# ---------- cpio ----------
def _cpio(data, name):
    files = []
    pos = 0
    # 支持 newc（070701）/ odc（070707）魔数；其余报错
    if data[pos:pos + 6] in (b"070701", b"070702"):
        while pos + 110 <= len(data):
            hdr = data[pos:pos + 110]
            if hdr[:6] not in (b"070701", b"070702"):
                break
            namesize = int(hdr[94:102], 16)
            filesize = int(hdr[54:62], 16)
            fname = data[pos + 110:pos + 110 + namesize].rstrip(b"\x00").decode("utf-8", errors="replace")
            body_start = pos + 110 + ((namesize + 3) & ~3)
            body = data[body_start:body_start + filesize]
            if fname == "TRAILER!!!":
                break
            if fname.endswith("/"):
                files.append((fname.rstrip("/") + "/", b""))
            else:
                files.append((fname, body))
            pos = body_start + ((filesize + 3) & ~3)
        return _list_result(files, name)
    return "cpio 格式暂不支持（仅 newc/odc）"


# ---------- deb（ar + 数据解压） ----------
def _deb(data, name):
    files = _ar(data, name)
    # deb 是 ar 归档，内含 control.tar.* + data.tar.* —— 递归解包 data 成员
    out = []
    for rel, d in files:
        if rel.endswith(".tar.xz") or rel.endswith(".tar.zst") or rel.endswith(".tar.gz") or rel.endswith(".tar.bz2"):
            try:
                sub = _tar(d, rel)
                out.append(("[" + rel + "]", sub))
            except Exception:
                out.append((rel, d))
        else:
            out.append((rel, d))
    if any(o[0].startswith("[") for o in out):
        return "\n\n".join(["= 外层 ar ="] + ["- %s (%s)" % (r, _fmt_size(len(d))) for r, d in out if not r.startswith("[")] +
                             ["", "= data 包解出 ="] + [s for r, s in out if r.startswith("[")])
    return _list_result(files, name)


# ---------- 入口 ----------
def decompile_archive(data, name):
    lower = name.lower()
    # tar 系列（tarfile 自动识别 gz/bz2/xz/zst 压缩）
    if lower.endswith((".tar", ".tgz", ".tbz2", ".txz", ".tzst", ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")):
        return _tar(data, name)
    # zip 魔数
    if data[:4] == b"PK\x03\x04" or data[:2] == b"PK":
        return _zip(data, name)
    # 单文件压缩（先魔数后扩展名）
    if data[:2] == b"\x1f\x8b" or lower.endswith(".gz"):
        return _single(data, gzip.decompress, name, "GZIP")
    if data[:3] == b"BZh" or lower.endswith(".bz2"):
        return _single(data, bz2.decompress, name, "BZIP2")
    if data[:6] == b"\xfd7zXZ\x00" or lower.endswith((".xz", ".lzma")):
        return _single(data, lzma.decompress, name, "XZ/LZMA")
    if data[:4] == b"\x28\xb5\x2f\xfd" or lower.endswith(".zst"):
        return _zstd(data, name)
    if lower.endswith(".br"):
        return _brotli(data, name)
    if lower.endswith(".lz4") or data[:4] == b"\x04\x22\x4d\x18":
        return _lz4(data, name)
    if lower.endswith(".uue") or data[:5] == b"begin":
        return _uue(data, name)
    if lower.endswith(".ar") or data.startswith(b"!<arch>\n"):
        return _ar(data, name)
    if lower.endswith(".cpio") or data[:6] in (b"070701", b"070702"):
        return _cpio(data, name)
    if lower.endswith(".deb"):
        return _deb(data, name)
    return "无法识别该压缩/归档类型（扩展名: %s）" % lower


if __name__ == "__main__":
    # 本地快速自测
    data = open(sys.argv[1], "rb").read()
    print(decompile_archive(data, sys.argv[1]))
