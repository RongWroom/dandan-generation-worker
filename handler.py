import runpod
from runpod.serverless import start
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def handler(job):
    logger.info(f"Baseline worker received a job: {job}")
    return {"message": "Hello from the baseline Generation Worker!"}

if __name__ == "__main__":
    logger.info("Starting baseline worker...")
    start(handler)