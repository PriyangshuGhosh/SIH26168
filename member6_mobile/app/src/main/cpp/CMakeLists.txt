cmake_minimum_required(VERSION 3.22)
project(idr_jni LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
add_library(idr_jni SHARED idr_jni.cpp)
target_include_directories(idr_jni PRIVATE ${IDR_ENGINE_INCLUDE} ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../member5_engine/include)
# Prefer a prebuilt libidr_engine.so from the Member 5 Android build.
if(DEFINED IDR_ENGINE_SO)
  target_link_libraries(idr_jni PRIVATE ${IDR_ENGINE_SO})
endif()
