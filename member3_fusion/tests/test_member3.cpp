#include "member3/EKFFusionEngine.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
namespace {
using namespace sih26168::member2; using namespace sih26168::member3;
AlignedIMUFrame imu(double t,double ax=0,double ay=0,double gz=0,CalibrationStatus st=CalibrationStatus::FULLY_ALIGNED){AlignedIMUFrame x{};x.timestamp=t;x.ax_v=ax;x.ay_v=ay;x.az_v=9.80665;x.gz_v=gz;x.status=st;return x;}
GnssMeasurement gnss(double t,double lat,double lon,double speed=0){GnssMeasurement g{};g.timestamp=t;g.latitude=lat;g.longitude=lon;g.altitude=100;g.speed_mps=speed;g.hdop=1;g.num_sats=10;return g;}
void eight(){static_assert(EKFFusionEngine::kStateDim==8);EKFFusionEngine e;assert(e.stateVector().size()==8);assert(e.covariance().rows()==8);}
void frame(){EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);e.predict(imu(.1,1,2,3),NavigationMode::DEAD_RECKONING);assert(e.state().v_x>.05);assert(std::abs(e.state().yaw_rad-.3)<.05);}
void prediction(){EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);for(int i=1;i<=10;++i)e.predict(imu(i*.1,1),NavigationMode::DEAD_RECKONING);assert(std::abs(e.state().v_x-1)<.15);}
void nhc(){EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);e.predict(imu(.1,0,2,0,CalibrationStatus::YAW_UNCERTAIN),NavigationMode::DEAD_RECKONING);assert(std::abs(e.state().v_y)>.05);e.predict(imu(.2,0,0,0),NavigationMode::DEAD_RECKONING);assert(std::abs(e.state().v_y)<.2);}
void gnss(){EKFFusionEngine e;e.updateGnss(gnss(0,17.385,78.4867,4));assert(e.state().valid);e.predict(imu(.1),NavigationMode::GNSS_AIDED);e.updateGnss(gnss(.1,17.38502,78.48672,4));assert(e.state().last_gnss_accepted);}
void gnss_gate(){EKFFusionEngine e;e.updateGnss(gnss(0,17.385,78.4867));e.predict(imu(.1),NavigationMode::GNSS_AIDED);auto before=e.state();e.updateGnss(gnss(.1,17.390,78.4917));auto after=e.state();assert(!after.last_gnss_accepted);assert(std::abs(after.latitude-before.latitude)<1e-5);assert(std::abs(after.longitude-before.longitude)<1e-5);}
void ai(){EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);e.updateAiSpeed({0.05,1.5,.25,true});assert(e.state().last_ai_speed_accepted);double v=e.state().v_x;e.updateAiSpeed({0.05,80,.01,true});assert(!e.state().last_ai_speed_accepted);assert(std::abs(e.state().v_x-v)<1e-9);}
void invalid_time(){EKFFusionEngine e;e.predict(imu(1),NavigationMode::DEAD_RECKONING);auto t=e.state().timestamp;e.predict(imu(1,10),NavigationMode::DEAD_RECKONING);assert(e.state().timestamp==t);e.predict(imu(.5,10),NavigationMode::DEAD_RECKONING);assert(e.state().timestamp==t);auto b=imu(2);b.ax_v=std::numeric_limits<double>::quiet_NaN();e.predict(b,NavigationMode::DEAD_RECKONING);assert(std::isfinite(e.state().v_x));}
void covariance_blackout(){EKFFusionEngine e;e.updateGnss(gnss(0,17.385,78.4867));e.predict(imu(.01),NavigationMode::GNSS_AIDED);double p0=e.covariance()(0,0);for(int i=2;i<=100;++i)e.predict(imu(i*.01,.05),NavigationMode::DEAD_RECKONING);auto P=e.covariance();assert(P.allFinite());assert(P.isApprox(P.transpose(),1e-10));assert(P(0,0)>p0);}
void gap(){EKFFusionEngine e;e.predict(imu(0),NavigationMode::DEAD_RECKONING);e.predict(imu(2,1),NavigationMode::DEAD_RECKONING);assert(e.state().timestamp==2);assert(std::isfinite(e.state().v_x));}
}
int main(){eight();frame();prediction();nhc();gnss();gnss_gate();ai();invalid_time();covariance_blackout();gap();std::cout<<"All Member 3 completion tests passed.\n";}
