# 运镜计划与组件接口

创建页面／动画计划时读本页。可运行技术夹具见 [demo-plan.json](../assets/demo-plan.json)，只验证运镜与指针，不是默认商业文案。

默认通过 `screencast-build --content` 编译语义内容数据：Agent不计算帧号。旧版已完成的帧级author仍可用 `--author` 编译，但新项目走下述语义输入。revision是内容指纹，不手写固定001反复覆盖。

## 新项目：句子ID绑定，无项目生成脚本

content-authored.json 的 root 为 `canvas{width,height,fps}`、`viewport`、`pages[]`、`scenes[]`，可带background/chrome/caption_box。pages沿用下文元素接口；scene只有 `page_id/sentences/cues`，sentences是该段按顺序覆盖的句子ID。cue填写 `target_id/kind/reason/sentences`，不写camera或帧号。

所有scene的句子ID顺序拼接必须与script完全一致；cue引用当前scene内连续句子，目标source_ids须支持这些句子。数组里的视觉先后不会覆盖旁白时序，公共编译器按真实时码排序，给后续强调保留空间，短窗口装不下就报出目标ID；不跨句借时间，也不重新分配配音。字幕自动按最多两行分页，保留全部原句文字／标点（忽略原文换行），在实测句子区间内按字符数分配页时间，明确不是词级时码。

```text
python <video-production>/scripts/video_production.py screencast-build --workspace-root <workspace> --content <work/content-authored.json> --script <brief/script-sentences.json> --timing <work/timing.json> --audio <work/voice/voiceover.wav> --out <work/screencast-plan.json>
```

句子文件可直接复用公共tts输出；已有配音则用本次原文与公共align对齐。时长从音频读取。可选 `--author-out` 仅供内部诊断，不作为下次编排事实源。音频哈希和实测句子窗口写入计划，检查器会拒绝强调越过自己的旁白或绑定到另一句的内容。

若维护旧帧级author，它也必填 `script.sentences`，每句有唯一 `id` 和原文 `text_zh`；新content输入则由公共编译器读取独立script文件。每个非 rule 内容元素必填 `source_ids`（有效句子 ID 数组）和 `takeaway`（该项的视觉判断）。例如原文“先确认需求，再判断产品是否匹配”，可用 `flow` 的 `items: ["确认需求", "判断匹配"]`，并记录对应句子，而不是沿用参考片的卡片文字。引用只验证可追溯性，不自动证明摘要保留了原文条件；数字、单位、否定和因果仍需内容核对。旧版无script的已编译计划仍可几何检查，但正式交付同样要先预检／审核。

## 坐标和时间

`revision`、`width`、`height`、`fps`、`duration_frames` 描述最终时间轴；所有事件使用最终帧号，区间为 `[start_frame, end_frame)`。参考片时间和配音时间的换算保留在项目文件中。

`viewport` 的 `x/y/w/h` 是屏幕上的内容区域，字幕另占屏幕区域。`pages[]` 包含 `id/width/height/elements[]`；元素有唯一 `id`、页面坐标 `x/y/w/h`，可带 `text/font_size/color` 等呈现数据。包围盒应包含完整文字和图形，不用锚点假装尺寸。图片／图表可用自定义页面组件，但包围盒仍登记在 elements 中。

默认模板在 viewport 外包圆角、阴影和小工具栏，内容坐标不变。给页面周围留白，viewport 上方预留32像素给工具栏，固定页眉／字幕不要占此位置。默认背景为柔和渐变，可用 root.background 覆盖；页面本身保持白底。不要让页面满屏贴边，也不要给每个元素再套一层录屏窗口。

`scenes[]` 连续覆盖最终时间轴；每项有 `page_id/start_frame/end_frame/camera/cues`。同一页可以在不同场景重复出现。`camera[]` 使用绝对帧 `frame`，`cx/cy` 是视口中心对应的页面坐标，`scale` 是页面像素到屏幕像素倍率；首尾关键帧分别位于场景首帧和末帧，中间按 smoothstep 插值，重复同一姿态的键表示停留。

```text
screen_x = viewport.x + viewport.w / 2 + (page_x - camera.cx) * camera.scale
screen_y = viewport.y + viewport.h / 2 + (page_y - camera.cy) * camera.scale
```

页面和标注使用同一变换；字幕留在外层。鼠标位置经过变换，其图标尺寸不乘 scale。整页概览用实际页面尺寸适配视口，长页则按语义分组展示，不要求几万像素长页一次全塞进屏幕。

## 语义强调 cues

每项包含：

- `kind`：`circle / underline / point`。
- `target_id`：当前页元素 ID；`reason` 说明讲解理由。真实制作追加 `narration_id` 及词级时码关联；夹具可以无声。
- `start_frame/end_frame`：操作和停留的总区间。
- `approach_frames`：cue 开始到指针抵达路径起点的帧数；跨目标旅行也使用前一个 cue 结束后的空档。`draw_frames` 是画圈／划线时间，point 的 draw_frames 为指针停留缓冲。
- `padding`：目标外的页面像素留白；可选 `color`。

同一场景 cues 不重叠，防止多个鼠标／关注点争抢；并列比较用一个含两方的父级目标。圈画在操作结束后保留到场景末尾，换场景清除，不为了留标记而延长 cue 干扰后续强调。镜头在 cue 开始前到位，画线或画圈时保持稳定。

组件提供整段连续指针：首帧从视口内空白处出发，目标间按屏幕坐标缓入缓出，绘制时尖端精确跟随页面路径，最后回到空白处。下一场景从同一屏幕位置开始，避免跳闪；无 cue 的介绍段也保留指针。图标为32×41屏幕像素，几何检查覆盖包括过渡在内的每帧。轨迹由语义目标派生，不声称复制了参考视频的真实鼠标记录。

## 组件与调用

[CameraStage.tsx](../assets/remotion/CameraStage.tsx) 接收 `plan`、`renderPage(page)`；由页面组件绘制真实文本、图表和图片。它负责场景选择、视口裁剪、镜头变换、指针与标注。字幕、音频和其他屏幕层放在 CameraStage 外。所有时序消费同一计划，使用本地字体并在字体加载完成后恢复渲染。

首次试用可复制 assets 中的 demo-plan 与 remotion 文件到规范项目的 `project/`，以 `Demo.tsx` 为技术夹具入口；`render-demo.mjs <tools.json> <project/入口> <output/样片.mp4>` 使用工作区共享依赖，不联网安装或下载浏览器。它使用相邻的 `public/`，复制主 Skill 的 `LXGWWenKai-Regular.ttf` 到 public 后运行。实际项目仍锁定所消费的依赖版本。

正式制作走 [Screencast.tsx](../assets/remotion/Screencast.tsx) 固定模板，不把技术demo当成品渲染器。`text/chips/stat/panel/flow/bullets/quote/bars/rule` 对应当前实片元素；模板加载真实本地字体并按DOM测量适配文字，不改变目标框。密度太高时编译／预检报错，Agent拆页或缩短屏幕摘要。旁白原文不随视觉摘要改写。

元素共有 `id/kind/x/y/w/h/color/font_size`；数据字段如下，不需要读TSX来猜接口：

| kind | 内容字段 |
|---|---|
| text | text；可选align、weight、line_height、border |
| chips / flow / bullets | items（字符串数组）；chips/flow可指定每行cols |
| stat | caption、value（可含换行）、value_size |
| panel | title、lines（字符串数组）、title_size |
| quote | lines（字符串数组） |
| bars | items，每项label、value、ratio（0–1；数据／示意来源必须明确） |
| rule | 只需几何和color |

已有风格需要固定页眉／页脚时，chrome提供badge/title/sub/footer_label/progress的位置框；对应page提供同名文字／progress数值，留在屏幕层不随镜头缩放。普通页面可省略chrome，页面内容仍由elements完整表达。

通过统一 CLI 运行计划检查：

```text
python <video-production>/scripts/video_production.py screencast-check --plan <work/screencast-plan.json> --out <qc/plan-check.json>
```

检查：结构、有限数值、ID 唯一性、场景覆盖、关键帧顺序、目标／标注／鼠标在每个活动帧的可见性、字幕区间与安全区。检查不负责推断讲解正确性、实际字体宽度、图层遮挡或阅读自然度；需渲染前／中／后帧与连续观看。

## 先预检／审核，再 MP4-only 交付

```text
python <video-production>/scripts/video_production.py screencast-preview --workspace-root <workspace> --plan <work/screencast-plan.json> --audio <已对齐配音.wav> --out-dir <output>
python <video-production>/scripts/video_production.py screencast-deliver --workspace-root <workspace> --plan <work/screencast-plan.json> --audio <已对齐配音.wav> --out-dir <output> --review <已审核review.json>
```

preview只渲染静帧，生成签名目录内preflight.json与review-draft.json，不开始整片渲染。数据包逐页列出标题／副标题、元素显示文字、引用原句、表达意图和预检帧号。逐页核对语义（特别是数字、否定、如果／只要／有机会）及画面，把结论写为review.json：semantic/visual为pass，pages每项status为pass且notes有具体证据，issues中high/medium须解决。工具验证覆盖与指纹，不具备自动判真能力；不要把占位not_checked改成pass而不实际检查。

issues每项包含level（high/medium/low）、status（open/resolved）及问题／解决证据；空列表表示未发现问题，不是默认替审核员清空问题。low可保留说明，high/medium未解决则阻断。

默认完整预检包含每页首／末帧和每个cue绘制中帧。`--frames`只做局部探测，不能授权完整交付。审核绑定当前revision和snapshot signature；内容、音频、字体或模板改变会失效。先批量修改content数据、重新build和preview、更新审核，然后才deliver。

交付器复用相同快照的完整预检，避免重复跑静帧；执行渲染、混流及技术QC，包括五个一秒音轨对比窗口。音频时长偏差超过一帧或声音哈希改变会拒绝交付。拿job_id/job_dir等待，再读handoff取得实际MP4路径。技术ready仍不代表完整听审；内部代码和计划仅供重试，不交剪映工程。

主题→文案→配音仍由Agent与共享TTS／ASR流程完成；本交付器消费已经对齐的配音和计划，不声称在没有配置和授权的环境里自动拥有配音服务。one-shot要求Agent贯通这些步骤，而不是让用户提供所有中间数据。
