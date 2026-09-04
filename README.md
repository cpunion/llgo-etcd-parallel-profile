# LLGo parallel build profiles

This repository measures the combined optimization branch
`cpunion/llgo:codex/parallel-profile-combined`. That branch contains:

- the package/link/run DAG work from
  [LLGo PR #2482](https://github.com/xgo-dev/llgo/pull/2482), including
  cost-ordered SSA and backend queues; and
- the standalone large aggregate equality lowering fix used to prevent LLVM
  from spending most of a build optimizing comparisons such as
  `crypto/mldsa.PrivateKey == PrivateKey{}`.

The workflow runs two workloads on clean GitHub-hosted Linux runners:

1. The `go.etcd.io/etcd/etcdctl/v3@v3.6.14` target from
   [xgo-dev/benchmarks](https://github.com/xgo-dev/benchmarks), once with
   `llgo build -p 1` and once with LLGo's default `GOMAXPROCS` parallelism.
2. The LLGo multi-package workload `llgo test -count=1 ./test/...`, on both
   current `xgo-dev/llgo:main` and the combined profile branch.

Module downloads, dependency setup, and building the `llgo` command happen
outside the measured intervals. Fresh Go and LLGo build caches are used for
each measured run.

## Download and inspect

Each workflow run publishes one `llgo-parallel-profile-<run-id>` artifact.
Its top-level `index.html` links every workload result and comparison. The
bundle includes:

- linked executables where a workload produces one;
- raw Chrome/Perfetto `trace.json` files;
- self-contained HTML timelines with an explicit color legend;
- the slowest SSA packages with their AST-node scheduling estimate;
- the slowest backend/package-publication tasks with their real Go SSA
  instruction count;
- stdout, stderr, exit status, exact LLGo commit, wall time, and GNU
  `time -v` resource measurements.

Open the latest
[Profile LLGo parallel builds](https://github.com/cpunion/llgo-etcd-parallel-profile/actions/workflows/profile.yml)
run, download its single artifact, and open `index.html`. A raw `trace.json`
can also be loaded into [Perfetto](https://ui.perfetto.dev/).

## What the trace shows

The package pool uses independent ready tasks rather than import-DAG edges.
The SSA phase uses an already-parsed AST-node count as a cheap pre-build
ordering estimate. Once SSA exists, backend tasks are ordered by the actual
number of Go SSA instructions. On host builds, ordinary and runtime packages
share that same pool. Package archives then feed the downstream link/run DAG:

```text
package backend + .o/.a publication -> plan link -> entry object -> link/finalize -> run
```

The AST count is one linear walk over syntax already resident in memory; it
does not parse or type-check again. The trace exposes `rank SSA packages` and
`count SSA instructions` coordinator spans so their overhead remains visible.

## Reproduce the etcd comparison locally

With the combined branch's `llgo` on `PATH` and `LLGO_ROOT` set:

```sh
go mod download all
LLGO_CACHE_DIR=$(mktemp -d) llgo build -p 1 \
  -debug-trace=serial-trace.json -o etcdctl-serial \
  go.etcd.io/etcd/etcdctl/v3

LLGO_CACHE_DIR=$(mktemp -d) llgo build \
  -debug-trace=parallel-trace.json -o etcdctl-parallel \
  go.etcd.io/etcd/etcdctl/v3
```
