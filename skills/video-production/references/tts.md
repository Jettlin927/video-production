# 公共 TTS 执行器

需要从文案生成新旁白时读本页；已有用户录音仍走 ASR，不重做声音。公共入口是 `video_production.py tts`，钩子、PPT 讲解和其他旁白路线共用。

## 一次调用，直接生成配音

使用工作区 `tools.json` 中的 Python 运行公共入口，不直接执行 `.py` 文件。首次使用当前配置先预检；不带 `--execute` 时只输出模型、音色、分段数量和 Key 是否存在，不联网、不写文件：

```text
python <video-production>/scripts/video_production.py tts --workspace-root <workspace-root> --script <brief/copy-source.txt或script.json> --out-dir <work/voice>
```

已获得当次配音调用授权后，在同一命令加 `--execute`。它返回公共后台 job；按返回的 job_dir/job_id 用 `job-watch` 等终态，再读 `work/voice/tts-manifest.json`，不要在模型循环中轮询。首次配置用实际生成的首个分段检验接口，不另写试配音脚本或重复合成同一段。

Agent 只准备本次原文或句子数据，不为每条片写 prepare_text、build_sentences、tts_synth、WebSocket 调用或音频拼接脚本，也不去旧项目里找配音实现。公共脚本报错时保留错误和缓存，交给明确的维护任务修复，不在视频生产会话修改共享脚本。

## 输入、默认值与输出

- 输入为 UTF-8 文本，或包含 `sentences[{id,text_zh}]` 的 JSON。文本自动生成稳定句子 ID；JSON 保留已有 ID 和原句。原文标点与文字不改写，数字／英文发音需要调整时另备经确认的配音文本，画面与字幕仍保留原文。
- 默认 `qwen3-tts-flash / Cherry / Chinese`；`.env` 可设置 `BAILIAN_TTS_MODEL/BAILIAN_TTS_VOICE/BAILIAN_TTS_LANGUAGE`，CLI 的 `--model/--voice/--language-type` 优先。共用 `DASHSCOPE_API_KEY/DASHSCOPE_BASE_URL`；无需每条视频重新选音色或复制配置。当前执行器只适配 Qwen3-TTS-Flash 协议，不自动切换到声音克隆或其他 TTS 协议。
- 文案自动按标点／空白分成不超过500字符的请求，连续原文合并到分段预算内；超长无标点内容按上限切开，不丢字、不改顺序。按段顺序合成，保持同一模型和音色。
- 音频统一为24kHz、单声道、PCM16 WAV，拼接直接处理样本，不构造数百段 FFmpeg 跨淡化图。默认不额外插入段间静音；确有需要用 `--gap-s`，天然标点停顿保留，不在 TTS 内压气口或变速。
- 产物为 `voiceover.wav`、`script-sentences.json`、`tts-manifest.json`。清单记录输入／模型／音色指纹、每段请求ID、用量、音频时长、拼接偏移和产物哈希。分段偏移不是句／词级时码；仍须用 `transcribe` 回扫，再用公共 `align` 对齐执行器输出的句子数据。

## 缓存与恢复

缓存位于当前输出目录的 `.tts-cache/<signature>/`，音频指纹包含实际配音全文、模型、音色、语言、业务端点和段间留白。修改这些输入会使用另一套缓存；只改字幕分句或句子ID时更新句子数据，不重复合成同一全文。不要以“同名 chunk.wav 存在”判断可复用。

重复执行同一命令复用哈希一致的完整音频或已完成分段；下载／本地转换失败可从已保存的 API 响应继续，不重新付费合成。签名下载地址仅留在本地缓存状态，不输出到 stdout／公开清单，不提交缓存或凭证。

提交超时、结果不明或明确拒绝时停止，保留对应分段状态，不自动重复 POST。先核对供应商结果、配置及错误，结果无法恢复且确需重试时获得新的调用授权，只处理明确失败的分段状态；不要清空全部缓存或换目录绕过未决请求。

## 节奏与验证边界

钩子视频后处理遵循其 [配音与节奏](../../hook-video/references/tts.md)；PPT 讲解保留语义停顿，不能继承钩子的默认强压气口规则。改变音频后，字幕和运镜必须使用更新后的同一时间轴。

离线测试覆盖文本完整性、缓存失效、失败恢复、避免重复提交和本地音频拼接／转换，不证明实际供应商开通、音色听感、收费或实时性能。正式业务调用仍依赖当前服务配置和授权。
