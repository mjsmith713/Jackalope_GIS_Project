import os
import glob
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin
from osgeo import gdal
from scipy.ndimage import gaussian_filter

# ==============================================================================
# 1. DEFINE PROJECT PATHS & MASTER 1KM ALBERS GRID (EPSG:5070)
# ==============================================================================
PROJECT_DIR = r"C:\QGIS_Work\Jackalope_GIS_Project"
RAW_RASTER_DIR = os.path.join(PROJECT_DIR, "rasters", "raw")
OUT_RASTER_DIR = os.path.join(PROJECT_DIR, "rasters", "processed")
DATA_RAW_DIR = os.path.join(PROJECT_DIR, "data_raw")
os.makedirs(OUT_RASTER_DIR, exist_ok=True)

TARGET_CRS = "EPSG:5070"
PIXEL_SIZE = 1000.0  # 1 km x 1 km resolution

# Great Plains & Intermountain West bounding box in EPSG:5070 (meters)
X_MIN, Y_MIN, X_MAX, Y_MAX = -1500000.0, 900000.0, 200000.0, 2900000.0
WIDTH = int((X_MAX - X_MIN) / PIXEL_SIZE)
HEIGHT = int((Y_MAX - Y_MIN) / PIXEL_SIZE)
MASTER_TRANSFORM = from_origin(X_MIN, Y_MAX, PIXEL_SIZE, PIXEL_SIZE)

MASTER_PROFILE = {
    "driver": "GTiff",
    "height": HEIGHT,
    "width": WIDTH,
    "count": 1,
    "dtype": "float32",
    "crs": TARGET_CRS,
    "transform": MASTER_TRANSFORM,
    "nodata": -9999.0,
    "compress": "lzw",
}


# ==============================================================================
# 2. AUTO-LOCATE DOWNLOADED RASTERS IN SUBFOLDERS
# ==============================================================================
def find_file(pattern, exclude=None):
    matches = glob.glob(os.path.join(RAW_RASTER_DIR, "**", pattern), recursive=True)
    if exclude:
        matches = [m for m in matches if exclude.lower() not in os.path.basename(m).lower()]
    if not matches:
        raise FileNotFoundError(f"Could not find file matching '{pattern}' inside {RAW_RASTER_DIR}")
    print(f"Found: {matches[0]}")
    return matches[0]


def align_raster_to_master(src_path, resampling_method=Resampling.bilinear, subdataset_keyword=None):
    """Reprojects and resamples any GeoTIFF or HDF subdataset onto the 1km EPSG:5070 grid."""
    dst_array = np.full((HEIGHT, WIDTH), -9999.0, dtype=np.float32)
    if src_path.lower().endswith(".hdf"):
        ds = gdal.Open(src_path)
        subdatasets = ds.GetSubDatasets()
        target_sds = subdatasets[0][0]
        for sds_name, sds_desc in subdatasets:
            if "flash" in sds_name.lower() or "rate" in sds_name.lower() or "mean" in sds_name.lower():
                target_sds = sds_name
                break
        print(f"  -> Reading HDF subdataset: {target_sds}")
        sds_ds = gdal.Open(target_sds)
        raw_arr = sds_ds.ReadAsArray().astype(np.float32)
        h_src, w_src = raw_arr.shape
        src_transform = from_origin(-180.0, 90.0, 360.0 / w_src, 180.0 / h_src)
        reproject(
            source=raw_arr,
            destination=dst_array,
            src_transform=src_transform,
            src_crs="EPSG:4326",
            dst_transform=MASTER_TRANSFORM,
            dst_crs=TARGET_CRS,
            resampling=resampling_method,
            dst_nodata=-9999.0,
        )

    else:
        with rasterio.open(src_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=dst_array,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=MASTER_TRANSFORM,
                dst_crs=TARGET_CRS,
                resampling=resampling_method,
                dst_nodata=-9999.0,
            )
    return dst_array


def normalize_0_1(arr):
    valid = arr != -9999.0
    out = np.full_like(arr, -9999.0, dtype=np.float32)
    if np.any(valid):
        vmin, vmax = np.nanpercentile(arr[valid], 1), np.nanpercentile(arr[valid], 99)
        if vmax > vmin:
            scaled = np.clip((arr[valid] - vmin) / (vmax - vmin), 0.0, 1.0)
            out[valid] = scaled
        else:
            out[valid] = 0.0
    return out


def save_geotiff(arr, filename):
    out_path = os.path.join(OUT_RASTER_DIR, filename)
    with rasterio.open(out_path, "w", **MASTER_PROFILE) as dst:
        dst.write(arr.astype(np.float32), 1)
    print(f"Saved raster: {out_path}")
    return out_path


# ==============================================================================
# 3. KERNEL DENSITY ESTIMATION FOR HOST & VECTOR POINTS
# ==============================================================================
def compute_point_kde(gpkg_path, sigma_km):
    print(f"Computing {sigma_km} km KDE for {os.path.basename(gpkg_path)}...")
    gdf = gpd.read_file(gpkg_path).to_crs(TARGET_CRS)
    grid = np.zeros((HEIGHT, WIDTH), dtype=np.float32)

    cols = ((gdf.geometry.x - X_MIN) / PIXEL_SIZE).astype(int)
    rows = ((Y_MAX - gdf.geometry.y) / PIXEL_SIZE).astype(int)
    in_bounds = (cols >= 0) & (cols < WIDTH) & (rows >= 0) & (rows < HEIGHT)

    for r, c in zip(rows[in_bounds], cols[in_bounds]):
        grid[r, c] += 1.0

    kde = gaussian_filter(grid, sigma=sigma_km)
    return normalize_0_1(kde)


# ==============================================================================
# 4. MAIN SPATIAL MODELING WORKFLOW
# ==============================================================================
if __name__ == "__main__":
    print("=== STEP 1: LOCATING & ALIGNING ENVIRONMENTAL RASTERS ===")
    lc_path = find_file("*USA_NALCMS_landcover*.tif")
    prism_path = find_file("*tmean*.tif")
    lightning_path = find_file("*COMB_OTD_TRMM_ISS_AnnualMean*.hdf")

    lc_arr = align_raster_to_master(lc_path, Resampling.nearest)
    temp_arr = align_raster_to_master(prism_path, Resampling.bilinear)
    light_arr = align_raster_to_master(lightning_path, Resampling.bilinear, subdataset_keyword="FlashRate")

    print("\n=== STEP 2: RECLASSIFYING ECOLOGICAL SUITABILITY (1-5 SCALE) ===")
    # CEC NALCMS 2020 Land Cover Classes:
    # 8 = Temperate/sub-polar shrubland, 10 = Temperate/sub-polar grassland -> Score 5
    # 15 = Cropland (edge habitat) -> Score 4
    # 1, 5, 6 = Forests -> Score 2 | Water/Urban/Barren -> Score 1
    lc_reclass = np.full_like(lc_arr, 1.0, dtype=np.float32)
    lc_reclass[np.isin(lc_arr, [8, 10])] = 5.0
    lc_reclass[np.isin(lc_arr, [15])] = 4.0
    lc_reclass[np.isin(lc_arr, [1, 5, 6, 14])] = 2.0
    lc_reclass[lc_arr <= 0] = -9999.0

    # PRISM Mean Annual Temp (Celsius): optimal arthropod vector survival 10C - 20C
    temp_reclass = np.full_like(temp_arr, 1.0, dtype=np.float32)
    temp_reclass[(temp_arr >= 10.0) & (temp_arr <= 20.0)] = 5.0
    temp_reclass[((temp_arr >= 6.0) & (temp_arr < 10.0)) | ((temp_arr > 20.0) & (temp_arr <= 24.0))] = 3.0
    temp_reclass[temp_arr == -9999.0] = -9999.0

    print("\n=== STEP 3: GENERATING HOST & VECTOR KERNEL DENSITIES ===")
    host_kde = compute_point_kde(os.path.join(DATA_RAW_DIR, "track_a_hosts.gpkg"), sigma_km=50)
    vector_kde = compute_point_kde(os.path.join(DATA_RAW_DIR, "track_a_vectors.gpkg"), sigma_km=75)

    print("\n=== STEP 4: CALCULATING TRACK A & TRACK B SUITABILITY INDICES ===")
    lc_norm = normalize_0_1(lc_reclass)
    temp_norm = normalize_0_1(temp_reclass)
    light_norm = normalize_0_1(light_arr)

    # Track A: Epidemiological Risk Index (Shope Papillomavirus Suitability)
    track_a_risk = (host_kde * 0.40) + (lc_norm * 0.25) + (vector_kde * 0.20) + (temp_norm * 0.15)
    track_a_risk[lc_reclass == -9999.0] = -9999.0
    track_a_path = save_geotiff(track_a_risk, "track_a_epidemiological_risk.tif")

    # Track B: Folklore Habitat Suitability Index (Prairie Biome + Electrical Storm Lore)
    prairie_norm = np.where(np.isin(lc_arr, [8, 10]), 1.0, np.where(lc_arr == 15, 0.5, 0.0)).astype(np.float32)
    track_b_folklore = (light_norm * 0.50) + (prairie_norm * 0.50)
    track_b_folklore[lc_reclass == -9999.0] = -9999.0
    save_geotiff(track_b_folklore, "track_b_folklore_suitability.tif")

    print("\n=== STEP 5: EXTRACTING RISK SCORES ONTO CANDIDATE SIGHTINGS ===")
    cand_gpkg = os.path.join(DATA_RAW_DIR, "track_a_pathology_candidates.gpkg")
    if os.path.exists(cand_gpkg):
        cands = gpd.read_file(cand_gpkg).to_crs(TARGET_CRS)
        coords = [(pt.x, pt.y) for pt in cands.geometry]
        with rasterio.open(track_a_path) as src:
            cands["viral_risk_score"] = [val[0] for val in src.sample(coords)]
        val_out = os.path.join(OUT_RASTER_DIR, "validated_pathology_points.gpkg")
        cands.to_file(val_out, driver="GPKG")
        print(f"Saved {len(cands)} scored pathology points to: {val_out}")

    print("\nAll spatial suitability rasters generated successfully!")
