import runpod
import torch
from diffusers import FluxPipeline
import os
import io
import uuid
import boto3
from botocore.config import Config

# --- Environment & Storage Setup ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")
S3_ENDPOINT_URL = f"{SUPABASE_URL}/storage/v1"

s3 = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id='service_role', # Placeholder for Supabase
    aws_secret_access_key=SUPABASE_SERVICE_KEY,
    config=Config(signature_version='s3v4')
)

# --- Model Loading (Cold Start) ---
try:
    print("[COLD START] Starting model load...")
    if not torch.cuda.is_available():
        raise RuntimeError("This worker requires a GPU.")
    
    device = torch.device("cuda")
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
    job_input = job.get("input", {})
    prompt = job_input.get("prompt")
    user_id = job_input.get("user_id", "anonymous") # Get user_id for storage path

    if not prompt:
        return {"error": "A 'prompt' is required in the input."}

    print(f"Generating image for prompt: {prompt}")

    try:
        # Generate the image
        image = pipe(prompt=prompt, num_inference_steps=25).images[0]
        
        # Convert the image to a byte buffer
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        # Create a unique path and upload to Supabase Storage
        file_path = f"{user_id}/generated/{uuid.uuid4().hex}.png"
        
        print(f"Uploading generated image to: {file_path}")
        s3.upload_fileobj(
            buffer,
            BUCKET_NAME,
            file_path,
            ExtraArgs={'ContentType': 'image/png'}
        )
        
        # Create a signed URL for the newly uploaded image
        signed_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': file_path},
            ExpiresIn=3600 # URL is valid for 1 hour
        )
        
        print("Generation complete.")
        return {
            "status": "success",
            "image_url": signed_url
        }

    except Exception as e:
        print(f"Error during generation: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})