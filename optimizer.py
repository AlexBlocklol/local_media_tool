# -*- coding: utf-8 -*-
"""optimizer.py —— FFmpeg 调色板两步法 + 体积优化

本模块封装所有 FFmpeg 调用，是整个工具的画质核心。

为什么用"两步法"而不是一条命令直接转 GIF？
  直接 `ffmpeg -i in.mp4 out.gif` 会使用固定的 256 色调色板，渐变、
  肤色等区域容易出现明显色带；两步法先针对**当前素材**生成一张专属
  调色板（palettegen），再按这张调色板抖动合成（paletteuse），色彩
  还原度与过渡平滑度都明显更好。

关键 FFmpeg 参数说明：
  * fps=12          —— 限制输出帧率。表情包 10~15fps 观感足够且体积小。
  * scale=480:-1    —— 宽固定 480、高按比例（-1），flags=lanczos 是高质量
                      缩放算法，缩小图片时边缘更清晰。
  * palettegen      —— 从（过滤后的）帧序列统计出最优的 256 色。
  * paletteuse=dither—— 用抖动算法把 24bit 颜色映射回 256 色，减轻色带。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid

logger = logging.getLogger("dygif.optimizer")

# 中文/日文/韩文等字符范围，用于判断是否需要 CJK 字体
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")

# 常见字体路径（Windows / macOS / Linux），按优先级排列
_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",                       # 微软雅黑（Windows）
    "C:/Windows/Fonts/msyhbd.ttc",                     # 微软雅黑粗体
    "C:/Windows/Fonts/simhei.ttf",                     # 黑体
    "C:/Windows/Fonts/simsun.ttc",                     # 宋体
    "/System/Library/Fonts/PingFang.ttc",              # macOS
    "/System/Library/Fonts/STHeiti Light.ttc",         # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # 文泉驿微米黑
]
_LATIN_FONTS = [
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def resolve_ffmpeg(ffmpeg_path: str = "") -> str:
    """按优先级返回可用的 FFmpeg 可执行文件路径。

    1. 配置中显式指定的路径；
    2. 系统 PATH 里的 ffmpeg；
    3. imageio-ffmpeg 自带的静态编译版（免手动安装 FFmpeg）。
    """
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        return ffmpeg_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "未找到 FFmpeg：请安装 FFmpeg 并加入 PATH，或执行 `pip install imageio-ffmpeg`。"
        ) from exc


# --------------------------------------------------------------------------
# 过滤器（filter）链构建
# --------------------------------------------------------------------------

def _esc_path(path: str) -> str:
    """转义 FFmpeg filtergraph 中的路径参数。

    实测 Windows 盘符（如 C:）里的冒号会被当作过滤器参数分隔符，
    必须：1) 反斜杠转正斜杠；2) 冒号加 ``\\`` 前缀；3) 整体用单引号包裹。
    """
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    return f"'{p}'"


def _detect_font(prefer_cjk: bool) -> str | None:
    """自动探测可用字体，找不到返回 None（drawtext 用默认字体，中文可能缺字）。"""
    candidates = (_CJK_FONTS + _LATIN_FONTS) if prefer_cjk else (_LATIN_FONTS + _CJK_FONTS)
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _write_text(tmpdir: str, text: str, name: str) -> str:
    """把文字写入 UTF-8 临时文件，供 drawtext 的 textfile= 读取。

    用 textfile 而不是 text=，是为了彻底避开冒号/引号/百分号等转义问题。
    """
    path = os.path.join(tmpdir, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _drawtext_filters(post: dict, tmpdir: str) -> list[str]:
    """根据 postprocess 配置生成 drawtext 过滤器片段列表。"""
    top = (post.get("top_text") or "").strip()
    bottom = (post.get("bottom_text") or "").strip()
    watermark = (post.get("watermark") or "").strip()
    if not (top or bottom or watermark):
        return []

    font_size = int(post.get("font_size") or 22)
    font_color = post.get("font_color") or "white"
    need_cjk = bool(_CJK_RE.search(top + bottom + watermark))
    font_path = post.get("font_path") or _detect_font(need_cjk)
    font_arg = f":fontfile={_esc_path(font_path)}" if font_path else ""

    filters = []
    if top:
        tf = _write_text(tmpdir, top, "top")
        filters.append(
            f"drawtext=textfile={_esc_path(tf)}{font_arg}:fontsize={font_size}"
            f":fontcolor={font_color}:x=(w-text_w)/2:y=10"
        )
    if bottom:
        tf = _write_text(tmpdir, bottom, "bottom")
        filters.append(
            f"drawtext=textfile={_esc_path(tf)}{font_arg}:fontsize={font_size}"
            f":fontcolor={font_color}:x=(w-text_w)/2:y=h-text_h-10"
        )
    if watermark:
        tf = _write_text(tmpdir, watermark, "wm")
        filters.append(
            f"drawtext=textfile={_esc_path(tf)}{font_arg}:fontsize={font_size}"
            f":fontcolor={font_color}:alpha=0.85:x=w-text_w-10:y=h-text_h-10"
        )
    return filters


def _build_filter_chain(width: int, fps: float, speed: float, post: dict, tmpdir: str) -> str:
    """按固定顺序拼出视频过滤器链：crop → scale → fps → setpts → drawtext。"""
    parts = []
    crop = (post.get("crop") or "").strip()
    if crop:
        parts.append(f"crop={crop}")
    if width and width > 0:
        # 宽固定、高按比例；lanczos 缩放质量高
        parts.append(f"scale={width}:-1:flags=lanczos")
    if fps and fps > 0:
        parts.append(f"fps={fps}")
    if speed and abs(float(speed) - 1.0) > 1e-6:
        # setpts 缩放时间戳：加速则把时间戳压缩，减速则拉长
        parts.append(f"setpts={1.0 / float(speed):.6f}*PTS")
    parts.extend(_drawtext_filters(post, tmpdir))
    return ",".join(parts)


def _build_scale_fps_chain(width: int, fps: float) -> str:
    """体积优化用的精简链：只缩放+限帧率（不重复叠加文字/裁剪/变速）。"""
    parts = []
    if width and width > 0:
        parts.append(f"scale={width}:-1:flags=lanczos")
    if fps and fps > 0:
        parts.append(f"fps={fps}")
    return ",".join(parts)


def _make_tmpdir(cfg: dict) -> str:
    """创建临时目录。默认落在输出目录下（避免系统临时目录被沙箱/权限限制）。

    注意：这里刻意用 os.makedirs + uuid 而不是 tempfile.mkdtemp，
    因为部分受限环境（如本机沙箱）会拒绝对 mkdtemp 创建的目录进行写入。
    """
    base = (cfg.get("advanced") or {}).get("tmp_dir") or cfg.get("output_dir") or "."
    os.makedirs(base, exist_ok=True)
    d = os.path.join(base, f".dygif_tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    os.makedirs(d, exist_ok=False)
    return d


def _run(cmd: list[str], label: str, verbose: bool = False) -> subprocess.CompletedProcess:
    """执行 FFmpeg 命令，失败时抛出带 stderr 的错误。"""
    if verbose:
        logger.info(">> %s", " ".join(cmd))
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{label}：{proc.stderr.strip()[:800]}")
    return proc


def _two_step(
    ffmpeg: str,
    in_opts: list[str],
    in_path: str,
    palette_path: str,
    out_path: str,
    chain: str,
    cfg: dict,
    duration: float = 0.0,
) -> None:
    """调色板两步法：palettegen 生成调色板 → paletteuse 合成 GIF。"""
    pal = cfg.get("palette") or {}
    stats_mode = pal.get("stats_mode") or "full"
    dither = pal.get("dither") or "floyd_steinberg"
    loop = int((cfg.get("gif") or {}).get("loop", 0) or 0)
    verbose = bool((cfg.get("advanced") or {}).get("verbose"))

    # ---- 第一步：生成专属调色板 ----
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "info" if verbose else "error"]
    if duration and duration > 0:
        cmd += ["-t", f"{duration}"]  # 只读前 N 秒，保证调色板与最终片段一致
    cmd += in_opts + ["-i", in_path]
    vf = (chain + "," if chain else "") + f"palettegen=stats_mode={stats_mode}"
    cmd += ["-vf", vf, palette_path]
    _run(cmd, "生成调色板失败", verbose)

    # ---- 第二步：抖动合成 GIF ----
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "info" if verbose else "error"]
    if duration and duration > 0:
        cmd += ["-t", f"{duration}"]
    cmd += in_opts + ["-i", in_path, "-i", palette_path]
    if chain:
        fc = f"{chain}[x];[x][1:v]paletteuse=dither={dither}"
    else:
        fc = f"[0:v][1:v]paletteuse=dither={dither}"
    cmd += ["-filter_complex", fc, "-loop", str(loop), out_path]
    _run(cmd, "合成 GIF 失败", verbose)


# --------------------------------------------------------------------------
# 对外转换接口
# --------------------------------------------------------------------------

def convert_video_to_gif(ffmpeg: str, src: str, dst: str, cfg: dict) -> None:
    """视频（.mp4/.webm/...）→ GIF：截取前 N 秒高光片段，调色板两步法合成。"""
    v = cfg.get("video") or {}
    post = cfg.get("postprocess") or {}
    duration = float(v.get("duration", 3.0) or 0.0)
    fps = v.get("fps") or 12
    width = v.get("width") or 480
    speed = float(post.get("speed") or 1.0)

    tmpdir = _make_tmpdir(cfg)
    try:
        chain = _build_filter_chain(int(width), float(fps), speed, post, tmpdir)
        _two_step(ffmpeg, [], src, os.path.join(tmpdir, "pal.png"), dst, chain, cfg, duration)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    enforce_size_limit(ffmpeg, dst, cfg)


def optimize_gif(ffmpeg: str, src: str, dst: str, cfg: dict) -> None:
    """已有 GIF → 统一规格：限宽/限帧率/限时长，用调色板重编码提升一致性。"""
    g = cfg.get("gif") or {}
    post = cfg.get("postprocess") or {}
    duration = float(g.get("max_duration", 5.0) or 0.0)
    fps = g.get("fps") or 12
    width = g.get("max_width") or 480
    speed = float(post.get("speed") or 1.0)

    tmpdir = _make_tmpdir(cfg)
    try:
        chain = _build_filter_chain(int(width), float(fps), speed, post, tmpdir)
        _two_step(ffmpeg, [], src, os.path.join(tmpdir, "pal.png"), dst, chain, cfg, duration)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    enforce_size_limit(ffmpeg, dst, cfg)


def convert_sequence_to_gif(ffmpeg: str, frames: list[str], dst: str, cfg: dict) -> None:
    """图片序列（img_001.jpg、img_002.jpg…）→ GIF。

    先把所有帧归一化成临时目录下的 frame_%04d.png，再交给 ffmpeg 序列输入，
    这样无论原始文件名是否缺帧、补零宽度是否一致，都能稳定按顺序合成。
    """
    from PIL import Image

    v = cfg.get("video") or {}
    post = cfg.get("postprocess") or {}
    fps = v.get("fps") or 12
    width = v.get("width") or 480
    speed = float(post.get("speed") or 1.0)

    tmpdir = _make_tmpdir(cfg)
    try:
        norm_dir = os.path.join(tmpdir, "frames")
        os.makedirs(norm_dir, exist_ok=True)
        for i, f in enumerate(frames, start=1):
            with Image.open(f) as im:
                im.convert("RGB").save(os.path.join(norm_dir, f"frame_{i:04d}.png"))
        pattern = os.path.join(norm_dir, "frame_%04d.png")
        chain = _build_filter_chain(int(width), float(fps), speed, post, tmpdir)
        # -framerate 指定序列输入帧率；序列通常很短，不截断时长
        _two_step(ffmpeg, ["-framerate", str(fps)], pattern,
                  os.path.join(tmpdir, "pal.png"), dst, chain, cfg, duration=0.0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    enforce_size_limit(ffmpeg, dst, cfg)


def enforce_size_limit(ffmpeg: str, gif_path: str, cfg: dict) -> None:
    """输出 GIF 超过 max_size_kb 时，逐级降低分辨率/帧率重编码，直到达标。"""
    max_kb = int((cfg.get("gif") or {}).get("max_size_kb", 0) or 0)
    if max_kb <= 0:
        return
    width = (cfg.get("gif") or {}).get("max_width") or 480
    fps = (cfg.get("gif") or {}).get("fps") or 12

    tmpdir = _make_tmpdir(cfg)
    try:
        for i in range(6):  # 最多尝试 6 次
            if os.path.getsize(gif_path) <= max_kb * 1024:
                return
            if width and width > 0:
                width = max(int(width * 0.8), 120)  # 每次降宽 20%，下限 120px
            if i >= 2 and fps and fps > 6:
                fps = max(int(fps) - 2, 6)          # 第 3 次起同时降帧率，下限 6fps
            chain = _build_scale_fps_chain(int(width), float(fps))
            tmp = os.path.join(tmpdir, "reduced.gif")
            _two_step(ffmpeg, [], gif_path, os.path.join(tmpdir, "pal.png"),
                      tmp, chain, cfg, duration=0.0)
            os.replace(tmp, gif_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if os.path.getsize(gif_path) > max_kb * 1024:
        logger.warning("体积仍超过 %dKB，已保留最小可接受版本：%s", max_kb, gif_path)
