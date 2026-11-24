# Jackalope GIS & Wildlife Epidemiology — Development Log

## Entry 1: Environment Setup & Automated Data Acquisition
* **Date:** [November 24, 2026]
* **Goal:** Automate downloading and cleaning lagomorph host, tick vector, and symptomatic rabbit records from GBIF and iNaturalist.
* **Tools Used:** Python (`requests`, `pandas`, `geopandas`), GBIF REST API, iNaturalist API.
* **Key Decisions:** Filtered out observations with >5,000 m coordinate uncertainty and reprojected outputs from WGS84 (EPSG:4326) to NAD83 Conus Albers (EPSG:5070) for equal-area modeling.
* **Next Step:** Load `.gpkg` layers into QGIS and visually inspect `photo_url` links in `track_a_pathology_candidates.csv` to verify true papilloma lesions.

---

## Entry 2: Debugging & Executing Track A Automated Data Pull
* **Date:** November 24, 2026
* **Goal:** Run `fetch_track_a_data.py` in OSGeo4W Shell to pull and reproject GBIF host/vector points and iNaturalist symptomatic lagomorph records.
* **Issues Resolved:**
  * Fixed a `403 Client Error` by updating endpoints to `api.gbif.org/v1/occurrence/search` and `api.inaturalist.org/v1/observations` and adding a custom `User-Agent` request header.
  * Fixed indentation and added `records = response.json().get("results", [])` to parse the GBIF JSON response cleanly.
* **Outputs Generated (EPSG:5070):**
  * `track_a_hosts.gpkg` & `.csv` (789 deduplicated lagomorph host records across *Sylvilagus floridanus*, *S. audubonii*, and *Lepus townsendii*).
  * `track_a_vectors.gpkg` & `.csv` (4 *Haemaphysalis leporispalustris* rabbit tick records to supplement county-level CDC surveillance data).
  * `track_a_pathology_candidates.gpkg` & `.csv` (iNaturalist keyword-filtered symptomatic lagomorph observations).
* **Next Step:** Load the new GeoPackages into QGIS 4.2.3 on the Surface Pro to verify spatial alignment and visually inspect `photo_url` links for confirmed Shope papillomavirus lesions.

---

## Entry 3: Refining iNaturalist Query & Retrieving 285 Candidate Sightings
* **Date:** November 24, 2026
* **Goal:** Resolve zero-match return on iNaturalist symptomatic lagomorph query.
* **Fix:** Switched from `taxon_name="Lagomorpha"` to numeric `taxon_id=43094`, expanded bounding box to North America, and added layperson search terms (`"jackalope"`, `"growth"`, `"horns"`, `"warts"`).
* **Result:** Saved `track_a_pathology_candidates.gpkg` & `.csv` with **285 candidate observations** in EPSG:5070.

---

## Entry 4: Multi-Raster Standardization & Spatial Suitability Modeling
* **Date:** November 24, 2026
* **Goal:** Align CEC 30m land cover, PRISM 30-year mean temperature, and NASA 28-year combined lightning climatology (`COMB_OTD_TRMM_ISS_AnnualMean.hdf`) onto a 1 km EPSG:5070 Albers grid and compute suitability indices.
* **Technical Solutions:**
  * Built recursive file-discovery helpers in `Run_Suitability_Pipeline.py` to locate nested `.tif` and `.hdf` rasters automatically.
  * Extracted NASA HDF4 subdataset `:0` directly into a NumPy array via GDAL (`ReadAsArray()`) and reprojected onto the master Albers grid alongside 50 km host and 75 km vector Gaussian Kernel Density surfaces.
* **Outputs Generated (`rasters/processed/`):**
  * `track_a_epidemiological_risk.tif` (Shope papillomavirus suitability surface).
  * `track_b_folklore_suitability.tif` (Jackalope folklore habitat & electrical-storm surface).
  * `validated_pathology_points.gpkg` (285 candidate sightings enriched with sampled `viral_risk_score` values).
* **Next Step:** Open QGIS 3.44, load the two suitability GeoTIFFs and validation points, and build a bivariate choropleth map comparing real viral ecology against folklore habitat.
