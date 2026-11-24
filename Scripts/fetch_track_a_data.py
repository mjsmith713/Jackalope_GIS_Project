import os
import time
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ==============================================================================
# 1. SETUP OUTPUT FOLDER & STUDY BOUNDING BOX
# ==============================================================================
# Automatically creates a 'data_raw' folder next to your 'scripts' folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data_raw")
os.makedirs(OUT_DIR, exist_ok=True)

# Great Plains & Intermountain West bounding box (Lat/Lon WGS84)
MIN_LON, MAX_LON = -112.0, -94.0
MIN_LAT, MAX_LAT = 31.0, 49.0

# Target Albers Equal Area projection for North America (EPSG:5070)
TARGET_CRS = "EPSG:5070"


# ==============================================================================
# 2. FUNCTION TO QUERY & CLEAN GBIF OCCURRENCE DATA
# ==============================================================================
def fetch_gbif_species(scientific_name, limit=1000):
    print(f"Querying GBIF for: {scientific_name}...")
    url = "https://api.gbif.org/v1/occurrence/search"
    headers = {"User-Agent": "JackalopeGISResearchProject/1.0 (student portfolio)"}
    params = {
        "scientificName": scientific_name,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "decimalLatitude": f"{MIN_LAT},{MAX_LAT}",
        "decimalLongitude": f"{MIN_LON},{MAX_LON}",
        "year": "2000,2026",
        "limit": limit,
    }
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()

    records = response.json().get("results", [])

    cleaned = []
    for r in records:
        lat = r.get("decimalLatitude")
        lon = r.get("decimalLongitude")
        unc = r.get("coordinateUncertaintyInMeters") or 0

        # Skip records with poor GPS accuracy (> 5 km uncertainty)
        if lat is None or lon is None or unc > 5000:
            continue

        cleaned.append({
            "source": "GBIF",
            "species": scientific_name,
            "year": r.get("year"),
            "uncertainty_m": unc,
            "lat": lat,
            "lon": lon,
        })
    print(f"  -> Kept {len(cleaned)} clean records.")
    return cleaned
   


# ==============================================================================
# 3. FUNCTION TO QUERY & CLEAN INATURALIST SYMPTOMATIC OBSERVATIONS
# ==============================================================================
def fetch_inat_pathology(keywords, per_page=200):
    print("Querying iNaturalist for symptomatic lagomorphs...")
    url = "https://api.inaturalist.org/v1/observations"
    all_records = {}

    for kw in keywords:
        params = {
            "taxon_name": "Lagomorpha",
            "q": kw,
            "nelat": MAX_LAT,
            "nelng": MAX_LON,
            "swlat": MIN_LAT,
            "swlng": MIN_LON,
            "per_page": per_page,
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])

        for obs in results:
            obs_id = obs.get("id")
            geojson = obs.get("geojson")
            if not geojson or obs_id in all_records:
                continue

            lon, lat = geojson["coordinates"]
            acc = obs.get("positional_accuracy") or 0
            if acc > 5000:
                continue

            # Extract photo URL so you can inspect the "horns" visually
            photos = obs.get("photos", [])
            photo_url = photos[0]["url"].replace("square", "medium") if photos else ""

            all_records[obs_id] = {
                "source": "iNaturalist",
                "obs_id": obs_id,
                "keyword_match": kw,
                "species": obs.get("taxon", {}).get("name", "Lagomorpha"),
                "observed_on": obs.get("observed_on"),
                "description": obs.get("description", ""),
                "photo_url": photo_url,
                "lat": lat,
                "lon": lon,
            }
        # Pause briefly to respect iNaturalist API rate limits
        time.sleep(1.2)

    print(f"  -> Found {len(all_records)} unique candidate records.")
    return list(all_records.values())


# ==============================================================================
# 4. HELPER TO CONVERT DATAFRAME TO REPROJECTED GEOPACKAGE & CSV
# ==============================================================================
def save_spatial_outputs(records, base_filename):
    if not records:
        print(f"No records to save for {base_filename}.")
        return

    df = pd.DataFrame(records).drop_duplicates(subset=["lat", "lon"])
    csv_path = os.path.join(OUT_DIR, f"{base_filename}.csv")
    gpkg_path = os.path.join(OUT_DIR, f"{base_filename}.gpkg")

    # Save plain CSV for easy viewing in Excel
    df.to_csv(csv_path, index=False)

    # Convert to GeoDataFrame (WGS84) and reproject to Albers (EPSG:5070)
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    gdf_projected = gdf.to_crs(TARGET_CRS)
    gdf_projected.to_file(gpkg_path, driver="GPKG")

    print(f"Saved {len(gdf_projected)} points to:\n  - {csv_path}\n  - {gpkg_path}\n")


# ==============================================================================
# 5. MAIN EXECUTION BLOCK
# ==============================================================================
if __name__ == "__main__":
    # A. Fetch Host Rabbits & Hares
    host_species = [
        "Sylvilagus floridanus",
        "Sylvilagus audubonii",
        "Lepus townsendii",
    ]
    host_rows = []
    for sp in host_species:
        host_rows.extend(fetch_gbif_species(sp))
    save_spatial_outputs(host_rows, "track_a_hosts")

    # B. Fetch Rabbit Tick Vector
    vector_rows = fetch_gbif_species("Haemaphysalis leporispalustris")
    save_spatial_outputs(vector_rows, "track_a_vectors")

    # C. Fetch Symptomatic iNaturalist Observations
    pathology_rows = fetch_inat_pathology(["papilloma", "horn", "wart", "tumor"])
    save_spatial_outputs(pathology_rows, "track_a_pathology_candidates")

    print("All Track A automated downloads complete!")
