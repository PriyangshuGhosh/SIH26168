cmake_minimum_required(VERSION 3.16)
project(SIH26168 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(SIH26168_BUILD_MEMBER2 "Build Member 2 frame alignment" ON)
option(SIH26168_BUILD_MEMBER5 "Build Member 5 native IDR engine" ON)

enable_testing()

if(SIH26168_BUILD_MEMBER2)
  add_subdirectory(member2_alignment)
endif()

add_subdirectory(member3_fusion)


if(SIH26168_BUILD_MEMBER5)
  if(NOT SIH26168_BUILD_MEMBER2)
    message(FATAL_ERROR "Member 5 requires Member 2 (set SIH26168_BUILD_MEMBER2=ON)")
  endif()
  add_subdirectory(member5_engine)
endif()
