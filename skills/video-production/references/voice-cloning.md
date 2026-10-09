# 公共声音克隆

仅在用户明确要求使用自己的／已授权的声线时读本页。普通配音仍按 [公共 TTS](tts.md) 使用默认音色；参考视频只提供视觉风格，不构成克隆其声音的授权。克隆是可选的配音能力，不是新增视频类型，也不是数字人或口型能力。

## 用户需要提供什么

- 本人、明确获授权或合成的单人录音，以及需要配音的文案。推荐选10–20秒清楚、连续、无背景音乐的讲话；执行器接收本地音频／视频，从指定起点截取样本，不修改原素材。
- 仍使用主 Skill `.env` 的 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`，不需要另一把 Key。该 Key 所属地域／业务空间必须有对应模型权限和额度；配置检查通过不证明模型开通。
- 确认当次音色创建与配音调用范围。两者分别计费，不在安装检查时创建音色，也不因错误自动改模型或重复创建。

录音是声线参考，不是最终旁白；后续会用这个音色朗读新文案。主流程优先复用已有用户录音，用户未要求换声时不强制克隆。

## 首次创建一次，后续复用

先检查公共环境报告，再通过统一 CLI 的 `contract --command voice-create` 获取接口。音色记录与创建检查点保存在 `<workspace-root>/voice-library/<name>/`，不放在 Skill 源码中，也不按视频重复创建。不同声源使用独立音色目录，保留原记录。

```text
python <video-production>/scripts/video_production.py voice-create --workspace-root <workspace-root> --audio <本地录音> --out <workspace-root>/voice-library/<name>/voice-record.json --preferred-name <英文名称> --start-s 0 --sample-seconds 15
```

默认只预检，不联网、不写文件；`preferred-name` 为1–16位英文字母、数字或下划线。Agent确认样本区间确有清楚单人讲话、声源授权和付费范围后，在同一命令加 `--consent --execute`；`--consent` 是用户授权的记录，不是由Agent自行假定。此命令同步返回一次创建结果，不反复轮询。

执行器把样本统一为24kHz单声道PCM16 WAV，实际解码时长须为3–60秒且不超过10MiB。样本以请求内编码直接发送百炼，不要求用户上传到公开链接或配置对象存储。临时转换样本在创建结束后删除，原素材保持不变。

公共适配器固定使用 `qwen-voice-enrollment` 创建音色，绑定非实时模型 `qwen3-tts-vc-2026-01-22`。`voice-record.json` 保存音色ID、绑定模型、业务端点指纹、声源／样本哈希、用量及请求ID；不包含Key或音频编码。`ready` 只表示可调用，不证明音色相似度已经通过听审。供应商返回降级音色时记录 `review_required`，不直接进入新旁白合成。

## 用音色生成新旁白

```text
python <video-production>/scripts/video_production.py tts --workspace-root <workspace-root> --script <brief/copy-source.txt或script.json> --voice-record <workspace-root>/voice-library/<name>/voice-record.json --out-dir <work/voice>
```

预检通过且已有本次付费授权时加 `--execute`；返回公共后台任务，复用 `job-watch` 等终态。`--voice-record` 自动选择记录绑定的模型与音色，优先于普通 `.env` 默认值；不要把克隆ID塞进 `BAILIAN_TTS_VOICE` 后继续使用普通Flash模型。显式 `--model/--voice` 与记录不一致会被拒绝，不改写用户的普通配音配置。

克隆配音使用较短的200字符请求分段，保持原文与顺序，仍输出公共 `voiceover.wav`、`script-sentences.json`、`tts-manifest.json`，与普通TTS共享拼接、缓存和恢复机制。随后照常 `transcribe → align → 时间轴／字幕／渲染`；更换音色或文案后使用对应的新时间轴，不能沿用旧声音时码。

## 查询、恢复与换电脑

```text
python <video-production>/scripts/video_production.py voice-list --page-index 0 --page-size 20 --execute
```

这是供应商的分页查询，不创建／删除音色。完整列表按分页读取，不能从第一页没有找到就断言音色不存在。查询结果属于本账号，避免把所有音色ID发到公开日志。

- 相同输入重复 `voice-create` 复用已有记录；本地记录缺失但成功检查点还在时可恢复，不重新付费。普通制作只传 `--voice-record`，不要求重新读取原录音。
- 提交前写入 `voice-record.state.json`；超时／结果不明、拒绝或降级时停止，不自动重复POST。先结合请求ID、保存状态与 `voice-list` 核对供应商结果；不要删除状态、换目录绕过未决请求。需要人工恢复记录或重试时交由明确的维护任务，在已查明结果和调用授权范围内处理。
- TTS已收到的响应先保存在本地缓存，下载／转换失败只恢复音频处理；支持供应商返回HTTP音频地址时对同一官方OSS对象使用HTTPS下载，不使用明文传输或任意外站。
- 换电脑携带音色记录／检查点及所需素材、缓存，重新准备依赖和自己的 `.env`，继续使用有权限访问同一音色的账号／业务空间与地域。仅复制记录不转移供应商音色所有权；不同账号不能承诺直接可用。
- 不提交真实音色记录、参考录音、TTS缓存或凭证。本工具不主动删除远端音色。

## 验证边界

离线测试验证请求、绑定、缓存及恢复；真实接口验证应分别记录创建、查询、合成、用量和可解码音频。音色相似度、自然度与内容读音仍要听审；合成音色作为测试声源只证明技术链路，不证明真人克隆效果或成片可发布。

当前模型与价格以[官方克隆接口](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[声音克隆指南](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)及[模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)为准；实际调用前核对适用地域与费率，按用量估算不等于账单实扣。
