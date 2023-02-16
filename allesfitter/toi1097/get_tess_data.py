#!/usr/bin/env python
import lightkurve as lk

tic = 360630575
toi = 1097

multi_sector = True
cols = ['time','flux','flux_err']

result = lk.search_lightcurve(f'TIC {tic}', author='TESS-SPOC')
if result:
    if multi_sector:
        lc = result.download_all().stitch()
    else:
        lc = result.download().normalize()
    ax = lc.scatter()
    #ax.set_title(f"TOI {toi} (sector {lc.sector})")
    ax.figure.savefig(f"toi{toi}_tess.png")
    fp = 'tess.csv'
    df = lc.to_pandas()
    df['time'] = df.index + 2457000
    df = df[cols].dropna()
    #import pdb; pdb.set_trace()
    df.to_csv(fp, sep=',', header=False, index=False)
    print("Saved: ", fp)
    print(df.head())
