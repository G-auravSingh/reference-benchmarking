#!/usr/bin/env python
import argparse, logging
import ee
from darukaa_adaptive.config import LakeConfig
from darukaa_adaptive.lake_pipeline import LakePipeline

p=argparse.ArgumentParser(description='Darukaa Adaptive Lake Assessment — KML only')
p.add_argument('--kml',required=True)
p.add_argument('--gee-project',required=True)
p.add_argument('--year',type=int,default=2025)
p.add_argument('--out',default='./output')
p.add_argument('--riparian-buffer-m',type=float,default=100.0)
args=p.parse_args()
logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
ee.Authenticate()
ee.Initialize(project=args.gee_project)
cfg=LakeConfig(gee_project=args.gee_project,assessment_year=args.year,output_dir=args.out,riparian_buffer_m=args.riparian_buffer_m)
r=LakePipeline(cfg).run(args.kml,args.out)
print(f"Completed: {r['profile']}; area={r['site_area_ha_local']:.4f} ha; SoN={r['son']['score']}")
