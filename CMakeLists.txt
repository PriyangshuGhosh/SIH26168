cmake_minimum_required(VERSION 3.16)
project(SIH26168 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(SIH26168_BUILD_MEMBER2 "Build Member 2 frame alignment" ON)
option(SIH26168_BUILD_MEMBER3 "Build Member 3 sensor fusion" ON)
option(SIH26168_BUILD_MEMBER5 "Build Member 5 native IDR engine" ON)

option(SIH26168_BUILD_HOST_TOOLS "Build host tests, demos, and benchmarks" ON)
if(ANDROID)
  set(SIH26168_BUILD_HOST_TOOLS OFF)
endif()

enable_testing()

if(SIH26168_BUILD_MEMBER2)
  add_subdirectory(member2_alignment)
endif()

if(SIH26168_BUILD_MEMBER3)
  if(NOT SIH26168_BUILD_MEMBER2)
    message(FATAL_ERROR "Member 3 requires Member 2 (set SIH26168_BUILD_MEMBER2=ON)")
  endif()
  add_subdirectory(member3_fusion)
endif()

option(SIH26168_BUILD_MEMBER4 "Build Member 4 offline map matching" ON)
if(SIH26168_BUILD_MEMBER4)
  add_subdirectory(member4_map_matching)
endif()

if(SIH26168_BUILD_MEMBER5)
  if(NOT SIH26168_BUILD_MEMBER2)
    message(FATAL_ERROR "Member 5 requires Member 2 (set SIH26168_BUILD_MEMBER2=ON)")
  endif()
  add_subdirectory(member5_engine)
endif()
