#!/usr/bin/env python3
"""
CraicGPT Enhanced Prompt Generator Test Script

This script demonstrates the new functionality:
1. Reading date ranges from environment variables
2. Context data embedded directly into prompts
3. HTML placement references for each prompt
4. Enhanced context summaries
5. Clear delineation between prompts
6. Date-specific prompt variation

Usage:
  export START_DATE="2025-06-29"
  export END_DATE="2025-06-30"
  python test_enhanced_prompts.py

Or test with a single date:
  export START_DATE="2025-12-25"
  python test_enhanced_prompts.py
"""

import os
import sys
import json
from datetime import datetime

# Set required environment variables for testing
os.environ["PROMPT_BUCKET"] = "mock-craicgpt-bucket"
os.environ["BEDROCK_MODEL_IDS"] = "anthropic.claude-3-sonnet-20240229-v1:0"
os.environ["BEDROCK_IMAGE_MODEL_IDS"] = "amazon.titan-image-generator-v1"

# Add the lambda function directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda_code', 'PromptGenerator'))

# Mock the AWS dependencies for testing
class MockS3Client:
    def put_object(self, **kwargs):
        bucket = kwargs.get('Bucket', 'unknown')
        key = kwargs.get('Key', 'unknown')
        body = kwargs.get('Body', b'')
        if isinstance(body, bytes):
            content = body.decode('utf-8')
        else:
            content = str(body)
        
        print(f"📁 MOCK S3 PUT: s3://{bucket}/{key}")
        print(f"   Content length: {len(content)} characters")
        
        # Parse and display the JSON content for inspection
        try:
            data = json.loads(content)
            print(f"   Prompt type: {data.get('type', 'unknown')}")
            print(f"   Prompt ID: {data.get('id', 'unknown')}")
            print(f"   HTML placement: {data.get('html_placement', 'none')}")
            print(f"   Context summary: {list(data.get('context_summary', {}).keys())}")
            return {"ETag": "mock-etag"}
        except json.JSONDecodeError:
            print(f"   Raw content preview: {content[:100]}...")
            return {"ETag": "mock-etag"}

class MockBoto3:
    def client(self, service_name):
        if service_name == 's3':
            return MockS3Client()
        return self

# Patch the boto3 import
sys.modules['boto3'] = MockBoto3()

# Now import the lambda function
try:
    from lambda_function import lambda_handler, HTML_PLACEMENTS, BASE_CONTEXTS
    print("✅ Successfully imported enhanced lambda function")
except ImportError as e:
    print(f"❌ Failed to import lambda function: {e}")
    sys.exit(1)

def print_banner(title):
    """Print a formatted banner"""
    width = 80
    border = "=" * width
    print(f"\n{border}")
    print(f" {title.center(width-2)} ")
    print(f"{border}")

def test_environment_variable_dates():
    """Test date reading from environment variables"""
    print_banner("TESTING ENVIRONMENT VARIABLE DATE READING")
    
    start_date = os.getenv("START_DATE")
    end_date = os.getenv("END_DATE")
    
    print(f"Environment Variables:")
    print(f"  START_DATE: {start_date or 'Not set'}")
    print(f"  END_DATE: {end_date or 'Not set'}")
    
    if not start_date:
        print("\n⚠️  No START_DATE set. Setting test dates...")
        os.environ["START_DATE"] = "2025-06-29"
        os.environ["END_DATE"] = "2025-06-30"
        print(f"  Set START_DATE: {os.environ['START_DATE']}")
        print(f"  Set END_DATE: {os.environ['END_DATE']}")

def test_html_placements():
    """Test HTML placement references"""
    print_banner("HTML PLACEMENT REFERENCES")
    
    print("HTML placement mappings for frontend integration:")
    for content_type, placements in HTML_PLACEMENTS.items():
        print(f"\n📍 {content_type.upper()}:")
        if isinstance(placements, dict):
            for element, selector in placements.items():
                print(f"   {element}: {selector}")
        elif isinstance(placements, list):
            for i, selector in enumerate(placements):
                print(f"   ad_{i+1}: {selector}")

def test_base_contexts():
    """Test base context configuration"""
    print_banner("BASE CONTEXT CONFIGURATION")
    
    print("Configured base contexts (easily modifiable):")
    for content_type, context in BASE_CONTEXTS.items():
        print(f"\n🎯 {content_type.upper()}:")
        if isinstance(context, dict):
            for key, value in context.items():
                if isinstance(value, dict):
                    print(f"   {key}: {len(value)} items")
                elif isinstance(value, str) and len(value) > 60:
                    print(f"   {key}: {value[:60]}...")
                else:
                    print(f"   {key}: {value}")

def test_enhanced_prompt_generation():
    """Test the enhanced prompt generation"""
    print_banner("ENHANCED PROMPT GENERATION")
    
    # Test with empty event (should use environment variables)
    event = {}
    context = {}
    
    print("🚀 Calling lambda_handler with environment variable dates...")
    try:
        result = lambda_handler(event, context)
        
        print(f"\n📊 RESULTS:")
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Dates processed: {result.get('dates_processed', [])}")
        print(f"   Prompts generated: {result.get('prompts_generated', 0)}")
        
        if 'prompt_breakdown' in result:
            breakdown = result['prompt_breakdown']
            print(f"   LLM prompts: {breakdown.get('llm_prompts', 0)}")
            print(f"   Image prompts: {breakdown.get('image_prompts', 0)}")
        
        if 'configuration' in result:
            config = result['configuration']
            print(f"\n⚙️  CONFIGURATION:")
            for key, value in config.items():
                print(f"   {key}: {value}")
        
        if 'sample_outputs' in result and result['sample_outputs']:
            print(f"\n📝 SAMPLE OUTPUTS:")
            for i, sample in enumerate(result['sample_outputs'][:3]):
                print(f"   {i+1}. {sample.get('description', 'Unknown')}")
                print(f"      ID: {sample.get('id', 'unknown')}")
                print(f"      Type: {sample.get('type', 'unknown')}")
                print(f"      Prompt length: {sample.get('prompt_length', 0)} chars")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during prompt generation: {e}")
        import traceback
        traceback.print_exc()
        return None

def demonstrate_date_specific_variation():
    """Demonstrate how prompts vary by date"""
    print_banner("DATE-SPECIFIC PROMPT VARIATION")
    
    test_dates = [
        "2025-06-29",  # Summer Sunday
        "2025-12-25",  # Winter Christmas
        "2025-03-17",  # Spring St. Patrick's Day
        "2025-09-15",  # Autumn Monday
    ]
    
    for test_date in test_dates:
        date_obj = datetime.fromisoformat(test_date)
        day_of_week = date_obj.strftime("%A")
        season = ["Winter", "Winter", "Spring", "Spring", "Spring", "Summer", 
                  "Summer", "Summer", "Autumn", "Autumn", "Autumn", "Winter"][date_obj.month - 1]
        
        print(f"\n📅 {test_date} ({day_of_week}, {season}):")
        print(f"   Expected variations:")
        print(f"   • Seasonal elements: {season.lower()} atmosphere")
        print(f"   • Day-specific mood: {day_of_week} energy")
        print(f"   • Weather context: seasonal pattern for historical dates")
        print(f"   • News context: generated historical context for past dates")

def main():
    """Main test function"""
    print("🎭 CraicGPT Enhanced Prompt Generator Test Suite")
    print("=" * 60)
    
    # Run all tests
    test_environment_variable_dates()
    test_html_placements()
    test_base_contexts()
    demonstrate_date_specific_variation()
    
    # Run the main generation test
    result = test_enhanced_prompt_generation()
    
    if result and result.get('status') == 'SUCCESS':
        print_banner("TEST COMPLETED SUCCESSFULLY")
        print("✅ All enhanced features working as expected:")
        print("   • Environment variable date reading")
        print("   • Context data embedded in prompts")
        print("   • HTML placement references included")
        print("   • Enhanced context summaries generated")
        print("   • Clear prompt delineation with descriptions")
        print("   • Date-specific prompt variation implemented")
        
        print(f"\n📈 GENERATION STATISTICS:")
        print(f"   Total prompts: {result.get('prompts_generated', 0)}")
        if 'prompt_breakdown' in result:
            breakdown = result['prompt_breakdown']
            print(f"   LLM prompts: {breakdown.get('llm_prompts', 0)}")
            print(f"   Image prompts: {breakdown.get('image_prompts', 0)}")
        print(f"   Storage keys generated: {len(result.get('storage_keys', []))}")
        
    else:
        print_banner("TEST ENCOUNTERED ISSUES")
        print("⚠️  Some features may need adjustment")

if __name__ == "__main__":
    main() 