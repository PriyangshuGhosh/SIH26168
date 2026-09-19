#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace sih26168::member4 {

struct MapRegion {
    std::string id;
    std::string roadpack_path;
    double min_lat{0.0};
    double max_lat{0.0};
    double min_lon{0.0};
    double max_lon{0.0};
    int road_count{0};
    std::string version;
    std::string source;
    std::string license;
    std::string checksum_sha256;
    std::string created_at;
    std::string downloaded_at;
    std::string last_used_at;
    std::uint64_t bytes{0};
    bool synthetic{false};
};

/* Offline catalog only. No HTTP. Region choice is geographic, never a city name. */
class RegionCatalog {
public:
    bool loadManifestFile(const std::string& manifest_path);
    const std::vector<MapRegion>& regions() const { return regions_; }
    const std::string& lastError() const { return last_error_; }
    const std::string& catalogRoot() const { return root_; }

    const MapRegion* findCovering(double lat, double lon) const;
    std::vector<const MapRegion*> findAllCovering(double lat, double lon) const;
    bool covers(double lat, double lon) const { return findCovering(lat, lon) != nullptr; }

    /* Metres from (lat,lon) to the nearest edge of the region bbox. Negative = outside. */
    static double signedDistanceToBoundaryM(const MapRegion& r, double lat, double lon);
    static bool pointInRegion(const MapRegion& r, double lat, double lon);
    static bool approachingBoundary(const MapRegion& r, double lat, double lon,
                                    double threshold_m);

    static bool safeRelativePath(const std::string& relative);

private:
    std::vector<MapRegion> regions_;
    std::string root_;
    std::string last_error_;
};

}  // namespace sih26168::member4
