# 正式脚本契约

Agent 开始制作前先读本页。唯一公开入口是 `scripts/video_production.py`；接口不匹配时报告具体缺口并修改统一 CLI、公共模块及测试，不在 `scratch/` 重写同类脚本。先运行：

```text
python scripts/video_production.py contract --pretty
```

该 JSON 从同一套 `argparse` parser 自动生成，包含所有命令的参数、类型、必填项、choices、默认值、底层 runner 和产物；本页解释工作流边界，不重复充当参数事实源。

## 安装阶段：prepare_workspace.py

```text
python scripts/video_production.py prepare --workspace-root <workspace-root>
```

- 参数：`--workspace-root` 是存放原片、项目和共享依赖的工作区；`--dry-run` 只打印命令。
- 输出：命令进度和最终环境检查 JSON。
- 产物：`video-production-deps/venv/`、`ffmpeg/`、`node/`、`npm-cache/`、`tools.json`。
- 时机：下载 Skill 后执行一次；不是每条视频任务的一部分。

## 任务开始：check_env.py

```text
python scripts/video_production.py check --workspace-root <workspace-root> --deep
```

- 参数：工作区、可选 `.env`、是否检查网络。
- 输出：各依赖及路线的 `ok/problems/routes` JSON；非零退出表示环境未就绪。
- 产物：刷新 `video-production-deps/tools.json`。
- 边界：任务阶段只检查，不带 `--install`；缺依赖时停止制作并回到安装阶段。

## 通用时间轴：compile_timeline.py

```text
python scripts/video_production.py compile --selection <selection-plan.json> --transcript <transcript.json> --decisions <pause-decisions.json> --out-dir <work/edit>
```

- 参数：Agent依照实际内容写出的保留片段、词级转写、逐处语义气口决定；可选采样率。
- 输出：一行状态 JSON；无论视频时长、段数和内容如何都使用同一编译器。
- 产物：`edit-plan.json`、`mapped-words.json`、`pause-report.json`、`timeline-check.json`。
- 失败：词跨切口或时间基冲突时拒绝输出；Agent修改选择/气口决定，不另写时间轴修补脚本。

## 固定字幕格式：caption_pages.py

```text
python scripts/video_production.py captions --words <mapped-words.json> --editorial <caption-editorial.json> --out <work/captions/captions.json>
```

- 参数：编译器产生的 mapped words；Agent填写的 editorial JSON。每页提供有序 `word_keys`、1–2 行、`takeaway`，强调短语提供连续 word keys、`role` 与 `reason`。
- 输出：页数和警告 JSON。
- 产物：`captions.json` 与同名 `.srt`。
- 失败：漏词、重复词、未知 key、跨页保护短语或重叠页一律拒绝；不要绕过覆盖检查手写 SRT。

## 固定渲染器：render_timeline.py

```text
python scripts/video_production.py render --workspace-root <workspace-root> --source <raw.mp4> --plan <edit-plan.json> --captions-ass <captions.ass> --out <output/final.mp4> --encoder auto
```

- 参数：任意长度原片、已验证时间轴、可选 ASS、尺寸、编码器和质量参数。
- 输出：实际采用的 `libx264` 或 `h264_nvenc` 状态 JSON。
- 产物：`final.mp4`、旁边的 `render.log`。
- 行为：`auto` 只在 FFmpeg 真正列出 NVENC 时使用 GPU，否则明确回退 CPU；所有片段在同一个通用图中按实际计划拼接。

## 固定技术 QC：qc_delivery.py

```text
python scripts/video_production.py qc --workspace-root <workspace-root> --media <output/final.mp4> --plan <edit-plan.json> --out <qc/qc.json>
```

- 参数：成片、同 revision 时间轴及共享 FFmpeg 路径。
- 输出：`pass/fail` 状态 JSON和退出码。
- 产物：UTF-8 `qc.json`，包含 ffprobe 元数据、全片解码、时长差；人工内容和听审保持 `not_checked`。
- Windows：所有子进程输出均显式使用 UTF-8 并替换不可解码字节；不要使用 Bash heredoc 或 PowerShell 默认带 BOM 的中间文件。
