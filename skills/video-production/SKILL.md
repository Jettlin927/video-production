---
name: video-production
description: 视频制作与视频/录音转字幕入口。按素材和目标路由到百炼转写、真人口播剪辑、分镜制作或单条生成素材流程，并复用字幕字体资源。
---

# 视频制作主 Skill

识别用户目标后选择一个主流程，保持用户的素材、风格、时长、授权和输出目录。先路由，不把所有视频都当真人口播。

## 首次使用：先跑 bootstrap

本目录带一个一次性引导 [scripts/bootstrap.py](scripts/bootstrap.py)。Skill 刚复制到一台新机器时，第一件事是执行它：

```text
python scripts/bootstrap.py --keep
```

它核对本机依赖、打印结论并记录路径；缺命令行工具时给出需要当前任务授权后执行的 `python scripts/bootstrap.py --install --keep`。使用 `--keep` 保留脚本，方便版本维护。它只安装缺的、并且只装到本用户的工具目录，不改系统 PATH、不动别的软件。

后续运行或 `bootstrap.py` 缺失时，用 [scripts/check_env.py](scripts/check_env.py) 复查；脚本存在与否不能证明依赖已就绪。初始化只解决运行环境，`.env` 的业务空间 Key 和地址仍需人工填写。

## 决策树

```text
用户要制作视频或把音视频转成字幕
├─ 只要现有视频或录音的文字稿/SRT？ → references/asr.md 的字幕流程
├─ 有原片，核心是保留真人原声表达？
│  ├─ 是：真人讲述/知识分享/口播 → talking-head-cut 子 Skill
│  └─ 否：现有素材混剪/其他剪辑 → 当前项目既有流程；按片段计划剪辑
├─ 没有真人原片，只有文案/脚本/主题？
│  ├─ 目标是钩子/推广，接受纯排版动画（动态 PPT） → hook-video 子 Skill
│  └─ 其他分镜视频 → 本 Skill 的 references/storyboard.md
└─ 只要一张图或一个视频片段作为制作素材？
   └─ 生成素材 → references/generated-media.md 的百炼脚本
```

一句“生成一段口播”可能指剪已有真人录像或从文案造数字人口播；先检查附件与原片，只有这个区别影响后续时才简短澄清。没有真人原片时不承诺口型克隆、声音克隆或数字人能力。仅改字幕/换某镜头时沿用既有工程做局部修正。

混合任务如“剪口播，补几段 AI 图片和视频”仍以口播为主流程，再调用公共素材能力；不丢弃原声重做一条纯生成视频。

## 路由调用约定

真人口播读 [talking-head-cut/SKILL.md](../talking-head-cut/SKILL.md)。这是子 Skill，直接在当前任务执行，不自动新建任务或派生 Agent。用户日常只需提供 raw＋风格；主 Skill 负责识别，无需用户记住子 Skill 名称。直接调用子 Skill 也保持可用。

钩子视频读 [hook-video/SKILL.md](../hook-video/SKILL.md)，同为子 Skill，同一执行约定。用户只需提供宣传方向（加可选受众/CTA/时长）；路由到钩子视频后执行子流程的"钩子脚本 → 配音与时间戳 → 排版计划 → Remotion 制作 → 验收交付"。零实拍：画面由排版动画与生成配图构成，不伪造真人镜头或数据截图。

路由到真人口播后，执行子流程的“转写 → 内容选择 → 气口语义标注与字幕规划 → 应用剪辑 → 画面策划与包装 → 渲染/QC”。词级转写一到手就生成可复用的气口候选；切媒体前完成逐处时长与理由标注。主流程不能跳过计划直接按静音阈值删除。字幕/字体的局部修改复用已有转写与剪辑计划。

写入项目 `production.json`：`route`（transcription/talking-head/hook-video/storyboard/asset/existing-edit）、`route_reason`、`inputs`、`style`、`output_dir`、`constraints`。这是路由记录，不是给用户多加表单。仅转字幕时交付文字稿、词级 JSON、SRT 和说话人摘要；视频制作返回工程、文件和真实质检。

## 公共能力

- 用户要选择交付形式或回剪映手动调整时，读取 [jianying-export.md](references/jianying-export.md)，在最终渲染前记录 `production.json.export_format`（`mp4` / `jianying` / `both`）。剪映工程保留独立切段、完整原素材、文本字幕和独立 BGM；仅要工程时可跳过整片 MP4 渲染。生成文件、剪映实际打开、人工编辑保存和视听验收分别记录。

- 首次运行、换机器或工具报错时先跑 [scripts/check_env.py](scripts/check_env.py)：它按路线核对 Python、FFmpeg、Node/浏览器、共享 `.env`、字体完整性与磁盘余量，并解析不在 PATH 里的 ffmpeg。加 `--search <目录>` 扩大查找范围，`--write-tools` 记录结果供后续运行复用，`--json` 给机器读。缺依赖时按提示安装，或明确写出缺项；不把缺依赖说成已能制作。
- 视频/录音需要字幕或文字稿时读取 [asr.md](references/asr.md)。`.env` 已配置时，在用户要求的转写/剪辑范围内用百炼脚本执行；支持 WAV/MP3 上传、词级时码和说话人分离。含画外提示时先确定主角角色与保留词，再剪媒体和重建字幕。ffmpeg 不在 PATH 时按检查脚本解析出的路径传 `--ffmpeg`。
- 为整片补充证据链、解释画面或节奏空镜时，先读 [visual-planning.md](references/visual-planning.md)：按原句判断画面用途，真实证据绑定真实来源；生成图片共享一套视觉风格，并与首张合格基准图逐张对照。保持 raw＋风格的最小输入，缺省决策由 Agent 完成。
- 锁定画风时读 [visual-styles.md](references/visual-styles.md)：5 套预设（写实商务纪实／深色科技蓝／金棕奢华商业／明亮产品界面／原生随拍），按本片文案与片子质感选一套，用 `visual_plan.style_preset(id, aspect)` 生成 `visual_style`；一条片子只用一套，画幅跟随成片。**默认不是卡通插画。**
- 需要 AI 生图/生视频时读取 [generated-media.md](references/generated-media.md)。公共脚本与唯一 `.env` 放在本 Skill；当前指定 `qwen-image-3.0`、`wan3.0-video` 和业务空间地址。生成任务失败不盲目重复付费提交。
- 需要字幕或图形文字时读取 [fonts.md](references/fonts.md)。字体与许可证在 `assets/fonts/`，按视觉定调选择真实文件及字重，随工程带上用到的字体许可。
- 实际 API 调用、字体渲染、音画同步和语义质量分别记录证据。没有 Key 时先完成本地可验证工作；不能把模拟服务测试写成真实模型通过。

## 扩展边界

共享安装时将本 Skill 与 `talking-head-cut`、`hook-video` 放在同一级技能目录，按宿主的安装规则复制或建立目录链接。其他 harness 需要将共享目录纳入技能发现范围；可读取文件不等于会自动发现 Skill。没有自动发现能力时，显式读取本 Skill 的 `SKILL.md`，继续按相对路径读取子流程。

迁移到其他 Agent 时各 Skill 目录一并复制，保留相邻路径。用 `.env.example` 创建本机 `.env` 并填写自己的业务空间 Key 和地址；分享包排除真实 `.env` 和 `scripts/tools.json`（本机路径记录）。分享包包含 `scripts/bootstrap.py`；复制后先跑 `python scripts/bootstrap.py --keep`，根据报告补齐依赖再开始制作。更新前备份本机 `.env` 到 Skill 目录之外，更新后核对配置并重新检查环境。宿主仍需有文件/命令/网络执行能力和推理模型，Python、FFmpeg 及渲染器由环境提供；本 Skill 不把“一把百炼 Key”描述成不需要其他运行环境。

目前专门实现的子 Skill 是真人口播与钩子视频。新增类型只有在有明确独立流程及验证用例时才增加子 Skill 和路由分支；不要生成空目录或声称已经支持电影混剪、数字人等尚未实现的能力。路由参考案例见 [routing-cases.md](references/routing-cases.md)。
