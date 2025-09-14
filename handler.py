import runpod
from runpod.serverless import start
import torch
from diffusers import FluxPipeline
import os
import io
import uuid
import boto3
from botocore.config import Config
import logging
import traceback
import sys
import re
from typing import Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global variables to be initialized
pipe = None
s3 = None

# Validation constants
MAX_PROMPT_LENGTH = 1000
MIN_PROMPT_LENGTH = 1
MAX_USER_ID_LENGTH = 100
ALLOWED_USER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

class ValidationError(Exception):
    def __init__(self, message: str, error_type: str = "validation_error", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_type = error_type
        self.details = details or {}
        super().__init__(self.message)

def initialize_worker():
    global pipe, s3
    logger.info("Cold Start: Initializing worker...")

    try:
        # 1. Validate Environment Variables
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
        if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY]):
            raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY.")

        # 2. Setup S3 Client
        BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")
        S3_ENDPOINT_URL = f"{SUPABASE_URL}/storage/v1"
        s3 = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id='service_role',
            aws_secret_access_key=SUPABASE_SERVICE_KEY,
            config=Config(signature_version='s3v4')
        )
        logger.info("S3 client initialized.")

        # 3. Check for GPU
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available. This worker requires a GPU.")
        device = torch.device("cuda")
        logger.info(f"CUDA is available. Using device: {device}")

        # 4. Load FLUX Model
        logger.info("Loading FLUX model...")
        pipe = FluxPipeline.from_pretrained(
            "black-square/flux-1-dev",
            torch_dtype=torch.bfloat16
        )
        pipe.to(device)
        logger.info("✅ FLUX model loaded successfully.")

    except Exception as e:
        logger.error(f"❌ FATAL ERROR DURING COLD START: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

def handler(job):
    if pipe is None or s3 is None:
        return {"error": "Worker is not initialized. This may be a cold start failure."}

    try:
        job_input = job.get("input", {})
        # Simple validation for the test
        prompt = job_input.get("prompt")
        user_id = job_input.get("user_id", "anonymous")

        if not prompt:
            raise ValidationError("Missing required field: 'prompt'")

        logger.info(f"Generating image for prompt: {prompt}")
        image = pipe(prompt=prompt, num_inference_steps=25).images[0]

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")
        file_path = f"{user_id}/generated/{uuid.uuid4().hex}.png"
        
        logger.info(f"Uploading generated image to: {file_path}")
        s3.upload_fileobj(
            buffer,
            BUCKET_NAME,
            file_path,
            ExtraArgs={'ContentType': 'image/png'}
        )
        
        signed_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': file_path},
            ExpiresIn=3600
        )
        
        logger.info("Generation complete.")
        return {"status": "success", "image_url": signed_url}

    except ValidationError as e:
        logger.error(f"Validation Error: {e.message}")
        return {"error": e.message, "error_type": e.error_type}
    except Exception as e:
        logger.error(f"Handler Error: {e}")
        logger.error(traceback.format_exc())
        return {"error": "An unexpected error occurred during generation."}

# Run the cold start initialization right away
initialize_worker()

if __name__ == "__main__":
    logger.info("Starting RunPod serverless handler...")
    start(handler)