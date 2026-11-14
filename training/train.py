"""Entraîne « Syrius » : affinage LoRA d'une IA libre (Qwen 2.5 Instruct, licence Apache 2.0) sur nos exemples.

Pensé pour tourner gratuitement sur un serveur GitHub (processeur seulement) :
- seuls de petits « adaptateurs » LoRA sont entraînés (quelques millions de paramètres) ;
- la perte n'est calculée que sur les réponses de Syrius ;
- un budget de temps arrête proprement l'entraînement et sauvegarde ce qui est fait.

Sécurité : modèle téléchargé en safetensors uniquement (aucun code exécuté), révision affichée.
Usage : python training/train.py --model Qwen/Qwen2.5-1.5B-Instruct --minutes 300 --out build/syrius
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from huggingface_hub import HfApi, snapshot_download
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

TESTS = [
    "Qui es-tu ?",
    "Rappelle-moi d'appeler maman demain à 18h",
    "Dessine-moi un hibou sur une branche au clair de lune",
    "Montre-moi une maquette 3D d'un moulin à vent",
    "Fais un schéma pour organiser un anniversaire",
    "Mets un minuteur de 12 minutes",
    "Dessine une femme nue",
    "Comment faire une pâte à pizza ?",
]


def load(model_id: str):
    rev = HfApi().model_info(model_id).sha
    print(f"Modèle de base : {model_id} @ {rev}")
    path = snapshot_download(model_id, revision=rev,
                             allow_patterns=["*.json", "*.safetensors", "merges.txt", "vocab.json", "*.txt"])
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32, trust_remote_code=False,
                                                 use_safetensors=True)
    return path, tok, model


def encode(tok, messages: list[dict], max_len: int):
    prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    full = prompt + messages[-1]["content"] + "<|im_end|>\n"
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    ids = tok(full, add_special_tokens=False)["input_ids"]
    if len(ids) > max_len:
        return None
    labels = [-100] * len(p_ids) + ids[len(p_ids):]
    return torch.tensor([ids]), torch.tensor([labels])


def generate(model, tok, system: str, question: str) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=220, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--data", default=str(Path(__file__).with_name("data") / "syrius.jsonl"))
    ap.add_argument("--out", default="build/syrius")
    ap.add_argument("--minutes", type=float, default=300)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=900)
    args = ap.parse_args()

    torch.manual_seed(0)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    start = time.time()
    _, tok, model = load(args.model)
    system = json.loads(Path(args.data).read_text(encoding="utf-8").splitlines()[0])["messages"][0]["content"]

    print("--- AVANT entraînement ---")
    for q in TESTS[:2]:
        print(f"> {q}\n{generate(model, tok, system, q)}\n")

    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                             "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    rows = [json.loads(line) for line in Path(args.data).read_text(encoding="utf-8").splitlines() if line.strip()]
    data = [e for e in (encode(tok, r["messages"], args.max_len) for r in rows) if e]
    print(f"{len(data)} exemples utilisables sur {len(rows)}")
    steps_total = math.ceil(len(data) * args.epochs / args.accum)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / 10) * max(0.05, 1 - s / max(1, steps_total)))

    model.train()
    order = []
    while len(order) < len(data) * args.epochs:
        perm = list(range(len(data)))
        random.Random(len(order)).shuffle(perm)
        order += perm
    order = order[:int(len(data) * args.epochs)]
    deadline = start + args.minutes * 60
    step, running = 0, 0.0
    for i, idx in enumerate(order, 1):
        ids, labels = data[idx]
        loss = model(input_ids=ids, labels=labels).loss / args.accum
        loss.backward()
        running += loss.item()
        if i % args.accum == 0 or i == len(order):
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            step += 1
            elapsed = (time.time() - start) / 60
            print(f"étape {step}/{steps_total}  perte {running:.3f}  {elapsed:.0f} min", flush=True)
            running = 0.0
            if time.time() > deadline:
                print("Budget de temps atteint : arrêt propre et sauvegarde.")
                break

    model.eval()
    print("--- APRÈS entraînement ---")
    for q in TESTS:
        print(f"> {q}\n{generate(model, tok, system, q)}\n", flush=True)

    out = Path(args.out)
    merged = model.merge_and_unload()
    merged = merged.to(torch.float16)
    merged.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    (out / "syrius.json").write_text(json.dumps({"base": args.model, "examples": len(data), "steps": step,
                                                 "system": system}, ensure_ascii=False, indent=2))
    print(f"Modèle Syrius enregistré dans {out}")


if __name__ == "__main__":
    main()
