"""Original offline factor/statistical research. No proprietary model or data bundled."""
from __future__ import annotations
import numpy as np
from quant_common import cli, covariance, integer, require, scalar, timestamp, vector


def matrix(values, name='matrix', columns=None, minimum_rows=1):
    require(isinstance(values, list) and len(values) >= minimum_rows, 'INSUFFICIENT_ROWS:'+name)
    require(isinstance(values[0], list) and values[0], 'COLUMNS_REQUIRED:'+name)
    n = len(values[0]) if columns is None else columns
    return np.array([vector(row, name, n) for row in values])


def normalize(rows, fields, as_of, lower=.01, upper=.99, min_group=3):
    """Cross-sectional, within-sector quantile winsorization then population z score."""
    cutoff = timestamp(as_of)
    lower, upper = scalar(lower, 'lower', 0, 1), scalar(upper, 'upper', 0, 1)
    require(lower < upper, 'QUANTILE_ORDER')
    integer(min_group, 'min_group', 2)
    require(fields and len(set(fields)) == len(fields), 'UNIQUE_FIELDS')
    require(rows and len({r['id'] for r in rows}) == len(rows), 'UNIQUE_ROWS')
    groups, excluded = {}, []
    for row in rows:
        require(isinstance(row.get('sector'), str) and row['sector'].strip(), 'SECTOR_REQUIRED')
        if timestamp(row['available_at']) > cutoff:
            excluded.append({'id':row['id'], 'reason':'NOT_AVAILABLE_AT_CUTOFF'})
            continue
        groups.setdefault(row['sector'], []).append(row)
    results = {r['id']:{'id':r['id'], 'sector':r['sector'], 'values':{}} for g in groups.values() for r in g}
    parameters = []
    for sector, group in sorted(groups.items()):
        for field in fields:
            known = [(r['id'], scalar(r['values'][field], field)) for r in group if r.get('values',{}).get(field) is not None]
            if len(known) < min_group:
                for r in group: results[r['id']]['values'][field] = None
                parameters.append({'sector':sector,'field':field,'n':len(known),'status':'INSUFFICIENT_GROUP'})
                continue
            x = np.array([v for _,v in known])
            lo, hi = np.quantile(x, [lower, upper], method='linear')
            clipped = np.clip(x, lo, hi)
            mean, sd = float(clipped.mean()), float(clipped.std(ddof=0))
            scores = (clipped-mean)/sd if sd > 0 else np.zeros(len(x))
            lookup = {key:float(z) for (key,_),z in zip(known,scores)}
            for r in group: results[r['id']]['values'][field] = lookup.get(r['id'])
            parameters.append({'sector':sector,'field':field,'n':len(x),'clip_lower':float(lo),
                               'clip_upper':float(hi),'mean':mean,'population_std':sd,
                               'status':'CONSTANT_ZERO_SCORE' if sd == 0 else 'COMPUTED'})
    return {'rows':sorted(results.values(),key=lambda r:r['id']),'excluded':excluded,
            'parameters':parameters,'method':'sector-winsor-linear-population-z-v1',
            'as_of':as_of,'lower':lower,'upper':upper,'min_group':min_group,
            'limitation':'Point-in-time supplied membership; no automatic survivorship correction. Missing values are not imputed.'}


def fama_french(rows, model, frequency, units='decimal_return'):
    """Time-series OLS on supplied already constructed FF factor returns, intercept included."""
    require(model in ('FF3','FF5'), 'MODEL_MUST_BE_FF3_OR_FF5')
    require(frequency in ('daily','weekly','monthly','annual'), 'EXPLICIT_RETURN_FREQUENCY')
    require(units == 'decimal_return', 'DECIMAL_RETURNS_REQUIRED')
    names = ['mkt_rf','smb','hml'] + (['rmw','cma'] if model == 'FF5' else [])
    require(len(rows) > len(names)+1, 'INSUFFICIENT_REGRESSION_DF')
    dates = [timestamp(r['timestamp']) for r in rows]
    require(dates == sorted(set(dates)), 'UNIQUE_INCREASING_TIMESTAMPS_REQUIRED')
    # Each row is one aligned observation. Never silently inner-join missing dates.
    x = np.array([[1.] + [scalar(r[n],n) for n in names] for r in rows])
    y = np.array([scalar(r['asset_return'],'asset_return',-1)-scalar(r['rf'],'rf',-1) for r in rows])
    require(np.linalg.matrix_rank(x) == x.shape[1], 'RANK_DEFICIENT_FACTORS')
    beta = np.linalg.lstsq(x,y,rcond=None)[0]
    residual = y-x@beta
    sse = float(residual@residual)
    sst = float(((y-y.mean())**2).sum())
    return {'method':model+'-OLS-excess-return-v1','frequency':frequency,'units':units,
            'observations':len(rows),'alpha_per_period':float(beta[0]),
            'betas':dict(zip(names,map(float,beta[1:]))),'residuals':residual.tolist(),
            'residual_variance':sse/(len(rows)-x.shape[1]),'r_squared':None if sst == 0 else 1-sse/sst,
            'condition_number':float(np.linalg.cond(x)),
            'limitation':'Descriptive in-sample attribution; alpha is not validated predictive skill. Supplied factors must have the same dates, geography and frequency.'}


def style_risk(weights, exposures, factor_covariance, specific_variances):
    """B F B' + diagonal specific variance, original generic factor model, not Barra."""
    w = vector(weights,'weights')
    b = matrix(exposures,'exposures')
    require(len(w)==len(b), 'EXPOSURE_WEIGHT_ROWS')
    f = covariance(factor_covariance,b.shape[1])
    require(np.linalg.eigvalsh(f).min() >= 0, 'NEGATIVE_FACTOR_COVARIANCE_EIGENVALUE')
    d = vector(specific_variances,'specific_variances',len(w),0)
    load = b.T@w
    systematic = float(load@f@load)
    specific = float((w*w)@d)
    require(systematic >= 0, 'NEGATIVE_COMPUTED_FACTOR_VARIANCE')
    total = systematic+specific
    cov = b@f@b.T+np.diag(d)
    contributions = w*(cov@w)
    return {'method':'generic-linear-factor-risk-v1','factor_exposure':load.tolist(),
            'factor_variance':systematic,'specific_variance':specific,'portfolio_variance':total,
            'portfolio_volatility':total**.5,'asset_variance_contributions':contributions.tolist(),
            'limitation':'Input-period variance. Diagonal residual covariance assumed. Not a licensed Barra implementation or factor database.'}


def neutralize(scores, exposures):
    """OLS residual scores neutral to supplied exposures and intercept (not constrained holdings)."""
    y = vector(scores,'scores')
    b = matrix(exposures,'exposures')
    require(len(y)==len(b), 'SCORE_EXPOSURE_ROWS')
    x = np.column_stack([np.ones(len(b)),b])
    require(len(y)>x.shape[1] and np.linalg.matrix_rank(x)==x.shape[1], 'EXPOSURE_RANK_OR_DF')
    beta = np.linalg.lstsq(x,y,rcond=None)[0]
    residual = y-x@beta
    return {'method':'exposure-residualization-v1','residual_scores':residual.tolist(),
            'intercept':float(beta[0]),'coefficients':beta[1:].tolist(),
            'limitation':'Residual scores are not a feasible traded portfolio; apply position, turnover and cost constraints separately.'}


def fit_scaling(train, standardize):
    require(type(standardize) is bool, 'BOOLEAN_STANDARDIZE')
    center = train.mean(axis=0)
    sd = train.std(axis=0,ddof=0) if standardize else np.ones(train.shape[1])
    sd = np.where(sd==0,1.,sd)
    return center,sd,(train-center)/sd


def pca(train, components, test=None, standardize=True):
    """Fit on train only; persisted center/scale/loadings applied unchanged to test."""
    x = matrix(train,'train',minimum_rows=2)
    integer(components,'components',1,min(x.shape))
    center,scale,z = fit_scaling(x,standardize)
    _,s,v = np.linalg.svd(z,full_matrices=False)
    load = v[:components].copy()
    # Deterministic sign convention; repeated eigenvalues still have nonunique bases.
    for row in load:
        if row[np.argmax(np.abs(row))] < 0: row *= -1
    variance = s*s/(len(x)-1)
    total = float(variance.sum())
    require(total > 0, 'NO_PCA_VARIATION')
    return {'method':'train-only-svd-pca-v1','center':center.tolist(),'scale':scale.tolist(),
            'components':load.tolist(),'explained_variance':variance[:components].tolist(),
            'explained_variance_ratio':(variance[:components]/total).tolist(),
            'train_scores':(z@load.T).tolist(),
            'test_scores':None if test is None else (((matrix(test,'test',x.shape[1])-center)/scale)@load.T).tolist(),
            'limitation':'Fit preprocessing inside each training fold. Equal eigenvalues can rotate the basis; compare subspaces, not raw loading signs.'}


def kmeans(train, clusters, seed=0, test=None, standardize=True, max_iter=300, tolerance=1e-8):
    """Seeded k-means++ and Lloyd updates. Empty clusters retained, explicitly disclosed."""
    x = matrix(train,'train',minimum_rows=2)
    integer(clusters,'clusters',1,min(len(x),len(np.unique(x,axis=0))))
    integer(seed,'seed',0);integer(max_iter,'max_iter',1,10000)
    tolerance = scalar(tolerance,'tolerance',0)
    center,scale,z = fit_scaling(x,standardize)
    rng = np.random.default_rng(seed)
    means = [z[int(rng.integers(len(z)))].copy()]
    for _ in range(1,clusters):
        d = np.min(np.sum((z[:,None,:]-np.array(means)[None,:,:])**2,axis=2),axis=1)
        means.append(z[int(rng.choice(len(z),p=d/d.sum()))].copy())
    means = np.array(means)
    converged = False
    empty = []
    for iteration in range(1,max_iter+1):
        labels = np.argmin(((z[:,None,:]-means[None,:,:])**2).sum(axis=2),axis=1)
        new = means.copy();empty=[]
        for c in range(clusters):
            if np.any(labels==c): new[c]=z[labels==c].mean(axis=0)
            else: empty.append(c)
        shift = float(np.max(np.linalg.norm(new-means,axis=1)))
        means = new
        if shift <= tolerance: converged=True;break
    # Canonical centroid ordering avoids arbitrary cluster label permutations.
    order = sorted(range(clusters),key=lambda i:tuple(means[i]))
    means = means[order]
    def assign(a): return np.argmin(((a[:,None,:]-means[None,:,:])**2).sum(axis=2),axis=1)
    labels = assign(z)
    return {'method':'train-only-kmeans-plusplus-v1','seed':seed,'center':center.tolist(),'scale':scale.tolist(),
            'centroids_standardized':means.tolist(),'labels':labels.tolist(),
            'inertia':float(((z-means[labels])**2).sum()),'iterations':iteration,'converged':converged,
            'empty_clusters':[i for i in range(clusters) if not np.any(labels==i)],
            'test_labels':None if test is None else assign((matrix(test,'test',x.shape[1])-center)/scale).tolist(),
            'limitation':'One seeded initialization; grouping is descriptive, not proof of comparable economics or predictive performance.'}


OPERATIONS = {'factor.normalize':normalize,'factor.fama_french':fama_french,
              'factor.style_risk':style_risk,'factor.neutralize':neutralize,
              'factor.pca':pca,'factor.kmeans':kmeans}

if __name__ == '__main__':
    cli(OPERATIONS)
