#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
AVD_HOME="$PROJECT_DIR/.avd"
IMAGE='system-images;android-35-ext15;android-automotive;x86_64'

if [[ ! -x "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]]; then
  echo "Android SDK command-line tools not found at $SDK_ROOT" >&2
  exit 1
fi

if [[ ! -f "$SDK_ROOT/system-images/android-35-ext15/android-automotive/x86_64/system.img" ]]; then
  "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK_ROOT" "$IMAGE"
fi

mkdir -p "$AVD_HOME"
if [[ ! -f "$AVD_HOME/cockpit_aaos.ini" ]]; then
  printf 'no\n' | ANDROID_AVD_HOME="$AVD_HOME" ANDROID_SDK_ROOT="$SDK_ROOT" \
    "$SDK_ROOT/cmdline-tools/latest/bin/avdmanager" create avd \
    --name cockpit_aaos --package "$IMAGE"
fi

CONFIG="$AVD_HOME/cockpit_aaos.avd/config.ini"
sed -i 's/^hw.lcd.width=.*/hw.lcd.width=1024/' "$CONFIG"
sed -i 's/^hw.lcd.height=.*/hw.lcd.height=768/' "$CONFIG"
sed -i 's/^hw.initialOrientation=.*/hw.initialOrientation=landscape/' "$CONFIG"
sed -i 's/^hw.ramSize=.*/hw.ramSize=2048M/' "$CONFIG"
sed -i 's/^hw.gpu.enabled=.*/hw.gpu.enabled=yes/' "$CONFIG"
sed -i 's/^hw.mainKeys=.*/hw.mainKeys=no/' "$CONFIG"
echo "Android Automotive AVD ready: cockpit_aaos"
