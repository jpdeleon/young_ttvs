from pathlib import Path
import numpy as np
from itertools import combinations

import pandas as pd
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

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
    return d.sort_values("CTOI")

def get_nexsci_data(table_name="ps", clobber=False):
    """
    ps: self-consistent set of parameters
    pscomppars: a more complete, though not necessarily self-consistent set of parameters
    """
    url = "https://exoplanetarchive.ipac.caltech.edu/docs/API_PS_columns.html"
    print("Column definitions: ", url)
    fp = f"../data/nexsci_{table_name}.csv"
    if clobber:
        nexsci_tab = NasaExoplanetArchive.query_criteria(table=table_name, where="discoverymethod like 'Transit'")
        df_nexsci = nexsci_tab.to_pandas()
        df_nexsci.to_csv(fp, index=False)
        print("Saved: ", fp)
    else:
        df_nexsci = pd.read_csv(fp)
        print("Loaded: ", fp)
    return df_nexsci

def get_orbit_pairs(N=10, order=1):
    cs = list(combinations(np.arange(1, N), 2))
    cs = [(i,j) for i,j in cs if abs(i-j)==order]
    return cs

def get_resonant_pairs(periods, order=1, tol=0.01):
    """based on period commensurability"""
    periods = sorted(periods)
    Nplanets = len(periods) 
    
    resonant = []
    for n in range(Nplanets-1):
        Pout = periods[n+1]
        Pin = periods[n]
        for i,j in get_orbit_pairs(10, order=order):            
            delta = abs((Pout/Pin)*(i/j) - 1)
            if delta<=tol:
                text = f"{j}:{i} | P=({Pout:.2f},{Pin:.2f}) n=({n+1},{n+2}) (delta={delta*100:.2f}%)"
                resonant.append(text)
                break
    return resonant
