"""A7 — Diagnosing a sensor-mode calibration mismatch.

Compares two manufacturer calibrations on 1600x1200 recordings of one R8 stereo rig:
  WRONG : stereo_calibration_manufacturer.json (serial YC202607090123, pinhole + 5-coef, ~1920x1080 mode)
  RIGHT : Kalibr camchain (device id CCC4B2D9B5EA, equidistant fisheye, 800x600 = 1600x1200 at 0.5)
Tests
  (1) ChArUco board recordings 2026-10-26 (controlled targets): epipolar distance, rectified |dy|, left reprojection
  (2) The 2026-10-21 S1 evaluation clip (no target): SIFT matches on 16 frame pairs, epipolar distance + |dy|,
      per-200-px-cell medians
  (3) Static sanity checks readable from the files alone
Run: PYTHONPATH=. python3 a7_calibration_mismatch.py <S1_dir> out
"""
import sys, os, json
import numpy as np, pandas as pd, cv2
from odl_calib import best, obj, device_calib, DATA

S1, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
W, H = 1600, 1200

def skew(t): return np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
def c64(x): return np.ascontiguousarray(x, dtype=np.float64)

# ---- RIGHT: device Kalibr file scaled to 1600x1200
dc = device_calib(); T = dc['T_c1_c0']
RIGHT = dict(name='device_1600x1200_mode', model='fisheye', KL=c64(dc['cam0']['K']), DL=c64(dc['cam0']['D']), KR=c64(dc['cam1']['K']), DR=c64(dc['cam1']['D']),
             R=c64(T[:3, :3]), t=c64(T[:3, 3]).reshape(3, 1))
# ---- WRONG: bundled JSON used directly at 1600x1200
y = json.load(open(f'{S1}/04_Calibration/stereo_calibration_manufacturer.json'))['calibration']
WRONG = dict(name='bundled_1920x1080_mode', model='pinhole', KL=c64(y['K1']), DL=c64(y['D1'][:5]), KR=c64(y['K2']), DR=c64(y['D2'][:5]),
             R=c64(y['R']), t=c64(np.array(y['T']).reshape(3, 1) / 1000.0))
for C in (RIGHT, WRONG):
    C['E'] = skew(C['t'].ravel()) @ C['R']
    if C['model'] == 'fisheye':
        C['R1'], C['R2'], C['P1'], C['P2'] = cv2.fisheye.stereoRectify(C['KL'], C['DL'], C['KR'], C['DR'], (W, H), C['R'], C['t'], flags=cv2.CALIB_ZERO_DISPARITY, balance=0.0)[:4]
        C['und'] = lambda p, K, D, R=None, P=None: cv2.fisheye.undistortPoints(p.reshape(-1, 1, 2), K, D, R=R, P=P).reshape(-1, 2)
        C['proj'] = lambda o, rv, tv, K, D: cv2.fisheye.projectPoints(o.reshape(-1, 1, 3), rv, tv, K, D)[0].reshape(-1, 2)
    else:
        C['R1'], C['R2'], C['P1'], C['P2'] = cv2.stereoRectify(C['KL'], C['DL'], C['KR'], C['DR'], (W, H), C['R'], C['t'], alpha=0)[:4]
        C['und'] = lambda p, K, D, R=None, P=None: cv2.undistortPoints(p.reshape(-1, 1, 2), K, D, R=R, P=P).reshape(-1, 2)
        C['proj'] = lambda o, rv, tv, K, D: cv2.projectPoints(o, rv, tv, K, D)[0].reshape(-1, 2)

def residuals(C, pl, pr):
    ul, ur = C['und'](pl, C['KL'], C['DL']), C['und'](pr, C['KR'], C['DR'])
    hl = np.c_[ul, np.ones(len(ul))]; hr = np.c_[ur, np.ones(len(ur))]
    l2 = (C['E'] @ hl.T).T; l1 = (C['E'].T @ hr.T).T
    epi = (np.abs((hr * l2).sum(1)) / np.linalg.norm(l2[:, :2], axis=1) + np.abs((hl * l1).sum(1)) / np.linalg.norm(l1[:, :2], axis=1)) / 2 * C['KL'][0, 0]
    rl = C['und'](pl, C['KL'], C['DL'], C['R1'], C['P1']); rr = C['und'](pr, C['KR'], C['DR'], C['R2'], C['P2'])
    dy_native = (rl[:, 1] - rr[:, 1]) * C['KL'][0, 0] / C['P1'][0, 0]   # rectified dy rescaled to native focal length
    return epi, dy_native

# ---- (1) board recordings
RECS = {'124235_00000': 'a4', '124235_00001': 'a4', '124235_00002': 'a4', '142800_00000': 'a4', '143229_00000': 'a4',
        '145221_00000': 'a4', '150437_00000': 'a4', '145446_00000': 'far', '145935_00000': 'far', '145719_00000': 'far'}
board_rows = []
for rec, kind in RECS.items():
    L = json.load(open(f'{DATA}/det_{rec}_left.json')); Rr = json.load(open(f'{DATA}/det_{rec}_right.json'))
    for k, (a, b) in enumerate(zip(L, Rr)):
        if k % 2: continue  # every 2nd sampled frame keeps the run time reasonable
        th = 8 if kind == 'far' else 12
        bl = best(a, th); br = best(b, th)
        if bl is None or br is None: continue
        mL = dict(zip(bl['ids'], bl['pts'])); mR = dict(zip(br['ids'], br['pts'])); cc = sorted(set(mL) & set(mR))
        if len(cc) < 6: continue
        pl = np.array([mL[i] for i in cc], float); pr = np.array([mR[i] for i in cc], float); o = obj(cc, kind)
        for C in (RIGHT, WRONG):
            epi, dy = residuals(C, pl, pr)
            ul = C['und'](pl, C['KL'], C['DL'])
            ok, rv, tv = cv2.solvePnP(o, ul, np.eye(3), None)
            rep = np.linalg.norm(C['proj'](o, rv, tv, C['KL'], C['DL']) - pl, axis=1)
            for p, e1, e2, e3 in zip(pl, epi, dy, rep): board_rows.append((C['name'], rec, p[0], p[1], e1, abs(e2), e3))
B = pd.DataFrame(board_rows, columns=['calibration', 'recording', 'u', 'v', 'epi_px', 'rect_abs_dy_px', 'rep_left_px'])
B['r'] = np.hypot(B.u - 807.35, B.v - 613.06)
bsum = B.groupby('calibration').agg(points=('epi_px', 'size'), epi_median=('epi_px', 'median'), epi_p90=('epi_px', lambda s: s.quantile(.9)),
                                    rect_dy_median=('rect_abs_dy_px', 'median'), rep_left_median=('rep_left_px', 'median'), rep_left_p90=('rep_left_px', lambda s: s.quantile(.9))).reset_index()
bsum.round(3).to_csv(f'{OUT}/a7_board_summary.csv', index=False)
bands = []
for name, g in B.groupby('calibration'):
    for lo, hi in [(0, 200), (200, 400), (400, 550), (550, 700)]:
        s = g[(g.r >= lo) & (g.r < hi)]
        bands.append(dict(calibration=name, radius_px=f'{lo}-{hi}', points=len(s), epi_median=s.epi_px.median(), rect_dy_median=s.rect_abs_dy_px.median(), rep_left_median=s.rep_left_px.median()))
pd.DataFrame(bands).round(3).to_csv(f'{OUT}/a7_board_by_radius.csv', index=False)
print(bsum.round(3).to_string())

# ---- (2) S1 clip, SIFT matches
capL = cv2.VideoCapture(f'{S1}/01_Video/left_120s.mp4'); capR = cv2.VideoCapture(f'{S1}/01_Video/right_120s.mp4')
n = int(capL.get(7)); idx = np.linspace(100, n - 100, 16).astype(int)
sift = cv2.SIFT_create(4000); bf = cv2.BFMatcher(); PL = []; PR = []
for i in idx:
    capL.set(1, int(i)); capR.set(1, int(i)); _, a = capL.read(); _, b = capR.read()
    ka, da = sift.detectAndCompute(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), None); kb, db = sift.detectAndCompute(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), None)
    good = [x for x, y2 in bf.knnMatch(da, db, k=2) if x.distance < 0.7 * y2.distance]
    pa = np.float64([ka[g.queryIdx].pt for g in good]); pb = np.float64([kb[g.trainIdx].pt for g in good])
    keep = (np.abs(pa[:, 1] - pb[:, 1]) < 60) & (pa[:, 0] - pb[:, 0] > -20)
    PL.append(pa[keep]); PR.append(pb[keep])
PL = np.vstack(PL); PR = np.vstack(PR)
F, m = cv2.findFundamentalMat(PL, PR, cv2.FM_RANSAC, 8.0, 0.999); PL, PR = PL[m.ravel() == 1], PR[m.ravel() == 1]
rows = []
for C in (RIGHT, WRONG):
    epi, dy = residuals(C, PL, PR)
    for p, e1, e2 in zip(PL, epi, dy): rows.append((C['name'], p[0], p[1], e1, abs(e2)))
S = pd.DataFrame(rows, columns=['calibration', 'u', 'v', 'epi_px', 'rect_abs_dy_px'])
S.round(3).to_csv(f'{OUT}/a7_s1_matches.csv.gz', index=False, compression='gzip')
ssum = S.groupby('calibration').agg(matches=('epi_px', 'size'), epi_median=('epi_px', 'median'), epi_p75=('epi_px', lambda s: s.quantile(.75)),
                                    rect_dy_median=('rect_abs_dy_px', 'median'), share_epi_lt_1px=('epi_px', lambda s: (s < 1).mean())).reset_index()
ssum.round(4).to_csv(f'{OUT}/a7_s1_summary.csv', index=False)
grid = []
for name, g in S.groupby('calibration'):
    for i in range(6):
        for j in range(8):
            s = g[(g.v // 200 == i) & (g.u // 200 == j)]
            grid.append(dict(calibration=name, cell_row=i, cell_col=j, matches=len(s), epi_median=s.epi_px.median() if len(s) >= 25 else np.nan))
pd.DataFrame(grid).round(3).to_csv(f'{OUT}/a7_s1_grid.csv', index=False)
print(ssum.round(3).to_string())

# ---- (3) static file checks
checks = []
for C, res, mode in [(WRONG, 'not stated in file', 'JSON (pinhole, 5 distortion terms)'), (RIGHT, '800x600 (x2 = 1600x1200)', 'Kalibr YAML (equidistant fisheye)')]:
    fx, cx, cy = C['KL'][0, 0], C['KL'][0, 2], C['KL'][1, 2]
    checks.append(dict(calibration=C['name'], file_format=mode, resolution_field=res, fx_px=round(fx, 1), cx_px=round(cx, 1), cy_px=round(cy, 1),
                       principal_point_offset_from_1600x1200_centre_px=round(float(np.hypot(cx - 800, cy - 600)), 1),
                       implied_image_size_from_principal_point=f'~{2*cx:.0f} x {2*cy:.0f}', baseline_mm=round(float(np.linalg.norm(C['t'])) * 1000, 2)))
pd.DataFrame(checks).to_csv(f'{OUT}/a7_static_checks.csv', index=False)
print(pd.DataFrame(checks).to_string())

# ---- rectified example (frame 1500 of the S1 clip), central crop, both calibrations
capL.set(1, 1500); capR.set(1, 1500); _, a = capL.read(); _, b = capR.read()
crops = []
for C in (WRONG, RIGHT):
    if C['model'] == 'fisheye':
        m1 = cv2.fisheye.initUndistortRectifyMap(C['KL'], C['DL'], C['R1'], C['P1'], (W, H), cv2.CV_32FC1)
        m2 = cv2.fisheye.initUndistortRectifyMap(C['KR'], C['DR'], C['R2'], C['P2'], (W, H), cv2.CV_32FC1)
    else:
        m1 = cv2.initUndistortRectifyMap(C['KL'], C['DL'], C['R1'], C['P1'], (W, H), cv2.CV_32FC1)
        m2 = cv2.initUndistortRectifyMap(C['KR'], C['DR'], C['R2'], C['P2'], (W, H), cv2.CV_32FC1)
    ra = cv2.remap(a, *m1, cv2.INTER_LINEAR); rb = cv2.remap(b, *m2, cv2.INTER_LINEAR)
    np.save(f'{OUT}/_rect_{C["name"]}.npy', np.stack([ra, rb]))
print('done')
