# Author: Raphael Vallat <raphaelvallat9@gmail.com>
# Date: April 2018
import numpy as np
import pandas as pd
from pingouin import (compute_effsize, _remove_rm_na, _extract_effects,
                      multicomp)

__all__ = ["pairwise_ttests"]

def _append_stats_dataframe(stats, x, y, xlabel, ylabel, effects, paired, alpha,
                            t, p, ef, eftype, time=np.nan):
    stats = stats.append({
                        'A': xlabel,
                        'B': ylabel,
                        'mean(A)': np.mean(x),
                        'mean(B)': np.mean(y),
                        # Use ddof=1 for unibiased estimator (pandas default)
                        'std(A)': np.std(x, ddof=1),
                        'std(B)': np.std(y, ddof=1),
                        'Type': effects,
                        'Paired': paired,
                        # 'Alpha': alpha,
                        'T-val': t,
                        'p-unc': p,
                        'Eff_size': ef,
                        'Eff_type': eftype,
                        'Time': time}, ignore_index=True)
    return stats


def pairwise_ttests(dv=None, between=None, within=None, effects='all',
                    data=None, alpha=.05, tail='two-sided', padjust='none',
                    effsize='hedges', return_desc=True, remove_nan=True):
    '''Pairwise T-tests.

    Parameters
    ----------
    dv : string
        Name of column containing the dependant variable.
    between: string
        Name of column containing the between factor.
    within : string
        Name of column containing the within factor.
    data : pandas DataFrame
        DataFrame
    alpha : float
        Significance level
    tail : string
        Indicates whether to return the 'two-sided' or 'one-sided' p-values
    p-adjust : string
        Method used for testing and adjustment of pvalues. Available methods are ::

        'none' : no correction
        'bonferroni' : one-step correction
        'holm' : step-down method using Bonferroni adjustments
        'fdr_bh' : Benjamini/Hochberg FDR correction
        'fdr_by' : Benjamini/Yekutieli FDR correction
    effsize : string or None
        Effect size type. Available methods are ::

        'none' : no effect size
        'cohen' : Unbiased Cohen d
        'hedges' : Hedges g
        'glass': Glass delta
        'eta-square' : Eta-square
        'odds-ratio' : Odds ratio
        'AUC' : Area Under the Curve
    return_desc : boolean
        If True, return group means and std

    Returns
    -------
    stats : DataFrame
        Stats summary
    '''
    from itertools import combinations
    from scipy.stats import ttest_ind, ttest_rel

    effects = 'within' if between is None else effects
    effects = 'between' if within is None else effects

    if tail not in ['one-sided', 'two-sided']:
        raise ValueError('Tail not recognized')

    if not isinstance(alpha, float):
        raise ValueError('Alpha must be float')

    # Check NA in repeated measurements
    if within is not None and data[dv].isnull().values.any():
        data = _remove_rm_na(dv=dv, between=between, within=within, data=data)

    # Extract main effects
    dt_array, nobs = _extract_effects(dv=dv, between=between, within=within,
                                     effects=effects, data=data)

    stats = pd.DataFrame([])

    # OPTION A: simple main effects
    if effects.lower() in ['within', 'between']:
        # Compute T-tests
        paired = True if effects == 'within' else False

        # Extract column names
        col_names = list(dt_array.columns.values)

        # Number and labels of possible comparisons
        if len(col_names) >= 2:
            combs = list(combinations(col_names, 2))
            ntests = len(combs)
        else:
            raise ValueError('Data must have at least two columns')

        # Initialize vectors
        for comb in combs:
            col1, col2 = comb
            x = dt_array[col1].dropna().values
            y = dt_array[col2].dropna().values
            t, p = ttest_rel(x, y) if paired else ttest_ind(x, y)
            ef = compute_effsize(x=x, y=y, eftype=effsize, paired=paired)
            stats = _append_stats_dataframe(stats, x, y, col1, col2, effects,
                                            paired, alpha, t, p, ef, effsize)

    # OPTION B: interaction
    if effects.lower() == 'interaction':
        paired = False
        for time, sub_dt in dt_array.groupby(level=0, axis=1):
            col1, col2 = sub_dt.columns.get_level_values(1)
            x = sub_dt[(time, col1)].dropna().values
            y = sub_dt[(time, col2)].dropna().values
            t, p = ttest_rel(x, y) if paired else ttest_ind(x, y)
            ef = compute_effsize(x=x, y=y, eftype=effsize, paired=paired)
            stats = _append_stats_dataframe(stats, x, y, col1, col2, effects,
                                            paired, alpha, t, p, ef, effsize,
                                            time)

    if effects.lower() == 'all':
        stats_within = pairwise_ttests(dv=dv, within=within, effects='within',
                            data=data, alpha=alpha, tail=tail, padjust=padjust,
                            effsize=effsize)
        stats_between = pairwise_ttests(dv=dv, between=between,
                            effects='between', data=data, alpha=alpha,
                            tail=tail, padjust=padjust, effsize=effsize)

        stats_interaction = pairwise_ttests(dv=dv, within=within,
                            between=between, effects='interaction', data=data,
                            alpha=alpha, tail=tail, padjust=padjust,
                            effsize=effsize)
        stats = pd.concat([stats_within, stats_between,
                                stats_interaction]).reset_index()

    # Tail and multiple comparisons
    if tail == 'one-sided':
        stats['p-unc'] *= .5
        stats['Tail'] = 'one-sided'
    else:
        stats['Tail'] = 'two-sided'

    # Multiple comparisons
    padjust = None if stats['p-unc'].size <= 1 else padjust
    if padjust is not None:
        if padjust.lower() is not 'none':
            reject, stats['p-corr'] = multicomp(stats['p-unc'].values,
                                                alpha=alpha, method=padjust)
            stats['p-adjust'] = padjust
            # stats['reject'] = reject
    else:
        stats['p-corr'] = None
        stats['p-adjust'] = None
        # stats['reject'] = stats['p-unc'] < alpha

    # stats['reject'] = stats['reject'].astype(bool)
    stats['Paired'] = stats['Paired'].astype(bool)

    if not return_desc:
        stats[['mean(A)', 'mean(B)', 'std(A)', 'std(B)']] = np.nan

    # Reorganize column order
    col_order = ['Time', 'A', 'B', 'mean(A)', 'std(A)', 'mean(B)', 'std(B)',
                 'Type', 'Paired', 'Alpha', 'T-val', 'Tail', 'p-unc', 'p-corr',
                 'p-adjust', 'reject', 'Eff_size', 'Eff_type']

    stats = stats.reindex(columns=col_order)
    stats.dropna(how='all', axis=1, inplace=True)
    return stats