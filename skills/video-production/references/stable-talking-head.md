# 固定口播流水线

用于普通真人剪辑、分页字幕和重点短语。Agent 只编辑内容数据：选段范围、气口决定、字幕分组/强调/校字。时间计算、索引、词ID映射、字体、渲染、停止、QC和剪映导出由统一 CLI 完成。复杂滚动动效或额外音轨按对应参考执行，不在这条基础路线内临时搭 Remotion 工程。

使用 `video-production-deps/tools.json` 中的 Python 运行 `<skill-root>/scripts/video_production.py`。下面的 `vp` 表示这两个绝对路径组成的命令，不要求安装额外可执行文件。参数不清楚时运行 `vp contract --command <子命令>`，只读取当前阶段的契约。

## 1. 转写与选段

主 Skill 已完成环境门、init和转写时复用结果。

```text
vp index --transcript <transcript.source.json> --out <work/index>
```

产物是保留说话人字段的 `words.tsv`、`utterances.tsv`、`recording-review.json` 和 `selection.json`。选段前读取 [拍摄角色与多次复述](../../talking-head-cut/references/recording-roles.md)，确认拍摄模式、主角/领读角色及同句各 take；ASR 只有一个 speaker 也须核对低声领读。Agent 按索引填写 `ranges`，每项只有 `first`、`last`（从1开始、包含两端）和 `reason`。范围顺序就是成片顺序；保留原有内容选择和重排能力，在已确认的主角版本中比较重拍，不重写文案来反查词ID。

```text
vp select --workspace-root <workspace> --source <raw> --transcript <transcript.source.json> --selection <work/index/selection.json> --review <work/index/recording-review.json> --out <work/edit>
```

程序探测源帧率、旋转和尺寸，生成 `selection-plan.json`、`words.selected.json`、`pause-decisions.json`。缺省成片30fps、保持显示宽高比、短边不超过1080；用户指定规格时显式传 `--fps --width --height`。只做原速单源剪辑；不能把多原片当成一个source。

完成条件：保留范围全部为已确认主角，已标注的重拍组只选一个 take，无领读/未知声音区间、重复词和跨词切口，实际规格与角色表写入计划。角色关系一次核对后复用，只补异常范围，不逐句重复填表。角色表缺失或过期时先补核对；重跑 index 不覆盖已有人工决定。

## 2. 气口和时间轴

读取子 Skill 的语义气口参考，直接编辑生成的 `pause-decisions.json`：为候选填 `category`、`reason`，必要时填 `target_ms` 或 `preserve: true`。无需写Python、映射词ID或手算帧数。

```text
vp compile --selection <work/edit/selection-plan.json> --transcript <transcript.source.json> --decisions <work/edit/pause-decisions.json> --out-dir <work/compiled>
```

输出 `edit-plan.json`、`mapped-words.json`、`pause-report.json`、`timeline-check.json`。revision由选择、词稿、气口和采样率生成；修改任何这些输入会使旧字幕失效。语义不确定时保留原间隔并注明待听审。

完成条件：编译通过；切口与词映射同revision。

## 3. 字幕创作

```text
vp caption-draft --words <work/compiled/mapped-words.json> --plan <work/compiled/edit-plan.json> --out <work/caption-authoring.json>
```

程序生成可直接编译的分页草稿和对应TSV。Agent读取句意后调整以下数据，文字始终从词表生成：

```json
{
  "revision": "复制生成的revision",
  "review": "not_checked",
  "corrections": [{"word": 8, "text": "AI", "reason": "依据原声修正识别"}],
  "pages": [{
    "lines": [[1, 8], [9, 14]],
    "takeaway": "本句观众应记住的判断",
    "emphasis": [{"first": 9, "last": 12, "role": "focus", "reason": "完整判断短语"}]
  }]
}
```

数字均为**成片词索引**，不是源词索引；`lines`为1–2行，所有页按序恰好覆盖全部词。重复短语用位置区分。`role`可为`focus`（白色加粗）或`structure`（主题色）。`corrections`仅修改显示；删声音仍需回到选段。空显示修正不能造成整页无内容。

```text
vp caption-build --words <work/compiled/mapped-words.json> --plan <work/compiled/edit-plan.json> --draft <work/caption-authoring.json> --out <work/captions>
```

产出 JSON、SRT、ASS 和真实字体文件。输入错误统一返回页码、错误及漏词/重词列表；一次修改所有已报告问题，再编译。样式为克制的底部单/双行字幕，可用`--font`选真实字体；固定路线不声称实现滚动动画。自动草稿未经语义审查，不等于字幕设计通过。

## 4. 后台交付与恢复

```text
vp deliver --workspace-root <workspace> --plan <work/compiled/edit-plan.json> --captions-dir <work/captions> --out-dir <task/output>
```

默认快速返回`job_id/job_dir`。固定任务自动执行短样渲染、全片渲染、技术QC、剪映工程导出，写入 `<output>/<输入指纹>/`。每个阶段保存检查点，同一输出目录一次只允许运行一个任务。输出文件先写临时位置，成功后才替换目标；输入、代码或配置变化使用新的指纹目录。

```text
vp job-status --job-dir <返回的job_dir>
vp job-stop --job-dir <返回的job_dir>
vp job-resume --job-dir <返回的job_dir>
```

停止会处理整个进程树。resume复用仍有效的阶段文件；阶段失败需按状态中的日志定位，不用旧日志猜任务是否成功。成功后读 `<output>/handoff.json`，取得成片、SRT、工程和QC路径；项目根部存在`production.json`时程序同步登记输出。人工改过的工程不会被自动覆盖；需要新版本时改变内容数据。

后台任务完成通知到达后再读取状态；没有通知能力的宿主由宿主调度查询。状态未变时保持安静，模型无需执行数分钟sleep或为了缓存不断发请求。

## GPU与缓存成本

安装的`prepare`会在`video-production-deps/hardware.json`记录GPU/驱动和实际编码测试。每次`auto`渲染比对硬件、驱动、FFmpeg和检测版本；未变化且检测未超过24小时才复用。支持NVENC/QSV/AMF和macOS VideoToolbox，硬件不可用才选libx264；实际设备/编码器失败只回退CPU一次并记录原因。显式指定编码器失败会报告错误。GPU编码不等于滤镜和解码全部由GPU执行。

长任务的状态在文件中，不依赖模型会话缓存。`handoff.json`与阶段产物支持压缩上下文或新上下文接续；**异步返回和简短状态不能自动删掉DSH已有对话，也不保证服务端缓存TTL**。缓存失效时读取阶段摘要和必要文件；宿主的压缩/恢复能力需另行确认。不为保活发送无业务作用的模型请求。

完成条件：技术检查通过且双产物存在；听审和剪映实际打开/编辑保持独立状态。未经这些人工检查，整体为`review_required`。制作时遇到工具缺陷，返回失败阶段、错误摘要和可恢复路径；公共脚本修改由明确的工具维护任务处理。
