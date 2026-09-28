#!/bin/bash
# macOS runner 上用 swiftc 直编出无签名 IPA (TrollStore 免签安装)
# 产物: MiniMaxStudio.ipa
set -e
cd "$(dirname "$0")"
APP=MiniMaxStudio

SDK=$(xcrun --sdk iphoneos --show-sdk-path)
echo "== swiftc (arm64-apple-ios14.0) =="
xcrun -sdk iphoneos swiftc \
  -sdk "$SDK" \
  -target arm64-apple-ios14.0 \
  -O \
  -framework UIKit -framework WebKit -framework Photos \
  Sources/main.swift Sources/App.swift \
  -o App

echo "== 组装 Payload/$APP.app =="
rm -rf Payload "$APP.ipa"
mkdir -p "Payload/$APP.app"
cp App "Payload/$APP.app/$APP"
cp Resources/Info.plist "Payload/$APP.app/"
cp Resources/index.html    "Payload/$APP.app/"
cp Resources/templates.js  "Payload/$APP.app/"
cp Resources/AppIcon60x60@2x.png "Payload/$APP.app/"
cp Resources/AppIcon60x60@3x.png "Payload/$APP.app/"
printf 'APPL????' > "Payload/$APP.app/PkgInfo"

echo "== 校验 =="
file "Payload/$APP.app/$APP"
plutil -lint "Payload/$APP.app/Info.plist"
[ "$(file -b "Payload/$APP.app/$APP" | grep -c 'arm64')" -ge 1 ] || { echo "FATAL: not an arm64 Mach-O"; exit 1; }

echo "== zip -> $APP.ipa =="
zip -qry "$APP.ipa" Payload
rm -rf Payload App
ls -la "$APP.ipa"
echo "OK -> $APP.ipa"
