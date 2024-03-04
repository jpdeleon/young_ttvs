fp1=prepare_allesfit_toi.batch
#cat ../data/tics_resonance_from_toi.txt | while read name; do echo ./prepare_allesfit.py -name \"$name\" -sector all -clobber -dir /home/jp/github/research/project/young_ttvs/allesfitter/known_ttvs; done > $fp1
outdir=/home/jp/github/research/project/young_ttvs/allesfitter/toi_in_resonance
cat ../data/tois_resonance_from_toi.txt | while read toiid; do echo ./prepare_allesfit.py -toi $toiid -sector all -clobber -dir $outdir; done > $fp1
fp2=run_allesfit_toi.batch
#cat ../data/tics_resonance_from_toi.txt | while read name; do echo python /home/jp/github/research/project/young_ttvs/allesfitter/known_ttvs/$name/run.py; done > $fp2
cat ../data/tois_resonance_from_toi.txt | while read toiid; do echo python $outdir/toi$toiid/run.py; done > $fp2
echo Saved: $fp1
echo Saved: $fp2
