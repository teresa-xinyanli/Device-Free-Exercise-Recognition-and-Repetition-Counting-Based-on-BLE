"""Nested session-grouped RF selection; source data is read only."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold, GridSearchCV, ParameterSampler, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from rssi_features import RSSIFeatures

COLS = [f'rssi_{i:02d}' for i in range(20)]
LABELS = ['Fly','JumpingJack','Squat']
SEED = 42

def metrics(y,p):
    return {'accuracy':float(accuracy_score(y,p)), 'balanced_accuracy':float(balanced_accuracy_score(y,p)), 'macro_f1':float(f1_score(y,p,labels=LABELS,average='macro',zero_division=0)), 'confusion_matrix':confusion_matrix(y,p,labels=LABELS).tolist(), 'per_class':classification_report(y,p,labels=LABELS,output_dict=True,zero_division=0)}

def candidates():
    space={'features__mode':['absolute','shape'],'rf__max_depth':[4,8,None], 'rf__min_samples_leaf':[2,4,8], 'rf__max_features':['sqrt',.7], 'rf__class_weight':[None,'balanced_subsample']}
    sampled=list(ParameterSampler(space,n_iter=11,random_state=SEED))
    sampled.insert(0,{'features__mode':'absolute','rf__max_depth':8,'rf__min_samples_leaf':3,'rf__max_features':'sqrt','rf__class_weight':'balanced'})
    return [{k:[v] for k,v in s.items()} for s in sampled]

def search(X,y,g):
    cv=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=SEED).split(X,y,g))
    for tr,te in cv:
        assert set(g[tr]).isdisjoint(g[te])
        assert set(y[tr]) == set(LABELS) and set(y[te]) == set(LABELS)
    pipe=Pipeline([('features',RSSIFeatures()),('rf',RandomForestClassifier(n_estimators=150,random_state=SEED,n_jobs=2,bootstrap=True))])
    return GridSearchCV(pipe,candidates(),cv=cv,scoring='f1_macro',refit=True,n_jobs=1,error_score='raise').fit(X,y)
