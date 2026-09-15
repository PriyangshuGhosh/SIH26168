cmake_minimum_required(VERSION 3.16)
project(member2_alignment LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

if(POLICY CMP0169)
  cmake_policy(SET CMP0169 OLD)
endif()

find_package(Eigen3 3.3 QUIET NO_MODULE)
if(NOT Eigen3_FOUND)
  message(STATUS "Eigen3 not found via find_package; using FetchContent (3.4.0)")
  FetchContent_Declare(
    eigen
    URL https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  )
  FetchContent_GetProperties(eigen)
  if(NOT eigen_POPULATED)
    FetchContent_Populate(eigen)
  endif()
  add_library(Eigen3::Eigen INTERFACE IMPORTED)
  target_include_directories(Eigen3::Eigen INTERFACE ${eigen_SOURCE_DIR})
endif()

add_library(member2_alignment
  cpp/src/FrameAligner.cpp
)
add_library(sih26168::member2 ALIAS member2_alignment)

target_include_directories(member2_alignment
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include
)

if(TARGET Eigen3::Eigen)
  target_link_libraries(member2_alignment PUBLIC Eigen3::Eigen)
else()
  target_include_directories(member2_alignment PUBLIC ${eigen_SOURCE_DIR})
endif()

if(MSVC)
  target_compile_options(member2_alignment PRIVATE /W4)
else()
  target_compile_options(member2_alignment PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(member2_csv_aligner cpp/tools/csv_aligner.cpp)
target_link_libraries(member2_csv_aligner PRIVATE member2_alignment)

add_executable(member2_benchmark cpp/tools/benchmark.cpp)
target_link_libraries(member2_benchmark PRIVATE member2_alignment)

add_executable(member2_cpp_tests cpp/tests/test_member2.cpp)
target_link_libraries(member2_cpp_tests PRIVATE member2_alignment)

enable_testing()
add_test(NAME member2_cpp_tests COMMAND member2_cpp_tests)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
  add_test(
    NAME member2_python_tests
    COMMAND ${Python3_EXECUTABLE} -m pytest -q ${CMAKE_CURRENT_SOURCE_DIR}/tests/python
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
  set_tests_properties(member2_python_tests PROPERTIES
    ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/python"
  )
endif()
