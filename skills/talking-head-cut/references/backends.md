# 工具分工与能力证据

核对日期：2026-09-15。下列源码/文档说明能力和调用方向，未证明本机中文口播端到端质量。运行前以当前安装版本的工具 schema 与 CLI help 为准。

## 路线选择

1. **默认路线**：使用本 Skill 已有的 ASR/剪辑计划脚本和当前项目已有的 Remotion 工程/渲染器；它们是默认执行链，不需要比较或安装替代工具。
2. **OpenChatCut**：只有当前项目已经提供可调用连接，或用户明确指定时才使用；通过它的当前工具/API 列表确认目标工程，不为寻找它递归扫描机器。
3. **HyperFrames/其他 HTML 工具**：只有用户明确指定或当前项目已有可调用连接时才使用；否则不创建第二套包装路线。剪辑执行与字幕映射须落实，只有模板不能宣称已经剪好口播。

OpenChatCut 接 Remotion 的自定义外部工程不是已验证即插即用接口；需要时先做短片交接试验。可采用不烧字幕的粗剪中间文件＋final 时间轴字幕，再由一个渲染器包装，记录中间文件时间基与编码损失。粗剪 MP4 无法恢复源素材编辑能力，须保留 OpenChatCut 工程/源区间计划。

HyperFrames 作为 Remotion 工程的局部图解素材来源也是可选设计：先验证支持的导出格式、透明度/合成方式、帧率与时长；不假设跨工具直接导入时间线。纯口播无需为凑齐三个工具制造额外转码。

## OpenChatCut

核对提交 `607e0fcc2b755a92a659deb54305ba8164930ae3`：

- [talking-head-guide](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/skills/talking-head-guide/SKILL.md)：逐字稿编辑与字幕显示分层的官方工作流。
- [transcript-tools.ts](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/tools/transcript-tools.ts)：`manage_transcript fix` 只修文字/说话人，不剪原声；`clean_script` 处理指定清理及停顿规则。
- [silence-tools.ts](https://github.com/0xsline/OpenChatCut/blob/607e0fcc2b755a92a659deb54305ba8164930ae3/src/agent/tools/silence-tools.ts)：信号静音分析和裁剪执行；检测结果不是语义决策。

使用 OpenChatCut 时，先通过它的当前工具/API 列表确认目标工程，再用 `read_script`→编辑 `timeline.md`→`apply_script`。具体停顿可通过 `read_script({showSilence:true})` 暴露标记后调整，应用后读回工程确认。命令行工具、FFmpeg 和浏览器路径由主 Skill 的环境门提供，不在这里重新发现。

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

依赖安装与工具解析由主 Skill 的 `check_env.py` 环境门负责；本参考只处理路线选择和路线特有的模型/服务决策。云 ASR、LLM 和媒体生成是不同服务，分别确认用途及数据路径；用户给 LLM Key 不代表已配置转写。未授权上传时走本地路线。没有可运行路线时交付具体缺项和可执行计划，不生成虚假的转写、工具结果或质检通过项。
