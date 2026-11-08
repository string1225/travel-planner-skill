# Travel Planner Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for isolated helpers and independent reviews. Keep creator-page control in the primary agent only.

**Goal:** 本地安装能查询旅行、收集来源材料并拼合线路规划视频的 travel-planner skill。

**Architecture:** 根目录SKILL编排已安装的高德、FlyAI、Ego与video-report。小型本地脚本负责依赖检查/安装、稳定保存FlyAI JSON、素材清单校验和FFmpeg混合画面；源材料与凭证留在任务目录或私有配置中。

**Tech Stack:** Python标准库、Node CLI、FFmpeg/ffprobe、已有video-report环境。

用户已确认设计，并明确源码位置为 `C:/Users/junte/Code/travel-planner-skill`；在该干净仓库的新分支就地实施，不改变位置。已有origin指向用户创建的travel-planner-skill仓库，完成验证后提交推送当前分支。

## Task 1 — 依赖与查询交接

- [ ] 基线走查现有技能真实能力，不访问个人账号或配置。
- [ ] 在 `tests/test_services.py` 先验证环境发现、缺依赖行为及“成功JSON后CLI异常退出”的区分，再实现 `scripts/dependencies.py`、`scripts/flyai_query.py`。
- [ ] `python -m unittest discover -s tests -p test_services.py -v` 应全部通过；`python scripts/dependencies.py doctor` 不打印密钥且不安装或联网。
- [ ] 安装仅通过显式 `install-missing`，检查并复用已有安装；Key只由环境变量或已有私有配置读取。

## Task 2 — 清单与混合画面

- [ ] 在 `tests/test_media.py` 编写缺来源/缺文件/重复场景/失效引述、时间轴衔接和等比留白测试，先运行并确认功能缺失。
- [ ] 实现 `scripts/assemble.py` 的 `validate`、`build`。输入媒体清单与video-report产物目录，输出独立 `mixed/`，不覆盖已验证原片。
- [ ] 图片和视频在内容区等比缩放，保留全幅水印，底部来源区独立于完整句字幕；视频不够长时要求缩短使用或明确补足方案，不伪造新镜头。
- [ ] 按原始累计帧边界编排场景，统一使用voice.wav及原ASS，保留精确总帧数；生成可编辑HTML预览、混合来源与QA。
- [ ] 以实际FFmpeg生成的离线图片/片段做短样例，全片解码，抽帧检查比例、署名、字幕和时长；单元与集成测试全部通过。

## Task 3 — 技能、安装与交付

- [ ] 编写 `SKILL.md`、`agents/openai.yaml`、依赖查询/平台取材/媒体交接三份按需引用。
- [ ] 支持逐城景点发现、官方核实、小红书体验、B站素材、真实高德线路图、机票酒店报价；说明缺出发城市时不虚构机票价。
- [ ] 运行系统 `quick_validate.py`、脚本帮助与doctor，独立情景测试和代码审查；修复实际问题。
- [ ] 在 `~/.codex/skills/travel-planner` 创建指向源码根的目录联接，保留已存在同名安装时不覆盖。
- [ ] 检查Git差异、凭证与媒体排除规则，提交推送 `codex/travel-planner-skill`。最终报告安装位置、用法、已验证能力和线上限制。
