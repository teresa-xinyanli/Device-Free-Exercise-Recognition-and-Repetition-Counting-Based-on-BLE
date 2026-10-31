import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

FEATURE_NAMES = ['mean','std','min','max','range','q25','median','q75','mean_abs_deviation','mean_abs_step','step_std','slope','autocorr1','autocorr2','autocorr3','autocorr4','autocorr5','low_frequency_ratio','high_frequency_ratio']

class RSSIFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, mode='absolute'):
        self.mode = mode

    def fit(self, X, y=None):
        self.n_features_in_ = 20
        return self

    def transform(self, X):
        x = np.asarray(X, dtype=float)
        if x.ndim != 2 or x.shape[1] != 20 or not np.isfinite(x).all():
            raise ValueError('Expected finite RSSI array of shape (n_windows, 20), sampled at 10 Hz.')
        if self.mode not in ['absolute', 'shape']:
            raise ValueError('Unknown feature mode')
        c = x - x.mean(1,keepdims=True)
        diff = np.diff(x,axis=1)
        energy = abs(np.fft.rfft(c,axis=1))**2
        t = np.linspace(-1,1,20)
        cols = [x.mean(1),x.std(1),x.min(1),x.max(1),np.ptp(x,axis=1),*np.quantile(x,[.25,.5,.75],axis=1),np.mean(abs(c),axis=1),np.mean(abs(diff),axis=1),diff.std(1),c@t/(t@t)]
        cols += [np.sum(c[:,:-lag]*c[:,lag:],axis=1)/(np.sum(c*c,axis=1)+1e-9) for lag in range(1,6)]
        cols += [energy[:,1:4].sum(1)/(energy[:,1:].sum(1)+1e-9),energy[:,4:].sum(1)/(energy[:,1:].sum(1)+1e-9)]
        result = np.asarray(cols).T
        return result if self.mode == 'absolute' else result[:,self.indices()]

    def indices(self):
        return [i for i in range(19) if i not in [0,2,3,5,6,7]]

    def get_feature_names_out(self, input_features=None):
        names = np.asarray(FEATURE_NAMES)
        return names if self.mode == 'absolute' else names[self.indices()]
