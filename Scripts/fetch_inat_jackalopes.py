import os
import time
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

OUT_DIR = r"C:\QGIS_Work\Jackalope_GIS_Project\data_raw"
url = "https://api.inaturalist" + ".org/v1/observations"
headers = {"User-Agent": "JackalopeGISResearchProject/1.0"}

# Search all of North America for Order Lagomorpha (taxon_id=43094)
keywords = ["papilloma", "jackalope", "horn", "horns", "wart", "warts", "tumor", "growth"]
all_records = {}

for kw in keywords:
    print(f"Searching iNaturalist for '{kw}'...")
    params = {
        "taxon_id": 43094,
        "q": kw,
        "nelat": 55.0, "nelng": -65.0,
        "swlat": 24.0, "swlng": -125.0,
        "per_page": 200,
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()

    for obs in resp.json().get("results", []):
        obs_id = obs.get("id")
        geojson = obs.get("geojson")
        if not geojson or obs_id in all_records:
            continue
        lon, lat = geojson["coordinates"]
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
    time.sleep(1.2)

if all_records:
    df = pd.DataFrame(list(all_records.values())).drop_duplicates(subset=["lat", "lon"])
    df.to_csv(os.path.join(OUT_DIR, "track_a_pathology_candidates.csv"), index=False)
    gdf = gpd.GeoDataFrame(df, geometry=[Point(xy) for xy in zip(df["lon"], df["lat"])], crs="EPSG:4326").to_crs("EPSG:5070")
    gdf.to_file(os.path.join(OUT_DIR, "track_a_pathology_candidates.gpkg"), driver="GPKG")
    print(f"Saved {len(gdf)} candidate records!")
else:
    print("No records matched.")
