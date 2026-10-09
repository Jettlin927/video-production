# AI 视频制作技能包

把原始视频、文案和制作目标交给 AI，让它完成剪辑、字幕、配音或 PPT 运镜讲解。**你不需要写代码，也不需要记住命令。**

这不是独立的剪辑软件，而是一套给 AI 使用的制作流程和公共工具。需要在能读取本机文件、运行命令的 AI 软件中使用；只有聊天功能、没有本地执行能力的环境，不能仅靠一个仓库链接完成视频制作。

## 1. 四个 Skill 分别做什么？

建议整套安装，日常只说“用 video-production”，由 AI 选择合适的流程。

| Skill | 适合什么任务 | 你需要提供什么 | 默认交付 |
| --- | --- | --- | --- |
| `video-production`：总入口 | 判断视频类型、检查环境、调用公共工具；也支持只转写音视频 | 素材或主题，以及希望得到什么 | 转入下面的流程；只转写时交文字稿／字幕 |
| `talking-head-cut`：真人口播剪辑 | 剪你已经拍好的真人讲话，处理重拍、气口和字幕 | 真人原片；可选文稿、必须保留的内容、风格参考 | MP4 成片＋剪映草稿；字幕及检查结果按交付记录提供 |
| `hook-video`：钩子视频 | 没有真人原片，用大字、排版动画、配图和配音做推广短片 | 宣传主题或文案；可选受众、时长和结尾引导 | MP4 成片＋剪映草稿；复杂动效不保证在草稿中完全复现 |
| `ppt-screencast`：PPT 运镜讲解 | 将文案重构成页面，用推近、平移、连续鼠标圈画介绍重点 | 主题或完整文案；可选 PPT、录音、参考视频 | MP4 成片，不需要剪映工程 |

已有录音可以继续使用，不必重新配音。没有真人原片时，本包不会自动制作数字人或模拟口型。只给文案也能做 PPT 讲解，不要求先自己制作 PowerPoint 文件。

## 2. 不懂代码，怎样安装？

将下面这段话复制给你使用的 AI。它需要具备本机文件和命令执行权限。

```text
请读取这个仓库的 README，帮我安装并准备视频制作技能包：
https://github.com/Jettlin927/video-production

请整套安装 video-production、talking-head-cut、hook-video、ppt-screencast，保持四个目录同级。
先确认我正在使用的 AI 软件，以及原片、成片要保存到哪个文件夹。
检查基础软件，按 README 准备共享依赖，再验证我的 AI 是否能加载这些 Skill。
如果需要云服务配置，请告诉我在本机哪里填写，不要在聊天里显示我的密钥。
安装阶段不要提交付费的语音识别或配音请求。
最后用中文告诉我：哪些视频类型已经能用，哪些还缺条件，以及下一步怎么开始。
```

你主要需要配合两件事：选择视频工作文件夹；需要云转写／新配音时，由你或公司管理员提供服务配置和使用授权。其他安装命令交给 AI 执行即可。

**不要把“仓库已下载”当成“全部可以用了”。** 完整安装还包括：AI 能加载技能、共享依赖已准备、所选视频流程需要的条件已核对。

## 3. 需要哪些东西？

| 条件 | 用来做什么 | 谁负责 |
| --- | --- | --- |
| 能操作本机的 AI 软件 | 读取素材、调用工具、制作和检查视频 | 你选择软件；AI确认实际权限和技能加载方式 |
| Python | 运行公共剪辑与检查工具 | AI检测并指导安装；优先采用本仓库已有本机验证的 Python 3.12 |
| Node.js／npm | 运行排版动画和 PPT 渲染工具 | AI检测并准备；它们不是 `prepare` 自动安装的基础软件 |
| Git | 获取源码；当前共享依赖中的剪映草稿库也通过 Git 安装 | AI检测；使用 ZIP 下载仍不能省掉这项依赖安装条件 |
| 浏览器 | 为钩子和 PPT 页面生成画面 | AI按检查结果定位兼容浏览器；固定真人口播渲染不依赖它 |
| 视频工作文件夹和磁盘空间 | 保存原片、共享工具、项目及成片 | 你指定位置；AI检查访问权限与剩余空间 |
| 百炼云服务配置（按需） | 语音转写、从文案合成新配音 | 你或管理员提供账号配置、模型权限及费用授权 |
| 剪映应用（按需） | 打开和修改真人口播／钩子流程交付的草稿 | 需要编辑草稿时安装；PPT 讲解不要求剪映 |

处理音视频的 FFmpeg／ffprobe、生成画面的 Remotion 包、Python 包和字体，由共享准备流程处理，不让用户逐个研究。GPU 不是必备条件；固定口播的 FFmpeg 流程会实测可用硬件编码器，不能据此宣称所有视频步骤都用显卡加速，也不承诺固定生成时长。

没有云服务配置时，已有词级转写／时码的本地制作可按现有资料继续；新的语音转写或配音尚不能使用。本包不附送云服务额度，也没有随仓库提供离线语音识别模型。

## 4. 给安装 AI 的执行清单

以下步骤由安装 AI 完成，普通用户不需要手动执行。只安装和检查，不擅自开始制作、付费生成、迁移原片或改系统权限。

### 第一步：确认宿主（用户使用的 AI 软件）与工作区

- 确认用户使用的是 DeepSeek Harness、Codex、Claude Code 或其他宿主，并确认它能运行本地命令。不能执行时说明限制，不假称完成安装。
- 选择一个长期保存素材和成片的目录作为“工作区”。它不是技能安装目录，也不是某一个视频项目目录；不要搬动用户原片来凑目录结构。
- 按该宿主实际支持的规则安装技能。用户未提供这些信息时再简短询问，不把一整张技术参数表交给用户。

### 第二步：获取并安装四个完整目录

从本仓库 `main` 获取 `skills/` 中的四个文件夹，保留各自的 `SKILL.md`、`scripts/`、`references/`、`assets/` 和字体许可；四个文件夹必须在同一个技能父目录下。只复制 `SKILL.md` 不够。

优先采用宿主已支持的安装方式。支持 Skills CLI 的宿主可使用它；其他宿主可从完整仓库复制四个目录或建立本机目录链接。已有安装先检查版本和本机配置，不直接覆盖用户修改。

<details>
<summary>安装 AI：源码获取、Skills CLI 示例与宿主差异</summary>

首次获取源码可用 HTTPS，不要求普通用户先配置 SSH：

```shell
git clone --branch main --single-branch https://github.com/Jettlin927/video-production.git
```

也可以下载 GitHub 仓库 ZIP，由 AI 解压后安装完整的四个目录。源码下载目录不自动等于宿主的技能目录。

例如，通过 Skills CLI 安装到 Codex：

```shell
npx skills add Jettlin927/video-production --skill video-production talking-head-cut hook-video ppt-screencast -g -a codex
```

Claude Code 的目标标识为 `claude-code`。其他宿主先查 [Skills CLI 支持列表和说明](https://github.com/vercel-labs/skills)，不要把 `-a codex` 当作所有 AI 软件的通用参数，也不要猜测 DeepSeek Harness 的 CLI 标识。

Codex 的用户级本地技能目录为 `~/.agents/skills`，支持目录链接，详见 [OpenAI 官方技能文档](https://developers.openai.com/codex/skills/)。这不是其他宿主的目录承诺。DeepSeek Harness 等宿主需根据当前版本的配置确认目录，并验证实际加载；仅能打开文件不代表已经被技能系统发现。

若宿主没有自动发现能力，只能通过明确读取本机 `SKILL.md` 的方式执行，报告中应写“可手动加载”，不要写成“已注册”。更新未显示时按宿主机制刷新或开新会话，再确认四个 Skill。

</details>

### 第三步：先检查基础软件，再准备共享依赖

检测 Python、Git、Node.js／npm，以及所选渲染流程的浏览器。基础软件缺失时列出缺项并指导补齐；`prepare` 不负责自动安装这些基础软件。权限受限时报告具体阻塞，不反复探测整盘或绕过宿主限制。

基础条件满足后，调用**实际安装位置**的主 Skill 公共入口准备一次：

```text
python "<实际安装的video-production目录>/scripts/video_production.py" prepare --workspace-root "<视频工作区>" --dry-run
python "<实际安装的video-production目录>/scripts/video_production.py" prepare --workspace-root "<视频工作区>"
```

第一条只列出动作，第二条会下载和安装依赖；确认这些动作处于用户的安装授权内再执行。`python` 表示刚检测通过的解释器，必要时替换为其绝对路径；不要直接把 `.py` 文件当可执行程序调用。

准备流程在工作区建立一套 `video-production-deps/`，包含共享 Python 环境、FFmpeg／ffprobe、Node／Remotion 包、缓存和 `tools.json`，并进行硬件编码测试，保存 `hardware.json`。所有视频项目复用这一套，不逐项目复制依赖。

### 第四步：按需配置云转写与配音

使用新转写／新配音时，从实际执行的 `video-production` 目录内 `.env.example` 创建本机 `.env`，让用户或管理员填写：

| 配置项 | 含义 |
| --- | --- |
| `DASHSCOPE_API_KEY` | 百炼服务的访问密钥 |
| `DASHSCOPE_BASE_URL` | 对应业务空间或地域的 HTTPS API 地址，以 `/api/v1` 结尾 |
| `BAILIAN_ASR_MODEL` | 转写模型，示例默认 `paraformer-v2` |
| `BAILIAN_TTS_MODEL`／`BAILIAN_TTS_VOICE`／`BAILIAN_TTS_LANGUAGE` | 新配音的模型、音色和语言；示例默认 `qwen3-tts-flash`／`Cherry`／`Chinese` |

账号需具备相应模型权限；本执行器目前只适配 Qwen3-TTS-Flash 配音协议。不要填入其他供应商的 Key 后就宣称可用，也不要凭 Key 非空就断言模型已开通。

真实 `.env` 只留在本机，不提交仓库，不在日志或安装回复中展示密钥。配置写在仓库另一份副本、执行却用已安装目录，会造成“已填 Key 但脚本读不到”的问题；要核对实际路径。云配置暂缺时明确标出受影响的流程，不伪装成无声版完成了配音。

### 第五步：执行依赖检查，并按视频路线判断

```text
python "<实际安装的video-production目录>/scripts/video_production.py" check --workspace-root "<视频工作区>" --deep
```

以输出中的 `required`、`problems`、`warnings`、`routes`、`auto_fixable` 判断，不只看退出码。缺共享依赖时回到准备阶段；缺密钥、浏览器、空间或权限时处理实际缺项，不每次收到视频任务都重装。

- 固定真人口播：确认 FFmpeg、字体、草稿依赖和所需转写资料；不要求 Remotion 或浏览器。
- 钩子／PPT：确认 Node、npm、浏览器和共享渲染依赖；需要新声音时还要核对云配置。
- 只转写：确认百炼转写所需配置和音频处理工具。
- 检查中的 PPT“组件环境”就绪，不等于 TTS 已获权限，更不等于视频已通过审片。

需要检查网络时可给 `check` 加 `--network`，它只检测配置地址的 TLS 连通性，不试做付费转写／配音，也不证明模型权限。TTS 默认预检不生成声音；实际云调用另受用户授权约束，详见 [公共配音说明](skills/video-production/references/tts.md)。

### 第六步：验证宿主加载并给用户交接

确认宿主能够发现四个 Skill，或验证明确读取本机技能文件的可执行方式。复用检查结果，不为了“验收安装”重新安装依赖或自行付费制作视频。

最终用中文报告以下内容，失败或未测项如实保留：

| 安装结果 | 必须说清什么 |
| --- | --- |
| 技能文件 | 四个目录的实际安装位置、是否同级 |
| 宿主加载 | 已发现／只能手动加载／尚未验证 |
| 视频工作区 | 原片与成片的保存位置，以及共享依赖位置 |
| 各视频类型 | 哪些已具备条件，哪些还缺什么 |
| 云服务 | 配置、网络、模型权限分别验证到哪一步；不得回显 Key |
| 下一步 | 一条用户能直接复制的制作指令；未就绪时给出最小补齐动作 |

## 5. 安装后怎样开始？

把素材路径或文案交给 AI，说明目标即可。以下指令不要求用户记住子 Skill：

```text
用 video-production，把我提供的真人原片剪成商业口播，保留原声，处理重拍和气口，添加字幕，交付成片和剪映草稿。
```

```text
用 video-production，根据这段宣传文案做一条30秒竖屏钩子视频，突出重点，结尾引导预约演示。
```

```text
用 video-production，把下面的完整文案做成PPT运镜讲解。用悬浮页面、推近和平滑鼠标圈画讲清重点，直接交付MP4，不要剪映工程。
```

```text
用 video-production，把这段录音转成可读文字稿和SRT字幕，保留说话人区分。
```

每个新视频任务开始时只做环境检查，再进入对应 Skill；不要把安装工作重新做一遍。新转写／配音使用云服务，制作文件不等于向平台发布，平台上传需要另有授权。

## 6. 更新、换电脑与常见问题

- **怎么更新？** 先把本机 `.env` 备份到技能目录之外，再按原安装方式更新四个目录。Skills CLI 安装可用 `npx skills update video-production talking-head-cut hook-video ppt-screencast -g`；Git 副本用 `git pull --ff-only`，保留未提交修改；复制／ZIP 安装重新同步完整目录。恢复配置后重新检查，依赖要求改变时再准备。
- **换电脑只复制 Skill 就行吗？** 不够。新电脑要重新准备基础软件、共享依赖及本机配置。原片、成片、制作项目和付费转写缓存需另行携带；目录链接应在新机重建，不能照搬旧机的目标路径。
- **下载后 AI 还是不会用？** 先核对宿主加载与真实安装路径，不要只重复下载。可让 AI 明确读取主 Skill 的本机 `SKILL.md`，但应说明这是手动加载还是自动发现。
- **必须装剪映吗？** PPT 讲解只交 MP4，不要求剪映。真人口播／钩子默认交草稿；生成草稿的公共依赖由准备流程安装，打开、编辑、保存仍需剪映应用内验证。
- **能保证一次出片、固定耗时吗？** 目标是一条需求完成制作，但实际速度、内容和画面质量仍受素材、模型及硬件影响。工具检查通过不能代替内容、画面与完整听审。

## 给制作 AI 和维护者的进一步说明

安装就绪后再读取对应 Skill 执行制作，流程细节不在本页重复：

- [主 Skill](skills/video-production/SKILL.md) · [真人口播](skills/talking-head-cut/SKILL.md) · [钩子视频](skills/hook-video/SKILL.md) · [PPT 运镜讲解](skills/ppt-screencast/SKILL.md)
- [公共命令契约](skills/video-production/references/script-contracts.md) · [工作区规范](skills/video-production/references/workspace-layout.md) · [固定口播流水线](skills/video-production/references/stable-talking-head.md)
- [PPT 编译、预检与渲染前审核](skills/ppt-screencast/references/motion-plan.md) · [公共配音](skills/video-production/references/tts.md) · [剪映草稿导出](skills/video-production/references/jianying-export.md)

制作 AI 只编辑本次内容数据，使用公共工具，不从旧项目复制制作脚本，不在生产会话修改共享代码。PPT 先预检和审核，再开始长渲染；原片、字幕、声音与画面使用一致的输入版本。视频实际路径以当前 `output/handoff.json` 和制作记录为准，不猜某个名为 `final.mp4` 的文件。

维护者修改仓库 `skills/`，验证后按明确授权提交发布。测试与维护者本机案例不证明所有电脑、模型或新题材已通过生产验收。字体和第三方工具保留各自许可；本仓库尚未指定自有代码与文档的开源许可证，不包含真实凭证、依赖安装目录、模型权重或用户制作项目。
