#include "member3/EKFFusionEngine.hpp"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <vector>
using namespace sih26168::member2; using namespace sih26168::member3;
static AlignedIMUFrame imu(double t){AlignedIMUFrame f{};f.timestamp=t;f.ax_v=.2;f.az_v=9.80665;f.status=CalibrationStatus::FULLY_ALIGNED;return f;}
static double pct(std::vector<double> v,double p){std::sort(v.begin(),v.end());return v[static_cast<size_t>(p*(v.size()-1))];}
template<class F> void run(const char*n,int N,F f){std::vector<double> a;a.reserve(N);for(int i=0;i<N;++i){auto s=std::chrono::steady_clock::now();f(i);auto e=std::chrono::steady_clock::now();a.push_back(std::chrono::duration<double,std::micro>(e-s).count());}double sum=0;for(auto x:a)sum+=x;std::cout<<n<<" avg_us="<<sum/N<<" p95_us="<<pct(a,.95)<<" p99_us="<<pct(a,.99)<<"\n";}
int main(){const int N=10000;EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);run("IMU prediction",N,[&](int i){e.predict(imu((i+1)*.01),NavigationMode::DEAD_RECKONING);});e.reset();GnssMeasurement g{};g.timestamp=0;g.latitude=17.385;g.longitude=78.4867;g.altitude=100;g.hdop=1;g.num_sats=10;g.speed_mps=4;e.updateGnss(g);run("GNSS update",N,[&](int){g.timestamp=0;e.updateGnss(g);});AiSpeedMeasurement s{0,4,.25,true};run("AI speed update",N,[&](int){e.updateAiSpeed(s);});e.reset();e.predict(imu(0),NavigationMode::DEAD_RECKONING);run("100 Hz complete loop",N,[&](int i){double t=(i+1)*.01;e.predict(imu(t),NavigationMode::DEAD_RECKONING);if(i%10==0){s.timestamp=t;e.updateAiSpeed(s);}});}
