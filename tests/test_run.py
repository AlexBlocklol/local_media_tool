# -*- coding: utf-8 -*-
"""test_run.py —— 端到端测试：对 sample/ 素材跑一遍完整转换，校验输出。

前置条件：sample/ 已存在素材（可运行 tests/make_samples.py 生成）。
运行：python tests/test_run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as main_mod  # noqa: E402


def main() -> int:
    sample = ROOT / "sample"
    out = ROOT / "output"

    if not (sample / "video_demo.mp4").exists() or not (sample / "emoji_demo.gif").exists():
        print("sample/ 缺少素材，请先运行：python tests/make_samples.py")
        return 2

    print(f"输入目录：{sample}")
    print(f"输出目录：{out}")
    rc = main_mod.main(["--input", str(sample), "--output", str(out)])

    # ---- 断言 ----
    errors = []
    for expect in ("video_demo.gif", "emoji_demo.gif", "seq.gif", "single.gif"):
        if not (out / expect).exists():
            errors.append(f"缺少输出：{expect}")
    if not (out / "manifest.json").exists():
        errors.append("缺少 manifest.json")

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    print(f"\nmanifest 摘要：total={manifest['total']} ok={manifest['ok']} failed={manifest['failed']}")

    if rc != 0:
        errors.append(f"CLI 返回非零退出码：{rc}")
    if manifest["ok"] < 4:
        errors.append(f"成功数不足（期望 >=4，实际 {manifest['ok']}）")

    if errors:
        print("\n❌ 测试失败：")
        for e in errors:
            print("  -", e)
        return 1
    print("\n✅ 全部测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
