---
name: hook-video
description: 视频制作中的钩子视频子流程，由 video-production 按"无真人原片、只有宣传方向"路由，也支持直接调用。零实拍的纯排版动画（动态 PPT 风格）：钩子脚本、TTS 配音、逐层堆叠大字、关键词点亮与配图。
---

# 钩子视频（纯排版动画）

本 Skill 是 [video-production](../video-production/SKILL.md) 的钩子视频子流程；主 Skill 判断"没有真人原片、目标是钩子/推广"后在当前任务进入这里，直接调用时同样执行。主 Skill 统一管理百炼 Key、生成脚本、字体与环境检查；本子流程管理钩子脚本、配音、排版动画与验收，不复制第二份配置。

输入最少为一个宣传方向（"宣传什么"）加一句受众或 CTA 定调。输出带配音的排版动画 MP4、脚本与排版计划、可编辑 Remotion 工程和质检结果。整条视频零实拍：画面由文字排版动画与生成配图构成，不包含真人镜头；核心是保留真人原声表达的内容回 [talking-head-cut](../talking-head-cut/SKILL.md)。

参考形态（来自一条 30 秒样片的逐帧拆解）：白底大字逐层堆叠、打字机逐字出现、关键词圆角 chip 依次点亮、色彩按语义分级、底部双语字幕、结尾 CTA。形态由当次风格定调决定，参考形态用于校准组件，不是默认模板。

## 1. 定方向、写钩子脚本

- 记录宣传对象、受众、平台与目标时长（默认 20–40 秒，画幅按平台）；每次运行建立独立输出目录。
- 写脚本前读取 [copy-model.md](references/copy-model.md)：按"结论前置 → 论据 → 痛点对比 → 方案 → 佐证 → CTA"组织，30 秒约 6–8 屏；每句标注屏幕角色、强调词与排版意图。
- 产出 `hook-script.json`：稳定句 ID、中文文案、英文翻译（需要双语字幕时）、句角色、强调词、预期屏内时长。文案中的数据与承诺来自用户资料或用户给定的方向；不编造具体收益数字、政策条文或截图证据。
- 把风格定调写成 `style.json`：画幅、色彩语义（陈述/结论/最大结论的用色）、字号层级、动画强度、是否双语字幕、是否配图、音乐。缺省项作可逆选择并简述，无需逐项询问。

完成条件：每句文案有角色与排版意图；强调词逐句选定；脚本朗读一遍在目标时长内。

## 2. 配音与时间戳

- 需要配音时读取 [tts.md](references/tts.md)：先探测主 Skill `.env` 的 TTS 配置；可用则合成配音并取得句/词级时间戳（TTS 自带，或用主 Skill 的 ASR 对配音回扫）；不可用则明确列出缺项，交付无声排版版与待补配音说明，不把静默版说成已完成配音。
- 文字动画随配音出现：每屏文字的开始帧对齐对应句的配音起点；无配音版按阅读时长定节奏。
- 可选 BGM 不抢配音；音效（打字声、点亮声）按风格定调少量使用。

完成条件：每句有 final 时间轴起止（配音实测或阅读时长推算，来源写入 `layout-plan.json`）。

## 3. 画面排版计划

- 读取 [layout-motion.md](references/layout-motion.md)：把脚本逐句落成 `layout-plan.json`——每屏包含哪些层（大标题、陈述行、对比行、chip 组、配图、引用条）、层出现顺序、堆叠或清屏策略、色彩分级、强调词与组件的绑定、每层起止帧。
- 配图需求列入计划：读主 Skill [visual-planning.md](../video-production/references/visual-planning.md) 判断真实证据与示意图，并从 [visual-styles.md](../video-production/references/visual-styles.md) 选一套风格预设（纯排版动画通常落 `tech-blue-01` 或 `clean-ui-01`，一条片子只用一套）；生成调用遵循 [generated-media.md](../video-production/references/generated-media.md)；示意素材不当作真实截图或数据证据。
- 连续多屏无视觉变化时检查是否需要配图或版式变化；纯文字屏也核对阅读时间。

完成条件：每句文案在计划中有对应视觉层；每屏信息密度与阅读时间核对过；配图有来源与审查结论。

## 4. Remotion 制作

- 按主 Skill [check_env.py](../video-production/scripts/check_env.py) 确认 Node、浏览器、FFmpeg 可用；在独立输出目录建立 Remotion 工程，锁定依赖版本，单一帧时钟驱动所有动画。
- 组件从 [assets/remotion](assets/remotion) 起步：TypewriterLine、KeywordChips、BilingualSubtitleBar。这些是模板组件，首次实片渲染后按实际效果校准再复用。
- 字体读取主 Skill [fonts.md](../video-production/references/fonts.md)，等待真实字体加载后再渲染；大字排版按真实字宽检查换行与溢出。
- 配音、字幕、动画消费同一份 `layout-plan.json` 与帧映射；后续修改重建映射再渲染受影响片段。

完成条件：工程可重复渲染；所有文字层使用已加载字体；逐屏检查过溢出、换行与安全区。

## 5. 验收并交付

- 执行文案核对（画面文字与脚本逐句一致）、同步核对（文字出现与配音对齐）、阅读时间核对（每屏停留 ≥ 阅读所需）、渲染帧检查（首/中/末及每层首现帧）。
- 交付 `final.mp4`、`hook-script.json`、`layout-plan.json`、`style.json`、工程与 `qc.json`；qc 每项用 `pass / fail / not_checked` 记录方法与证据，存在必检 fail 或 not_checked 时标 `review_required`。
- 成功答复简述成片位置、时长、脚本结构取舍和验收边界。制作可发布文件不等于向平台发布；仅在用户明确授权发布时进入平台动作。

## 验证状态

本子流程依据一条 30 秒参考成片的逐帧拆解建立。2026-09-16 据维护者本机记录完成首个真实任务（原片、工程与完整证据未随仓库公开）（54s 竖屏成片）：

- TTS 路线已验证：业务空间端点支持 `POST /services/aigc/multimodal-generation/generation`，模型 `qwen3-tts-flash`（voice Cherry, language_type Chinese），返回 `output.audio.url`（WAV 24kHz 单声道），不带字级时间戳；时间戳用主 Skill 的 paraformer-v2 对配音回扫取得，词级准确。计费字符数约为文本字数的 2 倍。
- 端到端流程已验证：脚本 → TTS → ASR 回扫 → layout-plan → Remotion 渲染 → QC。沙箱内 `npm install` 需 `--ignore-scripts`（生命周期 spawn 被 EPERM 拒绝）；Remotion 渲染需完整权限（Chrome spawn）。
- 组件校准结论：模板组件思路可用，实际工程用数据驱动的单文件渲染器（layers 消费 layout-plan.json）更顺；字幕分隔线需按最长字幕行数预留（三行 42px 字幕时分隔线 bottom≥396px）；大数字层"标签+数字"顺序要按中文自然语序（"仅用 7天"而非"时间 7天"）；ZCOOL 庆科黄油数字字形较窄，150px 内"140多个学生"不溢出。
- ASR 对 TTS 配音的两处误识别（他/它、进校/尽校）确认：画面文字始终以用户原文为准，ASR 只供时码。
