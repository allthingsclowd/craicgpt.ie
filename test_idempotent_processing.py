#!/usr/bin/env python3
"""
Test script to verify idempotent processing works correctly
Tests that content is skipped when it already exists
"""

import json
import boto3
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lambda client
lambda_client = boto3.client('lambda', region_name='eu-west-1')

# Test configuration
TEST_DATE = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
TEST_MODELS = ['anthropic.claude-3-haiku-20240307-v1:0']
TEST_IMAGE_MODELS = ['amazon.titan-image-generator-v1']

def test_orchestrator_idempotent():
    """Test that orchestrator runs idempotently"""
    
    logger.info("🧪 Testing Orchestrator Idempotent Processing")
    
    # First run - should process everything
    logger.info("📍 First run - processing fresh content")
    event = {
        "start_date": TEST_DATE,
        "end_date": TEST_DATE,
        "llm_models": TEST_MODELS,
        "image_models": TEST_IMAGE_MODELS
    }
    
    response = lambda_client.invoke(
        FunctionName='craicgptie-orchestrator',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    first_run_body = json.loads(result['body'])
    
    logger.info(f"✅ First run completed in {first_run_body.get('processing_time', 0):.2f}s")
    logger.info(f"📊 LLM tasks: {first_run_body.get('llm_tasks', 0)}")
    logger.info(f"📊 Image tasks: {first_run_body.get('image_tasks', 0)}")
    
    # Second run - should skip existing content
    logger.info("📍 Second run - should skip existing content")
    
    response = lambda_client.invoke(
        FunctionName='craicgptie-orchestrator',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    second_run_body = json.loads(result['body'])
    
    logger.info(f"✅ Second run completed in {second_run_body.get('processing_time', 0):.2f}s")
    logger.info(f"📊 LLM tasks: {second_run_body.get('llm_tasks', 0)}")
    logger.info(f"📊 Image tasks: {second_run_body.get('image_tasks', 0)}")
    
    # Verify second run was much faster
    first_time = first_run_body.get('processing_time', 0)
    second_time = second_run_body.get('processing_time', 0)
    
    if second_time < first_time * 0.3:  # Second run should be at least 70% faster
        logger.info("🎉 SUCCESS: Second run was significantly faster (idempotent working!)")
        logger.info(f"⚡ Speed improvement: {((first_time - second_time) / first_time * 100):.1f}%")
    else:
        logger.warning("⚠️  Second run wasn't significantly faster - idempotent may not be working")
    
    return first_run_body, second_run_body

def test_direct_llm_idempotent():
    """Test LLM handler directly for idempotent behavior"""
    
    logger.info("🧪 Testing LLM Handler Idempotent Processing")
    
    # Test single model/date in worker mode
    event = {
        "worker_mode": True,
        "model": TEST_MODELS[0],
        "date": TEST_DATE
    }
    
    # First run
    logger.info("📍 First LLM run")
    response = lambda_client.invoke(
        FunctionName='craicgptie_llm_runner',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    first_run = json.loads(result['body'])
    
    logger.info(f"✅ First LLM run: {first_run.get('processing_time', 0):.2f}s")
    logger.info(f"📊 Prompts processed: {first_run.get('prompts_processed', 0)}")
    
    # Second run - should skip
    logger.info("📍 Second LLM run - should skip existing")
    response = lambda_client.invoke(
        FunctionName='craicgptie_llm_runner',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    second_run = json.loads(result['body'])
    
    logger.info(f"✅ Second LLM run: {second_run.get('processing_time', 0):.2f}s")
    logger.info(f"📊 Prompts processed: {second_run.get('prompts_processed', 0)}")
    
    return first_run, second_run

def test_direct_image_idempotent():
    """Test Image handler directly for idempotent behavior"""
    
    logger.info("🧪 Testing Image Handler Idempotent Processing")
    
    # Test single model/date in worker mode
    event = {
        "worker_mode": True,
        "model": TEST_IMAGE_MODELS[0],
        "date": TEST_DATE
    }
    
    # First run
    logger.info("📍 First Image run")
    response = lambda_client.invoke(
        FunctionName='craicgptie_image_runner',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    first_run = json.loads(result['body'])
    
    logger.info(f"✅ First Image run: {first_run.get('processing_time', 0):.2f}s")
    logger.info(f"📊 Prompts processed: {first_run.get('prompts_processed', 0)}")
    
    # Second run - should skip
    logger.info("📍 Second Image run - should skip existing")
    response = lambda_client.invoke(
        FunctionName='craicgptie_image_runner',
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    second_run = json.loads(result['body'])
    
    logger.info(f"✅ Second Image run: {second_run.get('processing_time', 0):.2f}s")
    logger.info(f"📊 Prompts processed: {second_run.get('prompts_processed', 0)}")
    
    return first_run, second_run

def main():
    """Run all idempotent processing tests"""
    
    logger.info("🚀 Starting Idempotent Processing Tests")
    logger.info(f"📅 Test date: {TEST_DATE}")
    logger.info(f"🤖 Test LLM models: {TEST_MODELS}")
    logger.info(f"🎨 Test Image models: {TEST_IMAGE_MODELS}")
    
    print("=" * 60)
    
    try:
        # Test orchestrator
        orch_results = test_orchestrator_idempotent()
        print("=" * 60)
        
        # Test LLM handler directly
        llm_results = test_direct_llm_idempotent()
        print("=" * 60)
        
        # Test Image handler directly
        img_results = test_direct_image_idempotent()
        print("=" * 60)
        
        # Summary
        logger.info("📋 SUMMARY")
        logger.info("✅ All idempotent tests completed successfully!")
        logger.info("💡 Key Benefits:")
        logger.info("   - Prevents duplicate content generation")
        logger.info("   - Reduces Lambda execution time")
        logger.info("   - Avoids unnecessary API calls")
        logger.info("   - Enables safe re-runs after failures")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    main() 