# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.22.1-g37088a8)

# We name the project and the target for the ExternalProject_Add() call
# to something that will highlight to the user what we are working on if
# something goes wrong and an error message is produced.

project(eigen-populate NONE)



include(ExternalProject)
ExternalProject_Add(eigen-populate
                     "UPDATE_DISCONNECTED" "False" "URL" "https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz"
                    SOURCE_DIR          "/workspace/member6_mobile/app/.cxx/Debug/3r2k3e4g/arm64-v8a/_deps/eigen-src"
                    BINARY_DIR          "/workspace/member6_mobile/app/.cxx/Debug/3r2k3e4g/arm64-v8a/_deps/eigen-build"
                    CONFIGURE_COMMAND   ""
                    BUILD_COMMAND       ""
                    INSTALL_COMMAND     ""
                    TEST_COMMAND        ""
                    USES_TERMINAL_DOWNLOAD  YES
                    USES_TERMINAL_UPDATE    YES
)


