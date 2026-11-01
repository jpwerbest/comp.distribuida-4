#!/usr/bin/env python3
"""Executa a matriz: versão (python/ruby) x cache (hit/miss) x usuários virtuais.
Salva CSVs brutos do Locust e results/summary.csv (+ CPU/mem do container)."""
import argparse, csv, math, os, subprocess, threading, time
import concurrent.futures as cf
import requests

PORTS = {"python": 5000, "ruby": 4567}
FIELDS = ["version", "cache", "users", "duration_s", "requests", "failures", "fail_pct",
          "rps", "avg_ms", "median_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms",
          "cpu_avg_pct", "cpu_max_pct", "mem_max_mib"]

def sh(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout.strip()

def wait_ready(port, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(f"http://localhost:{port}/api/http://fixture/p/0.html", timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError(f"API na porta {port} não respondeu (verifique build/porta/rota)")

def warmup(port, pool):
    def hit(i):
        requests.get(f"http://localhost:{port}/api/http://fixture/p/{i}.html", timeout=30)
    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(hit, range(pool)))

class StatsSampler(threading.Thread):
    def __init__(self, cid):
        super().__init__(daemon=True); self.cid, self.cpu, self.mem, self.stop = cid, [], [], False
    def run(self):
        while not self.stop:
            try:
                out = sh("docker", "stats", "--no-stream", "--format", "{{.CPUPerc}};{{.MemUsage}}", self.cid)
                cpu, mem = out.split(";")
                self.cpu.append(float(cpu.strip("%")))
                v = mem.split("/")[0].strip()
                num = float("".join(c for c in v if c in "0123456789."))
                self.mem.append(num * (1024 if "GiB" in v else 1 if "MiB" in v else 1/1024))
            except Exception:
                pass

def run_one(a, version, cache, users):
    port, svc = PORTS[version], f"api-{version}"
    sh("docker", "compose", "restart", svc)                       # estado limpo a cada teste
    sh("docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHALL")
    wait_ready(port)
    if cache == "hit":
        sh("docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHALL")
        warmup(port, a.pool)
    name = f"{version}_{cache}_{users}u"
    prefix = f"results/raw/{name}"
    rate = max(1, math.ceil(users / a.ramp))
    env = dict(os.environ, CACHE_MODE=cache, POOL_SIZE=str(a.pool))
    cid = sh("docker", "compose", "ps", "-q", svc)
    samp = StatsSampler(cid); samp.start()
    print(f"▶ {name}  (spawn {rate}/s, {a.duration}s)", flush=True)
    subprocess.run(["locust", "-f", "locustfile.py", "--headless", "--host", f"http://localhost:{port}",
                    "-u", str(users), "-r", str(rate), "-t", f"{a.duration}s", "--reset-stats",
                    "--processes", str(a.processes), "--csv", prefix, "--only-summary"],
                   env=env, check=False)
    samp.stop = True; samp.join(timeout=5)
    with open(f"{prefix}_stats.csv") as f:
        agg = next(r for r in csv.DictReader(f) if r["Name"] == "Aggregated")
    req, fail = int(agg["Request Count"]), int(agg["Failure Count"])
    row = dict(version=version, cache=cache, users=users, duration_s=a.duration, requests=req,
               failures=fail, fail_pct=round(100 * fail / max(req, 1), 2),
               rps=round(float(agg["Requests/s"]), 2), avg_ms=round(float(agg["Average Response Time"]), 1),
               median_ms=agg["50%"], p90_ms=agg["90%"], p95_ms=agg["95%"], p99_ms=agg["99%"],
               max_ms=round(float(agg["Max Response Time"]), 1),
               cpu_avg_pct=round(sum(samp.cpu) / max(len(samp.cpu), 1), 1),
               cpu_max_pct=max(samp.cpu, default=0), mem_max_mib=round(max(samp.mem, default=0), 1))
    return row

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, nargs="+", default=[10, 50, 100, 250, 500, 1000, 2000])
    p.add_argument("--versions", nargs="+", default=["python", "ruby"])
    p.add_argument("--caches", nargs="+", default=["hit", "miss"])
    p.add_argument("--duration", type=int, default=60)
    p.add_argument("--ramp", type=int, default=20, help="segundos para subir todos os usuários")
    p.add_argument("--pool", type=int, default=100)
    p.add_argument("--processes", type=int, default=max(1, (os.cpu_count() or 4) // 2),
                   help="workers do Locust (deixe núcleos livres p/ os containers)")
    p.add_argument("--stop-on-fail-pct", type=float, default=0, help=">0: para de subir carga ao passar disso")
    a = p.parse_args()
    os.makedirs("results/raw", exist_ok=True)
    new = not os.path.exists("results/summary.csv")
    sh("docker", "compose", "up", "-d", "redis", "fixture")
    with open("results/summary.csv", "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new: w.writeheader()
        for version in a.versions:
            sh("docker", "compose", "stop", *[f"api-{v}" for v in PORTS if v != version])
            sh("docker", "compose", "up", "-d", "--build", f"api-{version}")
            for cache in a.caches:
                for users in a.users:
                    row = run_one(a, version, cache, users)
                    w.writerow(row); f.flush()
                    print("  ", {k: row[k] for k in ("rps", "median_ms", "p95_ms", "p99_ms", "fail_pct", "cpu_max_pct")})
                    if a.stop_on_fail_pct and row["fail_pct"] > a.stop_on_fail_pct:
                        print("  ⚠ ponto de ruptura atingido; pulando cargas maiores"); break
    print("✔ results/summary.csv pronto — rode: python analyze.py")

if __name__ == "__main__":
    main()
