# 项目计划书：oss-license-checker（开源许可证合规判定器）

> 求职型 VibeCoding 项目之一。定位「知产 / 开源法务」，依托专利代理师 + 律师 + 代码能力的交集。

## 一、定位

- **产品名**：`oss-license-checker`（暂定）
- **一句话**：输入依赖清单 → 解析 license → 判定商用 / 传染 / 义务 / 冲突 → 输出法务 + 工程双版合规报告
- **目标用户**：科技公司工程团队（引入依赖前自查）、知产/开源合规法务、并购尽调团队、开源项目维护者

## 二、为什么做

- **痛点**：软件 70–90% 代码来自开源依赖，但几乎没人读懂 license 法律含义；GPL/AGPL 传染、CC-BY-NC 商用禁用、专利条款缺失、SBOM 合规（EO 14028 / 欧盟 CRA）都是真实风险。
- **空白**：FOSSA / Snyk / ScanCode 只「列出」不「判定」；SPDX 只给数据；律所人工慢贵不可复现。缺一个「律师 + 工程师都能用、离线可跑、输出法律级判定」的工具。
- **招聘信号**：直接对标开源合规 / IP / AI 产品合规法务岗，证明「能把 IP 法专业能力工程化」。

## 三、moat（为什么是这个人）

| 角色 | 能做 | 做不好 |
|------|------|--------|
| 律师 | 读懂 license 法律含义 | 不会解析依赖树、不懂 SPDX 表达式 |
| 工程师 | 解析依赖树 | 不懂法律后果、不知道传染路径 |
| 现有工具 | 列出 license | 不做法律判定、不给义务清单 |

**专利代理师 + 律师 + 会写代码**：三者交集的产物。

## 四、技术架构

```
依赖清单(package.json / requirements.txt / go.mod)
  → 解析器(零网络纯标准库)
  → license 匹配器(包名→license 映射)
  → 判定引擎(商用 / 传染 / 义务 / 冲突)
  → 报告(Markdown 法务版 + JSON 工程版)
```

## 五、核心模块

1. **license 事实库** `data/licenses.jsonl`：22 个主流 license，字段含 `commercial_use` / `copyleft_scope` / `patent_grant` / `obligations` / `source_url` / `source_accessed_at`。
2. **兼容性矩阵** `data/compatibility.json`：四态判定（compatible / incompatible / one-way / conditional），争议项标 `disputed`，未收录默认 `unknown`（不静默放行）。
3. **依赖解析器** `parsers/`：npm / python / go，零网络。
4. **判定引擎** `engine.py`：license 归一化 + SPDX 表达式（OR/AND）+ 风险分级。
5. **报告生成** `report.py`：Markdown（法务版）+ JSON（工程版），含免责声明。

## 六、难点与应对

| 难点 | 应对 |
|------|------|
| 兼容矩阵有争议（GPLv2 vs Apache-2.0） | 标「主流观点」，附来源，不做绝对结论 |
| 版本差异（GPLv2 vs GPLv3） | 精确到版本，不笼统写「GPL」 |
| 双 license / 多 license | 支持 SPDX 表达式（OR / AND） |
| 传递依赖 | MVP 只做直接依赖，Phase 2 做传递 |
| 法律意见边界 | 输出「检查清单」，明确不构成法律意见 |
| 包名映射不全 | 覆盖主流包，其余标「需人工核实」 |

## 七、路线图

- **短期**：开源积累 Star，HN / r/opensource / 律师社群推广；与 `legal-hallucination-bench` 联动（评测 AI 生成的合规建议是否准确）。
- **中期**：企业版（私有化 + CI 集成 + 持续监控）、SBOM 输出（SPDX / CycloneDX）、API。
- **长期**：成为「SBOM 法律层」标准工具，并购尽调标准工具，参与标准制定。

## 八、MVP 范围（已完成）

- [x] 22 个 license 事实库
- [x] 兼容矩阵（四态 + 争议标注）
- [x] npm / python / go 解析器
- [x] 判定引擎（归一化 + SPDX + 风险分级）
- [x] Markdown / JSON 报告 + CLI
- [x] 单元测试（27 项，全绿）+ 演示数据
- [x] 130+ 主流包名 → license 映射（含 GPL/AGPL/CC-NC 陷阱包）

## 九、下一步（项目二、三）

- 项目二：隐私政策体检器（AI / 数据合规法务）
- 项目三：代币监管定性器（Web3 / 加密法务）
