import sys,json,hashlib,tempfile,subprocess,unittest
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from predict import load_model

class ReleaseTests(unittest.TestCase):
    def test_all_models_match_manifest_and_contract(self):
        manifest=json.loads((ROOT/'models/manifest.json').read_text(encoding='utf-8'))
        data=pd.read_csv(ROOT/'examples/format_example.csv').to_numpy()
        for name in manifest['models']:
            model,_=load_model(name)
            self.assertEqual(list(model.classes_),['Fly','JumpingJack','Squat'])
            self.assertEqual(len(model.predict(data)),3)
            self.assertTrue(np.allclose(model.predict_proba(data).sum(axis=1),1))
    def test_prediction_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'predictions.csv'
            subprocess.run([sys.executable,str(ROOT/'predict.py'),'--input',str(ROOT/'examples/format_example.csv'),'--output',str(output)],check=True,capture_output=True)
            result=pd.read_csv(output)
            self.assertEqual(len(result),3)
            self.assertNotIn('Idle',set(result.prediction))
            self.assertTrue(np.allclose(result.filter(like='score_').sum(axis=1),1))
if __name__=='__main__':unittest.main()
