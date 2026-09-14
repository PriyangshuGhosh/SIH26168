# SIH26168

Repository for the SIH26168 intelligent GNSS-denied navigation system.

## Team Work Distribution & Deliverables

The complete production-grade work distribution, interface contracts, module dependencies, integration gates, engineering rules, and deliverables are maintained in:

**[docs/WORK_DISTRIBUTION.md](docs/WORK_DISTRIBUTION.md)**

### Pipeline

`Phone IMU/GNSS → Frame Alignment → AI Speed Estimation → EKF/UKF Fusion → Offline HMM Map Matching → Native C++ Engine → Mobile Navigation UI`

### Integration Order

**Member 2 → Member 1 → Member 3 → Member 4 → Member 5 → Member 6**

Each member owns a testable module with an explicit interface and downstream handoff. See the work-distribution document for the exact contracts and Definition of Done.