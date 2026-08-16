> ⚠️ **安全提示**：本仓库仅提供图像格式转换（如 WebP 转 GIF/PNG）的本地处理工具。相关脚本仅限用于个人本地文件的整理，请勿用于任何违反相关平台用户协议的行为。因违规使用本工具产生的一切后果，由使用者自行承担。

# 本地媒体资源转码与整理工具

把你**保存在本地的媒体素材**（视频 / 图片序列 / 单图 / GIF），自动整理并转成规格统一、体积可控的 GIF 或 PNG。

## 功能特性

- **自动分类**：扫描输入目录，自动区分
  - 已是 `.gif` 的 → 进入后期优化流程
  - `.mp4` / `.webm` 等视频 → 截取高光片段转 GIF（默认前 3 秒，可配）
  - 图片序列（如 `img_001.jpg`、`img_002.jpg` …）→ 按文件名数字排序合成 GIF
  - 单张图片 → 生成单帧静态 GIF
- **FFmpeg 调色板两步法**保证画质（先 `palettegen` 生成专属调色板，再 `paletteuse` 抖动合成）
- **批量处理**：遍历整个目录，输出到 `./output/`，保留原文件名
- **GIF 优化**：限帧率（默认 12fps）、限宽（默认 480px）、限时长（默认 5 秒）、无限循环；超出自动压缩
- **可选体积上限**：`max_size_kb > 0` 时超限自动降分辨率/降帧率重编码
- **可选后期**：文字水印、顶部/底部文字、裁剪、调速（均读配置文件）
- **命名规则**：`原文件名.gif`，冲突时自动追加 `_1`、`_2` …
- **manifest.json**：记录「源文件 → 输出文件 → 尺寸/帧率/体积」完整映射

## 环境要求

- Python **3.11+**（3.10 亦可运行）
- FFmpeg（**可选**：装 `imageio-ffmpeg` 后会自动带一个静态 FFmpeg，未装系统 FFmpeg 也能跑）

## 安装

```bash
cd local_media_tool
pip install -r requirements.txt
```

### FFmpeg 安装指引（可选但推荐）

本工具查找 FFmpeg 的优先级：`config.yaml` 里的 `advanced.ffmpeg_path` → 系统 `PATH` → `imageio-ffmpeg` 自带二进制。
即使完全不装 FFmpeg，`pip install imageio-ffmpeg` 也能正常转换；但若你想用系统 FFmpeg：

> **内置版 FFmpeg 说明**：内置二进制来自 [imageio-ffmpeg](https://pypi.org/project/imageio-ffmpeg/)，
> 实为 **Gyan.dev 的 FFmpeg Windows 静态构建**（`release-essentials`，含 libwebp/libfreetype/libx264 等）。
> 安装时 `imageio-ffmpeg` 版本对应的 FFmpeg 大版本（本机实测为 **FFmpeg 7.1 essentials**）。
> 若遇到个别冷门 WebP 帧解码失败，可优先安装系统 FFmpeg（下述方式）并确保其在 `PATH` 中，工具会优先使用系统版。

- **Windows**
  ```powershell
  # 方式一（推荐，用包管理器）：
  winget install Gyan.FFmpeg
  # 方式二：到 https://www.gyan.dev/ffmpeg/builds/ 下载 release-essentials，
  #         解压后把 bin 目录加入 PATH。
  ```
- **macOS**
  ```bash
  brew install ffmpeg
  ```
- **Linux (Debian/Ubuntu)**
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```

## 快速开始

1. 把你的素材放到 `config.yaml` 的 `input_dir` 指定的目录（或任意目录）；
2. 直接跑：

```bash
# 用默认配置（config.yaml）
python main.py

# 或者指定输入/输出目录
python main.py --input ./sample --output ./output
```

其他常用参数：

```bash
python main.py --input ./x --output ./y --config my_config.yaml
python main.py --input ./x --fps 15 --width 360 --duration 2 --max-size-kb 800
python main.py --verbose     # 打印每条 FFmpeg 命令，便于排错
```

## 配置说明（`config.yaml`）

| 配置段 | 关键项 | 说明 |
| --- | --- | --- |
| `input_dir` / `output_dir` | — | 输入/输出目录 |
| `video` | `duration` `fps` `width` `loop` | 视频截取时长、输出帧率、宽度、循环 |
| `gif` | `max_width` `fps` `max_duration` `max_size_kb` | 已有 GIF 的优化上限与体积上限 |
| `palette` | `stats_mode` `dither` | 调色板统计模式 / 抖动算法 |
| `postprocess` | `speed` `crop` `watermark` `top_text` `bottom_text` | 变速、裁剪、文字叠加 |
| `advanced` | `ffmpeg_path` `tmp_dir` `verbose` | FFmpeg 路径、临时目录、调试输出 |

> 例子：想给所有输出右下角打“已收藏”水印、并裁剪成 320×320：
> ```yaml
> postprocess:
>   crop: "320:320:0:0"
>   watermark: "已收藏"
> ```

## 输出与 manifest.json

转换完成后，输出目录里会生成：

- 每个素材对应的 `*.gif` 文件
- `manifest.json`：

```json
{
  "total": 4,
  "ok": 4,
  "failed": 0,
  "items": [
    {
      "source": "sample/video_demo.mp4",
      "output": "output/video_demo.gif",
      "type": "video",
      "status": "ok",
      "width": 480,
      "height": 360,
      "frames": 36,
      "duration_s": 3.0,
      "fps": 12.0,
      "size_kb": 412.3
    }
  ]
}
```

## 项目结构

```
local_media_tool/
├── main.py                # CLI 转换入口（python main.py --input ./x --output ./y）
├── converter.py           # 扫描/分类/图片序列分组 + convert_file() 单文件转换
├── optimizer.py           # FFmpeg 调色板两步法 + 体积优化
├── config.yaml            # 用户可调参数（input_dir/video/gif/palette/postprocess/advanced）
├── requirements.txt       # moviepy / imageio / imageio-ffmpeg / numpy / Pillow / PyYAML
├── README.md
├── LICENSE
├── sample/                # 本地合成的测试素材（video_demo.mp4、emoji_demo.gif、图片序列…）
└── tests/
    ├── make_samples.py    # 生成 sample 素材
    └── test_run.py        # 转换端到端测试
```

## 运行测试

```bash
# 1. 生成测试素材（sample/）
python tests/make_samples.py

# 2. 端到端跑一遍（对 sample 里的 mp4 和 gif 各输出优化后的 gif）
python main.py --input ./sample --output ./output

# 3. 或者直接跑带断言的测试脚本
python tests/test_run.py
```

## 关键 FFmpeg 参数为什么这样写

| 参数 | 作用 / 理由 |
| --- | --- |
| `fps=12` | 表情包 10~15fps 观感足够；帧率越低体积越小，12 是画质与体积的折中 |
| `scale=480:-1:flags=lanczos` | 宽固定 480、高按比例（`-1`）；`lanczos` 是高质量缩放算法，缩小后边缘更清晰 |
| `palettegen=stats_mode=full` | GIF 仅 256 色，先对全部帧统计最优调色板，避免直接转换出现色带 |
| `paletteuse=dither=floyd_steinberg` | 用 Floyd–Steinberg 抖动把 24bit 颜色映射回 256 色，让渐变过渡更平滑 |
| `-loop 0` | GIF 无限循环播放（表情包常用） |
| `setpts=(1/speed)*PTS` | 变速：加速则压缩时间戳、减速则拉长，作用于所有帧 |

## 常见问题

- **报「未找到 FFmpeg」**：执行 `pip install imageio-ffmpeg`，或按上文安装系统 FFmpeg。
- **中文水印显示成方块/不显示**：`postprocess.font_path` 显式指定一个中文字体文件路径（Windows 一般会自动命中 `C:/Windows/Fonts/msyh.ttc`）。
- **想要更小体积**：把 `gif.max_size_kb` 设为具体值（如 `500`），超限会自动压缩。
- **视频只想要全程而不是前 3 秒**：把 `video.duration` 设为 `0`。

## 更新日志 (Release Notes)

### v1.0.0 (2026-08-16)

#### ✨ 新特性
- 本地媒体资源批量转码：视频 / 图片序列 / 单图 → GIF，已有 GIF 再优化。
- FFmpeg 调色板两步法保证画质；静态图转 PNG/JPG/WebP、动图统一转 GIF。
- 完整 `config.yaml` 配置（帧率 / 宽度 / 时长 / 体积上限 / 水印 / 裁剪 / 变速）+ `manifest.json` 清单。

#### 🐛 修复
- 修复个别 WebP 解码失败导致的处理中断：转码统一走「FFmpeg 优先、Pillow 降级」的多级容错，单文件失败仅告警、绝不中断批次。

## 许可证 (License)

本项目采用 [MIT 许可证](LICENSE)，`Copyright (c) 2026 AlexBlock_lol`。可自由使用、修改、分发，保留版权声明即可。

## 联系方式 (Contact)

- 🔗 GitHub: https://github.com/AlexBlocklol
