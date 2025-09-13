#!/usr/bin/env python3
"""
Test script for the AI headshot generation handler.
This script tests the minimal fixes implemented in tasks 1-3.
"""

import json
import sys
import os
import traceback
from unittest.mock import Mock, patch
import logging

# Configure logging for testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_validation_fixes():
    """Test the request validation and input sanitization fixes"""
    print("\n=== Testing Request Validation Fixes ===")
    
    # Import the handler module
    try:
        from handler import validate_request, sanitize_prompt, sanitize_user_id, ValidationError
        print("✓ Successfully imported validation functions")
    except ImportError as e:
        print(f"✗ Failed to import validation functions: {e}")
        return False
    
    # Test 1: Valid request
    try:
        valid_input = {
            "prompt": "A professional headshot of a business person",
            "user_id": "test_user_123"
        }
        prompt, user_id = validate_request(valid_input)
        print(f"✓ Valid request processed: prompt='{prompt[:50]}...', user_id='{user_id}'")
    except Exception as e:
        print(f"✗ Valid request failed: {e}")
        return False
    
    # Test 2: Missing prompt
    try:
        invalid_input = {"user_id": "test_user_123"}
        validate_request(invalid_input)
        print("✗ Missing prompt should have failed")
        return False
    except ValidationError as e:
        print(f"✓ Missing prompt correctly rejected: {e.message}")
    except Exception as e:
        print(f"✗ Unexpected error for missing prompt: {e}")
        return False
    
    # Test 3: Missing user_id
    try:
        invalid_input = {"prompt": "A professional headshot"}
        validate_request(invalid_input)
        print("✗ Missing user_id should have failed")
        return False
    except ValidationError as e:
        print(f"✓ Missing user_id correctly rejected: {e.message}")
    except Exception as e:
        print(f"✗ Unexpected error for missing user_id: {e}")
        return False
    
    # Test 4: Prompt too long
    try:
        long_prompt = "A" * 1001  # Exceeds MAX_PROMPT_LENGTH
        invalid_input = {"prompt": long_prompt, "user_id": "test_user"}
        validate_request(invalid_input)
        print("✗ Long prompt should have failed")
        return False
    except ValidationError as e:
        print(f"✓ Long prompt correctly rejected: {e.message}")
    except Exception as e:
        print(f"✗ Unexpected error for long prompt: {e}")
        return False
    
    # Test 5: Invalid user_id characters
    try:
        invalid_input = {"prompt": "A professional headshot", "user_id": "user@domain.com"}
        validate_request(invalid_input)
        print("✗ Invalid user_id should have failed")
        return False
    except ValidationError as e:
        print(f"✓ Invalid user_id correctly rejected: {e.message}")
    except Exception as e:
        print(f"✗ Unexpected error for invalid user_id: {e}")
        return False
    
    print("✓ All validation tests passed")
    return True

def test_initialization_error_handling():
    """Test the initialization error handling fixes"""
    print("\n=== Testing Initialization Error Handling ===")
    
    try:
        from handler import initialize_worker
        print("✓ Successfully imported initialize_worker function")
    except ImportError as e:
        print(f"✗ Failed to import initialize_worker: {e}")
        return False
    
    # Test initialization without environment variables
    original_env = {}
    env_vars_to_test = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
    
    # Save original environment variables
    for var in env_vars_to_test:
        original_env[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]
    
    try:
        # Test missing SUPABASE_URL
        result = initialize_worker()
        if result.get("success", True):
            print("✗ Initialization should have failed without SUPABASE_URL")
            return False
        else:
            print(f"✓ Initialization correctly failed without SUPABASE_URL: {result.get('error', 'Unknown error')}")
        
        # Test with SUPABASE_URL but missing SUPABASE_SERVICE_KEY
        os.environ["SUPABASE_URL"] = "https://test.supabase.co"
        result = initialize_worker()
        if result.get("success", True):
            print("✗ Initialization should have failed without SUPABASE_SERVICE_KEY")
            return False
        else:
            print(f"✓ Initialization correctly failed without SUPABASE_SERVICE_KEY: {result.get('error', 'Unknown error')}")
        
    finally:
        # Restore original environment variables
        for var, value in original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
    
    print("✓ Initialization error handling tests passed")
    return True

def test_handler_error_responses():
    """Test that the handler returns proper error responses instead of crashing"""
    print("\n=== Testing Handler Error Response Behavior ===")
    
    try:
        from handler import handler
        print("✓ Successfully imported handler function")
    except ImportError as e:
        print(f"✗ Failed to import handler: {e}")
        return False
    
    # Test 1: Invalid input format
    try:
        job = {"input": {"invalid": "data"}}  # Missing required fields
        result = handler(job)
        
        if "error" in result:
            print(f"✓ Handler returned error response for invalid input: {result.get('error', 'Unknown error')[:100]}...")
        else:
            print(f"✗ Handler should have returned error for invalid input, got: {result}")
            return False
            
    except Exception as e:
        print(f"✗ Handler crashed instead of returning error response: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    # Test 2: Empty job input
    try:
        job = {}  # No input field
        result = handler(job)
        
        if "error" in result:
            print(f"✓ Handler returned error response for empty job: {result.get('error', 'Unknown error')[:100]}...")
        else:
            print(f"✗ Handler should have returned error for empty job, got: {result}")
            return False
            
    except Exception as e:
        print(f"✗ Handler crashed instead of returning error response: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    # Test 3: Malformed job structure
    try:
        job = {"input": None}  # Null input
        result = handler(job)
        
        if "error" in result:
            print(f"✓ Handler returned error response for null input: {result.get('error', 'Unknown error')[:100]}...")
        else:
            print(f"✗ Handler should have returned error for null input, got: {result}")
            return False
            
    except Exception as e:
        print(f"✗ Handler crashed instead of returning error response: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    print("✓ Handler error response tests passed")
    return True

def test_problematic_prompt():
    """Test with the same type of prompt that was causing crashes"""
    print("\n=== Testing with Problematic Prompt ===")
    
    try:
        from handler import handler
        print("✓ Successfully imported handler function")
    except ImportError as e:
        print(f"✗ Failed to import handler: {e}")
        return False
    
    # Test with a prompt similar to what might have caused crashes
    problematic_prompts = [
        "A professional headshot of a business executive in a modern office setting with natural lighting",
        "Generate a high-quality portrait photo of a confident professional person wearing business attire",
        "Create a professional LinkedIn profile photo of a person in business casual clothing",
        "Professional headshot with clean background and professional lighting setup"
    ]
    
    for i, prompt in enumerate(problematic_prompts, 1):
        try:
            print(f"\nTesting prompt {i}: '{prompt[:50]}...'")
            
            job = {
                "input": {
                    "prompt": prompt,
                    "user_id": f"test_user_{i}"
                }
            }
            
            result = handler(job)
            
            # Check if we get a structured response (either success or error)
            if isinstance(result, dict):
                if "error" in result:
                    print(f"✓ Prompt {i} returned structured error response: {result.get('error_type', 'unknown')} - {result.get('error', 'Unknown error')[:100]}...")
                elif "status" in result:
                    print(f"✓ Prompt {i} returned structured response with status: {result.get('status')}")
                else:
                    print(f"✓ Prompt {i} returned structured response: {list(result.keys())}")
            else:
                print(f"✗ Prompt {i} returned non-dict response: {type(result)} - {str(result)[:100]}...")
                return False
                
        except Exception as e:
            print(f"✗ Prompt {i} caused handler to crash: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return False
    
    print("✓ All problematic prompts handled without crashes")
    return True

def main():
    """Run all tests to verify the minimal fixes"""
    print("Starting comprehensive test of AI headshot generation fixes...")
    print("=" * 60)
    
    tests = [
        ("Request Validation", test_validation_fixes),
        ("Initialization Error Handling", test_initialization_error_handling),
        ("Handler Error Responses", test_handler_error_responses),
        ("Problematic Prompt Handling", test_problematic_prompt)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            if test_func():
                passed += 1
                print(f"✓ {test_name} PASSED")
            else:
                print(f"✗ {test_name} FAILED")
        except Exception as e:
            print(f"✗ {test_name} CRASHED: {e}")
            print(f"Traceback: {traceback.format_exc()}")
    
    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! The minimal fixes are working correctly.")
        print("\nKey improvements verified:")
        print("- ✓ Request validation prevents crashes from invalid input")
        print("- ✓ Initialization errors return structured responses")
        print("- ✓ Handler catches exceptions and returns error responses")
        print("- ✓ Worker stays alive even with problematic prompts")
        return True
    else:
        print(f"❌ {total - passed} tests failed. Review the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)