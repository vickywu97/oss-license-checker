# oss-license-checker

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

**内置事实库**：22 个主流 license（MIT / Apache-2.0 / BSD / GPL / LGPL / AGPL / MPL / EPL / CDDL / CC 系列 / ISC / Unlicense / CC0 / PSF / HPND / WTFPL），每个附来源 URL + 核验日期；兼容矩阵覆盖关键组合，争议项（如 GPLv2 vs Apache-2.0、CC-BY-SA vs GPL）显式标注，不装「确定」。

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

## License

MIT © 2026 Vicky Wu
