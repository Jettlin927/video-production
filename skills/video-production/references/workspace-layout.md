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
│  └─ tools.json            # 当前共享工具路径
├─ projects/
├─ scratch/                 # 可删除的探测、实验和临时文件
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
├─ project/                 # Remotion、剪映及其他可编辑工程
├─ output/                  # final.mp4、final.srt 等最终交付
└─ qc/                      # qc.json、审片帧、波形与检查报告
```

文件按用途进入对应目录。中间文件不得写入 `output/`；最终交付不得散落在任务根部；审片帧不得混入素材目录。外部工具必须在其他位置生成时，完成后移动到对应目录，并同步 `production.json` 中的实际路径。

## 新建与复用

使用 `scripts/init_project.py` 新建目录并生成清单。脚本遇到已存在的同名项目会停止；继续旧任务时直接使用已有路径和 revision。探测性工作使用 `<workspace-root>/scratch/<purpose>/`，结束时只清理本次创建且确认无后续价值的内容。
