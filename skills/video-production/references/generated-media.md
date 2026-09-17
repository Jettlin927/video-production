# 百炼生成口播补充画面

## 配置与接口合同

用户指定的视频模型为 `wan3.0-video`，图片模型为 `qwen-image-3.0`。在 `.env` 的 `DASHSCOPE_BASE_URL` 填写使用者自己的业务空间地址，例如：

`https://YOUR-WORKSPACE.cn-beijing.maas.aliyuncs.com/api/v1`

这两个模型的请求合同来自用户给出的 curl，尚未进行真实账号调用验证；不能用较早模型文档推定所有参数通用。脚本严格采用：

- 图片：同步 POST `/services/aigc/multimodal-generation/generation`，`input.messages[].content[].text`，`parameters.prompt_extend=true`；从 `output.choices[].message.content[].image` 取下载 URL。图片宽高先在提示词中描述，收到后探测，不擅自添加未核实模型参数。
- 视频：异步 POST `/services/aigc/video-generation/video-synthesis`，`input.prompt`，默认 `resolution=480P, ratio=adaptive, duration=5`，带 `X-DashScope-Async: enable`；保存 task_id，以 GET `/tasks/{task_id}` 轮询，成功后下载 `output.video_url`。

参考百炼的[异步任务管理](https://help.aliyun.com/zh/model-studio/manage-asynchronous-tasks)、[视频异步响应说明](https://help.aliyun.com/zh/model-studio/text-to-video-api-reference)、[图像响应结构](https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference)。这些通用响应约定仍需用指定模型实测，失败时保留错误而不偷偷换模型。

从 Skill 根目录 `.env.example` 创建本机 `.env`，填写自己的 `DASHSCOPE_API_KEY` 和业务空间地址；环境变量同名值优先。`.env.example` 可分享，真实 `.env` 不读取到对话、不打印、不进入工程/ZIP/截图；打包用明确文件白名单。脚本没有向媒体下载地址转发 Authorization。模型、付费调用和生成数量遵循当前任务的授权与清单；历史任务的授权不适用于新用户。

## 先设计“为什么插”，再生成

完成口播内容剪辑并锁定 final revision 后，先执行 [visual-planning.md](visual-planning.md)，再写 `schema_version: 2` 的 `broll-plan.json`。每个镜头绑定原句/word IDs、用途、画面目标、事实范围和来源，所有生成镜头引用同一个 visual_style.id。旧无版本清单仍可读用于已有工程，不用于新策划。

- 图片：概念、物体、隐喻、场景建立；复杂准确图表/金额/文字由模板叠加，避免依赖模型把字画对。
- 视频：动作、流程、空间变化、具有时间先后的案例；提示词明确单镜头主体动作、景别、运镜和风格，不要求生成另一段说话人抢走口播。
- 脚本将整片 visual_style 的媒介、配色、线条/材质和构图规范加入每条提示词。先选定一张合格基准图，记录 style_reference，再逐张对照实际画风；同一 style_id 不等于视觉检查通过。生成示意明确标示，真实 UI 使用对应授权截图。
- 只有 raw 也可按当前授权生成素材，无需用户另外提供 B-roll。图片优先，先校准一张再继续；按解释价值选镜头，并在连续约20–30秒无补充画面时检查空镜候选，普通空镜约2–3秒。语义不合适或真人表达需要保留时跳过，详见策划参考。
- `adaptive` 和 480P 是用户给定的生成参数，不能保证直接得到 9:16/1080p；下载后检查构图与清晰度。低清视频优先小窗或有限尺寸，无法满足全屏时说明并按已有授权调整请求，不能通过拉伸冒充高清。

## 生成、下载、重入

在 Skill 根目录执行（路径也可全写绝对路径）：

```powershell
python scripts/bailian_media.py --plan 'D:/项目/broll-plan.json' --out 'D:/项目/generated'
python scripts/bailian_media.py --plan 'D:/项目/broll-plan.json' --out 'D:/项目/generated' --execute
```

第一条为不联网的请求预览，展示注入整片风格后的请求。第二条按当前授权提交/恢复，并可收集 local_real/template 本地文件（只读输入并计算哈希，无需 Key）。每个 image 只发一次同步请求，每个 video 只创建一次异步任务；默认每次最多新建6项。v2 的 budget 另外限制整片累计生成数、估算总费用与同镜头尝试数，校准/拆批/新 ID 重生成均使用同一 --out 账本。提交前检查整个批次，拒绝超限；失败和结果未知也保守占用预算。估算金额不是账单实付金额。失败/超时不自动重建；pending 继续轮询。同步图片超时或提交响应丢失标 submission_unknown，先查控制台，不能盲重试产生重复费用。

任务状态及签名下载链接保存在任务产物目录，不写 Skill 目录；`media-manifest.json` 存可交付的路径、哈希、模型、时间线、共享风格和编辑依据。下载后查看完整媒体，在 manifest 写 asset_review=pass 和 review_notes；生成素材还需 style_review=pass、style_review_notes、style_reference_sha256。基准图在计划的 style_reference 中填 path/sha256，重跑相同计划生成清单（不重新付费）后再审查。风格/原句/用途/时间轴变化会使旧审查失效；审查字段由实际检查填写，不能为了通过脚本批量填 pass。

重跑同请求复用已有资产；改提示词或整片风格需新 ID，沿用同一 shot_id，明确意味着一次新生成。下载失败可重入；链接过期先查原 task 更新结果，不先重新生成。锁文件防止并发重复提交；若进程崩溃，仅在确认无运行进程后清理该任务目录的 `.generation.lock`。新版本不继承旧的无审查绑定记录，需重新审查；旧输出目录没有费用账本时先核对历史支出，不可删除状态来规避限额。

清单示例（演示时码和费用；正式填写当前 final 落点、已核对报价与任务预算。首次校准可仅保留第一项；后续用同一输出目录跑完整清单。`visual_style` 用 `visual_plan.style_preset('real-biz-01', 'portrait')` 生成，这里为省行数压成一行）：

```json
{
  "schema_version":2,
  "revision":"cut-001", "fps":{"num":25,"den":1}, "duration_frames":1500,
  "visual_style":{
    "id":"real-biz-01", "medium":"写实摄影，商业纪实/编辑摄影质感；非插画、非三维渲染",
    "palette":"真实自然色调，整体低饱和；以环境光为准——暖白日光、窗边冷灰、木色与肤色为主",
    "rendering":"真实材质与皮肤质感；浅景深；自然光为主光方向；高光柔和滚降、暗部保留细节；35mm–50mm 视角；轻微胶片颗粒",
    "composition":"主体置于画面中上部，视线方向留出空气；背景交代行业环境而非纯色背景；下方为平缓低对比区域供字幕；竖幅 9:16，成片为竖屏",
    "avoid":"矢量插画、三维塑料质感、霓虹与赛博光效、HDR 过锐、摆拍露齿假笑、可读文字与商标、过度磨皮的塑料皮肤"
  },
  "budget":{"max_total_jobs":6,"max_attempts_per_shot":2,"max_estimated_cost":3,"currency":"CNY"},
  "jobs":[
    {"id":"organize-v1","shot_id":"organize","kind":"image","source_type":"generated",
     "purpose":"explanation","source_text":"把零散记录整理成客户资料","source_word_ids":["k1:w12","k1:w13"],
     "visual_goal":"展示零散记录汇集为结构化卡片的关系","claim_scope":"工作流程示意，不代表某客户实际交付",
     "style_id":"real-biz-01","estimated_cost":0.5,
     "prompt":"主题是销售工作自动化。当前讲述整理客户资料。一位职员在真实办公桌前，把散落的空白纸页归拢成一叠整齐文件，侧逆窗光，浅景深，背景是虚化的普通办公室；无真实品牌、客户身份、文字或效果数字。",
     "start_frame":250,"end_frame":325,"placement":"full","reason":"帮助观众理解整理前后的信息结构"},
    {"id":"desk-v1","shot_id":"desk","kind":"image","source_type":"generated",
     "purpose":"pacing","source_text":"这些日常工作每天都在重复","source_word_ids":["k5:w1","k5:w2"],
     "visual_goal":"展示与当前话题相关的日常工作场景","claim_scope":"一般场景，不代表真实员工",
     "style_id":"real-biz-01","estimated_cost":0.5,
     "prompt":"主题是销售工作自动化。当前讲述日常重复工作。一个职员在整洁办公桌前整理一小叠空白卡片，午后自然光，浅景深，画面简单，无文字与品牌。",
     "start_frame":1050,"end_frame":1100,"placement":"inset","rect":{"x":0.1,"y":0.30,"width":0.8,"height":0.28},"reason":"连续真人段中的相关空镜，避开结论"}
  ]
}
```

真实素材项用 `source_type: local_real`，写 `path` 和 `source_note`；purpose=evidence 时再写 `evidence_basis`（来源身份、事件/片段、能证明什么）。不需要 prompt/style_id/estimated_cost。本地排版示意图用 template；两类仍需 source_text/source_word_ids/visual_goal/claim_scope 及实际内容审查。单条素材任务没有原声时用脚本句 ID 和需求文本。

## 真正插入视频

```powershell
python scripts/prepare_broll.py --manifest 'D:/项目/generated/media-manifest.json' --timeline 'D:/项目/edit-plan.json' --public 'D:/项目/remotion/public' --ffmpeg '绝对路径/ffmpeg.exe' --ffprobe '绝对路径/ffprobe.exe'
```

脚本核对 revision/fps/全片长度、素材哈希、审查上下文绑定、实片审查状态与源时长；v2生成素材额外核对基准图哈希和风格审查。统一尺寸/帧率，去掉补充视频声音，检查全解码和输出帧数；写 `public/broll.timeline.json` 和 `public/generated/`。图片转为真 PNG，视频转为无声 H.264，画幅采用 contain 留边，不裁掉关键信息或拉伸。过短视频拒绝静默循环或冻结。标签按来源设置：生成素材“AI 生成示意”、模板“示意图”、真实素材不标成AI；工程继续保留来源和原句绑定。

Remotion：将 `assets/remotion/BRollLayer.tsx` 复制到项目 src；在 composition 中 import `{BRollLayer}` 和 `public/broll.timeline.json`，在人物视频之后、字幕及主题层之前插入 `<BRollLayer assets={broll.assets} />`。保持原 PCM 人声轨不变，再实际渲染；文件进入素材库不算已经入片。此组件由主 composition 的同一帧时钟驱动。

HyperFrames/OpenChatCut：消费同一清单，将实际下载素材放在 final 区间的叠加层，设置静音并保留字幕上层，应用后读回工程并查实帧；本次交付的可运行适配器是 Remotion，其他两者的原生导入仍需现场验证。

检查每个插入起/中/末帧及前后接缝：语义匹配、主体不变形、画幅/清晰度、脸/字幕遮挡、返回人物的连续感、AI示意标签、音频未被替换。总体成片时长应不变，不能为等生成片播完延长原声。
