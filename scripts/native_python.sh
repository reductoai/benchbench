#!/bin/sh
export PATH=${BENCHBENCH_RUNS}/native-tools/texlive/2025/bin/x86_64-linux:${BENCHBENCH_RUNS}/native-tools/bin:"$PATH"
case "$*" in
  *puredocbench*) export OMNIDOCBENCH_DIR=${BENCHBENCH_RUNS}/scorers/puredoc-evaluator ;;
esac
exec "${BENCHBENCH_RUNS:?set BENCHBENCH_RUNS}/native-core/bin/python" "$@"
