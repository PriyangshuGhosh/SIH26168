#pragma once

#include <string>
#include <vector>

namespace sih26168::member5 {

struct MapRegion {
    std::string id;
    std::string roadpack_path;
    double min_lat{0.0};
    double max_lat{0.0};
    double min_lon{0.0};
    double max_lon{0.0};
    int road_count{0};
    std::string version;
    std::string coordinate_reference{"EPSG:4326"};
    std::string built_at;
};

enum class MapCoverage : int {
    Unknown = 0,
    InRegion = 1,
    OutOfRegion = 2,
    NoPackage = 3
};

class MapCatalog {
public:
    bool loadManifestFile(const std::string& manifest_path);
    bool loadSingleRoadpack(const std::string& roadpack_path, const std::string& id = "loaded");

    void setBoundsFromGeometry(double min_lat, double max_lat, double min_lon, double max_lon);

    const std::vector<MapRegion>& regions() const { return regions_; }
    const std::string& lastError() const { return last_error_; }
    const std::string& catalogRoot() const { return root_; }

    const MapRegion* findCovering(double lat, double lon) const;
    bool covers(double lat, double lon) const { return findCovering(lat, lon) != nullptr; }

    static bool pointInRegion(const MapRegion& r, double lat, double lon);

private:
    std::vector<MapRegion> regions_;
    std::string root_;
    std::string last_error_;
};

}  // namespace sih26168::member5
