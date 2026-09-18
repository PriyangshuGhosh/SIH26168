cmake_minimum_required(VERSION 3.16)
project(member5_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(IDR_WITH_ONNXRUNTIME "Link ONNX Runtime for Member 1 speed_estimator.onnx" OFF)
set(IDR_ONNXRUNTIME_ROOT "" CACHE PATH "ONNX Runtime install prefix (include/ and lib/)")

if(NOT TARGET sih26168::member2)
  message(FATAL_ERROR "Member 5 requires Member 2 (sih26168::member2).")
endif()
if(NOT TARGET sih26168::member3)
  message(FATAL_ERROR "Member 5 requires Member 3 (sih26168::member3).")
endif()
if(NOT TARGET sih26168::member4)
  message(FATAL_ERROR "Member 5 requires Member 4 (sih26168::member4).")
endif()

set(IDR_ENGINE_SOURCES
  src/SpeedEstimator.cpp
  src/Engine.cpp
  src/idr_engine_api.cpp
)

add_library(idr_engine_static STATIC ${IDR_ENGINE_SOURCES})
add_library(sih26168::member5 ALIAS idr_engine_static)
target_compile_definitions(idr_engine_static PUBLIC IDR_ENGINE_STATIC)
target_include_directories(idr_engine_static
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_link_libraries(idr_engine_static PUBLIC
  sih26168::member2
  sih26168::member3
  sih26168::member4
)

if(NOT WIN32)
  find_package(Threads REQUIRED)
  target_link_libraries(idr_engine_static PUBLIC Threads::Threads)
endif()

if(MSVC)
  target_compile_options(idr_engine_static PRIVATE /W4)
else()
  target_compile_options(idr_engine_static PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_library(idr_engine SHARED ${IDR_ENGINE_SOURCES})
target_include_directories(idr_engine
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_compile_definitions(idr_engine PRIVATE IDR_ENGINE_EXPORTS)
target_link_libraries(idr_engine PUBLIC
  sih26168::member2
  sih26168::member3
  sih26168::member4
)
if(NOT WIN32)
  target_link_libraries(idr_engine PUBLIC Threads::Threads)
endif()

set_target_properties(idr_engine PROPERTIES
  OUTPUT_NAME idr_engine
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
)

if(ANDROID)
  set_target_properties(idr_engine PROPERTIES OUTPUT_NAME idr_engine)
endif()

if(IDR_WITH_ONNXRUNTIME)
  set(_ort_inc "")
  set(_ort_lib "onnxruntime")
  if(IDR_ONNXRUNTIME_ROOT)
    set(_ort_inc "${IDR_ONNXRUNTIME_ROOT}/include")
  else()
    find_path(_ort_inc onnxruntime_cxx_api.h
      PATHS
        "${CMAKE_SOURCE_DIR}/.cache/onnxruntime/include"
        /usr/include
        /usr/local/include
      PATH_SUFFIXES onnxruntime
    )
    find_library(_ort_found onnxruntime
      PATHS
        "${CMAKE_SOURCE_DIR}/.cache/onnxruntime/lib"
        /usr/lib
        /usr/local/lib
    )
    if(_ort_found)
      set(_ort_lib "${_ort_found}")
    endif()
  endif()
  if(NOT _ort_inc)
    message(FATAL_ERROR
      "IDR_WITH_ONNXRUNTIME=ON but onnxruntime_cxx_api.h was not found. "
      "Set -DIDR_ONNXRUNTIME_ROOT=/path/to/onnxruntime")
  endif()
  foreach(_tgt idr_engine_static idr_engine)
    target_include_directories(${_tgt} PUBLIC ${_ort_inc})
    if(IDR_ONNXRUNTIME_ROOT)
      if(ANDROID)
        target_link_directories(${_tgt} PUBLIC ${IDR_ONNXRUNTIME_ROOT}/lib/${ANDROID_ABI})
      else()
        target_link_directories(${_tgt} PUBLIC ${IDR_ONNXRUNTIME_ROOT}/lib)
      endif()
    endif()
    target_compile_definitions(${_tgt} PUBLIC IDR_WITH_ONNXRUNTIME)
    target_link_libraries(${_tgt} PUBLIC ${_ort_lib})
  endforeach()
endif()

add_executable(member5_cpp_tests tests/test_member5.cpp)
target_link_libraries(member5_cpp_tests PRIVATE idr_engine_static)
target_include_directories(member5_cpp_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)

add_executable(member5_benchmark tools/benchmark.cpp)
target_link_libraries(member5_benchmark PRIVATE idr_engine_static)
target_include_directories(member5_benchmark PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)

add_executable(member5_demo tools/demo.cpp)
target_link_libraries(member5_demo PRIVATE idr_engine_static)
target_include_directories(member5_demo PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)

add_executable(member5_synthetic_e2e tools/synthetic_e2e.cpp)
target_link_libraries(member5_synthetic_e2e PRIVATE idr_engine_static)
target_include_directories(member5_synthetic_e2e PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests)

enable_testing()
add_test(NAME member5_cpp_tests COMMAND member5_cpp_tests)
set_tests_properties(member5_cpp_tests PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME member5_benchmark COMMAND member5_benchmark)
set_tests_properties(member5_benchmark PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME member5_synthetic_e2e COMMAND member5_synthetic_e2e)
set_tests_properties(member5_synthetic_e2e PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
