#!/usr/bin/env bash
# Construit la génération d'images hors ligne (MNN + syrius_sd).
#   ./build.sh android <dossier_sortie>   → libMNN.so + libsyrius_sd.so (arm64-v8a)
#   ./build.sh linux <dossier_sortie>     → programme de test syrius_sd (CI)
# Sécurité : MNN est récupéré à un commit précis (étiquette 3.5.0) et vérifié avant compilation.
set -euo pipefail
MODE="$1"; OUT="$(realpath -m "$2")"
MNN_TAG="3.5.0"
MNN_COMMIT="c35f14f3ab5cb65094863b9a0e888370b027a670"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$(mktemp -d)}"
mkdir -p "$OUT"

if [ ! -d "$WORK/MNN/.git" ]; then
  git clone -q --depth 1 --branch "$MNN_TAG" https://github.com/alibaba/MNN.git "$WORK/MNN"
fi
GOT="$(git -C "$WORK/MNN" rev-parse HEAD)"
if [ "$GOT" != "$MNN_COMMIT" ]; then
  echo "MNN : commit inattendu ($GOT) — arrêt par sécurité" >&2; exit 1
fi

MNN_FLAGS=(-DCMAKE_BUILD_TYPE=Release -DMNN_BUILD_SHARED_LIBS=ON -DMNN_SEP_BUILD=OFF
  -DMNN_BUILD_OPENCV=ON -DMNN_IMGCODECS=ON -DMNN_LOW_MEMORY=ON -DMNN_SUPPORT_TRANSFORMER_FUSE=ON
  -DMNN_BUILD_TOOLS=OFF -DMNN_BUILD_DEMO=OFF -DMNN_BUILD_TEST=OFF -DMNN_BUILD_BENCHMARK=OFF
  -DMNN_BUILD_TRAIN=OFF -DMNN_BUILD_CONVERTER=OFF -DMNN_BUILD_LLM=OFF -DMNN_BUILD_DIFFUSION=OFF)

if [ "$MODE" = "android" ]; then
  : "${ANDROID_NDK:?ANDROID_NDK manquant}"
  TC=(-DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake"
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-26 -DANDROID_STL=c++_static)
  cmake -S "$WORK/MNN" -B "$WORK/mnn-build" "${TC[@]}" "${MNN_FLAGS[@]}" -DMNN_ARM82=ON -DMNN_USE_LOGCAT=ON \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-z,max-page-size=16384" > /dev/null
  cmake --build "$WORK/mnn-build" -j"$(nproc)" --target MNN > /dev/null
  cmake -S "$HERE" -B "$WORK/sd-build" "${TC[@]}" -DCMAKE_BUILD_TYPE=Release \
    -DMNN_SRC="$WORK/MNN" -DMNN_LIB="$WORK/mnn-build/libMNN.so" > /dev/null
  cmake --build "$WORK/sd-build" -j"$(nproc)" > /dev/null
  cp "$WORK/mnn-build/libMNN.so" "$WORK/sd-build/libsyrius_sd.so" "$OUT/"
  "$ANDROID_NDK"/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip --strip-unneeded "$OUT"/*.so
else
  cmake -S "$WORK/MNN" -B "$WORK/mnn-build" "${MNN_FLAGS[@]}" -DMNN_AVX512=OFF > /dev/null
  cmake --build "$WORK/mnn-build" -j"$(nproc)" --target MNN > /dev/null
  cmake -S "$HERE" -B "$WORK/sd-build" -DCMAKE_BUILD_TYPE=Release \
    -DMNN_SRC="$WORK/MNN" -DMNN_LIB="$WORK/mnn-build/libMNN.so" > /dev/null
  cmake --build "$WORK/sd-build" -j"$(nproc)" > /dev/null
  cp "$WORK/mnn-build/libMNN.so" "$WORK/sd-build/syrius_sd" "$OUT/"
fi
ls -la "$OUT"
