import runpod

def handler(job):
    print("Generation worker received a job:")
    print(job)
    
    # Placeholder for generation logic
    return {"message": "Hello from the Generation Worker!"}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
