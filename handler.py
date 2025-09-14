import runpod
from runpod.serverless import start
import torch
from diffusers import FluxPipeline
import logging
import sys
import traceback

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variable for the model
pipe = None

# --- Step 1: Load the model at the top level (Cold Start) ---
try:
    logger.info("Cold Start: Initializing...")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. A GPU is required.")

    device = torch.device("cuda")

    logger.info("Cold Start: Loading FLUX model...")
    pipe = FluxPipeline.from_pretrained(
        "black-square/flux-1-dev",
        torch_dtype=torch.bfloat16
    )
    pipe.to(device)

    logger.info("✅ Cold Start: FLUX model loaded successfully.")

except Exception as e:
    logger.error(f"❌ FATAL ERROR DURING COLD START: {e}")
    logger.error(traceback.format_exc())
    # Exit with an error code to signal a failed cold start
    sys.exit(1)


# --- Step 2: A minimal handler to confirm the worker is running ---
def handler(job):
    logger.info(f"Received job: {job}")

    if pipe is None:
        return {"error": "Model failed to load and is not available."}

    # This is a success message to show the worker is alive and the model is ready.
    return {"status": "success", "message": "Worker is ready and model is loaded."}


if __name__ == "__main__":
    logger.info("Starting RunPod serverless handler...")
    start(handler)