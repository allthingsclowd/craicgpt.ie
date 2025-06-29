#!/usr/bin/env python3
"""
CraicGPT Date Range Test Script

This script demonstrates the new date range functionality for all three Lambda functions:
1. Prompt Generator - Creates prompts with dynamic context
2. LLM Handler - Processes text generation
3. Image Handler - Processes image generation

Usage:
    python test_date_range.py --single-date 2025-01-15
    python test_date_range.py --date-range 2025-01-10 2025-01-16
    python test_date_range.py --help
"""

import json
import boto3
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any

# Configuration
LAMBDA_FUNCTIONS = {
    "prompt_generator": "craicgpt-prompt-generator",
    "llm_handler": "craicgpt-llm-handler", 
    "image_handler": "craicgpt-image-handler"
}

class CraicGPTTester:
    def __init__(self, region: str = "eu-west-1"):
        self.lambda_client = boto3.client("lambda", region_name=region)
        
    def invoke_lambda(self, function_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a Lambda function and return the response"""
        try:
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload)
            )
            
            response_payload = json.loads(response["Payload"].read())
            return response_payload
            
        except Exception as e:
            return {"error": str(e), "function": function_name}
    
    def test_single_date(self, date: str):
        """Test single date processing"""
        print(f"\n🗓️  Testing Single Date: {date}")
        print("=" * 60)
        
        payload = {"date": date}
        
        # Test each function
        for func_type, func_name in LAMBDA_FUNCTIONS.items():
            print(f"\n📋 Testing {func_type}...")
            
            result = self.invoke_lambda(func_name, payload)
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                self.print_result_summary(func_type, result)
    
    def test_date_range(self, start_date: str, end_date: str):
        """Test date range processing"""
        print(f"\n📅 Testing Date Range: {start_date} to {end_date}")
        print("=" * 60)
        
        payload = {"start_date": start_date, "end_date": end_date}
        
        # Test each function
        for func_type, func_name in LAMBDA_FUNCTIONS.items():
            print(f"\n📋 Testing {func_type}...")
            
            result = self.invoke_lambda(func_name, payload)
            
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                self.print_result_summary(func_type, result)
    
    def test_custom_configuration(self):
        """Test custom configuration options"""
        print(f"\n⚙️  Testing Custom Configuration")
        print("=" * 60)
        
        # Test with specific models and prompts
        payload = {
            "dates": ["2025-01-15", "2025-01-20"],
            "prompt_ids": ["llm_01", "llm_03"],  # Only main article and LLM story
            "model_ids": ["anthropic.claude-3-sonnet-20240229-v1:0"]  # Only Claude
        }
        
        print(f"\n📋 Testing LLM handler with custom config...")
        result = self.invoke_lambda(LAMBDA_FUNCTIONS["llm_handler"], payload)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        else:
            self.print_result_summary("llm_handler", result)
    
    def print_result_summary(self, func_type: str, result: Dict[str, Any]):
        """Print a summary of the function result"""
        
        if func_type == "prompt_generator":
            print(f"✅ Status: {result.get('status', 'Unknown')}")
            print(f"📝 Prompts Generated: {result.get('prompts_generated', 0)}")
            print(f"🗓️  Dates Processed: {len(result.get('dates_processed', []))}")
            
            config = result.get('configuration', {})
            print(f"🌐 Fresh Context: {'✓' if config.get('fresh_context_enabled') else '✗'}")
            print(f"🌤️  Historical Weather: {'✓' if config.get('historical_weather_enabled') else '✗'}")
            
            sample = result.get('sample_daily_context', {})
            if sample:
                print(f"📊 Sample Context:")
                print(f"   - Weather Source: {sample.get('weather_source', 'unknown')}")
                print(f"   - Trending Topics: {', '.join(sample.get('trending_topics', [])[:3])}")
                print(f"   - News Categories: {', '.join(sample.get('news_categories', []))}")
        
        elif func_type == "llm_handler":
            print(f"✅ Status: {result.get('status', 'Unknown')}")
            print(f"⏱️  Processing Time: {result.get('processing_time_seconds', 0):.1f}s")
            print(f"🗓️  Dates Processed: {result.get('dates_processed', 0)}/{result.get('total_dates', 0)}")
            
            if result.get('dates_failed', 0) > 0:
                print(f"❌ Failed Dates: {result.get('dates_failed', 0)}")
            
            print(f"🤖 Models Used: {', '.join(result.get('models_used', []))}")
            print(f"📝 Prompt IDs: {', '.join(result.get('prompt_ids', []))}")
        
        elif func_type == "image_handler":
            print(f"✅ Status: {result.get('status', 'Unknown')}")
            print(f"⏱️  Processing Time: {result.get('processing_time_seconds', 0):.1f}s")
            print(f"🗓️  Dates Processed: {result.get('dates_processed', 0)}/{result.get('total_dates', 0)}")
            print(f"🖼️  Total Images: {result.get('total_images_generated', 0)}")
            
            if result.get('dates_failed', 0) > 0:
                print(f"❌ Failed Dates: {result.get('dates_failed', 0)}")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Test CraicGPT date range functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_date_range.py --single-date 2025-01-15
  python test_date_range.py --date-range 2025-01-10 2025-01-16
  python test_date_range.py --custom-config
  python test_date_range.py --all-tests
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    
    group.add_argument(
        "--single-date",
        type=str,
        help="Test with a single date (YYYY-MM-DD)"
    )
    
    group.add_argument(
        "--date-range",
        nargs=2,
        metavar=("START_DATE", "END_DATE"),
        help="Test with a date range (YYYY-MM-DD YYYY-MM-DD)"
    )
    
    group.add_argument(
        "--custom-config",
        action="store_true",
        help="Test custom configuration options"
    )
    
    group.add_argument(
        "--all-tests",
        action="store_true",
        help="Run all test scenarios"
    )
    
    parser.add_argument(
        "--region",
        type=str,
        default="eu-west-1",
        help="AWS region (default: eu-west-1)"
    )
    
    return parser.parse_args()

def main():
    """Main test runner"""
    args = parse_arguments()
    
    print("🚀 CraicGPT Date Range Functionality Test")
    print("=" * 60)
    
    tester = CraicGPTTester(region=args.region)
    
    try:
        if args.single_date:
            tester.test_single_date(args.single_date)
            
        elif args.date_range:
            start_date, end_date = args.date_range
            tester.test_date_range(start_date, end_date)
            
        elif args.custom_config:
            tester.test_custom_configuration()
            
        elif args.all_tests:
            # Run all test scenarios
            today = datetime.now().date()
            yesterday = (today - timedelta(days=1)).isoformat()
            week_start = (today - timedelta(days=6)).isoformat()
            week_end = today.isoformat()
            
            print("\n🎯 Running All Test Scenarios")
            
            # Single date test
            tester.test_single_date(yesterday)
            
            # Date range test
            tester.test_date_range(week_start, week_end)
            
            # Custom configuration test
            tester.test_custom_configuration()
    
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
    
    print("\n✨ Test completed!")

if __name__ == "__main__":
    main() 