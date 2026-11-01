# Methodology
* File B (Kalibr, 800×600): f×2, c×2+0.5, fisheye model; File A (JSON): pinhole + 5 coefficients used directly at 1600×1200, T in mm → m.
* Epipolar distance: symmetric point-to-epipolar-line distance in normalised coordinates × fx.
* Rectified |dy|: computed for both files, rescaled to native focal length; numerically equal to the epipolar distance (sanity check), so only epipolar distance is reported.
* Board data: every 2nd sampled frame of 10 recordings, ≥12 (A4) / ≥8 (far) corners.
* Real clip: 16 frames, SIFT (4000) + ratio 0.7, row band |dy|<60 px, loose F-RANSAC (8 px) on raw points to drop gross mismatches (calibration-free, same set for both files).
* Grid: 200 px cells, ≥25 matches.
