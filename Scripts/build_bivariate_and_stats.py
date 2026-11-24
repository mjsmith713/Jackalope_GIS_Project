import os
import numpy as np
import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu

# ==============================================================================
# 1. PATHS & LOAD RASTERS
# ==============================================================================
PROJECT_DIR = r"C:\QGIS_Work\Jackalope_GIS_Project"
PROC_DIR = os.path.join(PROJECT_DIR, "rasters", "processed")
OUT_FIG_DIR = os.path.join(PROJECT_DIR, "outputs")
os.makedirs(OUT_FIG_DIR, exist_ok=True)

risk_path = os.path.join(PROC_DIR, "track_a_epidemiological_risk.tif")
myth_path = os.path.join(PROC_DIR, "track_b_folklore_suitability.tif")
pts_path = os.path.join(PROC_DIR, "validated_pathology_points.gpkg")

with rasterio.open(risk_path) as src_a:
    risk_arr = src_a.read(1)
    profile = src_a.profile.copy()

with rasterio.open(myth_path) as src_b:
    myth_arr = src_b.read(1)

valid = (risk_arr != -9999.0) & (myth_arr != -9999.0) & (~np.isnan(risk_arr)) & (~np.isnan(myth_arr))

# ==============================================================================
# 2. BUILD 3x3 BIVARIATE RASTER (CODES 11 TO 33)
# ==============================================================================
# Classify each layer into Low (1), Medium (2), High (3) using terciles (33rd & 66th percentiles)
r_t1, r_t2 = np.percentile(risk_arr[valid], [33.3, 66.7])
m_t1, m_t2 = np.percentile(myth_arr[valid], [33.3, 66.7])

r_class = np.where(risk_arr <= r_t1, 1, np.where(risk_arr <= r_t2, 2, 3))
m_class = np.where(myth_arr <= m_t1, 1, np.where(myth_arr <= m_t2, 2, 3))

# Bivariate code: Tens digit = Science (1-3), Ones digit = Folklore (1-3)
# e.g., 11 = Low/Low, 31 = High Science/Low Myth, 13 = Low Science/High Myth, 33 = High/High
biv_arr = np.full(risk_arr.shape, 0, dtype=np.uint8)
biv_arr[valid] = (r_class[valid] * 10) + m_class[valid]

biv_out = os.path.join(PROC_DIR, "bivariate_science_vs_myth.tif")
profile.update(dtype="uint8", nodata=0)
with rasterio.open(biv_out, "w", **profile) as dst:
    dst.write(biv_arr, 1)
print(f"Saved 9-class Bivariate Raster: {biv_out}")

# ==============================================================================
# 3. STATISTICAL VALIDATION CHART (PATHOLOGY POINTS VS. RANDOM BACKGROUND)
# ==============================================================================
pts = gpd.read_file(pts_path)
obs_scores = pts["viral_risk_score"].dropna().values
obs_scores = obs_scores[obs_scores >= 0]

# Sample 2,000 random background pixels across the valid study extent
rng = np.random.default_rng(42)
bg_scores = rng.choice(risk_arr[valid], size=2000, replace=False)

stat, p_val = mannwhitneyu(obs_scores, bg_scores, alternative="greater")
print(f"Observed Mean Risk: {obs_scores.mean():.3f} | Background Mean Risk: {bg_scores.mean():.3f}")
print(f"Mann-Whitney U p-value: {p_val:.4e}")

# Create clean portfolio figure
plt.figure(figsize=(8, 4.8), dpi=300)
bins = np.linspace(0, 1, 26)
plt.hist(bg_scores, bins=bins, density=True, alpha=0.55, color="#6c757d", label="Random Background Extent (n=2,000)")
plt.hist(obs_scores, bins=bins, density=True, alpha=0.70, color="#c1121f", label=f"Symptomatic Lagomorph Sightings (n={len(obs_scores)})")
plt.axvline(bg_scores.mean(), color="#495057", linestyle="--", linewidth=1.5, label=f"Background Mean ({bg_scores.mean():.2f})")
plt.axvline(obs_scores.mean(), color="#780000", linestyle="-", linewidth=2.0, label=f"Sightings Mean ({obs_scores.mean():.2f})")

plt.title("Shope Papillomavirus Suitability Validation: Sightings vs. Background", fontsize=12, fontweight="bold", pad=12)
plt.xlabel("Track A Epidemiological Risk Index (0 = Low, 1 = High)", fontsize=10)
plt.ylabel("Probability Density", fontsize=10)
plt.legend(frameon=True, facecolor="white", fontsize=8.5)
plt.grid(axis="y", linestyle=":", alpha=0.5)
plt.tight_layout()

chart_out = os.path.join(OUT_FIG_DIR, "validation_chart.png")
plt.savefig(chart_out)
print(f"Saved high-res portfolio chart: {chart_out}")
