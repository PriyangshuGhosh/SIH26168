# Normalized V2X message model

**IMPLEMENTED** internal schema. **NOT** a complete ETSI CAM or SAE J2735 stack.

Units are in field names. Velocities are local ENU m/s. Heading is radians, 0 = North, increasing toward East.

JSONL (replay) keys: `vehicle_id`, `sender_time_s`, `receive_time_s`, `clock_offset_s`, `latitude_deg`, `longitude_deg`, `altitude_m`, `ve_mps`, `vn_mps`, `vu_mps`, `heading_rad`, `yaw_rate_rps`, `declared_pos_std_m`, `declared_vel_std_mps`, `source`, `quality`, `security`.

`vehicle_id` is a **pseudonym**.

Message age: `receive_time - sender_time - clock_offset`. Age inflates covariance. Age > `max_message_age_s` → stale reject.

Declared `pos_std` is the **remote's own** uncertainty, not ground truth.
