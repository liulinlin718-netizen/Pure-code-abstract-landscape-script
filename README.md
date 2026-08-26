# Pure Code Abstract Landscape Script

用纯 Python 图像分析把照片转换为极简、纸张质感的抽象风景 SVG。整个流程可离线运行，不调用生图模型，不使用风格迁移，不通过 Canvas 绘制，也不会把原始照片嵌入 SVG。

仓库范围：这里只发布 `photo-deconstruct-svg` 图片解构 Skill、它的运行依赖以及对应测试文档；同级工作区中的其他独立 Skill 不属于本项目。

## 特性

- 从原图提取主色、空间层级、主体轮廓和轻度渐变。
- 使用闭合三次 Bézier 路径生成原生 SVG 色块。
- 支持纸张纹理、传统细颗粒覆盖和确定性随机种子。
- 自动清理细夹缝、微洞、画布边缘漏底和锯齿轮廓。
- 保护跨越多个大色场的小型显著主体，例如地平线上的建筑、树或船。
- 针对夜景和水平倒影提供源图结构驱动的特殊简化分支。
- 同一输入、参数和种子会生成可重复的 SVG 与 JSON 分析结果。
- 附带结构验证器，检查路径、渐变、纹理顺序、元数据和禁止元素。

## 安装

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/liulinlin718-netizen/Pure-code-abstract-landscape-script.git
cd Pure-code-abstract-landscape-script

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell 激活虚拟环境：

```powershell
.venv\Scripts\Activate.ps1
```

## 快速使用

默认运行：

```bash
python3 photo-deconstruct-svg/scripts/deconstruct_photo.py input.jpg output.svg
```

推荐的极简风景参数：

```bash
python3 photo-deconstruct-svg/scripts/deconstruct_photo.py input.jpg output.svg \
  --detail 0.35 \
  --paper 0.50 \
  --paper-style rough \
  --paper-density 1.00 \
  --grain-overlay 0.34 \
  --gradient-strength 0.30 \
  --color-mode source \
  --curve-smoothing 0.82 \
  --min-negative-gap 0.018 \
  --palette-size 6 \
  --max-shapes 10 \
  --seed 17
```

程序会生成：

- `output.svg`：可继续编辑的原生矢量作品。
- `output.json`：尺寸、调色板、结构分型、色块数量和复现参数。

运行结构验证：

```bash
python3 photo-deconstruct-svg/scripts/validate_svg.py \
  output.svg --analysis output.json
```

## 常用参数

| 参数 | 作用 |
|---|---|
| `--detail` | 调整大色块保留程度。 |
| `--palette-size` | 设置源图调色板角色数量。 |
| `--max-shapes` | 限制结构色块总数。 |
| `--curve-smoothing` | 控制轮廓低通和平滑程度。 |
| `--gradient-strength` | 控制由原图色差测量得到的轻度渐变。 |
| `--min-negative-gap` | 合并过窄的负空间、细夹缝和微洞。 |
| `--paper` | 控制整体纸张纹理强度。 |
| `--grain-overlay` | 在粗糙纸张上增加传统细颗粒覆盖。 |
| `--seed` | 固定纸张颗粒和点状高光，使输出可复现。 |

查看全部参数：

```bash
python3 photo-deconstruct-svg/scripts/deconstruct_photo.py --help
```

## 项目结构

```text
.
├── README.md
├── requirements.txt
├── photo-deconstruct-svg/
│   ├── SKILL.md
│   ├── agents/
│   ├── references/
│   └── scripts/
└── tests/
    ├── README.md
    └── photo-deconstruct-svg/
        ├── datasets/
        │   ├── landscape-generalization-20/
        │   ├── minimal-landscape-10/
        │   └── testabstract-10/
        └── results/
```

核心程序目录：

```text
photo-deconstruct-svg/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── color-research.md
│   └── visual-grammar.md
└── scripts/
    ├── deconstruct_photo.py
    └── validate_svg.py
```

`photo-deconstruct-svg/SKILL.md` 记录图片工作流和验收契约；其 `references/` 记录颜色与视觉简化原则。核心运行逻辑位于 `photo-deconstruct-svg/scripts/deconstruct_photo.py`。三套图片测试原图统一放在 `tests/photo-deconstruct-svg/datasets/`，对应的程序输出、对比图和历史实验统一放在 `tests/photo-deconstruct-svg/results/`；详细索引见 `tests/README.md`。

## 输入与隐私

支持 JPG、PNG 和 WebP。程序本身不发起网络请求，所有分析和 SVG 生成均在本地完成。测试原图和生成结果保存在本地测试目录中，但因授权和体积原因由 `.gitignore` 排除；仓库只跟踪来源、校验值、报告和目录说明。

## 设计边界

本项目优先保留大面积色场和构图主体，不追求像素级描摹。占画面极小且非常狭长的人物、桅杆或帆线仍可能在极简化过程中被省略；此时应提高 `--detail`，而不是把所有纹理碎片恢复成色块。
