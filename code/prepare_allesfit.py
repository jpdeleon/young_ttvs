#!/usr/bin/env python
"""
Uses parameter from TOI/CTIO databse and
creates a directory with the files needed to run allesfitter:
1. params.csv
2. settings.csv
3. run.py
4. params_star.csv
5. tess.csv
TODO: add priors as args
"""
import sys
from argparse import ArgumentParser
from pathlib import Path
from utils import *
import numpy as np
import lightkurve as lk
assert lk.__version__[0]=='2'

home = Path.home()
sys.path.insert(0, f'{home}/github/research/project/young_ttvs/code')

cols = ['time','flux','flux_err']

Nsamples = 10_000
planets = "b c d e f g h i j k".split()
# quartiles = [16,50,84] #1-sigma
quartiles = [2.70, 50, 97.3] #3-sigma

if __name__=='__main__':
    ap = ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-toi",
        help="TOI ID",
        type=int
    )
    group.add_argument(
        "-ctoi",
        help="CTOI ID",
        type=int
    )
    ap.add_argument("-dir", help="base directory", type=str, default=f"{home}/github/research/project/young_ttvs/allesfitter/")
    ap.add_argument("-pipeline", help="TESS data pipeline", default="SPOC")
    ap.add_argument("-sector", help="--sector=all uses all sectors", default=None)
    ap.add_argument("-debug", action="store_true", default=False)
    ap.add_argument("-clobber", help="overwrite files", action="store_true", default=False)

    args = ap.parse_args(None if sys.argv[1:] else ["-h"])

    toiid = args.toi
    ctoiid = args.ctoi
    basedir = args.dir
    pipeline = args.pipeline
    debug = args.debug
    sector = args.sector
    clobber = args.clobber

    if args.sector=='all':
        multi_sector = True
    else:
        multi_sector = False

    p_key = 'Period (days)'
    if args.toi:
        df = get_tois()
        key = 'TOI'
        id = str(toiid)
        idx = df[key].apply(lambda x: str(x).split('.')==id)
        name = f'toi{id.zfill(4)}'
    if args.ctoi:
        df = get_ctois()
        key = 'CTOI'
        id = ctoiid
        idx = df['TIC ID']==int(ctoiid)
        name = f'ctoi{ctoiid}'
    errmsg = f"Coulnd't find {key} {id} in {key} database."
    assert sum(idx)>0, errmsg
    d = df[idx].reset_index(drop=True)
    del df
    ticid = d['TIC ID'].unique()[0]

    outdir = Path(basedir, name)
    try:
        outdir.mkdir(parents=True, exist_ok=clobber)
    except:
        raise FileExistsError("Use -clobber to overwrite files.")

    try:
        Teff, Teff_err, radius, radius_err, mass, mass_err = catalog_info_TIC(int(ticid))
    except Exception as e:
        print(e)

    ###=====Create params.csv=====###
    text = """#name,value,fit,bounds,label,unit,truth\n"""
    for i,row in d.iterrows():
        tic = row['TIC ID']
        Porb = row['Period (days)']
        Porberr = row['Period (days) err']
        Porb_s = np.random.normal(Porb, Porberr, size=Nsamples)
        epoch = row['Epoch (BJD)']
        epocherr = row['Epoch (BJD) err']

        pl = planets[i]
        rprs = np.sqrt(row['Depth (ppm)']/1e6)
        rprserr = np.sqrt(row['Depth (ppm) err']/1e6)

        rprs_s = np.random.normal(rprs, rprserr, size=Nsamples)
        rprs_min, rprs, rprs_max = np.percentile(rprs_s, q=quartiles)

        mass_s = np.random.normal(mass, mass_err, size=Nsamples)
        radius_s = np.random.normal(radius, radius_err, size=Nsamples)

        rho_s = rho_from_mr(mass_s, radius_s)
        as_s = as_from_rhop(rho_s, Porb_s)
        if debug:
            rhomin, rho, rhomax = np.percentile(rho_s, q=quartiles)
            as_min, a, as_max = np.percentile(as_s, q=quartiles)
            a_au_s = a_from_rhoprs(rho_s, Porb_s, radius_s)
            a_au_min, a_au, a_au_max = np.percentile(a_au_s, q=quartiles)

        rsuma_s = radius_s/as_s
        rsuma_min, rsuma, rsuma_max = np.percentile(rsuma_s, q=quartiles)

        theta = np.arcsin(radius_s/as_s)
        inc_s = np.pi/2 - theta
        inc_max, inc, inc_min = np.percentile(inc_s, q=quartiles)
        if debug:
            b_s = as_s * np.cos(inc_s)
            b_min, b, b_max = np.percentile(b_s, q=quartiles)

        text += f"#companion {pl} astrophysical params,,,,,,\n"
        text += f"{pl}_rr,{rprs:.4f},1,uniform {0} {rprs_max:.4f},$R_{pl} / R_\star$,,\n"
        text += f"{pl}_rsuma,{rsuma:.4f},1,uniform {rsuma_min:.4f} 0.1,$(R_\star + R_{pl}) / a_{pl}$,,\n"
        text += f"{pl}_cosi,0,1,uniform 0 1,$\cos"+"{i_"+pl+"}$,,\n"
        text += f"{pl}_epoch,{epoch:.2f},1,normal {epoch:.4f} {epocherr:.4f},$T_"+"{0;"+pl+"}$,BJD,\n"
        text += f"{pl}_period,{Porb:.4f},1,normal {Porb:.4f} {Porberr:.4f},$P_b$,d,\n"
        if debug:
            print(pl)
            print(f"rprs={rprs:.4f}")
            print(f"rho={rho:.4f}")
            print(f"a_s={a:.4f}")
            print(f"a_au={a_au:.4f}")
            print(f"rsuma={rsuma:.4f}")
            print(f"inc={np.rad2deg(inc):.2f}")
            print(f"b={b:.2f}")
    text += """b_f_c,0,0,uniform 0.0 0.0,$\sqrt{e_b} \cos{\omega_b}$,,
b_f_s,0,0,uniform 0.0 0.0,$\sqrt{e_b} \sin{\omega_b}$,,
#limb darkening coefficients per instrument,,,,,,
host_ldc_q1_tess,0.5,1,uniform 0.0 1.0,$q_{1; \mathrm{tess}}$,,
host_ldc_q2_tess,0.5,1,uniform 0.0 1.0,$q_{2; \mathrm{tess}}$,,
#errors per instrument,,,,,,
ln_err_flux_tess,-6,1,uniform -10 -1,$\log{\sigma_\mathrm{tess}}$,rel. flux,
#baseline per instrument,,,,,,
baseline_gp_offset_flux_tess,0,1,uniform -0.1 0.1,$\mathrm{gp ln sigma (tess)}$,,
baseline_gp_matern32_lnsigma_flux_tess,-5,1,uniform -15 0,$\mathrm{gp ln sigma (tess)}$,,
baseline_gp_matern32_lnrho_flux_tess,0,1,uniform -1 15,$\mathrm{gp ln rho (tess)}$,,"""
    if debug:
        print(text)
    fp = outdir.joinpath("params.csv")
    np.savetxt(fp, [text], fmt="%s")
    print("Saved: ", fp)

    ###=====Create settings.csv=====###
    text2="""#name,value
###############################################################################,
# General settings,
###############################################################################,\n"""

    text2+=f"companions_phot,{' '.join(planets[:len(d)])}"

    text2+="""
companions_rv,
inst_phot,tess
inst_rv,
###############################################################################,
# Fit performance settings,
###############################################################################,
multiprocess,True
multiprocess_cores,40
fast_fit,True
fast_fit_width,0.3333333333333333
secondary_eclipse,False
phase_curve,False
shift_epoch,True
inst_for_b_epoch,all
###############################################################################,
# MCMC settings,
###############################################################################,
mcmc_nwalkers,100
#mcmc_nwalkers,200
mcmc_total_steps,2000
#mcmc_total_steps,6000
mcmc_burn_steps,1000
#mcmc_burn_steps,1000
#mcmc_thin_by,20
mcmc_thin_by,2
###############################################################################,
# Nested Sampling settings,
###############################################################################,
ns_modus,dynamic
ns_nlive,1000
ns_bound,single
ns_sample,rwalk
ns_tol,0.01
###############################################################################,
# Limb darkening law per object and instrument,
###############################################################################,
host_ld_law_tess,quad
###############################################################################,
# Baseline settings per instrument,
###############################################################################,
#baseline_flux_tess,sample_offset
#baseline_flux_tess,hybrid_spline
#baseline_flux_tess,hybrid_poly_2
baseline_flux_tess,sample_GP_Matern32
###############################################################################,
# Error settings per instrument,
###############################################################################,
error_flux_tess,sample
###############################################################################,
# Stellar grid per object and instrument,
###############################################################################,
host_grid_tess,very_sparse
###############################################################################,
# Flares,
###############################################################################,
#N_flares,1
use_host_density_prior,True
###################################################,
# fit_ttvs
###################################################,
fit_ttvs,False
t_exp,"""

    if debug:
        print(text2)

    fp = outdir.joinpath("settings.csv")
    np.savetxt(fp, [text2], fmt="%s")
    print("Saved: ", fp)

    ###=====Create params_star.csv=====###
    text3=f"""#R_star,R_star_lerr,R_star_uerr,M_star,M_star_lerr,M_star_uerr,Teff_star,Teff_star_lerr,Teff_star_uerr
#R_sun,R_sun,R_sun,M_sun,M_sun,M_sun,K,K,K
{radius:.2f},{radius_err:.2f},{radius_err:.2f},{mass:.2f},{mass_err:.2f},{mass_err:.2f},{Teff:.0f},{Teff_err:.0f},{Teff_err:.0f}"""
    if debug:
        print(text3)

    fp = outdir.joinpath("params_star.csv")
    np.savetxt(fp, [text3], fmt="%s")
    print("Saved: ", fp)

    ###=====Create run.py=====###
    text4="""#!/usr/bin/env python
import allesfitter

fig = allesfitter.show_initial_guess('.')
#allesfitter.prepare_ttv_fit('.')

allesfitter.ns_fit('.')
allesfitter.ns_output('.')"""

    if debug:
        print(text4)

    fp = outdir.joinpath("run.py")
    np.savetxt(fp, [text4], fmt="%s")
    print("Saved: ", fp)


    all = lk.search_lightcurve(f'TIC {ticid}')
    if debug:
        print(all)
    pipelines = [i.lower() for i in all.author]
    idx = [i==pipeline.lower() for i in pipelines]
    if sum(idx)==0:
        errmsg = f"pipeline={pipeline} not in {pipelines}"
        print(all)
        raise ValueError(errmsg)
    print(f"Using {pipeline} pipeline.")
    result = lk.search_lightcurve(f'TIC {ticid}', author=pipeline)
    if result:
        s = map(int, [s.split()[-1] for s in result.mission])
        sectors = sorted(set(s))
        if multi_sector:
            lc = result.download_all().stitch()
            print(f"Using {len(sectors)} sectors: {sectors}")
        else:
            if sector is None:
                idx = 0
                sector = sectors[idx]
            else:
                if sector==-1:
                    idx = -1
                    sector = sectors[idx]
                else:
                    idx = [i==sector for i in sectors]
                    if sum(idx)==0:
                        errmsg = f"sector={sector} is not available in {sectors}"
                        raise ValueError(errmsg)
            msg = f"Using sector={sector}"
            if not multi_sector:
                msg += "; otherwise use -sector=all"
            print(msg)
            lc = result[idx].download().normalize()
            assert lc.sector==sector
        ax = lc.scatter()
        fp = outdir.joinpath(f"{name}_tess.png")
        ax.figure.savefig(fp)
        fp = outdir.joinpath("tess.csv")
        df = lc.to_pandas()
        df['time'] = df.index + 2457000
        df = df[cols].dropna()
        df.to_csv(fp, sep=',', header=False, index=False)
        print("TESS Ndata: ", len(df))
        print("Saved: ", fp)
        if debug:
            print(df.head())
