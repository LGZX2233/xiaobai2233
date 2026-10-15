# 演示视频与设计图构建

2026-10-15 重做版：19 张正文图；视频 233.223 秒（3分53秒）、1920×1080、30fps、H.264/AAC。成片在 [demo.mp4](../assets/demo.mp4)，字幕和分镜在同目录 `demo.srt`、`demo.segments.json`。SHA-256：`CAFF233FDFCA46015A98D126EC3E2325BD596A7164DBDE8F92641D64A72F9631`。

源码包位于本地 `outputs/video/`：`cards.py`、`assemble.py`、`cuts_v5.json`、唯一旁白 `narration_current.json`、`requirements.txt` 与 `term/` 原始输出。真实 AGH 录屏和截图在 `outputs/agh-run/`。这些本地素材不作为通用内核代码发布；源包说明位于该目录 README。画面使用揭幕、缓慢推近、淡入、标签滑入、进度条及错位双线框。

安装 Python 3.12+、Pillow、qrcode、edge-tts，并让完整 ffmpeg/ffprobe（含 WAV、ASS、zoompan）可从 PATH 运行。Windows 使用微软雅黑/Consolas；Linux 使用 Noto CJK/DejaVu。旁白生成需要 edge-tts 网络服务。

在本地 `outputs/video/` 中按顺序执行：

```powershell
python cards.py curtain
python cards.py
python assemble.py --step audio --cuts cuts_v5.json
python assemble.py --step clips --cuts cuts_v5.json
python assemble.py --step concat --cuts cuts_v5.json --out final5.mp4
```

脚本达到预算以 code 3 退出时，重复同一条命令继续；`work/` 与 `audio/` 是缓存。剪辑表固定选用 20 段，终端回放输入为 `term/term_pytest.mp4`，其文字来自同目录原始捕获，不是重新执行的证明。AGH 片段来自原始实机素材；当前视频保留当时的界面，内核文档不依赖前端。

发布前检查 ffprobe 时长小于240秒、图片文字与字幕无重叠、片头/中段/片尾抽帧及三份成片摘要一致；不要重写历史验收或声称新录制了实机画面。旧剪辑草稿、旧旁白、重复旧成片和可重建缓存已从当前构建入口移除，原始证据与历史交接保留。

发布同时补齐当前文档直接引用的历史审查与同步资料，字节不改；这些记录仍绑定原日期与源码。旧 bridge 测试路径的现有位置见目录分工，不为使历史链接可点击而重写签字或测试证据。
