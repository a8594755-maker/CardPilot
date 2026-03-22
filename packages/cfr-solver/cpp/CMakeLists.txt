cmake_minimum_required(VERSION 3.16)
project(ez_cfr CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(EZ_CFR_BUILD_NATIVE "Build native C++ targets (library + executable)" ON)
option(EZ_CFR_ENABLE_ORT "Enable ONNX Runtime C++ integration for native targets" OFF)
option(EZ_CFR_ENABLE_CUDA "Try linking CUDA runtime for native targets" ON)

set(EZ_CFR_CORE_SOURCES
    src/array_store.cpp
    src/hand_eval.cpp
    src/combo_mapping.cpp
    src/terminal_ev.cpp
    src/cfr_traverse.cpp
    src/chance_nodes.cpp
    src/full_game_solver.cpp
    src/single_street.cpp
    src/street_solver.cpp
    src/nn_evaluator.cpp
)

set(EZ_CFR_WASM_SOURCES
    ${EZ_CFR_CORE_SOURCES}
    src/bindings.cpp
)

if(EMSCRIPTEN)
    add_executable(cfr_core ${EZ_CFR_WASM_SOURCES})
    target_include_directories(cfr_core PRIVATE include)
    set_target_properties(cfr_core PROPERTIES SUFFIX ".js")
    target_link_options(cfr_core PRIVATE
        -sMODULARIZE=1
        -sEXPORT_NAME=createCfrModule
        -sALLOW_MEMORY_GROWTH=1
        -sMAXIMUM_MEMORY=4294967296
        -sINITIAL_MEMORY=268435456
        -sWASM=1
        -sENVIRONMENT=node
        --bind
        -O3
        -fno-fast-math
        "-sEXPORTED_FUNCTIONS=['_malloc','_free']"
        "-sEXPORTED_RUNTIME_METHODS=['HEAPU8','HEAPF32']"
    )
    target_compile_options(cfr_core PRIVATE -O3 -fno-fast-math)
    return()
endif()

if(EZ_CFR_BUILD_NATIVE)
    add_library(ez_cfr_native STATIC ${EZ_CFR_CORE_SOURCES})
    target_include_directories(ez_cfr_native PUBLIC include)
    target_compile_options(ez_cfr_native PRIVATE -O3 -fno-fast-math)

    if(EZ_CFR_ENABLE_ORT)
        set(ONNXRUNTIME_ROOT "$ENV{ONNXRUNTIME_DIR}" CACHE PATH "Path to ONNX Runtime install root")

        find_path(ONNXRUNTIME_INCLUDE_DIR
            NAMES onnxruntime_cxx_api.h
            HINTS
                ${ONNXRUNTIME_ROOT}/include
                ${ONNXRUNTIME_ROOT}/include/onnxruntime
        )
        find_library(ONNXRUNTIME_LIBRARY
            NAMES onnxruntime
            HINTS
                ${ONNXRUNTIME_ROOT}/lib
                ${ONNXRUNTIME_ROOT}/lib64
        )

        if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIBRARY)
            message(FATAL_ERROR
                "EZ_CFR_ENABLE_ORT=ON but ONNX Runtime not found. "
                "Set ONNXRUNTIME_DIR to your ORT SDK root.")
        endif()

        target_compile_definitions(ez_cfr_native PRIVATE EZ_CFR_ENABLE_ORT=1)
        target_include_directories(ez_cfr_native PRIVATE ${ONNXRUNTIME_INCLUDE_DIR})
        target_link_libraries(ez_cfr_native PRIVATE ${ONNXRUNTIME_LIBRARY})

        if(EZ_CFR_ENABLE_CUDA)
            find_package(CUDAToolkit QUIET)
            if(CUDAToolkit_FOUND)
                target_link_libraries(ez_cfr_native PRIVATE CUDA::cudart)
                target_compile_definitions(ez_cfr_native PRIVATE EZ_CFR_ENABLE_CUDA=1)
                message(STATUS "CUDA toolkit found: ${CUDAToolkit_VERSION}")
            else()
                message(WARNING "CUDAToolkit not found; ORT will run without explicit CUDA runtime linkage.")
            endif()
        endif()
    endif()

    add_executable(cfr_solver_native src/native_main.cpp)
    target_link_libraries(cfr_solver_native PRIVATE ez_cfr_native)
    target_compile_options(cfr_solver_native PRIVATE -O3 -fno-fast-math)
endif()

