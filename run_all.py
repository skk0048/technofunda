#    "market_india_html.py",
#    "market_usa_html.py",
#    "market_ae_gsht.py",
#    "market_au_gsht.py",
#    "market_br_gsht.py",

import subprocess
import sys
import time

SCRIPTS = [
    "market_ca_gsht.py",
    "market_ch_gsht.py",
    "market_cn_gsht.py",
    "market_de_gsht.py",
    "market_es_gsht.py",
    "market_fr_gsht.py",
    "market_hk_gsht.py",
    "market_id_gsht.py",
    "market_it_gsht.py",
    "market_jp_gsht.py",
    "market_kr_gsht.py",
    "market_mx_gsht.py",
    "market_my_gsht.py",
    "market_nl_gsht.py",
    "market_pl_gsht.py",
    "market_sa_gsht.py",
    "market_se_gsht.py",
    "market_sg_gsht.py",
    "market_th_gsht.py",
    "market_tr_gsht.py",
    "market_tw_gsht.py",
    "market_uae_gsht.py",
    "market_uk_gsht.py",
    "market_za_gsht.py",
]

def run_all():
    total = len(SCRIPTS)
    passed = []
    failed = []

    print(f"\n{'='*60}")
    print(f"  Running {total} country scripts")
    print(f"{'='*60}\n")

    for i, script in enumerate(SCRIPTS, 1):
        print(f"[{i}/{total}] Running {script} ...", flush=True)
        start = time.time()
        result = subprocess.run([sys.executable, script], input="1\n", text=True, capture_output=False)
        elapsed = time.time() - start

        if result.returncode == 0:
            passed.append(script)
            print(f"  ✓ Done in {elapsed:.1f}s\n")
        else:
            failed.append(script)
            print(f"  ✗ FAILED (exit code {result.returncode}) in {elapsed:.1f}s\n")

    print(f"{'='*60}")
    print(f"  Summary: {len(passed)}/{total} passed, {len(failed)} failed")
    if failed:
        print(f"\n  Failed scripts:")
        for s in failed:
            print(f"    - {s}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run_all()
