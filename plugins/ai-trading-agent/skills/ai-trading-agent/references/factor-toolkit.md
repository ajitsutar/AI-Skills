# Reproducible factor research

Use `scripts/factor_research.py INPUT.json`. Input is `{"operation":NAME,"inputs":{...}}`.
The command emits JSON, hashes the input and implementation, and performs no network or broker action.
Call the Python function with the same named inputs for library use. Preserve full numeric outputs;
round only for presentation and record that precision. All numbers must be finite JSON numbers,
not booleans or numeric strings. No implicit percent conversion or annualization is performed.

## Operations and exact conventions

| Operation | Required inputs | Optional inputs / frozen defaults |
|---|---|---|
| `factor.normalize` | `rows`, `fields`, `as_of` | `lower=0.01`, `upper=0.99`, `min_group=3` |
| `factor.fama_french` | `rows`, `model` (`FF3` or `FF5`), `frequency` | `units="decimal_return"` |
| `factor.style_risk` | `weights`, `exposures`, `factor_covariance`, `specific_variances` | None |
| `factor.neutralize` | `scores`, `exposures` | None |
| `factor.pca` | `train`, `components` | `test=null`, `standardize=true` |
| `factor.kmeans` | `train`, `clusters` | `seed=0`, `test=null`, `standardize=true`, `max_iter=300`, `tolerance=1e-8` |

For a cross-model comparison, write every optional argument explicitly in the frozen input.
Use `quant_workbench.py prepare` to materialize these defaults. Models must run the retained
packet rather than substitute their preferred indicator, estimator, or formula variant.

Normalization rows have unique `id`, `sector`, timezone-aware `available_at` and `values` keyed
by `fields`. `as_of` is timezone-aware. Future rows are excluded. Within each sector and field,
compute linear-interpolated quantile bounds, clip observations and use population mean/std
(ddof 0). Missing fields remain null, groups below `min_group` remain null, and a constant
group scores zero with a disclosed status. This is a dated cross-section, not a historical
point-in-time database; the caller must supply membership as it was known at that cutoff.

FF regression rows contain unique increasing timezone-aware `timestamp`, `asset_return`, `rf`,
`mkt_rf`, `smb`, `hml`, and for FF5 `rmw`, `cma`. All returns are decimals for the same declared
period. Regress asset_return minus rf on an intercept and the supplied factor returns.
Do not subtract rf again from mkt_rf or the long/short factors. Alpha is per input period.
Missing dates/factors, rank deficiency and insufficient residual degrees of freedom fail.
The helper neither downloads French data nor reconstructs factor portfolios from accounting ratios.

Style risk implements `w' (B F B' + diag(d)) w`. Exposures are asset-by-factor;
covariance and specific variances use one common period. Negative covariance eigenvalues
are rejected, including tiny negatives; no silent PSD repair or variance flooring is performed.
Specific residuals are assumed
uncorrelated. Weights may be signed and need not sum to one. Neutralization removes the
linear fit on supplied exposures plus an intercept; resulting scores are not constrained holdings.
This is an original generic factor model, **not MSCI Barra**, and includes no proprietary
factor estimates, data or licensed Barra implementation.

PCA uses training means and optional population-standard-deviation scaling, replacing zero
scales by one. SVD eigenvalues use ddof 1. Each loading's largest absolute entry is positive.
Test data never refits preprocessing. Repeated eigenvalues allow different equivalent bases:
compare reconstruction/subspaces rather than requiring identical loadings across BLAS versions.
K-means uses one seeded NumPy PCG64 k-means++ initialization, Lloyd updates and canonical
lexicographic centroid ordering. It reports convergence and empty clusters. Supplied train/test
training arrays have at least two rows; test arrays can contain a single observation.
The caller owns temporal splitting and feature availability.
Neither method predicts returns. Do not label clusters as validated economic peer groups.

## Example

Run `python scripts/factor_research.py examples/factor-normalize.json`.
For the three fictional observations 1, 2, 3 with clipping disabled, output z scores are
`[-sqrt(1.5), 0, sqrt(1.5)]`. The constant feature scores zero.

## Sources and provenance

All package code here is an original implementation of mathematical methods; no vendor or
third-party source code, datasets or model weights were copied.

- [Kenneth French factor definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html): factor meaning and excess-return convention.
- [NumPy SVD](https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html): numerical primitive; NumPy is an existing BSD-3-Clause dependency.
- [PCA reference documentation](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html): method context only; scikit-learn code is not copied or required.
- Arthur and Vassilvitskii, *k-means++: The Advantages of Careful Seeding*, SODA 2007: distance-squared initialization. Original implementation, not copied code.

Deep recurrent models, RL and proprietary risk-model replication are not required for this
workflow and are not bundled. Method complexity does not establish predictive advantage.
