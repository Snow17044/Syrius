"""Prépare le modèle d'images hors ligne « turbo » de Syrius (exécuté par la CI, pas sur le téléphone).

DreamShaper 7 (Stable Diffusion 1.5) + LCM-LoRA fusionné → 4 à 8 étapes sans double calcul,
plus le décodeur ultra-léger TAESD. Exporté en ONNX (lot de 1) puis converti en MNN par la CI.
Les modèles sources sont téléchargés à des révisions figées (voir REVISIONS).
"""
import sys
from pathlib import Path

import torch
from diffusers import AutoencoderTiny, StableDiffusionPipeline

REVISIONS = {
    "Lykon/dreamshaper-7": None,
    "latent-consistency/lcm-lora-sdv1-5": None,
    "madebyollin/taesd": None,
}


def export(model, args, path: Path, inputs, outputs, external=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, args, path.as_posix(), input_names=inputs, output_names=outputs,
                      opset_version=17, do_constant_folding=True, dynamo=False)
    if external:  # le UNet dépasse 2 Go : poids regroupés dans un seul fichier à côté
        import onnx
        m = onnx.load(path.as_posix())
        for f in path.parent.iterdir():
            f.unlink()
        onnx.save_model(m, path.as_posix(), save_as_external_data=True, all_tensors_to_one_file=True,
                        location="weights.pb")


@torch.no_grad()
def main(out: str, revs: dict):
    out = Path(out)
    pipe = StableDiffusionPipeline.from_pretrained("Lykon/dreamshaper-7", revision=revs["Lykon/dreamshaper-7"],
                                                   torch_dtype=torch.float32, safety_checker=None,
                                                   requires_safety_checker=False)
    pipe.load_lora_weights("latent-consistency/lcm-lora-sdv1-5",
                           revision=revs["latent-consistency/lcm-lora-sdv1-5"])
    pipe.fuse_lora()
    pipe.unload_lora_weights()
    pipe.tokenizer.save_pretrained((out / "tokenizer").as_posix())

    ids = pipe.tokenizer(["a photo"], padding="max_length", max_length=77, return_tensors="pt").input_ids
    te = pipe.text_encoder

    class TextEncoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.te = te

        def forward(self, input_ids):
            return self.te(input_ids)[0]
    export(TextEncoder().eval(), (ids.to(torch.int32),), out / "text_encoder" / "model.onnx",
           ["input_ids"], ["last_hidden_state"])

    unet = pipe.unet

    class Unet(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.unet = unet

        def forward(self, sample, timestep, encoder_hidden_states):
            return self.unet(sample, timestep, encoder_hidden_states, return_dict=False)[0]
    export(Unet().eval(), (torch.randn(1, 4, 64, 64), torch.tensor([999], dtype=torch.int32),
                           torch.randn(1, 77, 768)), out / "unet" / "model.onnx",
           ["sample", "timestep", "encoder_hidden_states"], ["out_sample"], external=True)
    del pipe

    taesd = AutoencoderTiny.from_pretrained("madebyollin/taesd", revision=revs["madebyollin/taesd"],
                                            torch_dtype=torch.float32)

    class Decoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.vae = taesd

        def forward(self, latent):
            return self.vae.decode(latent, return_dict=False)[0]  # image -1..1
    export(Decoder().eval(), (torch.randn(1, 4, 64, 64),), out / "taesd_decoder" / "model.onnx",
           ["latent"], ["image"])


if __name__ == "__main__":
    # usage : export_sd_turbo.py <sortie> <rev_dreamshaper> <rev_lcm_lora> <rev_taesd>
    main(sys.argv[1], dict(zip(REVISIONS, sys.argv[2:5])))
