#!/usr/bin/env python
"""
Usage
$python prepare_allesfit.py -toi 1097 -sec all -exp 120

Uses parameter from TOI/CTIO/NExSci databse and
creates a directory with the files needed to run allesfitter:
1. params.csv
2. settings.csv
3. run.py
4. params_star.csv
5. mission.csv e.g. tess.csv, k2.csv, kepler.csv
======
* for precise transit transit timing, some parameters can be fixed
* limb darkening can be fixed to theoretical values derived using ~ldtk~ limbdark;
  assumes feh=(0,0.1) dex if feh is not available 
* uses tess-point to check if target was observed by TESS
(useful to know even if `lightkurve.search_lightcurve` returned None)
* uses aliases (K2 name --> EPIC)
https://exoplanetarchive.ipac.caltech.edu/docs/sysaliases.html
======
TODO: 
1. add priors as args
"""
import sys
# import logging
from typing import Tuple
from argparse import ArgumentParser
from pathlib import Path
from math import ceil
import numpy as np
import lightkurve as lk
import astropy.units as u
import pandas as pd
from astropy.coordinates import SkyCoord
from allesfitter import allesclass#, config, nested_sampling_output, general_output
# from ldtk import LDPSetCreator, BoxcarFilter
from tess_stars2px import tess_stars2px_function_entry
from utils import catalog_info_TIC, get_tfop_info, get_tois, get_ctois, rho_from_mr, as_from_rhop, a_from_rhoprs, get_nexsci, get_name_aliases
try:
    import limbdark as ld
except Exception:
    command = (
        "pip install git+https://github.com/john-livingston/limbdark.git#egg=limbdark"
    )
    raise ModuleNotFoundError(command)

assert lk.__version__[0]=='2'

filter_widths = {
    "gp": (400, 550),
    "V": (480, 600),
    "rp": (560, 700),
    "ip": (700, 820),
    "zs": (825, 920),
    "I+z": (720, 1030),
    "tess": (585, 1050),
}

home = Path.home()
sys.path.insert(0, f'{home}/github/research/project/young_ttvs/code')

cols = ['time','flux','flux_err']

Nsamples = 10_000
planets = "b c d e f g h i j k".split()
quartiles_1sig = [16, 50, 84] #1-sigma
quartiles_3sig = [2.70, 50, 97.3] #3-sigma

def catalog_info_name(df) -> Tuple:
    Teff, Teff_err = df['st_teff'].astype(float), np.sqrt(df['st_tefferr1']**2+df['st_tefferr2']**2)
    logg, logg_err = df['st_logg'].astype(float), np.sqrt(df['st_loggerr1']**2+df['st_loggerr2']**2)
    feh, feh_err = 0, 0.1
    radius, radius_err = df['st_rad'].astype(float), np.sqrt(df['st_raderr1']**2+df['st_raderr2']**2)
    mass, mass_err = df['st_mass'].astype(float), np.sqrt(df['st_masserr1']**2+df['st_masserr2']**2)
    return Teff, Teff_err, logg, logg_err, feh, feh_err, radius, radius_err, mass, mass_err

def parse_target_name(toiid=None, ctoiid=None, name=None, update_db=False) -> Tuple:
    if toiid:
        df = get_tois(clobber=update_db)
        print("Using parameters from TOI database (use --update_db to update).")
        print(f"To use published parameters in NExSci, use -name=TOI-{toiid}")
        key = 'TOI'
        id = str(toiid)
        idx = df[key].apply(lambda x: str(x).split('.')[0]==id)
        source = 'tfop'
        target_name = f'TOI-{id.zfill(4)}'
    if ctoiid:
        print("Using parameters from CTOI database (use --update_db to update).")
        df = get_ctois(clobber=update_db)
        key = 'CTOI'
        id = ctoiid
        idx = df['TIC ID']==int(ctoiid)
        target_name = f'CTOI-{ctoiid}'
        source = 'ctoi'
    if name:
        print("Using parameters from NExSci database (use --update_db to update).")
        df = get_nexsci(clobber=update_db)
        df = df[df['default_flag']==1]
        df['Period (days)'] = df['pl_orbper'].astype(float)
        df['Period (days) err'] = np.sqrt(df['pl_orbpererr1']**2+df['pl_orbpererr2']**2)
        df['Epoch (BJD)'] = df['pl_tranmid'].astype(float)
        df['Epoch (BJD) err'] = 0.1
        df['Depth (ppm)'] = df['pl_trandep'].astype(float)/100*1e6 #% to ppm
        df['Depth (ppm) err'] = 1_000
        df['Duration (hours)'] = df['pl_trandur'].astype(float)
        df['Duration (hours) err'] = np.sqrt(df['pl_trandurerr1'].astype(float)**2+df['pl_trandurerr2'].astype(float)**2)
        key = 'hostname'
        id = name
        target_name = name.strip().replace(' ','')
        idx = df[key]==id
        source = 'nexsci'
    errmsg = f"Coulnd't find {key} {id} in {key} database."
    assert sum(idx)>0, errmsg
    return target_name, df[idx].reset_index(drop=True), source

def get_tess_sectors(target_name: str, df: pd.DataFrame, toiid=None, ctoiid=None, name=None) -> Tuple:
    if toiid or ctoiid:
        #if target is available in TOI,CTOI,or NexSci
        coord = SkyCoord(*df[['RA','Dec']].values[0], unit=('hourangle','deg'))
        ra,dec = coord.ra.deg, coord.dec.deg
        ticid = df['TIC ID'].unique()[0]
    elif name:
        #for other targets
        data_json = get_tfop_info(target_name)
        ra = float(data_json['coordinates']['ra'])
        dec = float(data_json['coordinates']['dec'])
        ticid = int(data_json['basic_info']['tic_id'])
    else:
        raise ValueError('Set toiid, ctoiid, or name.')
    try:
        outID, outEclipLong, outEclipLat, outSec, outCam, outCcd, \
                outColPix, outRowPix, scinfo = tess_stars2px_function_entry(ticid, ra, dec)
    except Exception as e:
        print("Error: ", e)
    return ticid, outSec

def check_if_sector_is_available(target_name: str, given_sector, all_sectors: list) -> str:
    """
    All cases for given_sector=(None, 0, 1, 'all', [1,2], -1)
    Check only if given_sector is non-negative int or list
    """
    if given_sector is None:
        return 'default'
    else:
        assert isinstance(given_sector, list)
        assert isinstance(all_sectors, np.ndarray)
        if len(given_sector)==1:
            if given_sector==['all']:
                return 'all_sector'
            elif given_sector==['-1']:
                return 'last'
            elif given_sector==['0']:
                return 'first'
        #check if given_sector exists if not 'all','0',or '-1'
        idx = np.array([True if int(s) in all_sectors else False for s in given_sector])
        errmsg = f"{target_name} was not observed in sector={np.array(given_sector)[~idx]}\n"
        errmsg += f"Try sector={all_sectors}."
        assert np.all(idx), errmsg
        return 'multi_sector'

def get_tdur(per, rsuma, inc, k, b):
    # transit duration in days
    return per/np.pi*np.arcsin(rsuma/np.sin(inc)*np.sqrt(1+k**2-b**2))

def get_rsuma(tdur, per, inc, k, b):
    # Rstar/a 
    return np.sin(inc) * (np.sin(tdur * np.pi / per) / np.sqrt(1 + k**2 - b**2))

if __name__=='__main__':
    ap = ArgumentParser()
    group1 = ap.add_mutually_exclusive_group(required=True)
    group1.add_argument(
        "-toi",
        help="TOI ID",
        type=int
    )
    group1.add_argument(
        "-ctoi",
        help="CTOI ID",
        type=int
    )
    group1.add_argument(
        "-name",
        help="Name",
        type=str
    )
    group2 = ap.add_mutually_exclusive_group(required=True)
    group2.add_argument("-s", "--sector", nargs='+', help="sector=-1 uses most recent TESS sector (default); try -sector=all to use all", default=None)
    group2.add_argument("-c", "--campaign", help="campaign=-1 uses most recent K2 campaign (default); try -campaign=all to use all", default=None)
    group2.add_argument("-q", "--quarter", help="quarter=-1 uses most recent Kepler quarter (default); try -quarter=all to use all", default=None)
    # ap.add_argument("-s", "--sector", "--sector", nargs='+', help="-sector=-1 uses most recent TESS sector (default); try -sector=all to use all", default=None)
    ap.add_argument("-e", "--exptime", help="exposure time (default=None)", type=float, default=None)
    ap.add_argument("-p", "--pipeline", help="TESS/Kepler data pipeline", type=str, default='spoc')
    ap.add_argument("-f", "--filename", help="filename of lightcurve", type=str, default='tess')
    ap.add_argument("-m", "--mission", type=str, default='tess', choices=['tess','k2','kepler'])
    ap.add_argument("-lc", "--lc_type", help="type of light curve (default=pdcsap)", choices=['pdcsap','sap'], type=str, default='pdcsap')
    ap.add_argument("-sig", "--sigma", help="sigma for removing outliers in (combined) TESS lc", type=float, default=None)
    ap.add_argument("-qb", "--quality", choices=['none','default','hard','hardest'], type=str, default='default')
    ap.add_argument("-dir", help="base directory", type=str, default=".")
    ap.add_argument("-i", "--interactive", help="manually input missing values (default=False)", action="store_true", default=False)
    ap.add_argument("-u", "--update_db", help="update TOI or NExSci database (default=False)", action="store_true", default=False)
    ap.add_argument("-r", "--results_dir", help="path to the results dir of a previous run to be used in params.csv", default=None)
    ap.add_argument("-o", "--overwrite", help="overwrite files (default=False)", action="store_true", default=False)
    ap.add_argument("--debug", action="store_true", default=False)

    args = ap.parse_args(None if sys.argv[1:] else ["-h"])

    toiid = args.toi
    ctoiid = args.ctoi
    name = args.name
    exptime = args.exptime
    basedir = args.dir
    mission = args.mission.lower()
    fn = args.filename
    quality_bitmask = args.quality
    sigma = args.sigma
    results_dir = args.results_dir
    interactive = args.interactive

    if mission=='tess':
        sector = args.sector
    elif mission=='k2':
        campaign = -1 if args.campaign is None else args.campaign
        raise NotImplementedError("TODO")
    elif mission=='kepler':
        quarter = -1 if args.quarter is None else args.quarter
        raise NotImplementedError("TODO")
    
    pipeline = args.pipeline
    lc_type = 'sap_flux' if pipeline=='qlp' else args.lc_type+'_flux'
    debug = args.debug
    
    overwrite = args.overwrite
    update_db = args.update_db

    target_name, target_df, source = parse_target_name(toiid, ctoiid, name, update_db)
    ticid, outSec = get_tess_sectors(target_name, target_df, toiid, ctoiid, name)
    sector_flag = check_if_sector_is_available(target_name, given_sector=sector, all_sectors=outSec)

    outdir = Path(basedir)
    if debug:
        print(target_df)

    try:
        if toiid or ctoiid:
            Teff, Teff_err, logg, logg_err, feh, feh_err, radius, radius_err, mass, mass_err = catalog_info_TIC(int(ticid))
        elif name:
            Teff, Teff_err, logg, logg_err, feh, feh_err, radius, radius_err, mass, mass_err = catalog_info_name(target_df.iloc[0])
        if debug:
            print(Teff, Teff_err, logg, logg_err, feh, feh_err, radius, radius_err, mass, mass_err)
    except Exception as e:
        print("Error", e)
    rhostar_prior = True
    if str(radius)=='nan':
        if interactive:
            radius = float(input("Rstar [Rsun]:"))
            rhostar_prior = False
        else:
            raise ValueError("use --interactive to input value")
    if str(mass)=='nan':
        if interactive:
            mass = float(input("Mstar [Msun]:"))
            rhostar_prior = False
        else:
            raise ValueError("use --interactive to input value")
    if str(radius_err)=='nan':
        radius_err = 0.1
        print(f'Rstar err is nan; setting to 0.1')
    if str(mass_err)=='nan':
        mass_err = 0.1
        print(f'Mstar err is nan; setting to 0.1')
    if debug:
        #print(f"Teff={Teff:.0f}+/-{Teff_err:.0f}, logg={logg:.2f}+/-{logg_err:.2f}, feh={feh:.2f}+/-{feh_err:.2f}")
        print(f"Rs={radius:.2f}+/-{radius_err:.2f}, Ms={mass:.2f}+/-{mass_err:.2f}")

    # band = mission.lower()
    if np.isnan(feh):
        feh = float(input("[Fe/H]: ")) if interactive else 0 #solar metallicity
    if np.isnan(feh_err):
        feh_err = float(input("[Fe/H] err: ")) if interactive else 0.1
    print(f"Using [Fe/H]=({feh},{feh_err}) dex")
    if np.isnan(logg):
        if interactive:
            logg = float(input("logg: "))
        else:
            raise ValueError("use --interactive to input value") #no assumption
    if np.isnan(logg_err):
        logg_err = float(input("logg err: ")) if interactive else 0.1
    print(f"Using logg=({logg:.2f},{logg_err:.2f}) cm/s^2")
    if np.isnan(Teff):
        if interactive:
            Teff = float(input("Teff: "))
        else:
            raise ValueError("use --interactive to input value") #no assumption
    if np.isnan(Teff_err):
        Teff_err = float(input("Teff err: ")) if interactive else 500
    print(f"Using Teff=({Teff:.0f},{Teff_err:.0f}) K")

    q1, q1_err, q2, q2_err = ld.claret(
                                    band='T',
                                    teff=Teff, uteff=Teff_err,
                                    logg=logg, ulogg=logg_err,
                                    feh=feh, ufeh=feh_err,
                                    law='quadratic'
                                )

    if results_dir:
        alles = allesclass(outdir.joinpath(results_dir))
        print("Updating params.csv")

        ###=====Update params.csv=====###
        text = """#name,value,fit,bounds,label,unit,truth\n"""
        for pl in alles.settings['companions_all']:
            rprs_min, rprs, rprs_max = np.percentile(alles.posterior_params[f'{pl}_rr'], q=quartiles_1sig)
            rsuma_min, rsuma, rsuma_max = np.percentile(alles.posterior_params[f'{pl}_rsuma'], q=quartiles_1sig)
            cosi_min, cosi, cosi_max = np.percentile(alles.posterior_params[f'{pl}_cosi'], q=quartiles_1sig)
            Porb_min, Porb, Porb_max = np.percentile(alles.posterior_params[f'{pl}_period'], q=quartiles_1sig)
            epoch_min, epoch, epoch_max = np.percentile(alles.posterior_params[f'{pl}_epoch'], q=quartiles_1sig)
            rprs_err = (rprs_max-rprs_min)/2
            rsuma_err = (rprs_max-rprs_min)/2
            cosi_err = (cosi_max-cosi_min)/2
            Porb_err = (Porb_max-Porb_min)/2
            epoch_err = (epoch_max-epoch_min)/2
            text += f"#companion {pl} astrophysical params,,,,,,\n"
            text += f"#{pl}_rr,{rprs:.4f},1,normal {rprs:.4f} {rprs_err:.4f},$R_{pl} / R_\star$,,\n"
            text += f"#{pl}_rsuma,{rsuma:.4f},1,normal {rsuma:.4f} {rsuma_err:.4f},$(R_\star + R_{pl}) / a_{pl}$,,\n"
            text += f"#{pl}_cosi,{cosi:.2f},1,normal {cosi:.2f} {cosi_err:.2f},$\cos"+"{i_"+pl+"}$,,\n"
            text += f"#{pl}_epoch,{epoch:.6f},1,normal {epoch:.6f} {epoch_err:.6f},$T_"+"{0;"+pl+"}$,BJD,\n"
            text += f"#{pl}_period,{Porb:.6f},1,normal {Porb:.6f} {Porb_err:.6f},$P_b$,d,\n"

            rprs_min, rprs, rprs_max = np.percentile(alles.posterior_params[f'{pl}_rr'], q=quartiles_3sig)
            rsuma_min, rsuma, rsuma_max = np.percentile(alles.posterior_params[f'{pl}_rsuma'], q=quartiles_3sig)
            cosi_min, cosi, cosi_max = np.percentile(alles.posterior_params[f'{pl}_cosi'], q=quartiles_3sig)
            Porb_min, Porb, Porb_max = np.percentile(alles.posterior_params[f'{pl}_period'], q=quartiles_3sig)
            epoch_min, epoch, epoch_max = np.percentile(alles.posterior_params[f'{pl}_epoch'], q=quartiles_3sig)
            text += f"{pl}_rr,{rprs:.4f},1,uniform {rprs_min:.4f} {rprs_max:.4f},$R_{pl} / R_\star$,,\n"
            text += f"{pl}_rsuma,{rsuma:.4f},1,uniform {rsuma_min:.4f} {rsuma_max:.4f},$(R_\star + R_{pl}) / a_{pl}$,,\n"
            text += f"{pl}_cosi,{cosi:.2f},1,uniform {cosi_min:.2f} {cosi_max:.2f},$\cos"+"{i_"+pl+"}$,,\n"
            text += f"{pl}_epoch,{epoch:.6f},1,uniform {epoch_min:.6f} {epoch_max:.6f},$T_"+"{0;"+pl+"}$,BJD,\n"
            text += f"{pl}_period,{Porb:.6f},1,uniform {Porb_min:.6f} {Porb_max:.6f},$P_b$,d,\n"
        text += "#b_f_c,0,0,uniform 0.0 0.0,$\sqrt{e_b} \cos{\omega_b}$,,\n"
        text += "#b_f_s,0,0,uniform 0.0 0.0,$\sqrt{e_b} \sin{\omega_b}$,,\n"
        text += "#limb darkening coefficients per instrument,,,,,,\n"
        q1_min, q1, q1_max = np.percentile(alles.posterior_params[f'host_ldc_q1_{fn}'], q=quartiles_1sig)
        q2_min, q2, q2_max = np.percentile(alles.posterior_params[f'host_ldc_q2_{fn}'], q=quartiles_1sig)
        text += f"host_ldc_q1_{fn},{q1:.2f},1,normal {q1:.2f} {q1_err:.2f},"+f"$q_{{1; \\mathrm{{{fn}}}}}$"+",,\n"
        text += f"host_ldc_q2_{fn},{q2:.2f},1,normal {q2:.2f} {q2_err:.2f},"+f"$q_{{2; \\mathrm{{{fn}}}}}$"+",,\n"
        text += "#errors per instrument,,,,,,\n"
        text += f"ln_err_flux_{fn},-6,1,uniform -10 -1,$\log{{\sigma ({fn})}}$,rel. flux,\n"
        text += "#baseline per instrument,,,,,,\n"
        text += f"baseline_gp_offset_flux_{fn},0,1,uniform -0.1 0.1,$\mathrm{{gp ln \sigma ({fn})}}$,,\n"
        text += f"baseline_gp_matern32_lnsigma_flux_{fn},-5,1,uniform -15 0,$\mathrm{{gp ln \sigma ({fn})}}$,,\n"
        text += f"baseline_gp_matern32_lnrho_flux_{fn},0,1,uniform -1 15,$\mathrm{{gp ln \\rho ({fn})}}$,,\n"
        text += "#TTV companion b,,,,,\n"
        text += "#b_ttv_transit_1,0,1,uniform -0.1 0.1,TTV$_\mathrm{b;1}$,d,\n"
        text += "#TTV companion c,,,,,\n"
        text += "#c_ttv_transit_1,0,1,uniform -0.1 0.1,TTV$_\mathrm{c;1}$,d,\n"
        fp = Path(results_dir, "params2.csv")
        np.savetxt(fp, [text], fmt="%s")
        print("Saved: ", fp)

    else:
        ### Write files ###
        outdir = Path(basedir, target_name)
        try:
            outdir.mkdir(parents=True, exist_ok=overwrite)
        except:
            raise FileExistsError("Use --overwrite to overwrite files.")

        ###=====Create params.csv=====###
        text = """#name,value,fit,bounds,label,unit,truth\n"""
        for i,row in target_df.iterrows():
            pl = planets[i]
            if debug:
                print(f"=====Planet {pl}=====")

            # tic = row['TIC ID']
            Porb = row['Period (days)']
            Porberr = row['Period (days) err']
            epoch = row['Epoch (BJD)']
            epocherr = row['Epoch (BJD) err']
            tdur = row['Duration (hours)']
            tdurerr = row['Duration (hours) err']

            if interactive and not np.all([Porb>0, epoch>0]):
                Porb = float(input("Porb: "))
                Porberr = float(input("Porb err: "))
                epoch = float(input("Epoch: "))
                epocherr = float(input("Epoch err: "))
            else:
                assert np.all([Porb>0, epoch>0])
            Porb_s = np.random.normal(Porb, Porberr, size=Nsamples)

            if debug:
                print(f"P={Porb:.4f}+/-{Porberr:.4f}, T0={epoch:.4f}+/-{epocherr:.4f}")

            rprs = np.sqrt(row['Depth (ppm)']/1e6)
            rprserr = np.sqrt(row['Depth (ppm) err']/1e6)
            if str(rprs)=='nan':
                if interactive:
                    try:
                        rprs = input(f"Planet {pl} Rp/Rs: ")
                        rprs = float(rprs)
                        rprserr = input(f"Planet {pl} Rp/Rs err: ")
                        rprserr = float(rprserr)
                    except Exception as e:
                        msg = f"Error in inputs.\n{e}"
                        raise ValueError(msg)
                elif hasattr(row, 'pl_rade'):
                    try:
                        rprs = row['pl_rade']*u.Rearth.to(u.Rsun)/row['st_rad']
                        Rperr = np.sqrt(row['pl_radeerr1']**2+row['pl_radeerr2']**2)
                        rprserr = Rperr*u.Rearth.to(u.Rsun)/radius_err
                    except Exception as e:
                        msg = f"Error in parsing rp/rs\n{e}"
                        raise ValueError(msg)
                else:
                    msg = "Rp/Rs is nan. Try --interactive for manual input"
                    raise ValueError(msg)
            assert rprs>0

            rprs_s = np.random.normal(rprs, rprserr, size=Nsamples)
            rprs_min, rprs, rprs_max = np.percentile(rprs_s, q=quartiles_3sig)

            mass_s = np.random.normal(mass, mass_err, size=Nsamples)
            radius_s = np.random.normal(radius, radius_err, size=Nsamples)

            # compute a/Rs from stellar density
            rho_s = rho_from_mr(mass_s, radius_s)
            as_s = as_from_rhop(rho_s, Porb_s)
            if debug:
                rhomin, rho, rhomax = np.percentile(rho_s, q=quartiles_3sig)
                as_min, a, as_max = np.percentile(as_s, q=quartiles_3sig)
                a_au_s = a_from_rhoprs(rho_s, Porb_s, radius_s)
                a_au_min, a_au, a_au_max = np.percentile(a_au_s, q=quartiles_3sig)

            #FIXME: as_s produces some NaNs e.g. for Kepler-51
            idx = as_s>0
            rsuma_s = radius_s[idx]/as_s[idx]
            rsuma_min, rsuma, rsuma_max = np.percentile(rsuma_s, q=quartiles_3sig)

            theta = np.arcsin(radius_s/as_s)
            inc_s = np.pi/2 - theta
            #if all(inc_s>np.pi/2):
            #    inc_s = np.random.uniform(np.deg2rad(80), np.deg2rad(90), size=Nsamples)
            inc_min, inc, inc_max = np.percentile(inc_s, q=quartiles_3sig)
            b_s = as_s * np.cos(inc_s)
            b_min, b, b_max = np.percentile(b_s, q=quartiles_3sig)
            if all(b_s>1):
                b_s = np.random.uniform(0, 1, size=Nsamples)
                b = 0

            if str(tdur)!='nan':
                #check if tdur derived from rhostar is consistent with tdur from tfop
                tdur_rhostar= get_tdur(Porb, rsuma, inc, rprs, b)*24
                print(f"tdur={tdur:.1f}h ({source}) {tdur_rhostar:.1f}h (derived from rhostar)")
                #check if tdur derived from orbit is consistent with tdur from tfop
                try:
                    tdurerr = 1 if str(tdurerr)=='nan' else tdurerr
                    tdur_s = np.random.normal(tdur, tdurerr, size=Nsamples)/24
                    rsuma_s = get_rsuma(tdur_s, Porb, inc_s, rprs_s, b_s)
                    tdur_orbit = get_tdur(Porb, np.median(rsuma_s), inc, rprs, b)*24
                    print(f"tdur={tdur:.1f}h ({source}) {tdur_orbit:.1f}h (derived from orbit)")
                    if np.nanargmin(np.abs(np.array([tdur_rhostar, tdur_orbit]) - tdur))==1:
                        print("Using Rstar/a derived from orbit.")
                        rsuma_min, rsuma, rsuma_max = np.percentile(rsuma_s, q=quartiles_3sig)
                    else:
                        print("Using Rstar/a derived from rhostar.")
                except Exception as e:
                    print(e)

            if debug:
                print(f"rsuma={rsuma:.4f}")
                print(f"rprs={rprs:.4f}")
                print(f"rho={rho:.4f}")
                print(f"a_s={a:.4f}")
                print(f"a_au={a_au:.4f}")
                print(f"inc={np.rad2deg(inc):.2f}")
                print(f"b={b:.2f}")
            text += f"#companion {pl} astrophysical params,,,,,,\n"
            text += f"{pl}_rr,{rprs:.4f},1,uniform 0 {ceil(rprs_max*10)/10:.4f},$R_{pl} / R_\star$,,\n"
            text += f"{pl}_rsuma,{rsuma:.4f},1,uniform {rsuma_min:.4f} {ceil(rsuma_max*10)/10:.4f},$(R_\star + R_{pl}) / a_{pl}$,,\n"
            text += f"{pl}_cosi,0,1,uniform 0 1,$\cos"+"{i_"+pl+"}$,,\n"
            text += f"{pl}_epoch,{epoch:.6f},1,normal {epoch:.6f} {epocherr:.6f},$T_"+"{0;"+pl+"}$,BJD,\n"
            text += f"{pl}_period,{Porb:.6f},1,normal {Porb:.6f} {Porberr:.6f},$P_b$,d,\n"
        text += "#b_f_c,0,0,uniform 0.0 0.0,$\sqrt{e_b} \cos{\omega_b}$,,\n"
        text += "#b_f_s,0,0,uniform 0.0 0.0,$\sqrt{e_b} \sin{\omega_b}$,,\n"
        text += "#limb darkening coefficients per instrument,,,,,,\n"
        text += f"host_ldc_q1_{fn},{q1:.2f},1,normal {q1:.2f} {q1_err:.2f},"+f"$q_{{1; \\mathrm{{{fn}}}}}$"+",,\n"
        text += f"host_ldc_q2_{fn},{q2:.2f},1,normal {q2:.2f} {q2_err:.2f},"+f"$q_{{2; \\mathrm{{{fn}}}}}$"+",,\n"
        text += "#errors per instrument,,,,,,\n"
        text += f"ln_err_flux_{fn},-6,1,uniform -10 -1,$\log{{\sigma ({fn})}}$,rel. flux,\n"
        text += "#baseline per instrument,,,,,,\n"
        text += f"baseline_gp_offset_flux_{fn},0,1,uniform -0.1 0.1,$\mathrm{{gp ln \sigma ({fn})}}$,,\n"
        text += f"baseline_gp_matern32_lnsigma_flux_{fn},-5,1,uniform -15 0,$\mathrm{{gp ln \sigma ({fn})}}$,,\n"
        text += f"baseline_gp_matern32_lnrho_flux_{fn},0,1,uniform -1 15,$\mathrm{{gp ln \\rho ({fn})}}$,,\n"
        text += "#TTV companion b,,,,,\n"
        text += "#b_ttv_transit_1,0,1,uniform -0.1 0.1,TTV$_\mathrm{b;1}$,d,\n"
        text += "#TTV companion c,,,,,\n"
        text += "#c_ttv_transit_1,0,1,uniform -0.1 0.1,TTV$_\mathrm{c;1}$,d,\n"
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

        text2+=f"companions_phot,{' '.join(planets[:len(target_df)])}"

        text2+=f"""
companions_rv,
inst_phot,{fn}
inst_rv,
###############################################################################,
# Fit performance settings,
###############################################################################,
multiprocess,True
multiprocess_cores,40
fast_fit,True
fast_fit_width,0.3333333333333333
#fast_fit_width,0.5
secondary_eclipse,False
phase_curve,False
shift_epoch,True
inst_for_b_epoch,all
###############################################################################,
# MCMC settings,
###############################################################################,
mcmc_nwalkers,100
mcmc_total_steps,2000
mcmc_burn_steps,1000
mcmc_thin_by,2
###############################################################################,
# Nested Sampling settings,
###############################################################################,
ns_modus,dynamic
ns_nlive,1000
ns_bound,single
ns_sample,auto
ns_tol,0.01
###############################################################################,
# Limb darkening law per object and instrument,
###############################################################################,
host_ld_law_{fn},quad
#####################################,
# Exposure interpolation settings,
#####################################,
### crucial only for long exposure times,
# t_exp_{fn},0.0208333
# t_exp_n_int_{fn},10
###############################################################################,
# Baseline settings per instrument,
###############################################################################,
#baseline_flux_{fn},sample_offset
#baseline_flux_{fn},hybrid_spline
#baseline_flux_{fn},hybrid_poly_2
baseline_flux_{fn},sample_GP_Matern32
###############################################################################,
# Error settings per instrument,
###############################################################################,
error_flux_{fn},sample
###############################################################################,
# Flares,
###############################################################################,
#N_flares,1
###############################################################################,
# Host density prior,
###############################################################################,\n"""

        text2+=f"use_host_density_prior,{rhostar_prior}"

        text2+=f"""
###################################################,
# Fit TTV,
###################################################,
fit_ttvs,False
###############################################################################,
# Stellar grid per object and instrument,
###############################################################################,
host_grid_{fn},very_sparse
# b_grid_{fn},very_sparse
# c_grid_{fn},very_sparse"""

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
allesfitter.prepare_ttv_fit('.', style='tessplot')

#allesfitter.ns_fit('.')
#allesfitter.ns_output('.')"""

        if debug:
            print(text4)

        fp = outdir.joinpath("run.py")
        np.savetxt(fp, [text4], fmt="%s")
        print("Saved: ", fp)

        query_name = name
        if toiid or ctoiid:
            query_name = f'TIC {ticid}'
        elif name.lower()[:2]=='k2':
            # search epic name or coordinates
            try:
                print("Searching for EPIC name")
                query_name = get_name_aliases(name, key='epic')
            except Exception as e:
                print(e)
        
        all = lk.search_lightcurve(query_name, mission=mission)
        if len(all)>0:
            pipelines = set([i.lower() for i in all.author])
        else:
            raise ValueError("No light curves found.")

        if debug:
            print(all)
            print(pipelines)
        
        idx = [i==pipeline.lower() for i in pipelines]
        if sum(idx)==0:
            errmsg = f"pipeline={pipeline} not in {pipelines}"
            print(all)
            raise ValueError(errmsg)
        print(f"Using {pipeline.upper()} pipeline.")
        result = lk.search_lightcurve(query_name, author=pipeline, exptime=exptime, mission=mission)
        if result:
            sectors = list(map(int, [s.split()[-1] for s in result.mission]))
            unique_sectors = sorted(set(sectors))
            if sector_flag=='all_sector':
                #case: sector='all'
                print(f"Using {len(sectors)} sectors: {sectors}")
                unique_exptimes = result.table.to_pandas().exptime.unique()
                if len(unique_exptimes)>1:
                    errmsg = f"Multiple exposure times are available for `all` sectors:\n{result}.\n"
                    errmsg += f"Try using -exp={unique_exptimes}"
                    raise ValueError(errmsg)
                exptime = unique_exptimes[0] if exptime is None else exptime
                lc = result.download_all(flux_column=lc_type,quality_bitmask=quality_bitmask).stitch()
                print("The lightcurves were not flattened/de-trended to avoid removing transits.")
                assert lc.sector==int(unique_sectors[-1])
                if pipeline=='spoc':
                    lc1 = result.download_all(quality_bitmask=quality_bitmask,flux_column='pdcsap_flux').stitch()
                    lc2 = result.download_all(quality_bitmask=quality_bitmask,flux_column='sap_flux').stitch()
            elif sector_flag=='multi_sector':
                #case: sector int or list
                idx = [str(i) in sector for i in sectors]
                if sum(idx)==0:
                    errmsg = f"{pipeline.upper()} lightcurves for sector={sector} is not available. Try sector={unique_sectors}."
                    raise ValueError(errmsg)

                filtered_result = result[idx]
                unique_exptimes = filtered_result.table.to_pandas().exptime.unique()
                msg = f"Using {len(sectors)} sectors: {sector} (exptime={unique_exptimes} sec).\n"
                if sector_flag!='all_sector':
                    msg += f"Otherwise use sector=({unique_sectors}, all))."
                print(msg)

                if len(sector)>len(filtered_result):
                    errmsg = f"Not all sector={sector} have exptime={exptime} sec.\n"
                    errmsg = f"Try to limit the sectors.\n"
                    raise ValueError(errmsg)
                elif len(sector)<len(filtered_result):
                    errmsg = f"Multiple exposure times are available for the given sector:\n{filtered_result}.\n"
                    errmsg += f"Try using -exp={unique_exptimes}"
                    raise ValueError(errmsg)
                assert len(sector)==len(filtered_result)
                exptime = unique_exptimes[0] if exptime is None else exptime
                lc = filtered_result.download_all(quality_bitmask=quality_bitmask,flux_column=lc_type).stitch()
                print("The lightcurves were not flattened/de-trended to avoid removing transits.")
                assert lc.sector==int(sector[-1])
                if pipeline=='spoc':
                    lc1 = filtered_result.download_all(quality_bitmask=quality_bitmask,flux_column='pdcsap_flux').stitch()
                    lc2 = filtered_result.download_all(quality_bitmask=quality_bitmask,flux_column='sap_flux').stitch()
            else:
                if sector_flag=='first':
                    idx = 0
                    sector = sectors[idx]
                elif sector_flag=='last' or sector_flag=='default':
                    idx = -1
                    sector = sectors[idx]

                filtered_result = result[idx]
                lc = filtered_result.download(quality_bitmask=quality_bitmask,flux_column=lc_type).normalize()
                unique_exptimes = filtered_result.table.to_pandas().exptime.unique()
                exptime = unique_exptimes[0] if exptime is None else exptime
                assert lc.sector==sector
                if pipeline=='spoc':
                    lc1 = filtered_result.download(quality_bitmask=quality_bitmask,flux_column='pdcsap_flux').normalize()
                    lc2 = filtered_result.download(quality_bitmask=quality_bitmask,flux_column='sap_flux').normalize()
            if sigma:
                lc = lc.remove_outliers(sigma=sigma)
                if pipeline=='spoc':
                    lc1 = lc1.remove_outliers(sigma=sigma)
                    lc2 = lc2.remove_outliers(sigma=sigma)
            if pipeline=='spoc':
                ax = lc1.scatter(label='PDCSAP')
                _  = lc2.scatter(ax=ax, label='SAP')
                ax.set_title(f"Sectors: {unique_sectors} exptime={int(exptime)}s")
            else:
                ax = lc.scatter(label=pipeline)
                ax.set_title(f"Sectors: {unique_sectors} exptime={int(exptime)}s")
            secs = 's'.join(map(str, unique_sectors))
            fp = outdir.joinpath(f"{target_name}_{mission}_{pipeline}_s{secs}_exp{int(exptime)}s.png")
            ax.figure.savefig(fp)
            if pipeline=='spoc':
                fp = outdir.joinpath(f"{mission}_{pipeline}_{lc_type.split('_')[0]}_s{secs}_exp{int(exptime)}s.csv")
            else:
                fp = outdir.joinpath(f"{mission}_{pipeline}_s{secs}_exp{int(exptime)}s.csv")
            df = lc.to_pandas()
            df['time'] = df.index + 2457000
            df = df.reset_index(drop=True).sort_values(by='time')
            df = df[cols].dropna()
            df.to_csv(fp, sep=',', header=False, index=False)
            print("Ndata: ", len(df))
            print("Saved: ", fp)
            if debug:
                print(df.head())

