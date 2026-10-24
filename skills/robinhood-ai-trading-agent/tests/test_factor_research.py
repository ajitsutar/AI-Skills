import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import factor_research as f


class FactorTests(unittest.TestCase):
    def test_normalization_cutoff_missing_constant(self):
        rows=[{'id':str(i),'sector':'A','available_at':'2026-01-01T00:00:00Z',
               'values':{'x':v,'constant':3}} for i,v in enumerate([1,2,3,None])]
        rows.append({'id':'future','sector':'A','available_at':'2026-01-03T00:00:00Z','values':{'x':10000}})
        r=f.normalize(rows,['x','constant'],'2026-01-02T00:00:00Z',0,1)
        self.assertAlmostEqual(r['rows'][0]['values']['x'],-(1.5)**.5)
        self.assertIsNone(r['rows'][3]['values']['x'])
        self.assertEqual(r['rows'][0]['values']['constant'],0)
        self.assertEqual(r['excluded'][0]['id'],'future')
    def test_regression_known_coefficients(self):
        rng=np.random.default_rng(10)
        x=rng.normal(0,.02,(20,5))
        rows=[dict(timestamp=f'2026-01-{i+1:02d}T00:00:00Z',rf=.001,
                   asset_return=float(.004+row@np.array([1,2,3,4,5])),
                   **dict(zip(['mkt_rf','smb','hml','rmw','cma'],map(float,row)))) for i,row in enumerate(x)]
        r=f.fama_french(rows,'FF5','daily')
        self.assertAlmostEqual(r['alpha_per_period'],.003)
        np.testing.assert_allclose(list(r['betas'].values()),[1,2,3,4,5],atol=1e-12)
        self.assertAlmostEqual(r['r_squared'],1)
        rows[2]['timestamp']=rows[1]['timestamp']
        with self.assertRaises(ValueError): f.fama_french(rows,'FF5','daily')
    def test_factor_variance_conservation(self):
        r=f.style_risk([.5,.5],[[1],[2]],[[.04]],[.01,.09])
        self.assertAlmostEqual(r['factor_variance'],.09)
        self.assertAlmostEqual(r['specific_variance'],.025)
        self.assertAlmostEqual(sum(r['asset_variance_contributions']),.115)
        with self.assertRaises(ValueError): f.style_risk([.5,.5],[[1],[2]],[[-.04]],[.01,.09])
    def test_neutral_scores(self):
        x=[[1],[2],[3],[4]]
        r=f.neutralize([2,1,5,7],x)['residual_scores']
        self.assertAlmostEqual(sum(r),0)
        self.assertAlmostEqual(sum(a*b[0] for a,b in zip(r,x)),0)
    def test_pca_test_does_not_change_fit(self):
        train=[[1,2],[2,4],[3,6]]
        a=f.pca(train,1,test=[[100,200],[0,0]])
        b=f.pca(train,1,test=[[-999,999],[1,1]])
        self.assertEqual(a['components'],b['components'])
        self.assertEqual(a['center'],[2,4])
        self.assertAlmostEqual(a['explained_variance_ratio'][0],1)
        self.assertAlmostEqual(a['train_scores'][1][0],0)
        with self.assertRaises(ValueError): f.pca([[1,1],[1,1]],1)
    def test_clusters_seed_and_test_isolation(self):
        x=[[0,0],[0,1],[10,10],[10,11]]
        r=f.kmeans(x,2,seed=7,test=[[0,.5],[10,10.5]])
        self.assertEqual(r['labels'],[0,0,1,1])
        self.assertEqual(r['test_labels'],[0,1])
        self.assertEqual(r,f.kmeans(x,2,seed=7,test=[[0,.5],[10,10.5]]))
        self.assertEqual(r['centroids_standardized'],f.kmeans(x,2,seed=7)['centroids_standardized'])
    def test_malformed_and_nonfinite(self):
        for rows in ([[1,2],[3]],[[1,float('nan')],[2,3]],[[True,2],[3,4]]):
            with self.assertRaises(ValueError): f.pca(rows,1)
        with self.assertRaises(ValueError): f.kmeans([[1],[1]],2)
    def test_single_observation_and_asset(self):
        self.assertEqual(len(f.pca([[1,2],[2,4]],1,test=[[3,6]])['test_scores']),1)
        self.assertEqual(f.kmeans([[1],[2]],1,test=[[3]])['test_labels'],[0])
        self.assertAlmostEqual(f.style_risk([1],[[2]],[[.04]],[.01])['portfolio_variance'],.17)
    def test_tiny_negative_covariance_cannot_be_levered(self):
        with self.assertRaises(ValueError):
            f.style_risk([.5,.5],[[1e7],[1e7]],[[-1e-13]],[0,0])


if __name__=='__main__': unittest.main()
