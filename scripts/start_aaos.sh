#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
export ANDROID_SDK_ROOT="$SDK_ROOT"
export ANDROID_AVD_HOME="$PROJECT_DIR/.avd"

if [[ ! -f "$ANDROID_AVD_HOME/cockpit_aaos.ini" ]]; then
  echo "Run bash scripts/setup_aaos.sh first" >&2
  exit 1
fi

ACCEL=on
if [[ ! -r /dev/kvm ]]; then
  ACCEL=off
  echo "KVM unavailable; first boot can take several minutes." >&2
fi

exec "$SDK_ROOT/emulator/emulator" -avd cockpit_aaos \
  -no-window -no-audio -gpu swiftshader_indirect -accel "$ACCEL" -port 5556
