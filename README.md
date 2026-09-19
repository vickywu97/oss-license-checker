# oss-license-checker

[![CI](https://github.com/vickywu97/oss-license-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/vickywu97/oss-license-checker/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**离线开源许可证合规判定工具** —— 输入依赖清单，自动解析每个依赖的 license，判定商用可行性、GPL/AGPL 传染路径、需履行的义务、冲突组合，输出一份法务和工程都能看懂的合规报告。

> 一句话定位：律师和工程师之间的「许可证翻译器」。大多数律师不看依赖树，大多数工程师不懂许可证法；这个工具把两端的判断能力合在一起，离线、零依赖、可复现。

---

## 为什么需要它

现代软件 70%–90% 的代码来自开源依赖，但引入依赖时几乎没人真正读懂每个 license 的法律后果：

- **GPL/AGPL 传染**：公司核心代码被迫开源，商业价值归零
- **商用禁用**：误用 `CC-BY-NC` 素材，被迫下架
- **专利条款缺失**：Apache-2.0 有专利授权、MIT 没有，混用可能带来专利风险
- **SBOM 合规**：美国 EO 14028、欧盟 CRA 要求 SBOM，但现有工具只「列」license 名称，不判法律后果

**市场空白**：FOSSA / Snyk / ScanCode 只做「列出」，SPDX 只给「数据」；律所人工意见慢、贵、不可复现。缺一个「律师 + 工程师都能用、离线可跑、输出法律级判定」的工具。

---

## 快速开始

零第三方依赖，`python` 标准库即可跑（Python ≥ 3.8）：

```bash
# 生成 Markdown 报告（默认 MIT 项目）
python -m oss_license_checker demo/sample_package.json

# 指定项目自身 license
python -m oss_license_checker --project-license Apache-2.0 demo/sample_package.json

# 同时扫多个清单（npm + python + go），输出 JSON
python -m oss_license_checker --format json demo/sample_package.json demo/sample_requirements.txt demo/sample_go.mod

# 查看内置 license 事实库
python -m oss_license_checker --list-licenses

# 导出 CycloneDX 1.5 SBOM（用于 EO 14028 / 欧盟 CRA 流水线）
python -m oss_license_checker --format cyclonedx demo/sample_package.json -o sbom.json

# CI 门禁：存在高风险依赖时以非零码退出
python -m oss_license_checker --fail-on high demo/sample_package.json
```

## 运行测试

```bash
python -m unittest discover -s tests -v
```

---

## 它判什么

对每个依赖输出：

| 维度 | 说明 |
|------|------|
| **商用可行性** | 是否允许商业使用（`CC-BY-NC` 判禁） |
| **传染性** | 无 / 弱（库级）/ 文件级 / 强（整体）/ 网络（AGPL）五档 |
| **需履行义务** | 署名、保留版权、公开源码、提供安装说明等 |
| **冲突检测** | 依赖 license vs 项目 license 的兼容性（四态：兼容 / 单向 / 有条件 / 不兼容） |
| **风险分级** | 🔴 高 / 🟡 中 / 🟢 低 |
| **建议** | 替换替代包、隔离进程、动态链接等 |

支持解析 `package.json`（npm/yarn/pnpm）、`requirements.txt`（pip）、`go.mod`，支持 SPDX 表达式（`MIT OR Apache-2.0`、`GPL-3.0 AND MIT`）。

**内置事实库**：27 个主流 license（MIT / Apache-2.0 / BSD / GPL / LGPL / AGPL / MPL / EPL / CDDL / CC 系列 / ISC / Unlicense / CC0 / PSF / HPND / WTFPL），每个附来源 URL + 核验日期；兼容矩阵覆盖关键组合，争议项（如 GPLv2 vs Apache-2.0、CC-BY-SA vs GPL）显式标注，不装「确定」。

---

## license 真实来源解析（三级解析：本地元数据 → 映射表 → unknown）

依赖的 license 不再只查「包名 → license」映射表（仅覆盖 138 个主流包），而是**优先读取已安装依赖自带的元数据**（npm `license` / Python `License-Expression:` `License:` `Classifier:` `License-File:` / Go `LICENSE` 正文）。实测覆盖率：npm 生态 98–100%，Python/PyPI 75–100%（修复 `License-Expression` 支持后；分生态明细见下方「真实项目实测」）：

| 优先级 | 来源 | 读取方式 | 可信度 |
|--------|------|----------|--------|
| 1 | **本地元数据** | npm `node_modules/<pkg>/package.json` 的 `license`/`licenses`；Python `site-packages/<pkg>-<ver>.dist-info/METADATA` 的 `License-Expression:` / `License:` / `Classifier:`；`License-File:` 指向的 LICENSE 正文（识别 MIT/Apache/GPL/LGPL/MPL 及 BSD 2/3-Clause）；Go `$GOMODCACHE/<module>@<ver>/LICENSE` 文件 | 最高（依赖自带） |
| 2 | **内置映射表** | `data/package_licenses.json`（138 个主流包，可能滞后） | 可信但有盲区 |
| 3 | **unknown** | 两者都未命中 | 需人工核实 |

每条依赖在报告中标注 `License 来源`，并在报告头给出统计：

```
- **license 来源**：本地元数据 3 · 内置映射表 1 · 未知 1（覆盖率 80%）
```

> 若项目尚未 `install` 依赖（检测不到 `node_modules` / `site-packages`），工具自动回退到映射表，并将未命中项标为「未知（需人工核实）」。所有解析离线完成，绝不联网查询；模糊写法（如 `BSD License` 无版本）宁可标 `unknown`，绝不猜测具体 BSD 变体。

示例见 [`demo/with_local_metadata/`](demo/with_local_metadata/) + [`demo/report_local_metadata.md`](demo/report_local_metadata.md)：三个不在映射表里的包通过本地 `node_modules` 元数据被准确识别，覆盖率从映射表单独使用的 20% 提升到 80%。

### 真实项目实测（可复现）

#### 覆盖率：多生态对照

直接跑 [`scripts/measure_real_coverage.py`](scripts/measure_real_coverage.py)（复用本工具的三级解析），真实安装真实项目：

| 生态 / 项目 | 唯一依赖 | 本地元数据 | 内置映射表 | 未知 | 覆盖率 |
|-------------|---------|-----------|-----------|------|--------|
| npm 现代 · [express](https://github.com/expressjs/express) | 66 | 66 | 0 | 0 | **100.0%** |
| npm 现代 · `request` | 47 | 47 | 0 | 0 | **100.0%** |
| npm 遗留 · [bower](https://github.com/bower/bower)（已废弃） | 263 | 258 | 0 | 5 | **98.1%** |
| npm 遗留 · `gulp@3.9.1` | 224 | 224 | 0 | 0 | **100.0%** |
| **Python · `flask`** | 7 | 7 | 0 | 0 | **100.0%** |
| **Python · `pandas`** | 4 | 2 | 1 | 1 | **75.0%** |
| Python · `requests` | 5 | 4 | 1 | 0 | **100.0%** |

**落 unknown 的包——按原因分类**（unknown 桶不掩盖，逐个说明为什么）：

| 项目 | 包 | 原因 |
|------|-----|------|
| bower | `beaker@1.0.0` · `buffers@0.1.1` · `garply@` · `requireg@0.1.7` · `retry@0.6.1` | `package.json` **无 license 字段**（2017 年前后的老包，发布时未声明） |
| pandas | `python-dateutil@2.9.0.post0` | `License` 字段写作 **`"Dual License"`**（实为 Apache-2.0 OR BSD-3-Clause），SPDX 单一值无法表达「或」，且本工具不猜测 → 不猜 |

> **关于 Werkzeug / MarkupSafe（诚实更正）**：早一版测得二者落 unknown，当时归因为「只给了 `License-File` 指针、BSD 变体正文无法区分 2/3-Clause」。复查真实文件后发现——二者 METADATA **明确声明 `License-Expression: BSD-3-Clause`**，且 LICENSE 正文含 3-Clause 的禁止背书条款。落 unknown 是**解析器的能力缺口**（漏读 `License-Expression` 字段、且对 BSD 正文一律拒识），并非「诚实的不猜」。已修复：新增 `License-Expression` 支持 + 从 LICENSE 正文识别 BSD 2/3-Clause 特征句，flask 覆盖率由 71.4% 升至 100%。这正说明「不猜」只应留给**真正含糊**的声明，不能把能力缺口包装成克制。

一个诚实的观察：**npm 生态自 2014 年起 license 字段就已高度规范**，连 2015 年代的 `gulp@3` / `browserify@10` 实测也在 95% 以上；**Python/PyPI** 的剩余覆盖率缺口主要来自两类——① 双许可/复合声明（`"Dual License"`、`Apache-2.0 OR BSD-3-Clause`）：SPDX 单一值无法表达「或」，本工具不猜测；② 极少数老包用含广告条款的 4-Clause 等罕见变体。凡是 `License-Expression` / `License:` / `Classifier:` 能明确判定的（含 LICENSE 正文含禁止背书条款的 BSD-3-Clause），解析器现已全部读取，不再假装读不出。

#### 为什么覆盖率不是核心

覆盖率只是**入场券**——FOSSA / Snyk 也能把依赖列出来、也能读 license 字段。真正只有本工具在做的是**判定层**：

- **兼容性判定**：依赖 license vs 项目 license 的四态判定（兼容 / 单向 / 有条件 / 不兼容），含 SPDX 表达式的 `AND` / `OR` / `WITH` 解析与 OR 择优（双许可按最宽松方案评估）
- **法律级义务清单**：署名、公开源码、提供安装说明、附许可全文等**具体义务**，而不是一句"GPL 有传染性"
- **传染路径分析**：GPL/AGPL 究竟从哪个**传递依赖**进来（见下节）——这是最容易被忽略、后果最严重的一类风险

> **「不猜」是刻意的取舍，但只留给真正含糊的声明**：纯 `BSD`（无版本）、`"Dual License"`（双许可）、含广告条款的 4-Clause、LICENSE 正文确实读不出 SPDX 的文件，一律标 `unknown` **并写明原因**。但凡是能明确判定的——METADATA 的 `License-Expression` / `License:` / `Classifier:` 声明、LICENSE 正文含禁止背书条款的 BSD-3-Clause——解析器会直接识别，**不会假装读不出**。对于 `"Dual License"` 这类双许可，报告会额外提示「可从宽选择、建议人工确认后取最宽松方案」，不影响判定的诚实性。在合规场景里，一个错误的判定比一句「需人工核实」危险得多；但把能力缺口包装成克制，同样会误导专业读者。

### 传递依赖分析（GPL / AGPL 传染路径）

只看直接依赖会漏掉真正的风险：GPL/AGPL 常常藏在**传递依赖**里。开启 `--transitive` 后，工具读取 lock 文件构建完整依赖图，区分直接与传递依赖，并对强传染依赖计算**从项目根出发的最短传染路径**：

```
gpl-transitive-demo (MIT)
    └─ acme-video-tool@1.0.0 (MIT)
        └─ ffmpeg-static@5.3.0 (GPL-3.0-or-later)  ⚠️ 传染终点
```

- **生态支持**：npm（`package-lock.json` v1/v2/v3，含 `optionalDependencies` 与 `file:` 链接包）、Python（`site-packages` METADATA 的 `Requires-Dist`，不依赖 pipdeptree）、Go（`vendor/modules.txt` / `go.mod` + `go.sum`）
- **风险优先级**：传递依赖的 GPL/AGPL 排在直接依赖之前——这类风险最易被忽略
- **优雅降级**：无 lock 文件时只分析直接依赖并在报告中说明原因；Go 模块图本身不提供边信息，明确标注「传递依赖未分析」而不是假装算得出
- **安全约束**：BFS 带 visited 集合 + 20 层深度上限，依赖环不会导致无限递归
- **CI 门禁**：`--transitive --fail-on high` 会把强传染传递依赖视同 high 并以非零码退出
- **路径展示**：当前展示从项目根到传染终点的**最短路径**；若同一强传染依赖存在多条引入路径，完整路径枚举为 Phase 2 增强（不影响「存在传染」的判定结论）

真实项目实测（依赖图基于 lock 文件）：

| 项目 | 总唯一依赖 | 直接 | 传递 | 发现 |
|------|-----------|------|------|------|
| express | 68 | 1 | 67 | 无 copyleft（全部宽松许可） |
| sharp | 32 | 1 | 31 | **LGPL-3.0-or-later** 传递依赖（第 2 层；平台二进制包挂在 `optionalDependencies` 下，忽略它会漏判） |
| 经本地包间接引入 ffmpeg-static | 21 | 1 | 20 | **GPL-3.0-or-later** 传递依赖（第 2 层），与 MIT 项目 `incompatible` → 🔴 高风险 |

> 说明两处诚实细节：① 上表是「只装了这一个包」的最小项目，所以直接依赖=1；② npm 包 `mysql` 实测**不含**任何 GPL 依赖，故改用 `ffmpeg-static` 作为强传染样本。

demo 见 [`demo/with_gpl_transitive/`](demo/with_gpl_transitive/) + [`demo/report_transitive_gpl.md`](demo/report_transitive_gpl.md)。

---

## 为什么是这个人来做

- **专利代理师**：开源 license 本质是著作权许可，与专利同属 IP 体系 —— 专业背书
- **律师**：能读懂法律文本、做法律判定、写合规报告
- **会写代码**：能直接解析依赖树，不依赖工程团队

三者交集的产物，市面没有第二个。

---

## 与现有工具对比

| 工具 | 定位 | 缺口 |
|------|------|------|
| FOSSA | 企业级 license 扫描 | 侧重「列出」，不擅长「法律判定 + 义务清单」 |
| Snyk License | 安全 + license | license 是附属功能，不深入 |
| ScanCode | 代码扫描 | 只识别 license，不判兼容性 |
| SPDX 官方 | 标准与列表 | 只提供数据，不提供判定 |
| **oss-license-checker** | **离线法律级判定** | 输出可提交给法务 + 工程的合规报告 |

---

## 免责声明

本工具输出为自动化初筛结果，**不构成法律意见**。license 事实与兼容性以官方文本为准（本库以 SPDX 官方列表 + FSF 兼容性清单为来源，附核验日期）。最终合规判断请咨询执业律师。

## 作品集关系

| 项目 | 合规领域 | 判定性质 |
|------|----------|----------|
| [privacy-policy-checker](https://github.com/vickywu97/privacy-policy-checker) | 数据 / 隐私法务 | 半硬规则（检查项） |
| [token-classifier](https://github.com/vickywu97/token-classifier) | Web3 / 加密法务 | 软规则（Howey 四要素） |
| **oss-license-checker** | 知产 / 开源法务 | 硬规则（兼容矩阵） |

三者共同构成「法律 + 工程」完整作品集，均由律师 + 税务师 + 专利代理师 + 代码能力交集构建。

---

## License

MIT © 2026 Vicky Wu (vickywu97)
