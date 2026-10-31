import argparse,json
from pathlib import Path
import numpy as np,pandas as pd,joblib
from training_core import COLS,search,metrics

ROOT=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--skip-evaluation',action='store_true');a=p.parse_args()
    raw=pd.read_csv(a.data/'training_windows.csv');policy=json.loads((ROOT/'evaluation/data_policy.json').read_text(encoding='utf-8'))
    required=set(COLS+['window_id','source_file','source_session','subject','action'])
    if not required.issubset(raw.columns):raise ValueError('Required data and metadata columns are missing')
    d=raw[~raw.action.isin(policy['excluded_actions'])].reset_index(drop=True)
    if set(d.action)!={'Fly','JumpingJack','Squat'} or d.window_id.duplicated().any() or not np.isfinite(d[COLS]).all().all():raise ValueError('Invalid exercise dataset')
    clean=d[~d.source_file.isin(policy['excluded_source_files'])].reset_index(drop=True)
    a.output.mkdir(parents=True,exist_ok=True);report={'classes':sorted(set(d.action)),'training_windows':len(clean),'results':{}}
    protocols=json.loads((ROOT/'evaluation/splits.json').read_text(encoding='utf-8'))
    if not a.skip_evaluation:
        for name,definition in protocols.items():
            pop=d if definition['subject'] is None else d[d.subject==definition['subject']].reset_index(drop=True)
            pred=np.empty(len(pop),dtype=object);coverage=np.zeros(len(pop),int)
            expected=set(s for fold in definition['folds'] for s in fold['test_sessions'])
            if set(pop.source_session)!=expected:raise ValueError('Exercise sessions differ from the published partitions; provide the matching data')
            for fold in definition['folds']:
                tr=pop.source_session.isin(fold['train_sessions'])&~pop.source_file.isin(policy['excluded_source_files']);te=pop.source_session.isin(fold['test_sessions'])
                training=pop[tr];test=pop[te]
                if not set(training.source_session).isdisjoint(test.source_session):raise ValueError('Recording overlap')
                fitted=search(training[COLS].to_numpy(),training.action.to_numpy(),training.source_session.to_numpy())
                pred[te]=fitted.predict(test[COLS].to_numpy());coverage[te]+=1
            if not np.all(coverage==1):raise ValueError('Incomplete held-out coverage')
            report['results'][name]=metrics(pop.action,pred)
            pop[['window_id','source_session','subject','action']].assign(prediction=pred).to_csv(a.output/(name+'_held_out_predictions.csv'),index=False)
    for name,pop in [('global',clean)]+list(clean.groupby('subject')):
        selection=search(pop[COLS].to_numpy(),pop.action.to_numpy(),pop.source_session.to_numpy())
        joblib.dump(selection.best_estimator_,a.output/(name+'_rf.joblib'))
    clean.to_csv(a.output/'training_windows_filtered.csv',index=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Refit complete. Full-data training predictions are not held-out evaluation scores.')
if __name__=='__main__':main()
