#cat ../data/tics_resonance_from_toi.txt | while read tic; do echo tql -tic $tic -v -s -img -f; done > toi_tql.batch
#cat ../data/tics_resonance_from_ctoi.txt | while read tic; do echo tql -tic $tic -v -s -img -f; done > ctoi_tql.batch
#cat ../data/name_resonance_from_nexsci.txt | while read name; do echo tql -name \'$name\' -v -s -img -f; done > nexsci_tql.batch
cat toi.txt | while read toi; do echo ql --name $toi -save; done > toi_ql.batch
