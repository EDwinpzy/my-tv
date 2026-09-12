# 词典构建工具（2026-08-29）：编译 AOSP 谷歌拼音 dictbuilder 为 Android 可执行文件，
# 推到模拟器上跑，把扩充后的 rawdict 重建为 dict_pinyin.dat。
# 本文件不参与 app 构建（独立 cmake 工程），用 NDK 工具链手动构建：
#   SDK=C:/Users/63054/Android
#   cmake -G Ninja -B build \
#     -DCMAKE_TOOLCHAIN_FILE=$SDK/ndk/27.0.12077973/build/cmake/android.toolchain.cmake \
#     -DANDROID_ABI=x86_64 -DANDROID_PLATFORM=android-30 \
#     -DCMAKE_MAKE_PROGRAM=$SDK/cmake/3.22.1/bin/ninja.exe
cmake_minimum_required(VERSION 3.22.1)
project(pinyinime_dictbuilder CXX)

set(PY_CPP ../../android/app/src/main/cpp/pinyinime)

add_executable(pinyinime_dictbuilder
        ${PY_CPP}/command/pinyinime_dictbuilder.cpp
        ${PY_CPP}/share/dictbuilder.cpp
        ${PY_CPP}/share/dictlist.cpp
        ${PY_CPP}/share/dicttrie.cpp
        ${PY_CPP}/share/lpicache.cpp
        ${PY_CPP}/share/matrixsearch.cpp
        ${PY_CPP}/share/mystdlib.cpp
        ${PY_CPP}/share/ngram.cpp
        ${PY_CPP}/share/pinyinime.cpp
        ${PY_CPP}/share/searchutility.cpp
        ${PY_CPP}/share/spellingtable.cpp
        ${PY_CPP}/share/spellingtrie.cpp
        ${PY_CPP}/share/splparser.cpp
        ${PY_CPP}/share/userdict.cpp
        ${PY_CPP}/share/utf16char.cpp
        ${PY_CPP}/share/utf16reader.cpp
        ${PY_CPP}/share/sync.cpp
        )

target_include_directories(pinyinime_dictbuilder PRIVATE ${PY_CPP}/include)
target_compile_definitions(pinyinime_dictbuilder PRIVATE ___BUILD_MODEL___)
find_library(log-lib log)
target_link_libraries(pinyinime_dictbuilder ${log-lib})
