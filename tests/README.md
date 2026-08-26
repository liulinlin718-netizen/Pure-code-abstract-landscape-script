# 工作区测试资产索引

当前 `tests/` 下的资产全部属于 `photo-deconstruct-svg` 图片解构 Skill。现有三套图片测试集，共 40 张原图；SHA-256 校验确认 40 张内容均不重复。

## 目录

```text
tests/
└── photo-deconstruct-svg/
    ├── datasets/                   # 图片原图、来源与校验清单
    │   ├── landscape-generalization-20/
    │   ├── minimal-landscape-10/
    │   ├── testabstract-10/
    │   └── SHA256SUMS.txt
    └── results/                    # 图片 SVG、JSON、PNG、对比图与开发归档
        ├── landscape-generalization-20/
        ├── minimal-landscape-10/
        ├── testabstract-10/
        └── development-history/
```

## 测试集

| 名称 | 数量 | 用途 | 来源记录 |
|---|---:|---|---|
| `landscape-generalization-20` | 20 | 题材与主体保留的泛化测试 | `photo-deconstruct-svg/datasets/landscape-generalization-20/SOURCES.md` |
| `minimal-landscape-10` | 10 | 极简风景固定参数回归 | `photo-deconstruct-svg/datasets/minimal-landscape-10/SOURCES.md` |
| `testabstract-10` | 10 | 早期轮廓、缝隙、颜色与纸张质感回归 | `photo-deconstruct-svg/datasets/testabstract-10/SOURCES.md` |

每套原图都位于相应目录的 `images/` 下。全部原图的内容校验值见 `photo-deconstruct-svg/datasets/SHA256SUMS.txt`。

## 测试结果

所有图片生成物已统一放入 `photo-deconstruct-svg/results/`，并按测试集和迭代阶段分组。当前推荐查看的总对比图、历史批次以及结果数量见 `photo-deconstruct-svg/results/README.md`。

## Git 策略

测试原图、源图 contact sheet 和生成结果体积较大，且原图涉及第三方授权，因此默认保留在本机并由 `.gitignore` 排除。Git 跟踪本索引、三套来源清单、SHA-256 清单和测试报告。
