#include "member5/MapCatalog.hpp"

#include <cmath>
#include <fstream>
#include <sstream>

namespace sih26168::member5 {
namespace {

std::string readFile(const std::string& path) {
    std::ifstream in(path);
    if (!in) {
        return {};
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string dirnameOf(const std::string& path) {
    const auto slash = path.find_last_of("/\\");
    if (slash == std::string::npos) {
        return ".";
    }
    if (slash == 0) {
        return "/";
    }
    return path.substr(0, slash);
}

bool extractString(const std::string& obj, const char* key, std::string& out) {
    const std::string pat = std::string("\"") + key + "\"";
    auto k = obj.find(pat);
    if (k == std::string::npos) {
        return false;
    }
    auto colon = obj.find(':', k + pat.size());
    if (colon == std::string::npos) {
        return false;
    }
    auto q1 = obj.find('"', colon + 1);
    if (q1 == std::string::npos) {
        return false;
    }
    auto q2 = obj.find('"', q1 + 1);
    if (q2 == std::string::npos) {
        return false;
    }
    out = obj.substr(q1 + 1, q2 - q1 - 1);
    return true;
}

bool extractNumber(const std::string& obj, const char* key, double& out) {
    const std::string pat = std::string("\"") + key + "\"";
    auto k = obj.find(pat);
    if (k == std::string::npos) {
        return false;
    }
    auto colon = obj.find(':', k + pat.size());
    if (colon == std::string::npos) {
        return false;
    }
    std::size_t i = colon + 1;
    while (i < obj.size() && (obj[i] == ' ' || obj[i] == '\t' || obj[i] == '\n')) {
        ++i;
    }
    try {
        std::size_t used = 0;
        out = std::stod(obj.substr(i), &used);
        return used > 0;
    } catch (...) {
        return false;
    }
}

}  // namespace

bool MapCatalog::pointInRegion(const MapRegion& r, double lat, double lon) {
    if (!std::isfinite(lat) || !std::isfinite(lon)) {
        return false;
    }
    return lat >= r.min_lat && lat <= r.max_lat && lon >= r.min_lon && lon <= r.max_lon;
}

bool MapCatalog::loadSingleRoadpack(const std::string& roadpack_path, const std::string& id) {
    last_error_.clear();
    regions_.clear();
    MapRegion r;
    r.id = id.empty() ? "loaded" : id;
    r.roadpack_path = roadpack_path;
    regions_.push_back(r);
    root_ = dirnameOf(roadpack_path);
    return true;
}

void MapCatalog::setBoundsFromGeometry(double min_lat, double max_lat, double min_lon,
                                       double max_lon) {
    if (regions_.empty()) {
        return;
    }
    regions_.back().min_lat = min_lat;
    regions_.back().max_lat = max_lat;
    regions_.back().min_lon = min_lon;
    regions_.back().max_lon = max_lon;
}

const MapRegion* MapCatalog::findCovering(double lat, double lon) const {
    for (const auto& r : regions_) {
        if (pointInRegion(r, lat, lon)) {
            return &r;
        }
    }
    return nullptr;
}

bool MapCatalog::loadManifestFile(const std::string& manifest_path) {
    last_error_.clear();
    regions_.clear();
    const std::string text = readFile(manifest_path);
    if (text.empty()) {
        last_error_ = "failed to read map manifest: " + manifest_path;
        return false;
    }
    root_ = dirnameOf(manifest_path);

    auto arr = text.find("\"regions\"");
    if (arr == std::string::npos) {
        last_error_ = "manifest missing regions array";
        return false;
    }
    auto lb = text.find('[', arr);
    auto rb = text.rfind(']');
    if (lb == std::string::npos || rb == std::string::npos || rb <= lb) {
        last_error_ = "manifest regions array malformed";
        return false;
    }
    const std::string body = text.substr(lb + 1, rb - lb - 1);
    std::size_t pos = 0;
    while (pos < body.size()) {
        auto o1 = body.find('{', pos);
        if (o1 == std::string::npos) {
            break;
        }
        auto o2 = body.find('}', o1);
        if (o2 == std::string::npos) {
            last_error_ = "unterminated region object";
            return false;
        }
        const std::string obj = body.substr(o1, o2 - o1 + 1);
        MapRegion r;
        extractString(obj, "id", r.id);
        extractString(obj, "roadpack", r.roadpack_path);
        extractString(obj, "version", r.version);
        extractString(obj, "coordinate_reference", r.coordinate_reference);
        extractString(obj, "built_at", r.built_at);
        extractNumber(obj, "min_lat", r.min_lat);
        extractNumber(obj, "max_lat", r.max_lat);
        extractNumber(obj, "min_lon", r.min_lon);
        extractNumber(obj, "max_lon", r.max_lon);
        double roads = 0.0;
        if (extractNumber(obj, "road_count", roads)) {
            r.road_count = static_cast<int>(roads);
        }
        if (r.id.empty() || r.roadpack_path.empty()) {
            last_error_ = "region missing id or roadpack";
            return false;
        }
        if (!r.roadpack_path.empty() && r.roadpack_path[0] != '/') {
            r.roadpack_path = root_ + "/" + r.roadpack_path;
        }
        regions_.push_back(r);
        pos = o2 + 1;
    }
    if (regions_.empty()) {
        last_error_ = "manifest contained no regions";
        return false;
    }
    return true;
}

}  // namespace sih26168::member5
