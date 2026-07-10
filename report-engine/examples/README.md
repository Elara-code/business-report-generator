# 示范报告

`examples/` 下放了 3 份预生成的报告 JSON，开箱即用：

| 文件 | 类型 | 主题 |
| --- | --- | --- |
| `coffee.json` | industry | 中国现制咖啡行业 |
| `notion.json` | product | Notion 产品拆解 |
| `notion-vs-obsidian.json` | competitor | Notion vs Obsidian 竞品对比 |

## 试用

```bash
# 行业报告
python generate.py --type industry --subject "咖啡" --ai mock --preset coffee

# 产品拆解
python generate.py --type product --subject "Notion" --ai mock --preset notion

# 竞品对比
python generate.py --type competitor --subject "Notion vs Obsidian" --ai mock --preset notion-vs-obsidian
```

输出在 `reports/YYYYMMDD_HHMMSS_<type>_<subject>/report.html`。

## 替换为你自己的内容

1. 复制任一 `examples/*.json` 改名为新主题
2. 修改 `meta.subject` / `meta.title` / `sections[*].content` / `chart.data`
3. 跑：`python generate.py --type industry --subject "你的主题" --ai mock --from-json examples/你的文件.json`
