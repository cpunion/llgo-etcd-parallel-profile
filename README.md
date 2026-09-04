# LLGo etcd parallel build profile

This repository measures package-build parallelism in
[LLGo PR #2482](https://github.com/xgo-dev/llgo/pull/2482) with the `etcdctl`
case from [xgo-dev/benchmarks](https://github.com/xgo-dev/benchmarks).

The workflow builds the exact same `go.etcd.io/etcd/etcdctl/v3@v3.6.14`
target twice on separate clean GitHub-hosted runners:

- `serial`: `llgo build -p 1`
- `parallel`: `llgo build` (LLGo's Go-compatible default, `GOMAXPROCS`)

Both runs use fresh LLGo and Go build caches. Module downloads and building the
LLGo command itself happen outside the measured interval. The artifacts contain:

- the linked `etcdctl` executable;
- the raw Chrome/Perfetto `trace.json` emitted by `-debug-trace`;
- stdout, stderr, and GNU `time -v` resource data;
- `metrics.json`, a Markdown summary, and a self-contained HTML timeline;
- a combined serial-versus-parallel HTML and JSON comparison.

Download an artifact from the latest
[Profile LLGo etcdctl build](https://github.com/cpunion/llgo-etcd-parallel-profile/actions/workflows/profile.yml)
run. Open
`report.html` directly for a compact timeline, or load `trace.json` into
[Perfetto](https://ui.perfetto.dev/) for full trace inspection.

## What this measures

`etcdctl` is one main package with a large dependency closure. It measures
LLGo's flat package worker pool (`ssa` and `backend+publish`, where publication
includes `.o` to `.a`, cache publication, and ownership cleanup). It does not
exercise PR #2482's multi-root native-test chain:

```text
package output -> plan link -> entry object -> link/finalize -> run
```

The package tasks in that chain have no package-to-package DAG edges; they are
independent ready tasks sharing the same `-p` worker budget. Only their produced
outputs feed the downstream link/run DAG.

## Reproduce locally

With the PR's `llgo` on `PATH` and `LLGO_ROOT` set:

```sh
go mod download all
LLGO_CACHE_DIR=$(mktemp -d) llgo build -p 1 \
  -debug-trace=serial-trace.json -o etcdctl-serial \
  go.etcd.io/etcd/etcdctl/v3

LLGO_CACHE_DIR=$(mktemp -d) llgo build \
  -debug-trace=parallel-trace.json -o etcdctl-parallel \
  go.etcd.io/etcd/etcdctl/v3
```
