# -*- coding: utf-8 -*-
"""生成 README 用的 Demo 预览图 docs/demo_output.png。

流程：
  1) 用转换器真实产物（output/*.gif）与 sample 里的图片，组装成样例目录
     docs/demo_output/（gif/ m-XXX.gif + static/ s-XXX.png + report.json）；
  2) 用 Pillow 拼一张「输出目录结构 + 生成文件缩略图」的预览图。

前置：先 `python main.py --input sample --output output` 生成真实产物（或用已有 output/）。
可重复运行：python docs/make_demo_preview.py
"""
from __future__ import annotations

import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))      # docs/
PROJ = os.path.dirname(ROOT)                            # 项目根
DEMO = os.path.join(ROOT, "demo_output")
PNG = os.path.join(ROOT, "demo_output.png")

# 真实源文件（转换器刚生成 / sample 自带）
SRC = {
    "m-001.gif": os.path.join(PROJ, "output", "video_demo.gif"),
    "m-002.gif": os.path.join(PROJ, "output", "emoji_demo.gif"),
    "m-003.gif": os.path.join(PROJ, "output", "seq.gif"),
    "s-001.png": os.path.join(PROJ, "sample", "seq_001.png"),
    "s-002.png": os.path.join(PROJ, "sample", "single.jpg"),
}


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    cands = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_demo_tree() -> None:
    """组装 docs/demo_output/ 样例目录（真实文件 + 短命名）。"""
    if os.path.exists(DEMO):
        shutil.rmtree(DEMO)
    os.makedirs(os.path.join(DEMO, "gif"))
    os.makedirs(os.path.join(DEMO, "static"))

    for name, src in SRC.items():
        if name.endswith(".gif"):
            shutil.copyfile(src, os.path.join(DEMO, "gif", name))
        else:
            if src.endswith(".jpg"):
                Image.open(src).convert("RGB").save(os.path.join(DEMO, "static", name))
            else:
                shutil.copyfile(src, os.path.join(DEMO, "static", name))

    report = {
        "stats": {
            "total": 5,
            "downloaded": 5,
            "failed_download": 0,
            "animated_to_gif_ok": 3,
            "static_to_png_ok": 2,
            "avatar_filtered": 3,
        },
        "items": [
            {"local_file": "gif/m-001.gif", "format": "webp", "is_animated": True},
            {"local_file": "gif/m-002.gif", "format": "webp", "is_animated": True},
            {"local_file": "gif/m-003.gif", "format": "gif", "is_animated": True},
            {"local_file": "static/s-001.png", "format": "png", "is_animated": False},
            {"local_file": "static/s-002.png", "format": "jpg", "is_animated": False},
        ],
    }
    with open(os.path.join(DEMO, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def thumb(path: str, box: tuple[int, int]) -> Image.Image:
    im = Image.open(path)
    try:
        im.seek(0)
    except Exception:
        pass
    im = im.convert("RGB")
    im.thumbnail(box)
    return im


def human_size(path: str) -> str:
    n = os.path.getsize(path)
    return f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.2f} MB"


def build_montage() -> None:
    W, H = 1280, 780
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    title_f = load_font(34, bold=True)
    sub_f = load_font(19)
    tree_f = load_font(20)
    cap_f = load_font(17)
    small_f = load_font(15)

    d.text((W // 2, 40), "本地媒体转码 → 输出预览", font=title_f, fill="#1a1a2e", anchor="mm")
    d.text((W // 2, 86), "output/ 目录结构 + 生成文件（gif/ 动图 · static/ 静态图）", font=sub_f, fill="#888888", anchor="mm")

    # ---- 左：目录树 ----
    tree_x0, tree_y0, tree_x1, tree_y1 = 40, 130, 470, 740
    d.rounded_rectangle([tree_x0, tree_y0, tree_x1, tree_y1], radius=12, fill="#f7f8fa", outline="#e3e6ea")
    d.text((tree_x0 + 22, tree_y0 + 16), "输出目录结构", font=load_font(20, bold=True), fill="#333333")
    tree_lines = [
        "output/",
        "├── gif/",
        "│   ├── m-001.gif   动图",
        "│   ├── m-002.gif   动图",
        "│   └── m-003.gif   动图",
        "├── static/",
        "│   ├── s-001.png   静态图",
        "│   └── s-002.png   静态图",
        "└── report.json",
        "",
        "动图(AWebP/APNG/GIF)",
        "  → 自动转 .gif",
        "静态图 → 自动转 .png",
    ]
    y = tree_y0 + 54
    for ln in tree_lines:
        color = "#111111" if ln.startswith(("output", "├", "└")) else "#555555"
        d.text((tree_x0 + 24, y), ln, font=tree_f, fill=color)
        y += 30

    # ---- 右：缩略图网格（3 列 × 2 行） ----
    tiles = [
        ("gif", "m-001.gif", "动图 → GIF"),
        ("gif", "m-002.gif", "动图 → GIF"),
        ("gif", "m-003.gif", "动图 → GIF"),
        ("static", "s-001.png", "静态图 → PNG"),
        ("static", "s-002.png", "静态图 → PNG"),
        (None, "report.json", "统计清单"),
    ]
    gx0, gy0, tw, th, gapx, gapy = 500, 130, 230, 235, 15, 25
    for i, (subdir, name, tag) in enumerate(tiles):
        c, r = i % 3, i // 3
        x = gx0 + c * (tw + gapx)
        y = gy0 + r * (th + gapy)
        d.rounded_rectangle([x, y, x + tw, y + th], radius=12, fill="#fbfbfd", outline="#e3e6ea")

        img_box = (tw - 24, 150)
        if subdir is None:
            # report.json：画一个 JSON 文案块
            jb_x0, jb_y0 = x + 12, y + 12
            d.rounded_rectangle([jb_x0, jb_y0, x + tw - 12, y + 12 + 150], radius=8, fill="#f0f4f8")
            d.text((x + tw // 2, y + 12 + 75), "{\n  \"stats\": {...},\n  \"items\": [...]\n}",
                   font=small_f, fill="#334155", anchor="mm", spacing=4)
        else:
            p = os.path.join(DEMO, subdir, name)
            im = thumb(p, img_box)
            ix = x + (tw - im.width) // 2
            iy = y + 12 + (150 - im.height) // 2
            canvas.paste(im, (ix, iy))

        d.text((x + tw // 2, y + th - 42), name, font=cap_f, fill="#111111", anchor="mm")
        if subdir is not None:
            size = human_size(os.path.join(DEMO, subdir, name))
            d.text((x + tw // 2, y + th - 20), f"{tag} · {size}", font=small_f, fill="#888888", anchor="mm")

    d.text((W // 2, 736), "以上为程序生成的真实样例文件（docs/demo_output/），非屏幕录制",
           font=small_f, fill="#aaaaaa", anchor="mm")

    canvas.save(PNG)
    print("saved:", PNG)


if __name__ == "__main__":
    build_demo_tree()
    build_montage()
