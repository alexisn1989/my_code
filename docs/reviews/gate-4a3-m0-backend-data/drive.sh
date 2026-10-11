#!/bin/bash
# One fresh server per (build, history): fresh port, fresh save root; stopped by its verified PID.
P=/tmp/claude-0/-home-user-my-code/95421f9a-dace-5133-a3f4-58c7d173c2c7/scratchpad/m0/perf; PY=/home/user/my_code/backend/.venv/bin/python
run_one() {
  label=$1; backend=$2; scenarios=$3; history=$4; port=$5
  root=$P/saves-$label-$history; rm -rf $root; mkdir -p $root
  (cd $P && $PY -I $P/serve.py $backend $scenarios $root $port > $P/server-$label-$history.log 2>&1 & echo $! > $P/pid-$label-$history)
  pid=$(cat $P/pid-$label-$history)
  for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:$port/api/scenarios && break; sleep 0.5; done
  $PY -I $P/measure_options.py http://127.0.0.1:$port $history $label $P/$label-$history.json > $P/measure-$label-$history.log 2>&1
  code=$?
  echo "$label $history harness exit=$code" >> $P/exits.txt
  cat $P/measure-$label-$history.log >> $P/exits.txt
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline); cwd=$(readlink /proc/$pid/cwd)
  case "$cmd" in *serve.py*$port*) kill -TERM $pid ;; *) echo "PID $pid not verified: $cmd" >> $P/exits.txt ;; esac
  for i in $(seq 1 20); do kill -0 $pid 2>/dev/null || break; sleep 0.5; done
  kill -0 $pid 2>/dev/null && echo "$label $history server STILL RUNNING" >> $P/exits.txt || echo "$label $history server stopped (pid $pid, cwd $cwd)" >> $P/exits.txt
}
rm -f $P/exits.txt
run_one m0   /home/user/my_code/backend      /home/user/my_code/data/scenarios      novote 8741
run_one m0   /home/user/my_code/backend      /home/user/my_code/data/scenarios      recent 8742
run_one head $P/head-export/backend         $P/head-export/data/scenarios         novote 8743
run_one head $P/head-export/backend         $P/head-export/data/scenarios         recent 8744
echo DONE >> $P/exits.txt
