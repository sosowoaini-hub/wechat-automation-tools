# wechat-automation-tools

把微信个人号自动化中几个「实际用起来会疼」的问题，做成可复用的小工具。全部基于**官方微信客户端界面**（UIA）或**公开天气 API**，不注入微信进程、不逆向数据库、无封号风险。

> 这些工具源于一个真实场景：让家庭微信群里的小助手「嘎嘎」能查天气、发穿衣播报、发朋友圈。把其中通用的部分抽出来分享。

## 包含什么

| 目录 | 内容 | 解决什么问题 |
|---|---|---|
| [`bridge-stability/`](bridge-stability/) | 微信桥的稳定性补丁（unified diff） | 桥假死、重复发送——来自真实踩坑 |
| [`moments-publisher/`](moments-publisher/) | 发微信朋友圈（图片/视频+文字） | UI 自动化发朋友圈，WeChat 4.x 可用，带 dry-run |
| [`weather-outfit/`](weather-outfit/) | 天气查询 + 26度穿衣法建议 | 免 API Key 查天气，给孩子生成穿衣建议（带逐件加总算式） |

## 快速开始

### 天气 + 穿衣建议（跨平台，零依赖）
```bash
python weather-outfit/weather_outfit.py 成都 --baby 宝宝
```
- 数据来自 Open-Meteo，免 API Key，10 分钟缓存
- `--baby` 或环境变量 `BABY_NAME` 设置称呼；`WEATHER_CITY` 设默认城市
- 输出示例：`今天 14℃，按26度穿衣法要补约 12℃，宝宝穿：羽绒服10℃ + 连体衣2℃ = 12℃，加上气温 14℃ 约等于 26℃`

### 发朋友圈（仅 Windows，需微信桌面客户端）
```bash
pip install uiautomation pywin32
python moments-publisher/moments_publisher.py --images "a.jpg;b.png" --text "周末快乐"   # 试运行，不发布
python moments-publisher/moments_publisher.py --images "a.jpg" --text "周末快乐" --go      # 真发布
```
- **不带 `--go` 永远不发布**（只附加素材+校验编辑器，然后取消）
- 最多 9 个素材；视频超过 28 秒自动用 ffmpeg 裁剪（朋友圈限 30 秒）
- 所有路径可在 `moments-publisher/config.json` 配置（参照 `config.example.json`）

### 桥稳定性补丁
见 [`bridge-stability/README.md`](bridge-stability/README.md)。适用于基于 `wechatauto` / `dsh-wechat-bridge` 的微信桥。

## 设计原则
- **零侵入**：不 hook、不注入、不改微信客户端
- **安全默认**：发朋友圈默认 dry-run；桥的补丁只重启桥不碰微信
- **配置驱动**：路径、称呼、群名全部外置，无硬编码隐私

## 背景与致谢
- 桥的上游 [`dsh-wechat-bridge`](https://github.com/Yuuyuko-uu/dsh-wechat-bridge)（MIT），本项目的补丁是对其的增量改进
- 稳定性补丁的思路部分借鉴了 [`sourcepro5/WeChatAgent`](https://github.com/sourcepro5/WeChatAgent) 的「可靠发送状态机」与 `timed_mutex` 设计
- 26度穿衣法来自网络流传的幼儿穿衣经验，仅供参照，具体请结合孩子体质

## 许可
MIT — 见 [LICENSE](LICENSE)。
