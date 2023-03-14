#!/usr/bin/env python
"""
Read allesfitter results and plot ttv
See also
https://github.com/MNGuenther/allesfitter/blob/master/allesfitter/prepare_ttv_fit.py

https://github.com/MNGuenther/allesfitter/blob/master/allesfitter/nested_sampling_output.py#L285
https://github.com/MNGuenther/allesfitter/blob/master/allesfitter/general_output.py#L1130
"""

import os
import sys
import pickle
import gzip
from pathlib import Path
from argparse import ArgumentParser
from tqdm import tqdm
import numpy as np
# import flammkuchen as fk
# import corner
import pandas as pd
from allesfitter import config, allesclass
from allesfitter import nested_sampling_output, general_output
from allesfitter.general_output import plot_ttv_results

# assert allesfitter.__version__[0]=='1.10'

home = Path.home()
sys.path.insert(0, f'{home}/github/research/project/young_ttvs/code')

if __name__=='__main__':
    ap = ArgumentParser()
    ap.add_argument("name", help="directory name", type=str)
    ap.add_argument("-dir", help="base directory", type=str, default=f"{home}/github/research/project/young_ttvs/allesfitter/")
    ap.add_argument("-clobber", help="overwrite files", action="store_true", default=False)
    ap.add_argument("-plot_ttv", help="plot TTVs", action="store_true", default=False)

    args = ap.parse_args(None if sys.argv[1:] else ["-h"])

    datadir = Path(args.dir, args.name)
    
    config.init(datadir)
    f = gzip.GzipFile(os.path.join(config.BASEMENT.outdir,'save_ns.pickle.gz'), 'rb')
    results = pickle.load(f)
    f.close()

    posterior_samples = nested_sampling_output.draw_ns_posterior_samples(results)
    # posterior_params = nested_sampling_output.draw_ns_posterior_samples(results, as_type='dic') # all weighted posterior_samples
    posterior_params_median, posterior_params_ll, posterior_params_ul = general_output.get_params_from_samples(posterior_samples)
    
    # plot TTVs
    if args.plot_ttv:
        print("Plotting TTVs...")
        plot_ttv_results(posterior_params_median, posterior_params_ll, posterior_params_ul)

    # key = 'flux' 
    # inst = 'tess'
    
    # fp_h5 = datadir.joinpath(f"{args.name}_results.h5")
    # if args.clobber:
    
    #     af = allesclass(datadir)
    #     df = {}

    #     #::: load the data (and the correct error bars)
    #     df['time'] = af.data[inst]['time']
    #     df['flux'] = af.data[inst][key]
    #     df['flux_err'] = af.data[inst]['err_scales_'+key] * af.posterior_params_median['err_'+key+'_'+inst]

    #     #::: load the median baseline and median lightcurve model
    #     df['baseline'] = af.get_posterior_median_baseline(inst, key)
    #     df['model'] = af.get_posterior_median_model(inst, key)

    #     #::: compute the detrended flux and the residuals
    #     df['detrended_flux'] = df['flux']-df['baseline']
    #     df['residuals'] = df['flux']-(df['model']+df['baseline'])


    #     df_samples = pd.DataFrame.from_dict(posterior_params)

    #     df_samples['b_epoch'] = df_samples['b_epoch']-2457000

    #     df_samples['aRs'] = 1/df_samples['b_rsuma']
    #     df_samples['inc'] = np.rad2deg(np.arccos(df_samples['b_cosi']))
    #     df_samples['imp_par'] = df_samples['b_cosi']*df_samples['aRs']
    #     df['posterior_samples'] = df_samples
        
    #     print("Saved: ", fp_h5)
    #     fk.save(fp_h5, df)
    # else:
    #     print("Loaded: ", fp_h5)
    #     df = fk.load(fp_h5)

    # cols = ['b_rr', 'aRs', 'imp_par', 'b_epoch', 'b_period']
    # param_labels = ['Rp/Rs', 'a/Rs', 'b', r'T$_0$ [BTJD]', 'P [d]']
    # fig = corner.corner(df['posterior_samples'][cols], 
    #                        labels=param_labels,
    #                        quantiles=[0.16, 0.5, 0.84],
    #                        show_titles=True, 
    #                        title_kwargs={"fontsize": 12},
    #                        title_fmt='.4f',
    # #                      divergences=True
    #                       )
    # fig.suptitle(fig_titles[n])
    # fp_fig = f"../figures/transit_corner_{name}_with_rhostar_prior.png"
    # fig.savefig(fp_fig, bbox_inches="tight")
    # print("Saved: ", fp_fig)