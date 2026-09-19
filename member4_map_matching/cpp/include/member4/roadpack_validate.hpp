#pragma once

#include <cstdint>
#include <string>

namespace sih26168::member4 {

struct RoadpackValidation {
    bool ok{false};
    std::string error;
    std::string schema;
    std::uint64_t bytes{0};
    int node_count{0};
    int edge_count{0};
    double min_lat{0.0};
    double max_lat{0.0};
    double min_lon{0.0};
    double max_lon{0.0};
};

/* Untrusted-input checks. Does not execute the file. No network. */
RoadpackValidation validateRoadpackFile(const std::string& path,
                                        std::uint64_t max_bytes = 64ull * 1024ull * 1024ull);

}  // namespace sih26168::member4
