# 工作区与项目目录规范

## 工作区

工作区根目录是用户投放原始视频、管理共享依赖和保存全部制作项目的目录。根目录允许直接放视频或录音，不要求用户先整理；Agent 不移动、不重命名、不复制这些原片，除非用户明确要求。

```text
<workspace-root>/
├─ 原始视频或录音文件
├─ video-production-deps/
│  ├─ venv/                 # Python 包
│  ├─ ffmpeg/bin/           # FFmpeg 与 ffprobe
│  ├─ node/                 # 共享 Node/Remotion 依赖或缓存
│  ├─ npm-cache/            # 包下载缓存（可重建）
│  ├─ tools.json            # 当前共享工具路径
│  └─ hardware.json         # GPU、驱动、编码器实测与选择
├─ projects/
├─ scratch/                 # 探测、实验文件；清理前确认没有交付引用或唯一转写缓存
└─ video-production/        # Skill 源码仓库（若工作区同时用于开发）
```

`venv`、Node 依赖和 FFmpeg 是同一共享依赖总目录下的不同子目录。所有制作项目复用它们，不在每个项目中复制 `node_modules`、FFmpeg 或 Python 环境。

## 项目分类

分类名与 `production.json.route` 保持一致：

- `talking-head`：真人原声口播剪辑。
- `hook-video`：纯排版动画钩子视频。
- `transcription`：只交付转写、字幕或说话人结果。
- `storyboard`：非口播的分镜视频。
- `asset`：单条图片、视频或音频素材生成。
- `existing-edit`：基于既有工程的局部修改或混剪。
- `validation`：Skill、导出链路或工具能力验证；不得冒充客户项目。

新项目路径为 `projects/<route>/<YYYYMMDD>-<slug>/`。`slug` 使用简短稳定的小写英文、数字和连字符；同一任务的返工通过 `production.json` 中的 revision 管理，不新建 `-v2`、`最终版`、`改好版` 等平行目录。

## 项目内部

```text
<task-root>/
├─ production.json          # route、输入、revision、路径和环境记录
├─ input/
│  └─ source-manifest.json  # 根目录原片的路径、大小、修改时间；默认不复制原片
├─ brief/                   # 用户目标、文案、参考资料和 style.json
├─ work/                    # ASR、计划、时间轴、中间音视频及下载素材
├─ project/                 # 扩展路线的 Remotion 等制作工程；固定路线可为空
├─ output/                  # 固定路线的版本化交付，结构见下文
└─ qc/                      # 制作期间的人工审片、补充检查；固定技术QC在交付快照内
```

普通口播的 `work/` 包含 `asr/`、`index/`、`edit/`、`compiled/`、`captions/` 和字幕创作JSON。文件名以当前命令返回的路径为准；同阶段复用已有文件，不从其他项目复制历史脚本。

## 固定口播的交付目录

`deliver` 使用输入和代码指纹隔离交付快照。当前交付由 `output/handoff.json` 与 `production.json.outputs` 确定，不按文件夹时间、名称或任意一个 `final.mp4` 猜测：

```text
output/
├─ handoff.json              # 当前交付路径、revision与未完成验收项
├─ .job/                     # 后台任务状态、日志和恢复请求
│  ├─ active.json
│  └─ runs/<job-id>/
├─ .delivery-lock/           # 运行锁；由程序管理
└─ <输入指纹>/
   ├─ final.mp4
   ├─ final.srt
   ├─ 剪映工程/              # 独立轨道、完整素材及导出报告
   ├─ project/               # 本次计划、字幕、字体、输入指纹快照
   ├─ qc.json                # 本次成片的技术QC
   ├─ delivery.json          # 阶段检查点
   ├─ preflight/             # 短样与检查点关联文件
   ├─ render.log
   ├─ render-result.json
   └─ render-progress.txt
```

锁和临时渲染目录由程序创建，文件存在不代表任务仍在运行；用 `job-status` 判断。正在运行或需要恢复时，保留 `.job/`、`delivery.json`、短样和其他阶段产物。历史快照可能包含人工改过的剪映工程，未被当前 `handoff.json` 引用不等于可以直接删除。旧项目可沿用原有目录，通过其 `production.json` 和工程实际引用判断。

钩子、分镜和旧工程仍可在项目级 `project/` 与 `qc/` 保存工程和检查结果；不能仅为符合新树状图移动旧交付或改动原素材路径。

## 新建与复用

使用统一 CLI 的 `init` 新建目录并生成清单。已有同名项目时读取其记录继续工作。探测性工作使用 `<workspace-root>/scratch/<purpose>/`；清理前区分可重建缓存、验证证据、付费转写结果与真实交付，不按目录名整批删除。
