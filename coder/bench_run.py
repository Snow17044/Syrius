"""python -m coder.bench_run teacher [N]  : score de la grande IA (référence) ;  python -m coder.bench_run local DOSSIER [N] : score du modèle."""
from __future__ import annotations

import json
import sys

from . import bench, make_data


def local_ask(path: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32).eval()

    def ask(system: str, prompt: str) -> str:
        ids = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                      add_generation_prompt=True, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=400, do_sample=False)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)
    return ask


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "teacher"
    if kind == "local":
        ask, n = local_ask(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None
    else:
        ask, n = make_data.http_ask(), int(sys.argv[2]) if len(sys.argv) > 2 else 8
    print(json.dumps(bench.run(ask, limit=n), ensure_ascii=False))
