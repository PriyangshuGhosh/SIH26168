#----------------------------------------------------------------
# Generated CMake target import file for configuration "Debug".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "sih26168::sih26168_v2x" for configuration "Debug"
set_property(TARGET sih26168::sih26168_v2x APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)
set_target_properties(sih26168::sih26168_v2x PROPERTIES
  IMPORTED_LINK_INTERFACE_LANGUAGES_DEBUG "CXX"
  IMPORTED_LOCATION_DEBUG "${_IMPORT_PREFIX}/lib/libsih26168_v2x.a"
  )

list(APPEND _IMPORT_CHECK_TARGETS sih26168::sih26168_v2x )
list(APPEND _IMPORT_CHECK_FILES_FOR_sih26168::sih26168_v2x "${_IMPORT_PREFIX}/lib/libsih26168_v2x.a" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
