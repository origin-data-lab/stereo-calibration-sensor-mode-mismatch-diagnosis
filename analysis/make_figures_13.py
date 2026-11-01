import os, numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = 'out'; FIG = f'{OUT}/figures'
exec(open('make_figures.py').read().split('def save')[0].split("OUT = ")[0])
C1, C2, GR, INK = '#1f5fbf', '#d9622b', '#8a8f98', '#1d232b'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10.5, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True, 'grid.color': '#e7eaee', 'axes.edgecolor': '#c9ced6'})
def save(fig, name): fig.savefig(f'{FIG}/{name}.png', dpi=170, bbox_inches='tight'); fig.savefig(f'{FIG}/{name}.svg', bbox_inches='tight'); plt.close(fig)
LAB = {'bundled_1920x1080_mode': 'File A (16:9 mode, bundled)', 'device_1600x1200_mode': 'File B (1600×1200 mode)'}
COL = {'bundled_1920x1080_mode': C2, 'device_1600x1200_mode': C1}
S = pd.read_csv(f'{OUT}/a7_s1_matches.csv.gz')
fig, ax = plt.subplots(figsize=(7, 3.8)); bins = np.logspace(-2, 2, 60)
for k in ['bundled_1920x1080_mode', 'device_1600x1200_mode']:
    e = S[S.calibration == k].epi_px
    ax.hist(e, bins=bins, color=COL[k], alpha=0.55, label=f'{LAB[k]} — median {e.median():.2f} px')
ax.set_xscale('log'); ax.axvline(1, color=INK, lw=0.8, ls='--'); ax.set_xlabel('Epipolar distance (px, log scale)'); ax.set_ylabel('Feature matches')
ax.legend(frameon=False, fontsize=9); ax.set_title(f'Same stereo clip, two calibration files ({len(S)//2:,} matches, 16 frames)', loc='left', fontsize=11)
save(fig, 'fn13_s1_epipolar_hist')
G = pd.read_csv(f'{OUT}/a7_s1_grid.csv')
fig, axs = plt.subplots(1, 2, figsize=(10.4, 3.9))
for ax, k in zip(axs, ['bundled_1920x1080_mode', 'device_1600x1200_mode']):
    g = G[G.calibration == k].pivot(index='cell_row', columns='cell_col', values='epi_median').values
    im = ax.imshow(np.clip(g, 0, 6), cmap='viridis', vmin=0, vmax=6, extent=[0, 1600, 1200, 0])
    for i in range(6):
        for j in range(8):
            if not np.isnan(g[i, j]): ax.text(j * 200 + 100, i * 200 + 100, f'{g[i,j]:.1f}', ha='center', va='center', fontsize=7.5, color='white' if g[i, j] < 4 else INK)
    ax.set_title(LAB[k], loc='left', fontsize=10.5); ax.grid(False); ax.set_xticks([0, 400, 800, 1200, 1600]); ax.set_yticks([0, 300, 600, 900, 1200])
cb = fig.colorbar(im, ax=axs, shrink=0.85); cb.set_label('Median epipolar distance (px), clipped at 6')
fig.suptitle('Where the error sits in the image (real work clip, blank = <25 matches)', x=0.06, ha='left', fontsize=11)
save(fig, 'fn13_s1_residual_map')
Bd = pd.read_csv(f'{OUT}/a7_board_by_radius.csv')
fig, ax = plt.subplots(figsize=(7, 3.8)); x = np.arange(4); w = 0.38
for o, k in [(-w / 2, 'bundled_1920x1080_mode'), (w / 2, 'device_1600x1200_mode')]:
    d = Bd[Bd.calibration == k]
    ax.bar(x + o, d.epi_median, w, color=COL[k], label=LAB[k])
    for xi, v in zip(x + o, d.epi_median): ax.text(xi, v + 0.05, f'{v:.2f}', ha='center', fontsize=8.5)
ax.set_xticks(x); ax.set_xticklabels([f'{r} px' for r in Bd.radius_px.unique()]); ax.set_xlabel('Radius from image centre'); ax.set_ylabel('Median epipolar distance (px)')
ax.legend(frameon=False, fontsize=9); ax.set_title('ChArUco board recordings, 2026-10-26 (112,538 corners)', loc='left', fontsize=11)
save(fig, 'fn13_board_by_radius')
print('ok')
