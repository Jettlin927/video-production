# 运镜计划与组件接口

创建页面／动画计划时读本页。可运行技术夹具见 [demo-plan.json](../assets/demo-plan.json)，只验证运镜与指针，不是默认商业文案。

默认通过 `screencast-build` 编译：author沿用下述pages/scenes结构，但不填写camera；每个cue给kind/target_id/reason/start_frame/end_frame，其余时长和padding可省略。编译器保留讲解时间，派生全景、推近、停稳、回全景以及指针到位／绘制时长；时序装不下时调整内容数据，不静默平移旁白。revision是内容指纹，不手写固定的001反复覆盖。

## 坐标和时间

`revision`、`width`、`height`、`fps`、`duration_frames` 描述最终时间轴；所有事件使用最终帧号，区间为 `[start_frame, end_frame)`。参考片时间和配音时间的换算保留在项目文件中。

`viewport` 的 `x/y/w/h` 是屏幕上的内容区域，字幕另占屏幕区域。`pages[]` 包含 `id/width/height/elements[]`；元素有唯一 `id`、页面坐标 `x/y/w/h`，可带 `text/font_size/color` 等呈现数据。包围盒应包含完整文字和图形，不用锚点假装尺寸。图片／图表可用自定义页面组件，但包围盒仍登记在 elements 中。

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
- `approach_frames`：指针从邻近位置到路径起点所需帧数；`draw_frames` 是画圈／划线时间，point 的 draw_frames 为指针停留缓冲。
- `padding`：目标外的页面像素留白；可选 `color`。

同一场景 cues 不重叠，防止多个鼠标／关注点争抢；并列比较用一个含两方的父级目标。标注在操作结束后隐藏；需要持续保留到段尾时延长 end_frame。镜头在 cue 开始前到位，画线或画圈时保持稳定。

组件的到位阶段是目标邻近的短距离移动，不模拟完整桌面操作轨迹。跨目标移动需要结合镜头过渡安排时间；真实参考需更精细鼠标动作时，再扩展并验证，不声称已自动复刻原鼠标轨迹。

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

## MP4-only 正式交付

```text
python <video-production>/scripts/video_production.py screencast-build --author <work/screencast-author.json> --out <work/screencast-plan.json>
python <video-production>/scripts/video_production.py screencast-deliver --workspace-root <workspace> --plan <work/screencast-plan.json> --audio <已对齐配音.wav> --out-dir <output>
```

交付器按计划／音频／字体／模板指纹隔离快照，执行预检、渲染、混流及公共技术QC；已有成功阶段可复用。原输入不覆盖，音频时长偏差超过一帧则拒绝混流。后台管理与主Skill一致：拿返回job_id/job_dir等待，再读handoff取得实际MP4路径。生成代码和计划只供内部重试；默认不生成／安装剪映，也不要求剪映打开、编辑、保存来判定本路线完成。

主题→文案→配音仍由Agent与共享TTS／ASR流程完成；本交付器消费已经对齐的配音和计划，不声称在没有配置和授权的环境里自动拥有配音服务。one-shot要求Agent贯通这些步骤，而不是让用户提供所有中间数据。
