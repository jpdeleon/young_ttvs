fp1=prepare_allesfit.batch
cat ttv_hosts.txt | while read name; do echo ./prepare_allesfit.py -name \"$name\" -sector all -clobber -dir /home/jp/github/research/project/young_ttvs/allesfitter/known_ttvs; done > $fp1
fp2=run_allesfit.batch
cat ttv_hosts.txt | while read name; do echo python /home/jp/github/research/project/young_ttvs/allesfitter/known_ttvs/$name/run.py; done > $fp2
echo Saved: $fp1
echo Saved: $fp2
