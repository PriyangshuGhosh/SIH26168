cmake_minimum_required(VERSION 3.16)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(sih26168_v2x LANGUAGES CXX)
  set(CMAKE_CXX_STANDARD 20)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)
  option(SIH26168_BUILD_HOST_TOOLS "Build host tests, demos, and benchmarks" ON)
  enable_testing()
endif()

add_library(sih26168_v2x
  src/frames.cpp
  src/timestamp.cpp
  src/validation.cpp
  src/security.cpp
  src/transport.cpp
  src/measurement.cpp
  src/core.cpp
)
add_library(sih26168::v2x ALIAS sih26168_v2x)
set_target_properties(sih26168_v2x PROPERTIES POSITION_INDEPENDENT_CODE ON)

target_include_directories(sih26168_v2x
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

if(MSVC)
  target_compile_options(sih26168_v2x PRIVATE /W4)
else()
  target_compile_options(sih26168_v2x PRIVATE -Wall -Wextra -Wpedantic)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS sih26168_v2x EXPORT sih26168_v2xTargets
        ARCHIVE DESTINATION lib LIBRARY DESTINATION lib)
install(DIRECTORY include/ DESTINATION include)
install(EXPORT sih26168_v2xTargets
        FILE sih26168_v2xTargets.cmake
        NAMESPACE sih26168::
        DESTINATION lib/cmake/sih26168_v2x)
configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/sih26168_v2xConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/sih26168_v2xConfig.cmake
  @ONLY
)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/sih26168_v2xConfig.cmake
        DESTINATION lib/cmake/sih26168_v2x)

if(NOT DEFINED SIH26168_BUILD_HOST_TOOLS)
  set(SIH26168_BUILD_HOST_TOOLS ON)
endif()
if(SIH26168_BUILD_HOST_TOOLS)
  add_executable(sih26168_v2x_tests tests/test_v2x.cpp)
  target_link_libraries(sih26168_v2x_tests PRIVATE sih26168::v2x)
  if(MSVC)
    target_compile_options(sih26168_v2x_tests PRIVATE /UNDEBUG)
  else()
    target_compile_options(sih26168_v2x_tests PRIVATE -UNDEBUG)
  endif()
  add_test(NAME sih26168_v2x_cpp_tests COMMAND sih26168_v2x_tests)

  add_executable(sih26168_v2x_benchmark tools/benchmark.cpp)
  target_link_libraries(sih26168_v2x_benchmark PRIVATE sih26168::v2x)

  add_executable(sih26168_v2x_example examples/example_core.cpp)
  target_link_libraries(sih26168_v2x_example PRIVATE sih26168::v2x)

  find_package(Python3 COMPONENTS Interpreter QUIET)
  if(Python3_Interpreter_FOUND)
    add_test(
      NAME sih26168_v2x_python_tests
      COMMAND ${Python3_EXECUTABLE} -m pytest -q ${CMAKE_CURRENT_SOURCE_DIR}/tests/python
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    )
    set_tests_properties(sih26168_v2x_python_tests PROPERTIES
      ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/python"
    )
  endif()
endif()
