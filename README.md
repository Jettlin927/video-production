# Video Production Skills

一组给 AI Agent 使用的视频制作 Skills：根据素材和目标路由到真人口播剪辑、钩子视频、PPT 运镜讲解或音视频转字幕流程。

| Skill | 用途 |
| --- | --- |
| `video-production` | 总入口；共享转写脚本、字体和环境检查；空镜制作交给后续剪辑师 |
| `talking-head-cut` | 真人原片剪辑、重拍取舍、语义气口、字幕层级和视听质检 |
| `hook-video` | 无真人原片的钩子脚本、配音流程、排版动画与 Remotion 组件 |
| `ppt-screencast` | PPT／长页信息地图、局部推近平移、鼠标指向圈画；附计划检查和运镜组件 |

四个目录需要一起安装并保持同级，子流程通过相对路径使用主 Skill 的公共能力。

本轮开发版暂存在 `wip/video-skills-20260930` 分支，未合并到 `main`。需要本轮修改（包括 `ppt-screencast`）时，先按下面的跨电脑步骤取得该分支，不用默认main安装命令替代。

## 国庆期间换电脑继续工作

```shell
git clone --branch wip/video-skills-20260930 --single-branch git@github.com:Jettlin927/video-production.git
cd video-production
```

将 `skills/` 内四个完整目录复制到新电脑实际使用的技能目录，并保持同级；或在新电脑重新建立指向该仓库的目录链接。不要直接复制旧电脑的junction，它们仍会指向旧电脑的路径。新电脑需有Python、Node.js与所选路线要求的浏览器／工具，按下文在新视频工作区运行 `prepare`，再用自己的配置创建本机 `.env`，执行 `check`。

源码分支不包含本机 `.env`／Key、依赖环境、DeepSeek session、原片、配音与制作项目。要继续旧视频，还需单独携带相应素材／项目／付费转写缓存，保留或重新定位文件引用；这些不随代码推送。

分支上的固定工具已做本地回归与真实媒体验证；新PPT路线的主题→成片DeepSeek one-shot成功率和Token降幅仍待新会话验证，不将暂存分支视为已完成生产验收。

## 安装

已安装 Node.js 和 Git 的用户，可以使用 [Skills CLI](https://github.com/vercel-labs/skills) 安装到 Codex：

以下默认仓库安装命令适用于这些修改已合并到main之后；当前开发版请使用上面的分支clone和同级目录安装。

```shell
npx skills add Jettlin927/video-production --skill video-production talking-head-cut hook-video ppt-screencast -g -a codex
```

Claude Code 用户将 `-a codex` 换成 `-a claude-code`。其他 Agent 请按宿主的技能发现规则安装；能读取文件不代表会自动发现 Skill。

也可以下载本仓库 ZIP，把 `skills/` 内的四个完整目录复制到宿主的技能目录，保留脚本、references、assets 和字体许可。ZIP 安装需要手动更新，不会自动登记到 Skills CLI。

## 下载后立即准备依赖（制作任务开始前）

安装 Skill 后、交给 Agent 剪第一条视频之前，先确定长期使用的工作区根目录，并在安装后的 `video-production` Skill 目录执行一次统一 CLI：

```shell
python scripts/video_production.py prepare --workspace-root <workspace-root>
```

准备脚本一次性创建 `<workspace-root>/video-production-deps/`，其中包括共享 Python venv、固定版本 Node/Remotion 依赖、npm 缓存、FFmpeg/ffprobe 和 `tools.json`。所有视频项目复用这一套依赖；不要等收到视频制作任务后再安装，也不要在每个项目里复制 venv、`node_modules` 或 FFmpeg。

准备阶段同时检测本机 GPU、驱动和 FFmpeg 编码器，实际编码短样后保存到 **`video-production-deps/hardware.json`**，并在 `tools.json`登记路径。支持 NVIDIA NVENC、Intel QSV、AMD AMF；macOS 检测 VideoToolbox。仅“列出编码器”不算可用，失败原因会写入报告。无可用硬件编码器时使用 CPU。

渲染默认 `--encoder auto`，会核对当前硬件/驱动和 FFmpeg。报告失效或超过24小时则重新实测；硬件编码运行失败时记录原因并回退 CPU 一次。要主动重测，运行 `python scripts/video_production.py hardware --workspace-root <workspace-root> --refresh`。报告中的“可用”表示编码可运行，不代表整条解码、字幕、滤镜链都使用 GPU，也不承诺固定提速倍数。

该命令会下载并安装第三方依赖；需要在下载 Skill 时由用户或部署流程明确执行。只想审阅动作时先运行：

```shell
python scripts/video_production.py prepare --workspace-root <workspace-root> --dry-run
```

Node、浏览器、Python 和 API 配置等缺项仍按最终报告处理。共享依赖目录不进入本 Skill 仓库。

将 `.env.example` 复制为 `.env`，填写自己的 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`（对应业务空间的 HTTPS API 地址，以 `/api/v1` 结尾）。模型名称需与自己的账号权限匹配。真实 `.env` 仅保存在本机。

```shell
python scripts/video_production.py check --workspace-root <workspace-root> --deep
```

建议使用 Python 3.12。视频处理需要 FFmpeg/ffprobe；Remotion 路线需要 Node.js、浏览器和工程依赖；部分分析需要 NumPy/SciPy 等 Python 包。依赖以检查结果和所选流程为准。本仓库包含约 136 MiB 的字体等资源，不包含模型权重、原始视频或成片。

## 每条视频任务开始时只检查

依赖准备完以后，每条任务只运行检查，不再安装：

```shell
python scripts/video_production.py check --workspace-root <workspace-root> --deep
```

按检查报告的所选路线处理缺项；固定口播路线不依赖浏览器或 Remotion。普通口播使用 [固定流水线](skills/video-production/references/stable-talking-head.md)：`index → select → compile → caption-draft → caption-build → deliver`。Agent只编辑内容数据；统一CLI提供字幕创作、后台渲染、GPU选择、停止、恢复、QC和剪映工程。用 `contract --command <当前子命令>`获取局部契约，完整接口见 [正式脚本契约](skills/video-production/references/script-contracts.md)。

`deliver`立即返回任务ID；使用`job-status / job-stop / job-resume`管理。完成后读取`output/handoff.json`。输入和代码未变化且产物未变动时复用阶段检查点。长渲染由独立程序执行，不需要Agent长时间sleep或临时写脚本；简短交接文件支持压缩或新上下文恢复，但不会自动改变宿主会话的缓存策略。

## 使用示例

在支持 Skill 的 Agent 中提出需求：

```text
用 video-production，把这个 raw.mp4 剪成克制商业风格的真人口播。
保留真人原声，处理重拍和气口，添加分层字幕，交付 MP4、剪映可编辑草稿、SRT 及质检结果。
```

```text
用 video-production，围绕“给小公司配置 AI 助手”制作一条 30 秒竖屏钩子视频。
白底大字，接受排版动画，结尾引导预约演示。
```

```text
用 video-production，把这段录音转成可读文字稿和 SRT，保留说话人区分。
```

```text
用 video-production，按这条参考制作 PPT 录屏式讲解。
保留全文，用推近、平移和鼠标圈画带着观众看重点，不做逐屏大字钩子。
```

`ppt-screencast` 的计划检查与组件技术短样不等于整片验收；它默认不生成剪映，内部计划／快照只供自动重试，不作为工程交付。

该路线默认one-shot输出可发布MP4，不交剪映或Remotion工程：Agent按主题／文案完成内容与配音，`screencast-build`派生运镜，`screencast-deliver`冻结快照并完成预检／渲染／混流／QC。旧两条路线的双产物合同不变；内部工程仅作重试缓存。

配音流程需要可用的 TTS 服务或用户录音；本仓库尚未提供统一 TTS 执行脚本。Agent 仍需文件、命令和网络执行能力；Skill 安装成功不等于所有视频路线都已具备运行条件。

## 完整视频流程：默认交付 MP4＋剪映草稿

PPT运镜路线默认只交MP4。其他完整视频路线在用户提供素材和风格或宣传方向后，至少交付以下两项，无需额外要求导出工程：

1. `final.mp4`：可播放的成片。
2. `剪映工程/`：包含完整素材的剪映可编辑草稿，可手动改字幕、拖切口调整气口、调整已用 BGM。

Agent 在 `production.json` 记录 `export_format: "both"`、两个实际输出路径及共同的时间轴 revision，并分别检查成片和草稿；缺少任一项时不算完整交付。仅转写、单条素材生成及明确的局部修改按各自范围执行。

剪映工程包含独立视频切段及完整原素材、可编辑文字字幕、独立 BGM/配音轨，方便手动调整气口、音乐和文字。完整视频流程所需的导出依赖、草稿安装与搬运方法见 [剪映工程导出](skills/video-production/references/jianying-export.md)。支持新草稿生成、素材打包和搬运后的路径重定位；原 Remotion 复杂动效、重点短语样式和字体未自动还原。

该适配基于固定提交的社区项目 pyJianYingDraft。脚本测试与剪映实际打开、编辑、保存是不同验证层次；请以目标 Windows 版本的应用内验收为准。

## 更新

使用 Skills CLI 安装的用户，先将自己的 `.env` 备份到技能目录之外，再执行：

```shell
npx skills update video-production talking-head-cut hook-video ppt-screencast -g
```

更新后检查并恢复本机 `.env`，再运行统一 CLI 的 `check`。已有 `video-production-deps/` 不由 Skill 更新覆盖；依赖锁发生变化时重新执行 `prepare`。目录替换可能丢失本机配置或改动，不要把个人配置与待发布文件混用。以上安装/更新语法依据 Skills CLI 文档；各宿主的实际发现与运行情况需在目标环境验证。

## 维护与发布

维护者在本仓库的 `skills/` 中修改，完成本地验证后提交并推送到 `main`。如果先修改了其他位置的已安装 Skill，需要把变更同步回仓库；已安装目录与 GitHub 不会自动同步。

```shell
git add README.md skills
git commit -m "Update video production skills"
git push origin main
```

通过 Git clone 管理且由目录链接安装的用户，可在自己的仓库副本运行 `git pull --ff-only` 更新；请保留未提交修改，勿强制覆盖。需要固定版本时，维护者可以创建 tag 和 GitHub Release，用户从 Releases 下载对应 ZIP。

## 验证与边界

仓库保留现有脚本测试，可从仓库根目录执行：

```shell
python -m unittest discover -s skills/video-production/scripts -p "test_*.py"
python -m unittest discover -s skills/talking-head-cut/scripts -p "test_*.py"
python -m unittest discover -s skills/ppt-screencast/scripts -p "test_*.py"
node --test skills/ppt-screencast/scripts/test_motion.mjs
```

历史验证说明见 [真人口播验证记录](skills/talking-head-cut/references/validation.md) 和 [钩子视频验证状态](skills/hook-video/SKILL.md#验证状态)。部分记录来自维护者本机，原片和完整证据未公开；不能据此声称新机器、不同模型或任意素材已通过端到端验收。实际服务调用、成片解码、字幕同步和完整听审分别确认。

字体附带各自的 OFL/许可证及来源清单，分发时保留。第三方工具和服务遵循各自的条款。本仓库尚未指定自有代码与文档的开源许可证。
