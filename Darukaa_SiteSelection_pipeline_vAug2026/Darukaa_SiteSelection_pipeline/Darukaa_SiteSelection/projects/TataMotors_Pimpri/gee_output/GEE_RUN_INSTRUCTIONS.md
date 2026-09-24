# GEE run instructions — TataMotors_Pimpri

Archetype: conservation (contiguous)

1. Go to code.earthengine.google.com
2. Assets tab -> NEW -> Table Upload -> Shapefile
   -> select gee_output/TataMotors_Pimpri_gee_upload.zip
   (a zipped .shp/.shx/.dbf/.prj — GEE's uploader does not accept raw
   .geojson/.json directly; this file was generated for you and verified
   readable before being written)
3. Name the asset (suggested: `tatamotors_pimpri_candidates`),
   wait for the upload task to finish (Tasks tab, yellow -> green)
4. Open gee_output/TataMotors_Pimpri_ready_to_run.js — this is a ready-to-paste copy of the
   shared script with CANDIDATE_SCHEMA and RUN_SEGMENTATION already set
   correctly for this project's archetype. Paste it into a new GEE script.
5. Find the ASSET_PATH line near the top and paste in the full asset path
   from step 3. This is the ONLY line that needs manual editing — it can't
   be pre-filled because the asset doesn't exist until step 3 runs.
6. Set EXPORT_NAME = "gee_covariates_output" and
   DRIVE_FOLDER = "tatamotors_pimpri_gee" if not already set.
7. Run the script, open the Tasks tab, click Run on the export task
8. Once complete, download the CSV from Google Drive
9. Place it at: projects/TataMotors_Pimpri/gee_output/gee_covariates_output.csv
10. Re-run: python covariate_ingest.py projects/TataMotors_Pimpri

Note: no aquatic export for this project — either it's agroforestry
(aquatic is never generated for that archetype) or no
water_feature_placemark_names are configured. WATERBODY_ASSET_PATH is left
as "" in the pasted script, so the aquatic section is skipped entirely,
not defaulted to any other project's waterbodies (see the script's own
history note on that bug).
