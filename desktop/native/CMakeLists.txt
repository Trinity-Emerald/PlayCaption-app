cmake_minimum_required(VERSION 3.18)
project(nexcap_remote C CXX)

set(CHIAKI_SOURCE "" CACHE PATH "Path to the pinned chiaki-ng source checkout")
if(NOT EXISTS "${CHIAKI_SOURCE}/lib/CMakeLists.txt")
    message(FATAL_ERROR "Set CHIAKI_SOURCE to the chiaki-ng checkout")
endif()

foreach(option GUI CLI TESTS STEAM_SHORTCUT STEAMDECK_NATIVE SETSU SPEEX FFMPEG_DECODER PI_DECODER)
    set(CHIAKI_ENABLE_${option} OFF CACHE STRING "" FORCE)
endforeach()
set(CHIAKI_LIB_ENABLE_OPUS OFF CACHE BOOL "" FORCE)
find_package(PkgConfig REQUIRED)
add_subdirectory("${CHIAKI_SOURCE}" chiaki EXCLUDE_FROM_ALL)

add_executable(nexcap-remote remote.c)
target_link_libraries(nexcap-remote PRIVATE chiaki-lib)
