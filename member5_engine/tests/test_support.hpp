#pragma once

#include <cstdlib>
#include <fstream>
#include <string>

inline std::string sih26168_find_roadpack() {
    if (const char* env = std::getenv("SIH26168_ROADPACK")) {
        if (env[0] != '\0') {
            return env;
        }
    }
    const char* candidates[] = {
        "member4_map_matching/data/synthetic_grid.roadpack",
        "../member4_map_matching/data/synthetic_grid.roadpack",
        "../../member4_map_matching/data/synthetic_grid.roadpack",
    };
    for (const char* p : candidates) {
        std::ifstream in(p, std::ios::binary);
        if (in.good()) {
            return p;
        }
    }
    return "member4_map_matching/data/synthetic_grid.roadpack";
}
