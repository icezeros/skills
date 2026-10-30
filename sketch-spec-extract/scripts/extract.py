#!/usr/bin/env python3
"""Offline .sketch spec extractor.

Unpacks a .sketch file (ZIP of JSON, no Sketch app required) and emits
per-artboard design specs: layer tree with absolute (artboard-relative)
coordinates, text runs (font/size/color), fills/borders/shadows, symbol
component references and bitmap assets.

Pure stdlib. Usage: see --help or the SKILL.md next to this script.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter

ALIGN = {0: "left", 1: "right", 2: "center", 3: "justify"}


def hexcolor(c):
    if not isinstance(c, dict):
        return None
    h = "#%02X%02X%02X" % (
        round(c.get("red", 0) * 255),
        round(c.get("green", 0) * 255),
        round(c.get("blue", 0) * 255),
    )
    a = c.get("alpha", 1)
    return h if a >= 0.999 else "%s/%d%%" % (h, round(a * 100))


def sanitize(name):
    s = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip()
    return s or "_"


def n(v):
    f = float(v)
    return str(int(f)) if f == int(f) else "%.1f" % f


def esc(text):
    return text.replace("\r", "").replace("\n", "⏎")


# ---------------------------------------------------------------- model


class Doc:
    def __init__(self, sketch_path):
        self.src = sketch_path
        self.tmp = tempfile.mkdtemp(prefix="sketch-spec-")
        with zipfile.ZipFile(sketch_path) as z:
            z.extractall(self.tmp)
        with open(os.path.join(self.tmp, "meta.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        with open(os.path.join(self.tmp, "document.json"), encoding="utf-8") as f:
            self.doc = json.load(f)
        self.pages = []  # list of (page_name, page_json)
        pdir = os.path.join(self.tmp, "pages")
        for fn in sorted(os.listdir(pdir)):
            if fn.endswith(".json"):
                with open(os.path.join(pdir, fn), encoding="utf-8") as f:
                    data = json.load(f)
                self.pages.append((data.get("name") or fn[:8], data))

    def font_references(self):
        out = []
        for fr in self.doc.get("fontReferences", []):
            names = fr.get("postscriptNames")
            if names:
                out.extend(names)
        return sorted(set(out))

    def preview_png(self):
        p = os.path.join(self.tmp, "previews", "preview.png")
        return p if os.path.exists(p) else None

    def image_file(self, ref):
        # ref like "images/<hash>.png"
        p = os.path.join(self.tmp, ref)
        return p if os.path.exists(p) else None


# ------------------------------------------------------------ extraction


def text_runs(layer):
    """Return list of {text,font,size,color,align,line_height} for a text layer."""
    attr = layer.get("attributedString") or {}
    whole = attr.get("string", "")
    runs = []
    for span in attr.get("attributes", []):
        loc, ln = a_loc = (span.get("location", 0), span.get("length", 0))
        at = span.get("attributes", {})
        fd = at.get("MSAttributedStringFontAttribute") or {}
        fa = fd.get("attributes") or {}
        ps = at.get("paragraphStyle") or {}
        lh = ps.get("maximumLineHeight") or ps.get("minimumLineHeight")
        runs.append(
            {
                "text": whole[loc : loc + ln],
                "font": fa.get("name") or "?",
                "size": fa.get("size"),
                "color": hexcolor(at.get("MSAttributedStringColorAttribute")),
                "align": ALIGN.get(ps.get("alignment", 0)),
                "line_height": lh,
                "kerning": at.get("kerning"),
            }
        )
    if not runs and whole:
        runs.append(
            {"text": whole, "font": "?", "size": None, "color": None, "align": None, "line_height": None, "kerning": None}
        )
    return runs


def style_summary(layer, stats):
    """Extract fills/borders/shadows/opacity; feed stats counters."""
    st = layer.get("style") or {}
    out = {}
    fills = []
    for f in st.get("fills") or []:
        if not f.get("isEnabled", True):
            continue
        ft = f.get("fillType", 0)
        if ft == 0:
            c = hexcolor(f.get("color"))
            if c:
                fills.append(c)
                stats["colors"][c] += 1
        elif ft == 1:
            g = f.get("gradient") or {}
            stops = [hexcolor(s.get("color")) for s in g.get("stops", [])]
            fills.append("gradient(%s)" % "→".join(s for s in stops if s))
        elif ft == 4:
            fills.append("image-fill")
    if fills:
        out["fill"] = fills
    borders = []
    for b in st.get("borders") or []:
        if not b.get("isEnabled", True):
            continue
        c = hexcolor(b.get("color"))
        if c:
            borders.append("%s %s" % (n(b.get("thickness", 1)), c))
            stats["colors"][c] += 1
    if borders:
        out["border"] = borders
    shadows = []
    for s in st.get("shadows") or []:
        if not s.get("isEnabled", True):
            continue
        shadows.append(
            "%s,%s %s %s"
            % (n(s.get("offsetX", 0)), n(s.get("offsetY", 0)), n(s.get("blurRadius", 0)), hexcolor(s.get("color")) or "?")
        )
    if shadows:
        out["shadow"] = shadows
    op = (st.get("contextSettings") or {}).get("opacity", 1)
    if op < 0.999:
        out["opacity"] = round(op, 2)
    return out


def walk(layer, ox, oy, depth, lines, node, stats, images, max_text=80):
    cls = layer.get("_class", "?")
    name = layer.get("name", "")
    fr = layer.get("frame") or {}
    x, y = ox + fr.get("x", 0), oy + fr.get("y", 0)
    w, h = fr.get("width", 0), fr.get("height", 0)
    visible = layer.get("isVisible", True)
    rot = layer.get("rotation", 0)

    node.update({"name": name, "class": cls, "x": round(x, 2), "y": round(y, 2), "w": w, "h": h})
    if not visible:
        node["hidden"] = True

    extras = []
    sty = style_summary(layer, stats)
    if sty:
        node["style"] = sty
        if "fill" in sty:
            extras.append("fill=" + ",".join(sty["fill"]))
        if "border" in sty:
            extras.append("border=" + ",".join(sty["border"]))
        if "shadow" in sty:
            extras.append("shadow=" + ";".join(sty["shadow"]))
        if "opacity" in sty:
            extras.append("opacity=%s" % sty["opacity"])

    if cls == "rectangle" and layer.get("fixedRadius"):
        extras.append("r=%s" % n(layer["fixedRadius"]))
        node["radius"] = layer["fixedRadius"]
    if rot:
        extras.append("rot=%s°" % n(rot))

    if cls == "text":
        runs = text_runs(layer)
        node["runs"] = runs
        full = "".join(r["text"] for r in runs)
        r0 = runs[0] if runs else {}
        mixed = len({(r["font"], r["size"], r["color"]) for r in runs}) > 1
        disp = esc(full)
        if len(disp) > max_text:
            disp = disp[:max_text] + "…"
        style_str = "%s %s %s" % (r0.get("font"), n(r0.get("size") or 0) + "px", r0.get("color"))
        if r0.get("line_height"):
            style_str += " lh=%s" % n(r0["line_height"])
        if r0.get("align") and r0["align"] != "left":
            style_str += " " + r0["align"]
        if mixed:
            style_str += " (mixed)"
        extras.append('"%s" — %s' % (disp, style_str))
        for r in runs:
            if r.get("font"):
                stats["fonts"]["%s %s" % (r["font"], n(r.get("size") or 0))] += 1
        stats["texts"] += 1
    elif cls == "symbolInstance":
        stats["components"][name] += 1
        node["symbol_id"] = layer.get("symbolID")
        ov = layer.get("overrideValues") or []
        if ov:
            extras.append("overrides=%d" % len(ov))
    elif cls == "bitmap":
        ref = (layer.get("image") or {}).get("_ref")
        if ref:
            node["image"] = ref
            images.add(ref)
            extras.append(ref)

    flags = "" if visible else " [hidden]"
    label = name if name else cls
    line = "%s- [%s] %s%s" % ("  " * depth, cls, label, flags)
    if extras:
        line += "  " + " | ".join(extras) if cls == "text" else "  " + ", ".join(extras)
    line += "  (%s×%s @ %s,%s)" % (n(w), n(h), n(x), n(y))
    lines.append(line)

    children = []
    for sub in layer.get("layers") or []:
        cn = {}
        walk(sub, x, y, depth + 1, lines, cn, stats, images)
        children.append(cn)
    if children:
        node["children"] = children


def extract_artboard(page_name, ab):
    stats = {"colors": Counter(), "fonts": Counter(), "components": Counter(), "texts": 0}
    images = set()
    lines, root = [], {}
    fr = ab.get("frame") or {}
    bg = hexcolor(ab.get("backgroundColor")) if ab.get("hasBackgroundColor") else None
    for sub in ab.get("layers") or []:
        cn = {}
        walk(sub, 0, 0, 0, lines, cn, stats, images)
        root.setdefault("children", []).append(cn)

    root.update(
        {
            "name": ab.get("name"),
            "class": ab.get("_class"),
            "page": page_name,
            "w": fr.get("width"),
            "h": fr.get("height"),
            "background": bg,
        }
    )

    md = []
    md.append("# %s" % ab.get("name"))
    md.append("")
    md.append("- 页面: %s" % page_name)
    md.append("- 类型: %s" % ab.get("_class"))
    md.append("- 尺寸: %s × %s" % (n(fr.get("width", 0)), n(fr.get("height", 0))))
    md.append("- 背景: %s" % (bg or "无（透明）"))
    md.append(
        "- 统计: 文本 %d 个 | 颜色 %d 种 | 字体 %d 种 | 组件引用 %d 种 | 位图 %d 张"
        % (stats["texts"], len(stats["colors"]), len(stats["fonts"]), len(stats["components"]), len(images))
    )
    md.append("")
    if stats["colors"]:
        md.append("## 颜色")
        md.append("")
        md.append("| 颜色 | 用量 |")
        md.append("|---|---|")
        for c, k in stats["colors"].most_common():
            md.append("| `%s` | %d |" % (c, k))
        md.append("")
    if stats["fonts"]:
        md.append("## 字体（字族 字号）")
        md.append("")
        md.append("| 字体 | 用量 |")
        md.append("|---|---|")
        for fnt, k in stats["fonts"].most_common():
            md.append("| %s | %d |" % (fnt, k))
        md.append("")
    if stats["components"]:
        md.append("## 组件引用（symbol → 设计系统组件）")
        md.append("")
        md.append("| 组件 | 用量 |")
        md.append("|---|---|")
        for c, k in stats["components"].most_common():
            md.append("| %s | %d |" % (c, k))
        md.append("")
    md.append("## 图层树（坐标相对画板左上角，单位 px）")
    md.append("")
    md.extend(lines)
    md.append("")
    return "\n".join(md), root, stats, images


# ------------------------------------------------------------------ cli


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline .sketch spec extractor (no Sketch app needed)")
    ap.add_argument("sketch", help="path to the .sketch file")
    ap.add_argument("-o", "--out", help="output directory (default: ./<name>-spec)")
    ap.add_argument("--page", help="only extract pages whose name contains this (case-insensitive)")
    ap.add_argument("--artboard", help="only extract artboards whose name contains this (case-insensitive)")
    ap.add_argument("--list", action="store_true", help="list pages/artboards and exit")
    args = ap.parse_args(argv)

    doc = Doc(args.sketch)

    inventory = []  # (page, artboard_layer)
    for pname, pdata in doc.pages:
        for l in pdata.get("layers") or []:
            if l.get("_class") in ("artboard", "symbolMaster"):
                inventory.append((pname, l))

    if args.list:
        cur = None
        for pname, l in inventory:
            if pname != cur:
                print("\n[%s]" % pname)
                cur = pname
            fr = l.get("frame") or {}
            mark = " (symbolMaster)" if l.get("_class") == "symbolMaster" else ""
            print("  %s×%s  %s%s" % (n(fr.get("width", 0)), n(fr.get("height", 0)), l.get("name"), mark))
        print("\n共 %d 个画板/symbol，%d 个页面" % (len(inventory), len(doc.pages)))
        return 0

    sel = [
        (p, l)
        for p, l in inventory
        if (not args.page or args.page.lower() in p.lower())
        and (not args.artboard or args.artboard.lower() in (l.get("name") or "").lower())
    ]
    if not sel:
        print("没有匹配的画板。用 --list 查看全部。", file=sys.stderr)
        return 1

    base = os.path.splitext(os.path.basename(args.sketch))[0]
    outdir = args.out or os.path.join(os.getcwd(), base + "-spec")
    os.makedirs(outdir, exist_ok=True)

    assets_copied = set()
    index_rows = {}  # page -> [(name, w, h, rel_md)]
    used_stems = {}  # page-dir -> set of used file stems (duplicate names get -2/-3)
    for pname, ab in sel:
        md, root, stats, images = extract_artboard(pname, ab)
        pdir = os.path.join(outdir, sanitize(pname))
        os.makedirs(pdir, exist_ok=True)
        stem = sanitize(ab.get("name"))
        taken = used_stems.setdefault(pdir, set())
        base_stem, k = stem, 2
        while stem in taken:
            stem = "%s-%d" % (base_stem, k)
            k += 1
        taken.add(stem)
        with open(os.path.join(pdir, stem + ".md"), "w", encoding="utf-8") as f:
            f.write(md)
        with open(os.path.join(pdir, stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False, indent=1)
        fr = ab.get("frame") or {}
        index_rows.setdefault(pname, []).append(
            (ab.get("name"), n(fr.get("width", 0)), n(fr.get("height", 0)), "%s/%s.md" % (sanitize(pname), stem))
        )
        for ref in images:
            if ref not in assets_copied:
                srcf = doc.image_file(ref)
                if srcf:
                    os.makedirs(os.path.join(outdir, "assets"), exist_ok=True)
                    shutil.copy(srcf, os.path.join(outdir, "assets", os.path.basename(ref)))
                    assets_copied.add(ref)

    pv = doc.preview_png()
    if pv:
        shutil.copy(pv, os.path.join(outdir, "preview.png"))

    idx = []
    idx.append("# %s 设计标注" % base)
    idx.append("")
    idx.append("- 来源: `%s`（%.1f MB）" % (os.path.abspath(args.sketch), os.path.getsize(args.sketch) / 1048576))
    idx.append("- Sketch 版本: %s | 提取时间: %s" % (doc.meta.get("appVersion"), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    idx.append("- 页面 %d 个 | 本次导出画板 %d 个" % (len(doc.pages), len(sel)))
    fonts = doc.font_references()
    if fonts:
        idx.append("- 文档引用字体: %s" % ", ".join(fonts))
    idx.append("")
    for pname in dict.fromkeys(p for p, _ in sel):
        rows = index_rows[pname]
        idx.append("## %s（%d）" % (pname, len(rows)))
        idx.append("")
        idx.append("| 画板 | 尺寸 | 标注 |")
        idx.append("|---|---|---|")
        for name, w, h, rel in rows:
            idx.append("| [%s](%s) | %s×%s | md + json |" % (name, rel, w, h))
        idx.append("")
    with open(os.path.join(outdir, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx))

    print("已提取 %d 个画板 → %s" % (len(sel), outdir))
    if assets_copied:
        print("位图资产 %d 张 → %s/assets/" % (len(assets_copied), outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
