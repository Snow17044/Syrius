# Bibliothèque native de génération d'images (voir syrius_sd.cpp). Construite par build.sh.
cmake_minimum_required(VERSION 3.10)
project(syrius_sd CXX)
set(CMAKE_CXX_STANDARD 17)

set(MNN_SRC "" CACHE PATH "Sources MNN (version épinglée)")
set(MNN_LIB "" CACHE FILEPATH "libMNN compilée")
set(SD ${MNN_SRC}/transformers/diffusion/engine)

set(SRCS syrius_sd.cpp ${SD}/src/stable_diffusion.cpp ${SD}/src/scheduler.cpp ${SD}/src/tokenizer.cpp)
if (ANDROID)
    add_library(syrius_sd SHARED ${SRCS})
    target_link_libraries(syrius_sd ${MNN_LIB} log)
    target_link_options(syrius_sd PRIVATE "-Wl,-z,max-page-size=16384")
else()
    add_executable(syrius_sd ${SRCS})
    target_link_libraries(syrius_sd ${MNN_LIB} pthread)
endif()
target_include_directories(syrius_sd PRIVATE
    ${MNN_SRC}/include ${MNN_SRC}/source ${MNN_SRC}/3rd_party ${MNN_SRC}/tools/cv/include ${SD}/include ${SD}/src)
target_compile_options(syrius_sd PRIVATE -O3 -fvisibility=hidden)
