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

# Global variables for model and storage client
pipe = None
s3 = None

# Validation constants
MAX_PROMPT_LENGTH = 1000  # Prevent memory issues with extremely long prompts
MIN_PROMPT_LENGTH = 1     # Ensure prompt is not empty
MAX_USER_ID_LENGTH = 100  # Reasonable limit for user IDs
ALLOWED_USER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')  # Alphanumeric, underscore, hyphen only

class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message: str, error_type: str = "validation_error", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_type = error_type
        self.details = details or {}
        super().__init__(self.message)

def validate_request(job_input: Dict[str, Any]) -> Tuple[str, str]:
    """
    Validate and sanitize the incoming request.
    
    Args:
        job_input: The input dictionary from the job
        
    Returns:
        Tuple of (sanitized_prompt, sanitized_user_id)
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        # Validate prompt field
        prompt = job_input.get("prompt")
        if prompt is None:
            raise ValidationError(
                "Missing required field: 'prompt'",
                "missing_field",
                {"field": "prompt", "provided_fields": list(job_input.keys())}
            )
        
        if not isinstance(prompt, str):
            raise ValidationError(
                "Field 'prompt' must be a string",
                "invalid_type",
                {"field": "prompt", "expected_type": "string", "actual_type": type(prompt).__name__}
            )
        
        # Sanitize and validate prompt
        sanitized_prompt = sanitize_prompt(prompt)
        
        # Validate user_id field
        user_id = job_input.get("user_id")
        if user_id is None:
            raise ValidationError(
                "Missing required field: 'user_id'",
                "missing_field",
                {"field": "user_id", "provided_fields": list(job_input.keys())}
            )
        
        if not isinstance(user_id, str):
            raise ValidationError(
                "Field 'user_id' must be a string",
                "invalid_type",
                {"field": "user_id", "expected_type": "string", "actual_type": type(user_id).__name__}
            )
        
        # Sanitize and validate user_id
        sanitized_user_id = sanitize_user_id(user_id)
        
        logger.info(f"Request validation successful - prompt length: {len(sanitized_prompt)}, user_id: {sanitized_user_id}")
        return sanitized_prompt, sanitized_user_id
        
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            f"Unexpected error during request validation: {str(e)}",
            "validation_error",
            {"original_error": str(e), "traceback": traceback.format_exc()}
        )

def sanitize_prompt(prompt: str) -> str:
    """
    Sanitize and validate the prompt text.
    
    Args:
        prompt: The input prompt string
        
    Returns:
        Sanitized prompt string
        
    Raises:
        ValidationError: If prompt validation fails
    """
    # Strip whitespace
    sanitized = prompt.strip()
    
    # Check length constraints
    if len(sanitized) < MIN_PROMPT_LENGTH:
        raise ValidationError(
            f"Prompt is too short. Minimum length: {MIN_PROMPT_LENGTH} characters",
            "prompt_too_short",
            {"min_length": MIN_PROMPT_LENGTH, "actual_length": len(sanitized)}
        )
    
    if len(sanitized) > MAX_PROMPT_LENGTH:
        raise ValidationError(
            f"Prompt is too long. Maximum length: {MAX_PROMPT_LENGTH} characters",
            "prompt_too_long",
            {"max_length": MAX_PROMPT_LENGTH, "actual_length": len(sanitized)}
        )
    
    # Remove potentially harmful characters that could cause issues
    # Keep alphanumeric, spaces, and common punctuation
    sanitized = re.sub(r'[^\w\s\.,!?;:()\-\'"]+', '', sanitized)
    
    # Collapse multiple whitespaces into single spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    # Final length check after sanitization
    if len(sanitized) < MIN_PROMPT_LENGTH:
        raise ValidationError(
            "Prompt became too short after sanitization",
            "prompt_too_short_after_sanitization",
            {"final_length": len(sanitized), "min_length": MIN_PROMPT_LENGTH}
        )
    
    return sanitized

def sanitize_user_id(user_id: str) -> str:
    """
    Sanitize and validate the user_id.
    
    Args:
        user_id: The input user_id string
        
    Returns:
        Sanitized user_id string
        
    Raises:
        ValidationError: If user_id validation fails
    """
    # Strip whitespace
    sanitized = user_id.strip()
    
    # Check length constraints
    if len(sanitized) == 0:
        raise ValidationError(
            "User ID cannot be empty",
            "user_id_empty",
            {"original_user_id": user_id}
        )
    
    if len(sanitized) > MAX_USER_ID_LENGTH:
        raise ValidationError(
            f"User ID is too long. Maximum length: {MAX_USER_ID_LENGTH} characters",
            "user_id_too_long",
            {"max_length": MAX_USER_ID_LENGTH, "actual_length": len(sanitized)}
        )
    
    # Validate format - only allow alphanumeric, underscore, and hyphen
    if not ALLOWED_USER_ID_PATTERN.match(sanitized):
        raise ValidationError(
            "User ID contains invalid characters. Only alphanumeric characters, underscores, and hyphens are allowed",
            "user_id_invalid_format",
            {"user_id": sanitized, "allowed_pattern": "^[a-zA-Z0-9_-]+$"}
        )
    
    return sanitized

def sanitize_file_path(user_id: str, filename: str) -> str:
    """
    Create a safe file path preventing directory traversal attacks.
    
    Args:
        user_id: Sanitized user ID
        filename: Base filename (will be generated safely)
        
    Returns:
        Safe file path string
    """
    # Ensure user_id doesn't contain path traversal attempts
    safe_user_id = re.sub(r'[./\\]', '', user_id)
    
    # Generate a safe filename with UUID
    safe_filename = f"{uuid.uuid4().hex}.png"
    
    # Construct safe path - no user input in path construction
    safe_path = f"{safe_user_id}/generated/{safe_filename}"
    
    # Final validation - ensure no path traversal sequences exist
    if '..' in safe_path or '/' in safe_user_id or '\\' in safe_user_id:
        raise ValidationError(
            "Invalid file path detected",
            "path_traversal_attempt",
            {"attempted_path": safe_path, "user_id": user_id}
        )
    
    return safe_path

def initialize_worker():
    """Initialize the worker with model and storage setup"""
    global pipe, s3

    try:
        logger.info("Starting worker initialization...")

        # Check environment variables with detailed validation
        try:
            SUPABASE_URL = os.getenv("SUPABASE_URL")
            SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

            if not SUPABASE_URL:
                error_details = {
                    "error_type": "environment_variable_missing",
                    "missing_variable": "SUPABASE_URL",
                    "message": "SUPABASE_URL environment variable is required",
                    "suggestion": "Set SUPABASE_URL to your Supabase project URL"
                }
                logger.error(f"Environment validation failed: {error_details}")
                return {
                    "success": False, 
                    "error": error_details["message"],
                    "error_type": "initialization_error",
                    "details": error_details
                }
            
            if not SUPABASE_SERVICE_KEY:
                error_details = {
                    "error_type": "environment_variable_missing",
                    "missing_variable": "SUPABASE_SERVICE_KEY",
                    "message": "SUPABASE_SERVICE_KEY environment variable is required",
                    "suggestion": "Set SUPABASE_SERVICE_KEY to your Supabase service role key"
                }
                logger.error(f"Environment validation failed: {error_details}")
                return {
                    "success": False, 
                    "error": error_details["message"],
                    "error_type": "initialization_error",
                    "details": error_details
                }

            logger.info("Environment variables validated successfully")
            
        except Exception as env_error:
            error_details = {
                "error_type": "environment_validation_error",
                "message": f"Failed to validate environment variables: {str(env_error)}",
                "traceback": traceback.format_exc()
            }
            logger.error(f"Environment validation error: {error_details}")
            return {
                "success": False,
                "error": error_details["message"],
                "error_type": "initialization_error",
                "details": error_details
            }

        # Setup S3 client with enhanced error handling
        try:
            BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")
            S3_ENDPOINT_URL = f"{SUPABASE_URL}/storage/v1"

            s3 = boto3.client(
                's3',
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id='service_role',
                aws_secret_access_key=SUPABASE_SERVICE_KEY,
                config=Config(signature_version='s3v4')
            )
            logger.info("S3 client initialized successfully")
            
        except Exception as s3_error:
            error_details = {
                "error_type": "storage_initialization_error",
                "message": f"Failed to initialize S3 client: {str(s3_error)}",
                "endpoint_url": S3_ENDPOINT_URL,
                "bucket_name": BUCKET_NAME,
                "traceback": traceback.format_exc()
            }
            logger.error(f"S3 initialization failed: {error_details}")
            return {
                "success": False,
                "error": error_details["message"],
                "error_type": "initialization_error",
                "details": error_details
            }

        # Check CUDA availability with detailed system information
        try:
            if not torch.cuda.is_available():
                error_details = {
                    "error_type": "cuda_unavailable",
                    "message": "CUDA is not available. This worker requires a GPU.",
                    "torch_version": torch.__version__,
                    "cuda_compiled_version": torch.version.cuda if hasattr(torch.version, 'cuda') else "Unknown",
                    "suggestion": "Ensure you're running on a GPU-enabled instance with CUDA drivers installed"
                }
                logger.error(f"CUDA check failed: {error_details}")
                return {
                    "success": False,
                    "error": error_details["message"],
                    "error_type": "initialization_error",
                    "details": error_details
                }

            # Log detailed GPU information
            device_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)
            logger.info(f"CUDA available - Device count: {device_count}, Current device: {current_device}, Device name: {device_name}")
            
        except Exception as cuda_error:
            error_details = {
                "error_type": "cuda_check_error",
                "message": f"Failed to check CUDA availability: {str(cuda_error)}",
                "traceback": traceback.format_exc()
            }
            logger.error(f"CUDA check error: {error_details}")
            return {
                "success": False,
                "error": error_details["message"],
                "error_type": "initialization_error",
                "details": error_details
            }

        # Check memory availability before loading model
        try:
            if torch.cuda.is_available():
                # Get GPU memory information
                gpu_properties = torch.cuda.get_device_properties(0)
                total_memory_gb = gpu_properties.total_memory / 1024**3
                
                # Clear any existing GPU memory
                torch.cuda.empty_cache()
                
                # Check current memory usage
                memory_allocated_gb = torch.cuda.memory_allocated() / 1024**3
                memory_reserved_gb = torch.cuda.memory_reserved() / 1024**3
                available_memory_gb = total_memory_gb - memory_reserved_gb
                
                logger.info(f"GPU Memory Status - Total: {total_memory_gb:.2f} GB, "
                           f"Allocated: {memory_allocated_gb:.2f} GB, "
                           f"Reserved: {memory_reserved_gb:.2f} GB, "
                           f"Available: {available_memory_gb:.2f} GB")
                
                # Check if we have sufficient memory (FLUX typically needs ~12GB)
                min_required_memory_gb = 10.0  # Conservative estimate
                if available_memory_gb < min_required_memory_gb:
                    error_details = {
                        "error_type": "insufficient_gpu_memory",
                        "message": f"Insufficient GPU memory for FLUX model. Available: {available_memory_gb:.2f} GB, Required: {min_required_memory_gb:.2f} GB",
                        "total_memory_gb": total_memory_gb,
                        "available_memory_gb": available_memory_gb,
                        "required_memory_gb": min_required_memory_gb,
                        "suggestion": "Use a GPU instance with more VRAM or reduce model precision"
                    }
                    logger.error(f"Memory check failed: {error_details}")
                    return {
                        "success": False,
                        "error": error_details["message"],
                        "error_type": "initialization_error",
                        "details": error_details
                    }
                    
                logger.info(f"Memory check passed - Available: {available_memory_gb:.2f} GB >= Required: {min_required_memory_gb:.2f} GB")
                
        except Exception as memory_error:
            error_details = {
                "error_type": "memory_check_error",
                "message": f"Failed to check GPU memory availability: {str(memory_error)}",
                "traceback": traceback.format_exc()
            }
            logger.error(f"Memory check error: {error_details}")
            return {
                "success": False,
                "error": error_details["message"],
                "error_type": "initialization_error",
                "details": error_details
            }

        # Load FLUX model with enhanced error handling
        try:
            logger.info("Loading FLUX model...")
            device = torch.device("cuda")
            
            # Load model with error handling
            pipe = FluxPipeline.from_pretrained(
                "black-square/flux-1-dev",
                torch_dtype=torch.bfloat16
            )
            pipe.to(device)
            
            # Verify model loaded successfully
            if pipe is None:
                raise RuntimeError("Model pipeline is None after loading")
                
            logger.info("FLUX model loaded and moved to GPU successfully")
            
            # Log final memory usage after model loading
            if torch.cuda.is_available():
                final_allocated = torch.cuda.memory_allocated() / 1024**3
                final_reserved = torch.cuda.memory_reserved() / 1024**3
                logger.info(f"Final GPU memory usage - Allocated: {final_allocated:.2f} GB, Reserved: {final_reserved:.2f} GB")
            
            return {
                "success": True,
                "message": "Worker initialized successfully",
                "details": {
                    "model_loaded": True,
                    "storage_connected": True,
                    "cuda_available": True,
                    "gpu_memory_gb": final_allocated
                }
            }
            
        except Exception as model_error:
            error_details = {
                "error_type": "model_loading_error",
                "message": f"Failed to load FLUX model: {str(model_error)}",
                "model_name": "black-square/flux-1-dev",
                "torch_dtype": "bfloat16",
                "traceback": traceback.format_exc()
            }
            logger.error(f"Model loading failed: {error_details}")
            
            # Clean up GPU memory if model loading failed
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("GPU memory cleared after model loading failure")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup GPU memory: {str(cleanup_error)}")
            
            return {
                "success": False,
                "error": error_details["message"],
                "error_type": "initialization_error",
                "details": error_details
            }

    except Exception as e:
        error_details = {
            "error_type": "unexpected_initialization_error",
            "message": f"Unexpected error during worker initialization: {str(e)}",
            "traceback": traceback.format_exc()
        }
        logger.error(f"Unexpected initialization error: {error_details}")
        
        # Clean up GPU memory on any initialization failure
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cleared after initialization failure")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup GPU memory: {str(cleanup_error)}")
            
        return {
            "success": False,
            "error": error_details["message"],
            "error_type": "initialization_error",
            "details": error_details
        }

def handler(job):
    global pipe, s3

    try:
        # Initialize worker if not already done
        if pipe is None or s3 is None:
            logger.info("Worker not initialized, attempting initialization...")
            init_result = initialize_worker()
            if not init_result.get("success", False):
                # Return structured error response from initialization
                error_response = {
                    "error": init_result.get("error", "Unknown initialization error"),
                    "error_type": init_result.get("error_type", "initialization_error"),
                    "status": "initialization_failed"
                }
                
                # Include detailed error information if available
                if "details" in init_result:
                    error_response["details"] = init_result["details"]
                
                logger.error(f"Worker initialization failed: {error_response}")
                return error_response

        # Validate and sanitize input
        try:
            job_input = job.get("input", {})
            
            # Validate and sanitize the request
            prompt, user_id = validate_request(job_input)
            
            logger.info(f"Processing request for user: {user_id}, prompt length: {len(prompt)}")
            
        except ValidationError as validation_error:
            error_response = {
                "error": validation_error.message,
                "error_type": validation_error.error_type,
                "status": "validation_failed"
            }
            
            # Include detailed error information
            if validation_error.details:
                error_response["details"] = validation_error.details
            
            logger.error(f"Request validation failed: {error_response}")
            return error_response
            
        except Exception as validation_error:
            error_msg = f"Unexpected validation error: {str(validation_error)}"
            logger.error(error_msg)
            logger.error(f"Validation error traceback: {traceback.format_exc()}")
            return {
                "error": error_msg,
                "error_type": "validation_error",
                "status": "validation_failed"
            }

        # Generate the image
        try:
            logger.info("Starting image generation...")
            
            # Log GPU memory before generation
            if torch.cuda.is_available():
                memory_allocated = torch.cuda.memory_allocated() / 1024**3
                memory_reserved = torch.cuda.memory_reserved() / 1024**3
                logger.info(f"GPU memory before generation - Allocated: {memory_allocated:.2f} GB, Reserved: {memory_reserved:.2f} GB")
            
            image = pipe(prompt=prompt, num_inference_steps=25).images[0]
            logger.info("Image generation completed")
            
        except Exception as generation_error:
            error_msg = f"Image generation failed: {str(generation_error)}"
            logger.error(error_msg)
            logger.error(f"Generation error traceback: {traceback.format_exc()}")
            
            # Clean up GPU memory after generation failure
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cleared after generation failure")
            
            return {"error": error_msg}

        # Convert the image to a byte buffer
        try:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            logger.info("Image converted to buffer")
        except Exception as buffer_error:
            error_msg = f"Image buffer conversion failed: {str(buffer_error)}"
            logger.error(error_msg)
            logger.error(f"Buffer error traceback: {traceback.format_exc()}")
            
            # Clean up GPU memory after buffer failure
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cleared after buffer failure")
            
            return {"error": error_msg}

        # Upload to Supabase Storage
        try:
            # Generate safe file path to prevent directory traversal
            try:
                file_path = sanitize_file_path(user_id, "generated_image.png")
            except ValidationError as path_error:
                error_response = {
                    "error": path_error.message,
                    "error_type": path_error.error_type,
                    "status": "path_validation_failed"
                }
                if path_error.details:
                    error_response["details"] = path_error.details
                
                logger.error(f"File path validation failed: {error_response}")
                
                # Clean up GPU memory after path validation failure
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("GPU memory cleared after path validation failure")
                
                return error_response
            
            BUCKET_NAME = os.getenv("SUPABASE_BUCKET_USER_UPLOADS", "user_uploads")

            logger.info(f"Uploading to: {file_path}")
            s3.upload_fileobj(
                buffer,
                BUCKET_NAME,
                file_path,
                ExtraArgs={'ContentType': 'image/png'}
            )
            logger.info("Upload completed")
        except Exception as upload_error:
            error_msg = f"Image upload failed: {str(upload_error)}"
            logger.error(error_msg)
            logger.error(f"Upload error traceback: {traceback.format_exc()}")
            
            # Clean up GPU memory after upload failure
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cleared after upload failure")
            
            return {"error": error_msg}

        # Create a signed URL for the newly uploaded image
        try:
            signed_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': BUCKET_NAME, 'Key': file_path},
                ExpiresIn=3600  # URL is valid for 1 hour
            )
            logger.info("Signed URL generated successfully")
        except Exception as url_error:
            error_msg = f"Signed URL generation failed: {str(url_error)}"
            logger.error(error_msg)
            logger.error(f"URL generation error traceback: {traceback.format_exc()}")
            
            # Clean up GPU memory after URL generation failure
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory cleared after URL generation failure")
            
            return {"error": error_msg}

        # Clean up GPU memory after successful generation
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            memory_allocated = torch.cuda.memory_allocated() / 1024**3
            memory_reserved = torch.cuda.memory_reserved() / 1024**3
            logger.info(f"GPU memory after cleanup - Allocated: {memory_allocated:.2f} GB, Reserved: {memory_reserved:.2f} GB")

        logger.info("Generation and upload completed successfully")
        return {
            "status": "success",
            "image_url": signed_url
        }

    except Exception as e:
        error_msg = f"Unexpected error in handler: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Handler error traceback: {traceback.format_exc()}")
        
        # Clean up GPU memory on any unexpected error
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("GPU memory cleared after unexpected error")
        
        return {"error": error_msg}

if __name__ == "__main__":
    # Add startup logging
    logger.info("=== STARTING RUNPOD WORKER ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Environment variables: SUPABASE_URL={'set' if os.getenv('SUPABASE_URL') else 'NOT SET'}")
    logger.info(f"Environment variables: SUPABASE_SERVICE_KEY={'set' if os.getenv('SUPABASE_SERVICE_KEY') else 'NOT SET'}")
    
    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"CUDA device count: {torch.cuda.device_count()}")
            logger.info(f"Current CUDA device: {torch.cuda.current_device()}")
    except Exception as e:
        logger.error(f"Error checking PyTorch/CUDA: {e}")
    
    # Validate critical environment variables before starting
    required_env_vars = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"CRITICAL: Missing required environment variables: {missing_vars}")
        logger.error("Worker cannot start without these environment variables")
        logger.error("Please set these in your RunPod environment configuration")
        sys.exit(1)
    
    logger.info("Environment validation passed")
    logger.info("Starting RunPod serverless handler...")
    start(handler)