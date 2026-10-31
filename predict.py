import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent

def load_model(name):
    manifest=json.loads((ROOT/'models/manifest.json').read_text(encoding='utf-8'))
    info=manifest['models'][name];path=ROOT/info['path']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Model checksum mismatch')
    return joblib.load(path),manifest

def main():
    p=argparse.ArgumentParser(description='Classify two-second BLE RSSI windows into three exercise classes.')
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',choices=['global','Person01','Person02','Person03'],default='global');a=p.parse_args()
    model,manifest=load_model(a.model);data=pd.read_csv(a.input)
    cols=manifest['input']['columns']
    if not set(cols).issubset(data.columns):raise ValueError('Input requires rssi_00 through rssi_19')
    x=data[cols].to_numpy(dtype=float)
    if len(x)==0 or not np.isfinite(x).all():raise ValueError('Input must contain finite RSSI values and at least one window')
    result=data[[c for c in ['window_id','subject','source_session'] if c in data]].copy()
    result['prediction']=model.predict(x);scores=model.predict_proba(x)
    for i,c in enumerate(model.classes_):result['score_'+c]=scores[:,i]
    result.to_csv(a.output,index=False)
    print(f'Saved {len(result)} predictions using {a.model}. Idle and repetition counting are not supported.')
if __name__=='__main__':main()
