---
name: sketch-spec-extract
description: Parse .sketch files fully offline (no Sketch app, no MCP, no network) and extract design specs to Markdown+JSON — layer tree, artboard-relative coordinates, sizes, colors, fonts, text content, symbol component references, and bitmap assets — for design-to-code and spec handoff. Use when the user provides a .sketch file path, asks for "sketch spec / design spec / spec export / annotation extraction / 标注提取 / 设计稿标注", wants sketch-to-code (sketch 转代码), or only has a Sketch MeaXure HTML export but needs richer structured data (MeaXure 导出包解析). Works on machines without Sketch installed.
---

# Sketch Spec Extract

A `.sketch` file is just a ZIP of JSON (open format since Sketch 43). This skill unpacks it with a pure-stdlib Python script and extracts design specs **without requiring the Sketch app**, MCP, or any network access.

## Usage

Script: `scripts/extract.py` (relative to this SKILL.md). Runs with any python3, zero dependencies.

```bash
# 1. List document structure (pages / artboards / sizes) — confirm scope with the user first
python3 scripts/extract.py <file.sketch> --list

# 2. Full extraction (writes ./<filename>-spec/)
python3 scripts/extract.py <file.sketch>

# 3. Filter by page / artboard name (substring, case-insensitive)
python3 scripts/extract.py <file.sketch> --page 设计图 --artboard 空间-首页 -o /tmp/out
```

Extracting 100+ artboards takes ~1-2s. If the output directory exists, same-named files are overwritten; the directory is not cleaned.

## Output structure

```
<out>/
├── INDEX.md            # Index: source, font references, artboards grouped by page (with links)
├── preview.png         # Document preview (Sketch's last-saved viewport, for quick glance only)
├── assets/             # Bitmaps referenced by extracted artboards (images/<hash>.png)
└── <page name>/
    └── <artboard name>.md    # Human-readable spec: color table, font table, component refs, layer tree
    └── <artboard name>.json  # Machine-readable full tree (incl. every text run's style)
```

## Field semantics (follow when reading specs)

- **Coordinates**: `@ x,y` in the layer tree are **absolute, artboard-relative** (parent offsets accumulated), in px; sizes are `W×H`.
- **Colors**: `#RRGGBB`; with alpha: `#RRGGBB/85%`. Usage tables sorted by frequency.
- **Text lines**: `"content" — FontFamily Sizepx #color lh=line-height align`; mixed runs are marked `(mixed)` — full run details in the JSON `runs` array.
- **`[symbolInstance]`**: design-system component reference; the layer name IS the component name (e.g. `1.Base基础/2.Button 按钮/…`) — map to code components by this name. `overrides=N` means N overrides (override contents are not deeply resolved; rely on visible children in the tree).
- **`[symbolMaster]`**: component master (e.g. icon artboards in an icon-library page) — treat as the component definition.
- **`[bitmap]`**: bitmap layer; `images/<hash>.png` is copied into `assets/`.
- **`[hidden]`**: layer hidden in Sketch (often an interaction state) — listed by default; decide per case.
- `fill=gradient(a→b)` keeps only stop colors (direction not resolved); `r=` corner radius; `shadow=x,y blur color`.

## Recommended workflow (design-to-code)

1. `--list` to confirm pages/artboards with the user (watch out for "backup/备份" pages — usually skip those).
2. Extract on demand: pilot one artboard, confirm granularity, then batch.
3. When implementing: read INDEX.md for fonts/artboards → read a page's .md color/font/component tables to build the design-token mapping → implement layout from the layer tree; bitmaps and icons come from `assets/` and the icon master artboards.
4. Document-level shared styles/swatches are empty in most files — always prefer per-layer styles.

## Honest limitations

- **No per-layer rasterization**: rendering vector layers is Sketch's engine job; offline can't do it. Visual comparison relies on preview.png, assets/ bitmaps, and frames only.
- Symbol overrides are not deeply expanded; nested symbol internals require reading the corresponding symbolMaster page (if present).
- Gradient direction, blend modes, blurs and other advanced effects are annotated, not fully parameterized.
- Text wrapping/truncation must be inferred from font size, line height and width.
