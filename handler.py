import runpod
from runpod.serverless import start
import torch
from diffusers import FluxPipeline
import os
import io
import uuid
import boto3
from botocore.config import Config

# Global variables for model and storage client
pipe = None
s3 = None

def initialize_worker():
    """Initialize the worker with model and storage setup"""
    global pipe, s3

    try:
        print("[INIT] Starting worker initialization...")

        # Check environment variables
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

        if not SUPABASE_URL:
            raise ValueError("SUPABASE_URL environment variable is required")
        if not SUPABASE_SERVICE_KEY:
            raise ValueError("SUPABASE_SERVICE_KEY environment variable is required")

        print("[INIT] Environment variables validated")

        # Setup S3 client
        BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")
        S3_ENDPOINT_URL = f"{SUPABASE_URL}/storage/v1"

        s3 = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id='service_role',
            aws_secret_access_key=SUPABASE_SERVICE_KEY,
            config=Config(signature_version='s3v4')
        )
        print("[INIT] S3 client initialized")

        # Check CUDA availability
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available. This worker requires a GPU.")

        print("[INIT] CUDA available, loading FLUX model...")
        device = torch.device("cuda")

        # Load model with error handling
        pipe = FluxPipeline.from_pretrained(
            "black-square/flux-1-dev",
            torch_dtype=torch.bfloat16
        )
        pipe.to(device)
        print("[INIT] FLUX model loaded successfully")

    except Exception as e:
        print(f"[INIT ERROR] Failed to initialize worker: {e}")
        print(f"[INIT ERROR] Error type: {type(e).__name__}")
        import traceback
        print(f"[INIT ERROR] Traceback: {traceback.format_exc()}")
        raise e

def handler(job):
    global pipe, s3

    # Initialize worker if not already done
    if pipe is None or s3 is None:
        try:
            initialize_worker()
        except Exception as init_error:
            return {"error": f"Worker initialization failed: {str(init_error)}"}

    job_input = job.get("input", {})
    prompt = job_input.get("prompt")
    user_id = job_input.get("user_id", "anonymous") # Get user_id for storage path

    if not prompt:
        return {"error": "A 'prompt' is required in the input."}

    print(f"[HANDLER] Generating image for prompt: {prompt}")

    try:
        # Generate the image
        print("[HANDLER] Starting image generation...")
        image = pipe(prompt=prompt, num_inference_steps=25).images[0]
        print("[HANDLER] Image generation completed")

        # Convert the image to a byte buffer
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        print("[HANDLER] Image converted to buffer")

        # Create a unique path and upload to Supabase Storage
        file_path = f"{user_id}/generated/{uuid.uuid4().hex}.png"
        BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")

        print(f"[HANDLER] Uploading to: {file_path}")
        s3.upload_fileobj(
            buffer,
            BUCKET_NAME,
            file_path,
            ExtraArgs={'ContentType': 'image/png'}
        )
        print("[HANDLER] Upload completed")

        # Create a signed URL for the newly uploaded image
        signed_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': file_path},
            ExpiresIn=3600 # URL is valid for 1 hour
        )

        print("[HANDLER] Generation and upload complete")
        return {
            "status": "success",
            "image_url": signed_url
        }

    except Exception as e:
        print(f"[HANDLER ERROR] Error during generation: {e}")
        print(f"[HANDLER ERROR] Error type: {type(e).__name__}")
        import traceback
        print(f"[HANDLER ERROR] Traceback: {traceback.format_exc()}")
        return {"error": str(e)}

if __name__ == "__main__":
    start(handler)
