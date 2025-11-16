import numpy as np
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 14,        # base font size
    "axes.titlesize": 18,   # ax.set_title
    "axes.labelsize": 16,   # ax.set_xlabel / set_ylabel
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 14,
})

# correlations: shape (256, n_samples) -> correlation for each key guess vs sample index
# maxcorr: shape (256,) -> max abs correlation per guess (np.max(np.abs(correlations), axis=1))

plt.figure(figsize=(10,6))
plt.imshow(correlations, aspect='auto', origin='lower')
plt.xlabel('Sample index')
plt.ylabel('Key guess (0..255)')
plt.title('CPA correlations (guess vs sample)')
plt.colorbar(label='correlation')
plt.tight_layout()
plt.savefig('cpa_heatmap.png', dpi=200)
plt.close()

plt.figure(figsize=(8,2))
plt.bar(np.arange(256), maxcorr)
plt.xlabel('Key guess')
plt.ylabel('max |corr|')
plt.title('Max absolute correlation per guess')
plt.tight_layout()
plt.savefig('cpa_maxcorr.png', dpi=200)
plt.close()
