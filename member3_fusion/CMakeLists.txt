cmake_minimum_required(VERSION 3.16)
project(member3_fusion LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT TARGET sih26168::member2)
  message(FATAL_ERROR "Member 3 requires Member 2 (sih26168::member2).")
endif()

add_library(member3_fusion
  src/EKFFusionEngine.cpp
)

add_library(sih26168::member3 ALIAS member3_fusion)
set_target_properties(member3_fusion PROPERTIES POSITION_INDEPENDENT_CODE ON)

target_include_directories(member3_fusion
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(member3_fusion
  PUBLIC
    sih26168::member2
)

if(MSVC)
  target_compile_options(member3_fusion PRIVATE /W4)
else()
  target_compile_options(member3_fusion PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(member3_cpp_tests
  tests/test_member3.cpp
)

target_link_libraries(member3_cpp_tests
  PRIVATE
    sih26168::member3
)

enable_testing()

add_test(
  NAME member3_cpp_tests
  COMMAND member3_cpp_tests
)