#include "member4/region_catalog.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>

namespace sih26168::member4 {
namespace {

constexpr double kPi = 3.14159265358979323846;

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

bool extractBool(const std::string& obj, const char* key, bool& out) {
    const std::string pat = std::string("\"") + key + "\"";
    auto k = obj.find(pat);
    if (k == std::string::npos) {
        return false;
    }
    auto colon = obj.find(':', k + pat.size());
    if (colon == std::string::npos) {
        return false;
    }
    const std::string rest = obj.substr(colon + 1);
    const auto t = rest.find_first_not_of(" \t\n");
    if (t == std::string::npos) {
        return false;
    }
    if (rest.compare(t, 4, "true") == 0) {
        out = true;
        return true;
    }
    if (rest.compare(t, 5, "false") == 0) {
        out = false;
        return true;
    }
    return false;
}

double areaDeg2(const MapRegion& r) {
    return std::max(0.0, r.max_lat - r.min_lat) * std::max(0.0, r.max_lon - r.min_lon);
}

}  // namespace

bool RegionCatalog::safeRelativePath(const std::string& relative) {
    if (relative.empty() || relative[0] == '/' || relative[0] == '\\') {
        return false;
    }
    if (relative.find("://") != std::string::npos) {
        return false;
    }
    if (relative.size() >= 2 && relative[1] == ':') {
        return false;
    }
    if (relative.find("../..") != std::string::npos || relative.find("..\\..") != std::string::npos) {
        return false;
    }
    return true;
}

bool RegionCatalog::pointInRegion(const MapRegion& r, double lat, double lon) {
    if (!std::isfinite(lat) || !std::isfinite(lon)) {
        return false;
    }
    return lat >= r.min_lat && lat <= r.max_lat && lon >= r.min_lon && lon <= r.max_lon;
}

double RegionCatalog::signedDistanceToBoundaryM(const MapRegion& r, double lat, double lon) {
    if (!std::isfinite(lat) || !std::isfinite(lon)) {
        return -1.0e300;
    }
    const double dlat_n = (r.max_lat - lat) * 111320.0;
    const double dlat_s = (lat - r.min_lat) * 111320.0;
    const double coslat = std::max(std::cos(lat * kPi / 180.0), 1e-6);
    const double dlon_e = (r.max_lon - lon) * 111320.0 * coslat;
    const double dlon_w = (lon - r.min_lon) * 111320.0 * coslat;
    if (!pointInRegion(r, lat, lon)) {
        return -std::min({std::abs(dlat_n), std::abs(dlat_s), std::abs(dlon_e), std::abs(dlon_w)});
    }
    return std::min({dlat_n, dlat_s, dlon_e, dlon_w});
}

bool RegionCatalog::approachingBoundary(const MapRegion& r, double lat, double lon,
                                        double threshold_m) {
    const double d = signedDistanceToBoundaryM(r, lat, lon);
    return d >= 0.0 && d <= threshold_m;
}

const MapRegion* RegionCatalog::findCovering(double lat, double lon) const {
    const MapRegion* best = nullptr;
    double best_area = 0.0;
    for (const auto& r : regions_) {
        if (!pointInRegion(r, lat, lon)) {
            continue;
        }
        const double a = areaDeg2(r);
        if (best == nullptr || a < best_area) {
            best = &r;
            best_area = a;
        }
    }
    return best;
}

std::vector<const MapRegion*> RegionCatalog::findAllCovering(double lat, double lon) const {
    std::vector<const MapRegion*> out;
    for (const auto& r : regions_) {
        if (pointInRegion(r, lat, lon)) {
            out.push_back(&r);
        }
    }
    return out;
}

bool RegionCatalog::loadManifestFile(const std::string& manifest_path) {
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
        extractString(obj, "source", r.source);
        extractString(obj, "license", r.license);
        extractString(obj, "checksum_sha256", r.checksum_sha256);
        extractString(obj, "created_at", r.created_at);
        extractString(obj, "downloaded_at", r.downloaded_at);
        extractString(obj, "last_used_at", r.last_used_at);
        extractNumber(obj, "min_lat", r.min_lat);
        extractNumber(obj, "max_lat", r.max_lat);
        extractNumber(obj, "min_lon", r.min_lon);
        extractNumber(obj, "max_lon", r.max_lon);
        double roads = 0.0;
        if (extractNumber(obj, "road_count", roads)) {
            r.road_count = static_cast<int>(roads);
        }
        double bytes = 0.0;
        if (extractNumber(obj, "bytes", bytes) && bytes >= 0.0) {
            r.bytes = static_cast<std::uint64_t>(bytes);
        }
        extractBool(obj, "synthetic", r.synthetic);
        if (r.id.empty() || r.roadpack_path.empty()) {
            last_error_ = "region missing id or roadpack";
            return false;
        }
        if (r.roadpack_path[0] != '/') {
            if (!safeRelativePath(r.roadpack_path)) {
                last_error_ = "rejected unsafe roadpack path: " + r.roadpack_path;
                return false;
            }
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

}  // namespace sih26168::member4
