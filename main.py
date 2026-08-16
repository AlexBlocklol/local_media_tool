# -*- coding: utf-8 -*-
"""main.py —— 命令行入口。

用法示例：
    python main.py                                   # 用 config.yaml 默认配置
    python main.py --input ./sample --output ./output   # 覆盖输入/输出目录
    python main.py --config my_config.yaml --verbose # 指定配置文件并打印 FFmpeg 命令
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml

from converter import run

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"


def load_config(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _ensure_sections(cfg: dict) -> dict:
    for key in ("video", "gif", "palette", "postprocess", "advanced"):
        cfg.setdefault(key, {})
    return cfg


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="本地媒体资源转码与整理工具（只处理本地素材）"
    )
    p.add_argument("--input", help="输入目录（覆盖 config.yaml 的 input_dir）")
    p.add_argument("--output", help="输出目录（覆盖 config.yaml 的 output_dir）")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="配置文件路径")
    p.add_argument("--fps", type=float, help="覆盖输出帧率")
    p.add_argument("--width", type=int, help="覆盖输出宽度（px）")
    p.add_argument("--duration", type=float, help="覆盖视频截取时长（秒）")
    p.add_argument("--max-size-kb", type=int, help="覆盖 GIF 体积上限（KB）")
    p.add_argument("--verbose", action="store_true", help="打印每条 FFmpeg 命令")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = _ensure_sections(load_config(args.config))

    # 命令行参数优先级高于配置文件
    if args.input:
        cfg["input_dir"] = args.input
    if args.output:
        cfg["output_dir"] = args.output
    if args.fps is not None:
        cfg["video"]["fps"] = args.fps
        cfg["gif"]["fps"] = args.fps
    if args.width is not None:
        cfg["video"]["width"] = args.width
        cfg["gif"]["max_width"] = args.width
    if args.duration is not None:
        cfg["video"]["duration"] = args.duration
    if args.max_size_kb is not None:
        cfg["gif"]["max_size_kb"] = args.max_size_kb
    if args.verbose:
        cfg["advanced"]["verbose"] = True

    logging.basicConfig(
        level=logging.DEBUG if cfg["advanced"].get("verbose") else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    results = run(cfg)

    # 生成 manifest.json：源文件 → 输出文件 → 尺寸/帧率/体积 映射
    output_dir = Path(cfg["output_dir"])
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "input_dir": cfg["input_dir"],
        "output_dir": cfg["output_dir"],
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "items": results,
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # 控制台摘要
    print()
    print(f"处理完成：{manifest['ok']} 成功 / {manifest['failed']} 失败")
    print(f"输出目录：{output_dir}")
    print(f"清单文件：{manifest_path}")
    for r in results:
        if r["status"] == "ok":
            size = r.get("size_kb", "-")
            dims = f"{r.get('width')}x{r.get('height')}" if r.get("width") else "-"
            print(f"  ✓ {r['output']}  ({dims}, {r.get('frames', '-')}帧, {size}KB)")
        else:
            print(f"  ✗ {r['source']}  {r.get('error')}")
    return 0 if manifest["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
