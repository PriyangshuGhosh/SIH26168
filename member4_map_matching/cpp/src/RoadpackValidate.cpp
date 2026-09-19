#include "member4/roadpack_validate.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

namespace sih26168::member4 {

RoadpackValidation validateRoadpackFile(const std::string& path, std::uint64_t max_bytes) {
    RoadpackValidation v;
    namespace fs = std::filesystem;
    std::error_code ec;
    if (!fs::exists(path, ec) || !fs::is_regular_file(path, ec)) {
        v.error = "roadpack missing or not a file";
        return v;
    }
    const auto sz = fs::file_size(path, ec);
    if (ec) {
        v.error = "unable to stat roadpack";
        return v;
    }
    v.bytes = static_cast<std::uint64_t>(sz);
    if (v.bytes == 0 || v.bytes > max_bytes) {
        v.error = "roadpack size rejected";
        return v;
    }

    std::ifstream in(path);
    if (!in) {
        v.error = "failed to open roadpack";
        return v;
    }
    std::string line;
    if (!std::getline(in, line) || line != "SIH26168_ROADPACK_V1") {
        v.error = "invalid roadpack header";
        return v;
    }
    v.schema = "SIH26168_ROADPACK_V1";

    bool have_bounds = false;
    auto touch = [&](double lat, double lon) {
        if (!std::isfinite(lat) || !std::isfinite(lon) || lat < -90.0 || lat > 90.0 ||
            lon < -180.0 || lon > 180.0) {
            return false;
        }
        if (!have_bounds) {
            v.min_lat = v.max_lat = lat;
            v.min_lon = v.max_lon = lon;
            have_bounds = true;
        } else {
            v.min_lat = std::min(v.min_lat, lat);
            v.max_lat = std::max(v.max_lat, lat);
            v.min_lon = std::min(v.min_lon, lon);
            v.max_lon = std::max(v.max_lon, lon);
        }
        return true;
    };

    while (std::getline(in, line)) {
        if (line.empty()) {
            continue;
        }
        std::istringstream ss(line);
        std::string tag;
        ss >> tag;
        if (tag == "NODE") {
            int id = 0;
            double lat = 0, lon = 0;
            ss >> id >> lat >> lon;
            if (!touch(lat, lon)) {
                v.error = "non-finite or out-of-range node";
                return v;
            }
            ++v.node_count;
        } else if (tag == "SEG") {
            ++v.edge_count;
        } else if (tag == "PT") {
            double lat = 0, lon = 0;
            ss >> lat >> lon;
            if (!touch(lat, lon)) {
                v.error = "non-finite or out-of-range geometry";
                return v;
            }
        }
    }
    if (v.edge_count <= 0 || v.node_count <= 0 || !have_bounds) {
        v.error = "roadpack failed graph sanity (nodes/edges/bounds)";
        return v;
    }
    v.ok = true;
    return v;
}

}  // namespace sih26168::member4
