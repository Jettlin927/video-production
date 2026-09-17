# 工具分工与能力证据

核对日期：2026-09-15。下列源码/文档说明能力和调用方向，未证明本机中文口播端到端质量。运行前以当前安装版本的工具 schema 与 CLI help 为准。

## 路线选择

1. **OpenChatCut 可用且有当前项目工具连接**：优先用它保管素材、逐字稿和可撤销的剪辑；样式足够时直接由它导出。其预览/导出使用 Remotion，通常不必另建一个 Remotion 工程。
2. **需要独立可复用模板或 OpenChatCut 无可用连接**：Agent＋已有本地 ASR/VAD＋规范剪辑计划，选择 Remotion 作为最终工程。剪辑执行与字幕映射须落实，只有模板不能宣称已经剪好口播。
3. **环境已有 HyperFrames 或选用 HTML/CSS 模板**：它可承担转写与最终字幕包装；使用相同剪辑计划，不额外建立一套不同的内容取舍。

OpenChatCut 接 Remotion 的自定义外部工程不是已验证即插即用接口；需要时先做短片交接试验。可采用不烧字幕的粗剪中间文件＋final 时间轴字幕，再由一个渲染器包装，记录中间文件时间基与编码损失。粗剪 MP4 无法恢复源素材编辑能力，须保留 OpenChatCut 工程/源区间计划。

HyperFrames 作为 Remotion 工程的局部图解素材来源也是可选设计：先验证支持的导出格式、透明度/合成方式、帧率与时长；不假设跨工具直接导入时间线。纯口播无需为凑齐三个工具制造额外转码。

## OpenChatCut

核对提交 `607e0fcc2b755a92a659deb54305ba8164930ae3`：

- [talking-head-guide](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/skills/talking-head-guide/SKILL.md)：逐字稿编辑与字幕显示分层的官方工作流。
- [transcript-tools.ts](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/tools/transcript-tools.ts)：`manage_transcript fix` 只修文字/说话人，不剪原声；`clean_script` 处理指定清理及停顿规则。
- [silence-tools.ts](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/tools/silence-tools.ts)：信号静音分析和裁剪执行；检测结果不是语义决策。

执行时先读实际工具列表、工程状态与版本，确认针对目标工程。语义删改用 `read_script`→编辑 `timeline.md`→`apply_script`。具体停顿可通过 `read_script({showSilence:true})` 暴露标记后调整，应用后读回工程确认。

批量 `clean_script` 适合有明确规则的机械清理。首次使用需显式选择清理范围及当前 schema 的参数，避免默认值意外同时删语气词；重拍、反问、情绪重复由 Agent 判断。字幕分屏使用显示层机制，不能通过修改原声转录来控制换行。

内置 Agent 能力不能直接当作外部 MCP 已开放能力。分别验证项目读取、编辑、应用、导出及返回文件。若只能生成草稿，就如实交付草稿状态，不声称 MP4 已导出。

## Remotion

- [Captions](https://www.remotion.dev/docs/captions/)：字幕数据/处理支持。
- [transcribe](https://www.remotion.dev/docs/install-whisper-cpp/transcribe)：本地 Whisper.cpp 转写接口。

在已有项目/受控项目目录中锁定依赖，生成单一帧时钟的 React composition。以 `edit-plan.json` 驱动源片区间、字幕和强调动画；保持音视频一致。词时间戳转成目标帧时统一舍入策略，不能各组件自行累计取整。依赖和字体加载完成后再截图/渲染。

## HyperFrames

核对提交 `a0a6244be7a40956c5343f5846609e584ee5c6b5`：

- [转写实现](https://github.com/heygen-com/hyperframes/blob/a0a6244be7a40956c5343f5846609e584ee5c6b5/packages/cli/src/commands/transcribe.ts)
- [官方转写说明](https://github.com/heygen-com/hyperframes/blob/a0a6244be7a40956c5343f5846609e584ee5c6b5/skills/media-use/audio/references/transcribe.md)

已安装且版本确认后，中文转写调用形式为：

```powershell
npx hyperframes transcribe 'raw.mp4' --model small --language zh
```

中文选择多语言模型，不使用 `.en`。双语口播先核对语言过滤行为，防止英文术语/混合语段丢失；small 只是起步，按实片识别情况调整。本地转写无需 ASR API Key，但首次模型/二进制下载与实际安装不是已经完成的前提。

以统一 final 时间轴生成 HTML/CSS/JS composition；在当前项目中核实并运行 `npx hyperframes lint`、`npx hyperframes check`、`npx hyperframes render` 的当前参数。lint/check 通过只覆盖工具检查，不替代口播内容与视听验收。

## 能力缺口处理

先复用已存在依赖；新装工具、下载模型或云转写根据当前任务授权和宿主权限执行。云 ASR、LLM 和媒体生成是不同服务，分别确认用途及数据路径；用户给 LLM Key 不代表已配置转写。未授权上传时走本地路线。没有可运行路线时交付具体缺项和可执行计划，不生成虚假的转写、工具结果或质检通过项。
