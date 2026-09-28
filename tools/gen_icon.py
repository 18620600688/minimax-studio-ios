# -*- coding: utf-8 -*-
"""用 Pillow 纯代码画 App 图标 (1024 -> 180/120), 无素材依赖.
风格: 深蓝紫渐变底 + 白色播放三角 + 黄色进度条点, 贴 MiniMax 生成台气质."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RES  = os.path.join(ROOT, "Resources")

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def draw(size):
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    top, bot = (34, 38, 92), (98, 44, 160)          # 深蓝 -> 紫
    for y in range(size):
        d.line([(0, y), (size, y)], fill=lerp(top, bot, y / size))
    s = size / 1024.0

    # 播放三角 (圆角近似: 大三角 + 同色圆头线帽)
    pts = [(330 * s, 260 * s), (330 * s, 764 * s), (760 * s, 512 * s)]
    d.polygon(pts, fill=(245, 247, 252))
    d.line([pts[0], pts[1]], fill=(245, 247, 252), width=int(52 * s))
    for p in (pts[0], pts[1]):
        r = 26 * s
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(245, 247, 252))

    # 底部进度条: 左黄条 + 右暗槽 (呼应"生成进度")
    bar_y = 810 * s
    d.rounded_rectangle([210 * s, bar_y, 814 * s, bar_y + 26 * s],
                        radius=13 * s, fill=(255, 255, 255, 40))
    d.rounded_rectangle([210 * s, bar_y, 480 * s, bar_y + 26 * s],
                        radius=13 * s, fill=(255, 191, 64))

    # 顶部小圆点 (三个"任务"点)
    for i in range(3):
        cx = (470 + i * 44) * s
        r = 12 * s
        col = (255, 191, 64) if i == 0 else (255, 255, 255, 90)
        d.ellipse([cx - r, 170 * s - r, cx + r, 170 * s + r], fill=col)
    return img

def main():
    big = draw(1024)
    for px, name in ((180, "AppIcon60x60@3x.png"), (120, "AppIcon60x60@2x.png")):
        big.resize((px, px), Image.LANCZOS).save(os.path.join(RES, name))
        print("icon ->", name, px)

if __name__ == "__main__":
    main()
