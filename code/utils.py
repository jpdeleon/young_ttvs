import json
import datetime
from pathlib import Path
from itertools import combinations
import urllib.request
import numpy as np
import pandas as pd
from tqdm import tqdm
from astropy.time import Time
import astropy.units as u
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

G = 6.67e-11
D_H = 24.
D_M = 60 * D_H
D_S = 60 * D_M
au             = 1.496e11
msun           = 1.9891e30
rsun           = 0.5*1.392684e9

def get_name_aliases(name, key=None):
    """
    https://exoplanetarchive.ipac.caltech.edu/docs/sysaliases.html
    """
    base = "https://exoplanetarchive.ipac.caltech.edu/cgi-bin/Lookup/nph-aliaslookup.py?objname="
    url = base + name
    html = urllib.request.urlopen(url).read()
    data = json.loads(html)
    aliases = np.array(data['system']['system_info']['alias_set']['aliases'])
    if len(data)>0:
        if key is None:
            return aliases
        else:
            idx = [i.lower()[:len(key)]==key.lower() for i in aliases]
            if sum(idx)>0:
                return aliases[idx][0]
            else:
                errmsg = f"No aliases found for {name} with key {key}"
                raise ValueError(errmsg)
    else:
        errmsg = f"No aliases found for {name}"
        raise ValueError(errmsg)
    
def as_from_rhop(rho, P):
    """Scaled semi-major axis from the stellar density and planet's orbital period.
    Parameters
    ----------
      rho    : stellar density [g/cm^3]
      period : orbital period  [d]
    Returns
    -------
      as : scaled semi-major axis [R_star]
    """
    return (G/(3*np.pi))**(1/3) * ((P * D_S)**2 * 1e3 * rho)**(1/3)

def a_from_rhoprs(rho, P, rstar):
    """Semi-major axis from the stellar density, stellar radius, and planet's orbital period.
    Parameters
    ----------
      rho    : stellar density [g/cm^3]
      period : orbital period  [d]
      rstar  : stellar radius  [R_Sun]
    Returns
    -------
      a : semi-major axis [AU]
    """
    return as_from_rhop(rho, P)*rstar*rsun/au

def rho_from_mr(Mstar, Rstar, 
            R_unit=u.Rsun,
            M_unit=u.Msun,
            return_unit='cgs'):
    """
    Assumes a spherical body.
    
    Parameters
    ----------
    R : array or float
        Body's radius.
    M : array or float
        Body's mass.
    R_unit : astropy unit, optional
        Radius unit. The default is u.Rsun.
    M_unit : array or float, optional
        Mass unit. The default is u.Msun.
    return_unit : str, optional
        Return unit. The default is 'cgs'.
    Returns
    -------
    None.
    """
    #apply units
    Rstar *= R_unit
    Mstar *= M_unit
    
    #calculate
    V = 4./3. * np.pi * Rstar**3
    rho = Mstar / V
    
    #return
    if return_unit == 'cgs':
        return rho.cgs.value
    else:
        return None #TODO
    
def estimate_ttv_super_period_of_first_order_mmr(P1, P2, MMR='2:1'):
    '''
    Estimates the TTV super-period.
    Only works for first order MMRs, e.g., 2:1, 3:2, 4:3, etc.
    Following Eq. 7 of Lithwick+ 2017, https://iopscience.iop.org/article/10.1088/0004-637X/761/2/122/pdf
    
    Parameters
    ----------
    P1 : float
        Orbital period of the inner planet.
    P2 : float
        Orbital period of the outer planet.
    MMR : str, optional
        Mean motion resonance. 
        The larger number must come first.
        The default is '2:1'.
    Returns
    -------
    TTV super-period : float
        The TTV super-period.
    '''
    
    j = int(MMR.split(':')[0])
    return 1. / np.abs( (1.*j/P2) - (1.*(j-1.)/P1) )

def catalog_info_TIC(TIC_ID):
    """Takes TIC_ID, returns stellar information from online catalog using Vizier
    
    Taken from 
    https://github.com/hippke/tls/blob/master/transitleastsquares/catalog.py#L64
    """
    if type(TIC_ID) is not int:
        raise TypeError('TIC_ID ID must be of type "int"')
    try:
        from astroquery.mast import Catalogs
    except:
        raise ImportError("Package astroquery required but failed to import")

    result = Catalogs.query_criteria(catalog="Tic", ID=TIC_ID).as_array()
    Teff = result[0][64]
    Teff_err = result[0][65]
#     logg = result[0][66]
    radius = result[0][70]
    radius_err = result[0][71]
    mass = result[0][72]
    mass_err = result[0][73]
    return Teff, Teff_err, radius, radius_err, mass, mass_err

def get_tois(
    clobber=False,
    outdir="../data",
    verbose=True,
    remove_FP=True,
):
    """Download TOI list from TESS Alert/TOI Release"""
    dl_link = "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv"
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir.joinpath("TOIs.csv")

    if not fp.exists() or clobber:
        msg = f"Downloading TOIs from: {dl_link}"
        if verbose: print(msg)
        d = pd.read_csv(dl_link)
        if remove_FP:
            # remove False Positives
            d = d[d["TFOPWG Disposition"] != "FP"]
            d.to_csv(fp, index=False)
            msg = "TOIs with TFPWG disposition==FP are removed."
            if verbose: print("Saved: ", msg)
    else:
        d = pd.read_csv(fp)
        if verbose: print("Loaded: ", fp)
    return d.sort_values("TOI")


def get_ctois(clobber=True, outdir="../data", verbose=False, remove_FP=True):
    """Download Community TOI list from exofop/TESS.

    Parameters
    ----------
    clobber : bool
        re-download table and save as csv file
    outdir : str
        download directory location
    verbose : bool
        print texts

    Returns
    -------
    d : pandas.DataFrame
        CTOI table as dataframe

    See interface: https://exofop.ipac.caltech.edu/tess/view_ctoi.php
    See also: https://exofop.ipac.caltech.edu/tess/ctoi_help.php
    """
    dl_link = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=csv"
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir.joinpath("CTOIs.csv")

    if not fp.exists() or clobber:
        d = pd.read_csv(dl_link)  # , dtype={'RA': float, 'Dec': float})
        msg = "Downloading {}\n".format(dl_link)
    else:
        d = pd.read_csv(fp).drop_duplicates()
        msg = "Loaded: {}\n".format(fp)
    d.to_csv(fp, index=False)

    # remove False Positives
    if remove_FP:
        d = d[d["User Disposition"] != "FP"]
        msg += "CTOIs with user disposition==FP are removed.\n"
    msg += "Saved: {}\n".format(fp)
    if verbose:
        print(msg)
    d.columns = [c.replace('Error', 'err') for c in d.columns]
    d.columns = [c.replace(' ppm', ' (ppm)') for c in d.columns]
    d.columns = [c.replace('Transit Epoch', 'Epoch') for c in d.columns]
    d.columns = [c.replace('hrs', '(hours)') for c in d.columns]
    return d.sort_values("CTOI")

def get_nexsci_data(table_name="ps", clobber=False):
    """
    ps: self-consistent set of parameters
    pscomppars: a more complete, though not necessarily self-consistent set of parameters
    """
    url = "https://exoplanetarchive.ipac.caltech.edu/docs/API_PS_columns.html"
    print("Column definitions: ", url)
    fp = Path("../data/",f"nexsci_{table_name}.csv")
    if not fp.exists() or clobber:
        print(f"Downloading NExSci {table_name} table...")
        nexsci_tab = NasaExoplanetArchive.query_criteria(table=table_name, where="discoverymethod like 'Transit'")
        df_nexsci = nexsci_tab.to_pandas()
        df_nexsci.to_csv(fp, index=False)
        print("Saved: ", fp)
    else:
        df_nexsci = pd.read_csv(fp)
        print("Loaded: ", fp)
    return df_nexsci

def get_tess_obs_per_year(year):
    url = f"https://tess.mit.edu/tess-year-{year}-observations/"
    tab = pd.read_html(url)[0]
    return tab

def convert_date(x, format1="%m/%d/%y", format2="%Y-%m-%d"):
    return datetime.datetime.strptime(x, format1).date().strftime(format2)

def get_tess_obs_dates(clobber=False):
    "Returns all years of TESS observations"
    fp = Path('/home/jp/github/research/project/young_ttvs/data/tess_obs.csv')
    if not fp.exists() or clobber:
        tabs = []
        print("Downloading data...")
        for n in tqdm([1,2,3,4,5,6], desc="TESS year"):
            tab = get_tess_obs_per_year(n)
            tabs.append(tab)

        df=pd.concat(tabs).reset_index(drop=True)
        df=df.drop('Unnamed: 7', axis=1)
        start = df['Dates'].apply(lambda x: x.split('-')[0])
        end = df['Dates'].apply(lambda x: x.split('-')[1])
        df['start'] = start.apply(convert_date).apply(lambda x: Time(x).jd)
        df['end'] = end.apply(convert_date).apply(lambda x: Time(x).jd)
        df.to_csv(fp, index=False)
        print("Saved: ", fp)
    else:
        df = pd.read_csv(fp, index_col=0)
        #print("Loaded: ", fp)
        #print(df.tail())
    
    return df

def get_sector(bjd):
    df = get_tess_obs_dates().reset_index()
    idx = (bjd>df.start) & (bjd<df.end)
    errmsg = "time not found in TESS sectors"
    assert sum(idx)>0, errmsg
    return df.loc[idx,'Sector'].values[0]

def get_orbit_pairs(N=10, order=1):
    cs = list(combinations(np.arange(1, N), 2))
    cs = [(i,j) for i,j in cs if abs(i-j)==order]
    return cs

def get_resonant_pairs(periods, order=1, tol=0.01):
    """based on period commensurability"""
    periods = sorted(periods)
    Nplanets = len(periods) 
    deltas = []
    resonant = []
    for n in range(Nplanets-1):
        Pout = periods[n+1]
        Pin = periods[n]
        for i,j in get_orbit_pairs(10, order=order):            
            delta = abs((Pout/Pin)*(i/j) - 1)
            if delta<=tol:
                text = f"{j}:{i} | P=({Pout:.2f},{Pin:.2f}) n=({n+1},{n+2}) (delta={delta*100:.2f}%)"
                resonant.append(text)
                deltas.append(delta)
                break
    return resonant, deltas

def impact_parameter_ec(a, i, e, w, tr_sign):
    return a * np.cos(i) * ((1.-e**2) / (1.+tr_sign*e*np.sin(w)))

def d_from_pkaiews(p, k, a, i, e, w, tr_sign=1, kind=14):
    """Transit duration (T14 or T23) from p, k, a, i, e, w, and the transit sign.
    Calculates the transit duration (T14) from the orbital period, planet-star radius ratio, scaled semi-major axis,
    orbital inclination, eccentricity, argument of periastron, and the sign of the transit (transit:1, eclipse: -1).
     Parameters
     ----------
       p  : orbital period         [d]
       k  : radius ratio           [R_Star]
       a  : scaled semi-major axis [R_star]
       i  : orbital inclination    [rad]
       e  : eccentricity           [-]
       w  : argument of periastron [rad]
       tr_sign : transit sign, 1 for a transit, -1 for an eclipse
       kind: either 14 for full transit duration or 23 for total transit duration
     Returns
     -------
       d  : transit duration T14  [d]
     """
    b  = impact_parameter_ec(a, i, e, w, tr_sign)
    ae = np.sqrt(1.-e**2)/(1.+tr_sign*e*np.sin(w))
    ds = 1. if kind == 14 else -1.
    return p/np.pi  * np.arcsin(np.sqrt((1.+ds*k)**2-b**2)/(a*np.sin(i))) * ae

