cmake_minimum_required(VERSION 3.16)
project(member4_map_matching LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT TARGET sih26168::member3)
  message(FATAL_ERROR "Member 4 requires Member 3 (sih26168::member3).")
endif()

add_library(member4_map_matching
  cpp/src/MapMatchingEngine.cpp
)

add_library(sih26168::member4 ALIAS member4_map_matching)

target_include_directories(member4_map_matching
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include
)

target_link_libraries(member4_map_matching
  PUBLIC
    sih26168::member3
)

if(MSVC)
  target_compile_options(member4_map_matching PRIVATE /W4)
else()
  target_compile_options(member4_map_matching PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(member4_cpp_tests
  cpp/tests/test_member4.cpp
)
target_link_libraries(member4_cpp_tests PRIVATE sih26168::member4)

add_executable(member4_benchmark
  cpp/tools/benchmark.cpp
)
target_link_libraries(member4_benchmark PRIVATE sih26168::member4)

enable_testing()
add_test(NAME member4_cpp_tests COMMAND member4_cpp_tests)
set_tests_properties(member4_cpp_tests PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(NAME member4_benchmark COMMAND member4_benchmark)
set_tests_properties(member4_benchmark PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
