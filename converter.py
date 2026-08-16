# -*- coding: utf-8 -*-
"""converter.py —— 扫描输入目录、自动分类、图片序列分组、编排转换流程。"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from optimizer import (
    resolve_ffmpeg,
    convert_video_to_gif,
    optimize_gif,
    convert_sequence_to_gif,
)

logger = logging.getLogger("dygif.converter")

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".ts"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}
GIF_EXT = ".gif"

# 匹配「前缀 + 数字 + 扩展名」的图片序列文件名，如 img_001.jpg / seq-12.png
_SEQ_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)(?P<ext>\.[A-Za-z0-9]+)$")


def scan(directory: Path) -> dict:
    """扫描目录，把文件分为：gif / video / image 三类。"""
    files = {
        "gifs": [],
        "videos": [],
        "images": [],
        "skipped": [],
    }
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == GIF_EXT:
            files["gifs"].append(p)
        elif ext in VIDEO_EXTS:
            files["videos"].append(p)
        elif ext in IMAGE_EXTS:
            files["images"].append(p)
        else:
            files["skipped"].append(p)
    return files


def group_image_sequences(images: list[Path]) -> tuple[list[dict], list[Path]]:
    """把图片按「前缀+扩展名」分组，>=2 帧的视为序列，其余视为单张。

    返回 (sequences, singles)：
      sequences: [{"stem": 输出文件名主干, "frames": [按数字排序的路径列表]}]
      singles  : 未成组的单张图片路径列表
    """
    buckets: dict[tuple[str, str] | None, list[tuple[int, Path]]] = {}
    for p in images:
        m = _SEQ_RE.match(p.name)
        if m:
            key = (m.group("prefix"), m.group("ext").lower())
            buckets.setdefault(key, []).append((int(m.group("num")), p))
        else:
            buckets.setdefault(None, []).append((0, p))

    sequences = []
    singles = []
    for key, items in buckets.items():
        if key is None:
            singles.extend(t[1] for t in items)
            continue
        items.sort(key=lambda t: t[0])
        if len(items) >= 2:
            stem = key[0].rstrip("_-. ") or "sequence"  # 去掉前缀末尾的分隔符
            sequences.append({"stem": stem, "frames": [t[1] for t in items]})
        else:
            singles.append(items[0][1])
    return sequences, singles


def unique_output_name(output_dir: Path, stem: str) -> Path:
    """输出文件命名：原文件名.gif，冲突时追加 _1、_2……"""
    candidate = output_dir / f"{stem}.gif"
    if not candidate.exists():
        return candidate
    i = 1
    while (output_dir / f"{stem}_{i}.gif").exists():
        i += 1
    return output_dir / f"{stem}_{i}.gif"


def convert_single_image(src: str, dst: str) -> None:
    """单张图片 → 单帧静态 GIF（GIF 只支持 256 色，用自适应调色板）。"""
    from PIL import Image
    with Image.open(src) as im:
        im.convert("RGB").convert("P", palette=Image.ADAPTIVE).save(
            dst, format="GIF", loop=0
        )


def gif_info(path: str) -> dict:
    """读取输出 GIF 的宽/高/帧数/时长/帧率/体积，供 manifest.json 与摘要使用。"""
    info = {
        "size_bytes": os.path.getsize(path),
        "size_kb": round(os.path.getsize(path) / 1024.0, 1),
    }
    try:
        from PIL import Image
        with Image.open(path) as im:
            width, height = im.size
            n_frames = getattr(im, "n_frames", 1)
            total_ms = 0
            try:
                for i in range(n_frames):
                    im.seek(i)
                    total_ms += im.info.get("duration", 0) or 0
            except Exception:  # noqa: BLE001
                total_ms = 0
            if total_ms <= 0:
                total_ms = n_frames * 100  # 读不到时长就按每帧 100ms 估算
            dur_s = total_ms / 1000.0
            info.update({
                "width": width,
                "height": height,
                "frames": n_frames,
                "duration_s": round(dur_s, 2),
                "fps": round(n_frames / dur_s, 2) if dur_s > 0 else 0.0,
            })
    except Exception:  # noqa: BLE001 —— 探测失败不阻断流程
        pass
    return info


def _rel(path) -> str:
    """转成相对当前工作目录的路径（便于 manifest 可读/可迁移）。"""
    try:
        return os.path.relpath(str(path))
    except ValueError:
        return str(path)


def _try(fn, src: Path, dst: Path, kind: str) -> dict:
    """执行单个转换并统一生成 manifest 条目，失败不中断批量处理。"""
    entry = {"source": _rel(src), "output": None, "type": kind, "status": "ok"}
    try:
        fn()
        entry["output"] = _rel(dst)
        entry.update(gif_info(str(dst)))
        logger.info("[OK] %s -> %s", src.name, dst.name)
    except Exception as exc:  # noqa: BLE001
        entry["status"] = "error"
        entry["error"] = str(exc)
        logger.error("[失败] %s：%s", src.name, exc)
    return entry


def run(cfg: dict) -> list[dict]:
    """主流程：扫描 → 分类 → 逐类转换 → 返回 manifest 条目列表。"""
    input_dir = Path(cfg["input_dir"])
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")

    ffmpeg = resolve_ffmpeg((cfg.get("advanced") or {}).get("ffmpeg_path", ""))
    logger.info("使用 FFmpeg：%s", ffmpeg)

    files = scan(input_dir)
    sequences, singles = group_image_sequences(files["images"])
    logger.info(
        "扫描结果：GIF %d 个、视频 %d 个、图片序列 %d 组、单张图片 %d 个、跳过 %d 个",
        len(files["gifs"]), len(files["videos"]),
        len(sequences), len(singles), len(files["skipped"]),
    )

    results: list[dict] = []

    # 1) 视频 → GIF（取前 N 秒高光片段）
    for src in files["videos"]:
        dst = unique_output_name(output_dir, src.stem)
        results.append(_try(
            lambda s=src, d=dst: convert_video_to_gif(ffmpeg, str(s), str(d), cfg),
            src, dst, "video",
        ))

    # 2) 已有 GIF → 优化
    for src in files["gifs"]:
        dst = unique_output_name(output_dir, src.stem)
        results.append(_try(
            lambda s=src, d=dst: optimize_gif(ffmpeg, str(s), str(d), cfg),
            src, dst, "gif",
        ))

    # 3) 图片序列 → GIF
    for seq in sequences:
        dst = unique_output_name(output_dir, seq["stem"])
        src = seq["frames"][0]
        results.append(_try(
            lambda fr=seq["frames"], d=dst: convert_sequence_to_gif(ffmpeg, list(fr), str(d), cfg),
            src, dst, "sequence",
        ))

    # 4) 单张图片 → 静态 GIF
    for src in singles:
        dst = unique_output_name(output_dir, src.stem)
        results.append(_try(
            lambda s=src, d=dst: convert_single_image(str(s), str(d)),
            src, dst, "image",
        ))

    return results


def is_animated(path: str | Path) -> bool:
    """判断图片/GIF 是否含多帧（如动图 webp / 动画 gif）。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return bool(getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) > 1)
    except Exception:  # noqa: BLE001
        return False


def convert_file(src: str | Path, cfg: dict, output_dir: str | Path | None = None) -> dict:
    """转换单个文件为 GIF（供其他模块按文件粒度调用）。

    参数:
        src        源文件路径（视频 / 动图 / 静态图片）
        cfg        完整配置 dict（含 video/gif/palette/postprocess/advanced 段）
        output_dir 输出目录；默认取 cfg["output_dir"]

    返回:
        {"source", "output", "size_kb", "fps", "width", "height", "frames", ...}
    """
    src = Path(src)
    out_dir = Path(output_dir) if output_dir else Path(cfg.get("output_dir") or ".")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 浅拷贝配置并把输出目录固定到 out_dir（避免 optimizer 的临时目录落到别处）
    cfg = dict(cfg)
    cfg["output_dir"] = str(out_dir)

    ffmpeg = resolve_ffmpeg((cfg.get("advanced") or {}).get("ffmpeg_path", ""))
    ext = src.suffix.lower()

    if ext == GIF_EXT:
        # 已有 GIF → 统一规格优化
        dst = unique_output_name(out_dir, src.stem)
        optimize_gif(ffmpeg, str(src), str(dst), cfg)
    elif ext in VIDEO_EXTS or is_animated(src):
        # 视频、以及动图（webp 动图 / APNG）都走 FFmpeg 视频管线（保留动画帧）
        dst = unique_output_name(out_dir, src.stem)
        convert_video_to_gif(ffmpeg, str(src), str(dst), cfg)
    elif ext in IMAGE_EXTS:
        # 静态图片 → 单帧 GIF
        dst = unique_output_name(out_dir, src.stem)
        convert_single_image(str(src), str(dst))
    else:
        raise ValueError(f"不支持的文件类型：{ext or src}")

    info = gif_info(str(dst))
    info.update({"source": str(src), "output": str(dst), "status": "ok"})
    return info
