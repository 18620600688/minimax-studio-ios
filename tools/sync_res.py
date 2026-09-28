# -*- coding: utf-8 -*-
"""把 Android 工程的界面拷进 iOS Resources/ (单一来源原则: 只改 Android 侧, 再跑本脚本).
用法: python tools/sync_res.py  (build_ipa.sh 在云端跑, 本地准备 Resources 用)"""
import os, shutil, json, re, sys

ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_PROJ= r"D:\_ai_\2026-09-26-minimax-app"
ASSETS  = os.path.join(APP_PROJ, "app", "assets")
RES     = os.path.join(ROOT, "Resources")

def main():
    os.makedirs(RES, exist_ok=True)
    for f in ("index.html", "templates.js"):
        src = os.path.join(ASSETS, f)
        if not os.path.isfile(src):
            sys.exit("缺 " + src + " —— 先在 Android 工程跑 python tools/sync_web.py")
        shutil.copy2(src, os.path.join(RES, f))
        print("copy", src)

    # 同步版本号: index.html 的 APP_VER -> Info.plist
    html = open(os.path.join(RES, "index.html"), encoding="utf-8").read()
    m = re.search(r'var\s+APP_VER\s*=\s*"V(\d+)"', html)
    n = int(m.group(1)) if m else 0
    pl = os.path.join(RES, "Info.plist")
    txt = open(pl, encoding="utf-8").read()
    txt = re.sub(r"<key>CFBundleShortVersionString</key>\s*<string>[^<]*</string>",
                 "<key>CFBundleShortVersionString</key>\n\t<string>1.%d</string>" % n, txt)
    txt = re.sub(r"<key>CFBundleVersion</key>\s*<string>[^<]*</string>",
                 "<key>CFBundleVersion</key>\n\t<string>%d</string>" % n, txt)
    open(pl, "w", encoding="utf-8").write(txt)
    print("Info.plist version -> 1.%d (%d)" % (n, n))

if __name__ == "__main__":
    main()
