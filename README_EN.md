[![CI](https://github.com/vickywu97/oss-license-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/vickywu97/oss-license-checker/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

# oss-license-checker

**Offline open-source license compliance checker** — feed it a dependency manifest; it parses each dependency's license, judges commercial feasibility, GPL/AGPL copyleft reach, obligations, and conflicting combinations, then emits a compliance report that both lawyers and engineers can understand.

> One-line positioning: a "license translator" between lawyers and engineers. Most lawyers never read the dependency tree; most engineers don't read license law. This tool fuses both judgment capabilities — offline, zero-dependency, reproducible.

---

## Why it exists

70%–90% of modern software is open-source dependencies, yet almost nobody reads the legal consequences of each license when pulling one in:

- **GPL/AGPL copyleft**: can force a company's core code open, wiping out commercial value
- **Commercial-use ban**: mishandling `CC-BY-NC` assets can force takedown
- **Missing patent clauses**: Apache-2.0 grants patents, MIT does not — mixing them creates patent risk
- **SBOM compliance**: U.S. EO 14028 and the EU CRA require an SBOM, but existing tools only *list* license names without judging legal consequences

**Market gap**: FOSSA / Snyk / ScanCode only *list*; SPDX only provides *data*; law-firm opinions are slow, expensive, and non-reproducible. What's missing is a tool that is "usable by both lawyers and engineers, runnable offline, and outputs legally graded judgments."

---

## Quick start

Zero third-party dependencies — runs on the Python standard library alone (Python ≥ 3.8):

```bash
# Generate a Markdown report (project assumed MIT by default)
python -m oss_license_checker demo/sample_package.json

# Specify the project's own license
python -m oss_license_checker --project-license Apache-2.0 demo/sample_package.json

# Scan multiple manifests together (npm + python + go), output JSON
python -m oss_license_checker --format json demo/sample_package.json demo/sample_requirements.txt demo/sample_go.mod

# Inspect the built-in license fact library
python -m oss_license_checker --list-licenses

# Export a CycloneDX 1.5 SBOM (for EO 14028 / EU CRA pipelines)
python -m oss_license_checker --format cyclonedx demo/sample_package.json -o sbom.json

# CI gate: exit non-zero if any dependency reaches the high risk level
python -m oss_license_checker --fail-on high demo/sample_package.json
```

See `demo/sample_report.md` for a sample rendered report.

## Run tests

```bash
python -m unittest discover -s tests -v
```

---

## What it judges

For each dependency it outputs:

| Dimension | Notes |
|-----------|-------|
| **Commercial feasibility** | Whether commercial use is allowed (`CC-BY-NC` → banned) |
| **Copyleft scope** | none / weak (library-level) / file-level / strong (whole) / network (AGPL) |
| **Obligations** | attribution, retain copyright, disclose source, provide install instructions, etc. |
| **Conflict detection** | dependency license vs. project license compatibility (four states: compatible / one-way / conditional / incompatible) |
| **Risk grade** | 🔴 high / 🟡 medium / 🟢 low |
| **Recommendations** | swap for an alternative, isolate the process, dynamic linking, etc. |

It parses `package.json` (npm/yarn/pnpm), `requirements.txt` (pip), and `go.mod`, and supports SPDX expressions (`MIT OR Apache-2.0`, `GPL-3.0 AND MIT`).

**Built-in fact library**: 22 mainstream licenses (MIT / Apache-2.0 / BSD / GPL / LGPL / AGPL / MPL / EPL / CDDL / CC family / ISC / Unlicense / CC0 / PSF / HPND / WTFPL), each with a source URL + verification date; the compatibility matrix covers the key combinations, and disputed items (e.g. GPLv2 vs Apache-2.0, CC-BY-SA vs GPL) are marked explicitly rather than assumed "certain."

---

## Why me

- **Patent attorney**: an open-source license is fundamentally a copyright grant — same IP family as patents, providing professional grounding
- **Lawyer**: can read legal text, make legal judgments, and write compliance reports
- **Can code**: can parse the dependency tree directly without an engineering team

The intersection of these three — no one else on the market has it.

---

## Comparison with existing tools

| Tool | Positioning | Gap |
|------|-------------|-----|
| FOSSA | Enterprise license scanning | Leans "listing", weak on "legal judgment + obligation checklist" |
| Snyk License | Security + license | License is a side feature, not deep |
| ScanCode | Code scanning | Only identifies licenses, doesn't judge compatibility |
| SPDX official | Standard & list | Only provides data, no judgment |
| **oss-license-checker** | **Offline legally-graded judgment** | Outputs a report submittable to both legal and engineering |

---

## Disclaimer

This tool's output is an automated preliminary screening result and **does not constitute legal advice**. License facts and compatibility are subject to the official text (this library sources from the SPDX official list + FSF compatibility list, with verification dates). Final compliance judgments should be made by a licensed attorney.

## Portfolio relationship

| Project | Compliance domain | Judgment nature |
|---------|-------------------|-----------------|
| [privacy-policy-checker](https://github.com/vickywu97/privacy-policy-checker) | Data / privacy legal | Semi-hard rules (checklist) |
| [token-classifier](https://github.com/vickywu97/token-classifier) | Web3 / crypto legal | Soft rules (Howey four factors) |
| **oss-license-checker** | IP / open-source legal | Hard rules (compatibility matrix) |

Together they form a complete "legal + engineering" portfolio, all built at the intersection of lawyer + tax adviser + patent attorney + coding ability.

## License

MIT © 2026 Vicky Wu (vickywu97)
