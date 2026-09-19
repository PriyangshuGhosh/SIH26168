# Member 4 Android road-data API (contract)

Member 6 may wrap this. **No Google tile scrape.** Visual map SDK ≠ roadpack.

```kotlin
interface RoadDataManagerApi {
    fun getAvailableRegions(): List<MapRegionInfo>
    fun getActiveRegion(): MapRegionInfo?
    fun getDownloadState(regionId: String? = null): DownloadStateInfo
    fun downloadRegion(regionId: String)
    fun cancelDownload(regionId: String)
    fun deleteRegion(regionId: String)
    fun prefetchAround(lat: Double, lon: Double, radiusM: Double)
    fun isRegionAvailable(lat: Double, lon: Double): Boolean
    fun storageInfo(): StorageInfo
}
```

Host implementation: `sih26168_map_matching.road_data_manager.RoadDataManager`.

C++ offline select: `sih26168::member4::RegionCatalog`.

Download **must not** run on the 100 Hz IMU / EKF / match thread.
