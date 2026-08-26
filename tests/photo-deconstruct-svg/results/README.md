# 测试结果索引

所有程序生成的 SVG、分析 JSON、PNG 预览与左右对比图统一存放在本目录。

| 测试集 | 当前推荐结果 | 总对比图 |
|---|---|---|
| `landscape-generalization-20` | `current-2026-08-26/` | `landscape-generalization-20/comparisons/current-all.jpg` |
| `minimal-landscape-10` | `cross-field-fix/` | `minimal-landscape-10/comparisons/cross-field-fix-all.jpg` |
| `testabstract-10` | `final/` | `testabstract-10/final/contact-sheet-source-vs-program.jpg` |

## 归档规则

- 每套测试的完整批次放在自身目录中，不与其他测试集混放。
- `comparisons/` 集中放置 source-vs-program 左右对比图。
- `coverage/` 保存微洞、漏底与覆盖检查。
- `focused-fixes/` 保存针对特定失败案例的回归产物。
- `development-history/` 保存无法可靠归属到完整批次的早期单图试验，避免污染当前结果。

整理时统计到 274 个 SVG、236 个 JSON、299 个 PNG 和 24 个 JPG。该目录为本地生成资产，不纳入 Git；本索引文件例外。
