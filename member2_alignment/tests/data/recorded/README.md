Place timestamped 6-axis IMU CSV files here for later hardware validation.

Expected columns:

```text
t,ax_p,ay_p,az_p,gx_p,gy_p,gz_p[,gnss_speed,gnss_hdop,gnss_sats]
```

Units: `t` in seconds, accelerometer specific force in m/s², gyroscope in rad/s,
optional GNSS speed in m/s.

Do not commit restricted or large recordings. Run:

```bash
PYTHONPATH=member2_alignment/python python3 member2_alignment/python/validate_recorded.py \
  member2_alignment/tests/data/recorded/your_log.csv
```

Recorded-data accuracy is **NOT VALIDATED** until a real log is supplied.
