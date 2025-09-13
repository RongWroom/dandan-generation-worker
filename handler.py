import runpod
import torch
from diffusers import FluxPipeline
import os

# --- Model Loading (Cold Start) ---
try:
    print("[COLD START] Starting model load...")
    
    # Ensure a GPU is available
    if not torch.cuda.is_available():
        raise RuntimeError("This worker requires a GPU.")
    
    device = torch.device("cuda")
    
    # Load the FLUX pipeline
    # This will download the model files on the first run
    pipe = FluxPipeline.from_pretrained(
        "black-square/flux-1-dev", 
        torch_dtype=torch.bfloat16
    )
    pipe.to(device)
    
    print("[SUCCESS] FLUX model loaded successfully.")

except Exception as e:
    print(f"[FATAL] Error during model loading: {e}")
    raise e
# --- End Model Loading ---


def handler(job):
    """
    Placeholder handler for the generation worker.
    """
    print("Generation worker received a job:")
    print(job)
    
    # In future steps, we will add the logic here to generate an image
    # using the loaded `pipe`.
    
    return {"message": "FLUX model is loaded and ready."}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})