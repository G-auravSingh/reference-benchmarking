from __future__ import annotations
import math

# These are the thresholds used by the supplied Nandoshi notebook/report.
# They are retained as a compatibility layer, not presented as newly validated thresholds.
PROTOCOL_A = {
    'tspi': {'breaks':[-0.10,0.00,0.10,0.20], 'scores':[1,2,3,4,5]},
    'sabf': {'breaks':[0.05,0.15,0.30,0.50], 'scores':[1,2,3,4,5]},
    'wcpi': {'breaks':[0.20,0.40,0.60,0.80], 'scores':[5,4,3,2,1]},
    'wsdi': {'breaks':[0.20,0.40,0.60,0.80], 'scores':[1,2,3,4,5]},
    'rci': {'breaks':[0.10,0.30,0.50,0.70], 'scores':[5,4,3,2,1]},
    'riparian_ndvi_trend': {'breaks':[-0.05,-0.02,0.00,0.02], 'scores':[5,4,3,2,1]},
    'jrc_water_persistence': {'breaks':[0.20,0.40,0.60,0.80], 'scores':[5,4,3,2,1]},
}
LABELS={1:'VL',2:'L',3:'M',4:'H',5:'VH'}

def protocol_a(name,value):
    if value is None or not math.isfinite(float(value)) or name not in PROTOCOL_A: return None
    v=float(value); spec=PROTOCOL_A[name]
    for b,s in zip(spec['breaks'],spec['scores']):
        if v < b: return s
    return spec['scores'][-1]

def son_score(scores):
    vals=[float(x) for x in scores if x is not None]
    if not vals: return None
    n=len(vals)
    return (sum(vals)-n)/(n*4)*10
