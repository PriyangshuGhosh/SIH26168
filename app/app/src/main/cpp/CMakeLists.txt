cmake_minimum_required(VERSION 3.16)
project(member6_jni)

set(CMAKE_CXX_STANDARD 20)
set(SIH26168_BUILD_HOST_TOOLS OFF CACHE BOOL "Skip host tests on Android" FORCE)
set(SIH26168_BUILD_MEMBER2 ON CACHE BOOL "Build Member 2" FORCE)
set(SIH26168_BUILD_MEMBER5 ON CACHE BOOL "Build Member 5" FORCE)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../../../../../ sih26168_build)

add_library(member6_jni SHARED
    idr_jni.cpp
)

target_link_libraries(member6_jni idr_engine)
target_include_directories(member6_jni PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../member5_engine/include)
