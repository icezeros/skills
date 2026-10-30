# skills

[![skills.sh](https://skills.sh/b/icezeros/skills)](https://skills.sh/icezeros/skills)

Agent skills by [@icezeros](https://github.com/icezeros). Installable via the [skills](https://skills.sh) CLI (`npx skills`). Listed at [skills.sh/icezeros/skills](https://skills.sh/icezeros/skills/sketch-spec-extract).

## Available Skills

| Skill | Description | Install |
|---|---|---|
| [`sketch-spec-extract`](./sketch-spec-extract) | Parse `.sketch` files fully offline (no Sketch app needed) and extract design specs to Markdown+JSON: layer tree, artboard-relative coordinates, colors, fonts, text, symbol component refs, bitmap assets. For design-to-code handoff. | `npx skills add icezeros/skills@sketch-spec-extract` |

### sketch-spec-extract

A `.sketch` file is a ZIP of JSON (open format since Sketch 43). This skill unpacks it with a pure-stdlib Python script — **no Sketch app, no MCP, no network** — and emits per-artboard specs:

```
<out>/
├── INDEX.md          # artboards grouped by page, with links
├── preview.png       # document preview
├── assets/           # referenced bitmaps
└── <page>/<artboard>.md   # colors / fonts / component refs / layer tree
└── <page>/<artboard>.json # full machine-readable tree
```

```bash
# list pages & artboards
python3 scripts/extract.py <file.sketch> --list
# extract everything (or filter with --page / --artboard)
python3 scripts/extract.py <file.sketch> -o <outdir>
```

Compared to a Sketch MeaXure HTML export, this preserves symbol component names, font references and the raw layer tree; compared to Sketch's official MCP skills, it works on machines **without Sketch installed** (e.g. a frontend dev who only receives the file).

---

## 中文说明

本仓库是 [@icezeros](https://github.com/icezeros) 的 agent skills 合集，通过 `npx skills` 安装。

- **sketch-spec-extract**：离线解析 `.sketch` 文件（无需安装 Sketch、无需联网），提取画板设计标注为 Markdown+JSON——图层树、画板相对坐标、颜色、字体字号、文本内容、symbol 组件引用、位图资产，供 design-to-code 使用。相比 MeaXure 导出的 HTML，保留了组件名、字体清单与原始图层树。

安装：`npx skills add icezeros/skills@sketch-spec-extract`

## License

[MIT](./LICENSE)
