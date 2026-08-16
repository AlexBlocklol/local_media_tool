# -*- coding: utf-8 -*-
"""make_samples.py —— 生成 sample/ 目录里的测试素材（无需联网，纯本地合成）。

生成内容：
  * video_demo.mp4                 —— 一段 4 秒、20fps 的彩色动画视频
  * emoji_demo.gif                 —— 一段 30 帧、带循环的动画 GIF
  * seq_001.png ~ seq_008.png      —— 图片序列（用于测试序列合成）
  * single.jpg                     —— 单张图片（用于测试静态 GIF）

运行：python tests/make_samples.py
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample"


def make_frame(i: int, w: int = 320, h: int = 240) -> np.ndarray:
    """生成一帧：渐变背景 + 移动圆点 + 帧号，返回 RGB 的 numpy 数组。"""
    img = Image.new("RGB", (w, h), (20, 30, 50))
    d = ImageDraw.Draw(img)
    # 纵向渐变背景，让调色板两步法有可观察的过渡色
    for y in range(h):
        d.line([(0, y), (w, y)], fill=(20, 30 + (y * 60) // h, 50 + (y * 70) // h))
    x = (i * 5) % (w - 60)
    d.ellipse([x, 90, x + 50, 140], fill=(250, 120, 40), outline=(255, 220, 120), width=3)
    d.text((8, 6), f"frame {i:02d}", fill=(255, 255, 255))
    return np.asarray(img)


def make_mp4() -> None:
    import imageio
    path = SAMPLE / "video_demo.mp4"
    writer = imageio.get_writer(str(path), fps=20, codec="libx264", pixelformat="yuv420p")
    try:
        for i in range(80):  # 4 秒 @ 20fps
            writer.append_data(make_frame(i))
    finally:
        writer.close()
    print(f"[sample] 生成视频 {path.name}  ({os.path.getsize(path)} bytes)")


def make_gif() -> None:
    path = SAMPLE / "emoji_demo.gif"
    frames = [Image.fromarray(make_frame(i)) for i in range(30)]
    frames[0].save(
        path, save_all=True, append_images=frames[1:],
        duration=50, loop=0,  # 每帧 50ms → 20fps，无限循环
    )
    print(f"[sample] 生成 GIF  {path.name}  ({os.path.getsize(path)} bytes)")


def make_sequence() -> None:
    for i in range(1, 9):
        path = SAMPLE / f"seq_{i:03d}.png"
        Image.fromarray(make_frame(i * 4)).save(path)
    print(f"[sample] 生成图片序列 seq_001.png ~ seq_008.png")


def make_single() -> None:
    path = SAMPLE / "single.jpg"
    Image.fromarray(make_frame(0)).save(path, quality=90)
    print(f"[sample] 生成单张图片 {path.name}")


def main() -> None:
    SAMPLE.mkdir(parents=True, exist_ok=True)
    make_mp4()
    make_gif()
    make_sequence()
    make_single()
    print(f"[sample] 完成，素材位于：{SAMPLE}")


if __name__ == "__main__":
    main()
