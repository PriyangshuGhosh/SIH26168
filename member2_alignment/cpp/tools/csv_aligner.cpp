#include "member2/FrameAligner.hpp"

#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    using sih26168::member2::FrameAligner;
    using sih26168::member2::OptionalGnssAid;

    if (argc < 3) {
        std::cerr << "usage: member2_csv_aligner input.csv output.csv\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "cannot open input\n";
        return 1;
    }
    std::ofstream out(argv[2]);
    if (!out) {
        std::cerr << "cannot open output\n";
        return 1;
    }
    out << std::setprecision(17);
    out << "t,ax_v,ay_v,az_v,gx_v,gy_v,gz_v,qw,qx,qy,qz,status,conf_overall,"
           "conf_gravity,conf_yaw,conf_temporal,conf_sensor\n";

    FrameAligner aligner;
    std::string line;
    bool header = true;
    while (std::getline(in, line)) {
        if (line.empty()) {
            continue;
        }
        if (header) {
            header = false;
            continue;
        }
        for (char& c : line) {
            if (c == ',') {
                c = ' ';
            }
        }
        std::istringstream ss(line);
        double t, ax, ay, az, gx, gy, gz;
        if (!(ss >> t >> ax >> ay >> az >> gx >> gy >> gz)) {
            continue;
        }
        std::vector<double> extra;
        double v;
        while (ss >> v) {
            extra.push_back(v);
        }
        // Optional trailing: ax_v..qz (10) then gnss_speed, hdop, sats
        // Full generator header has 10 truth fields after gyro, then gnss.
        if (extra.size() >= 13) {
            const double speed = extra[extra.size() - 3];
            const double hdop = extra[extra.size() - 2];
            const double sats = extra[extra.size() - 1];
            if (std::isfinite(speed) && std::isfinite(hdop) && std::isfinite(sats)) {
                OptionalGnssAid aid;
                aid.timestamp = t;
                aid.speed_mps = speed;
                aid.hdop = hdop;
                aid.num_sats = static_cast<int>(sats);
                aligner.feedGnss(aid);
            }
        } else if (extra.size() == 3) {
            OptionalGnssAid aid;
            aid.timestamp = t;
            aid.speed_mps = extra[0];
            aid.hdop = extra[1];
            aid.num_sats = static_cast<int>(extra[2]);
            if (std::isfinite(aid.speed_mps)) {
                aligner.feedGnss(aid);
            }
        }
        const auto f = aligner.process(t, ax, ay, az, gx, gy, gz);
        out << f.timestamp << ',' << f.ax_v << ',' << f.ay_v << ',' << f.az_v << ',' << f.gx_v << ','
            << f.gy_v << ',' << f.gz_v << ',' << f.q_pv[0] << ',' << f.q_pv[1] << ',' << f.q_pv[2] << ','
            << f.q_pv[3] << ',' << static_cast<int>(f.status) << ',' << f.confidence.overall << ','
            << f.confidence.gravity << ',' << f.confidence.yaw_observability << ','
            << f.confidence.temporal << ',' << f.confidence.sensor_quality << '\n';
    }
    return 0;
}
