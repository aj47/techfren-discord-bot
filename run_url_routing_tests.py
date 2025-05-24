#!/usr/bin/env python3
"""
Test runner for URL routing functionality.
This script runs all URL routing tests and provides a comprehensive report.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(command, description):
    """Run a command and return the result."""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        print(f"Command: {command}")
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print(f"\nSTDOUT:\n{result.stdout}")
        
        if result.stderr:
            print(f"\nSTDERR:\n{result.stderr}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_dependencies():
    """Check if required dependencies are available."""
    print("🔍 Checking dependencies...")
    
    required_packages = ['pytest', 'pytest-asyncio']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} is available")
        except ImportError:
            print(f"❌ {package} is missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False
    
    return True

def main():
    """Run all URL routing tests."""
    print("🚀 URL Routing Test Suite")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not Path("apify_handler.py").exists():
        print("❌ Error: apify_handler.py not found. Please run this script from the bot directory.")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Dependencies check failed. Please install missing packages.")
        sys.exit(1)
    
    # Test results
    test_results = []
    
    # Run URL routing tests
    success = run_command(
        "python -m pytest test_url_routing_automated.py -v",
        "Running URL Routing Tests"
    )
    test_results.append(("URL Routing Tests", success))
    
    # Run X scraping tests (URL routing subset)
    success = run_command(
        "python -m pytest test_x_scraping.py::TestXScrapingIntegration::test_url_detection_and_id_extraction_workflow -v",
        "Running URL Detection Workflow Tests"
    )
    test_results.append(("URL Detection Workflow", success))
    
    # Run URL routing integration tests
    success = run_command(
        "python -m pytest test_x_scraping.py::TestXScrapingIntegration::test_url_routing_logic_comprehensive -v",
        "Running Comprehensive URL Routing Tests"
    )
    test_results.append(("Comprehensive URL Routing", success))
    
    # Run simple URL routing test
    success = run_command(
        "python test_url_routing.py",
        "Running Simple URL Routing Test"
    )
    test_results.append(("Simple URL Routing", success))
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    all_passed = True
    for test_name, passed in test_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:<30} {status}")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ URL routing logic is working correctly")
        print("✅ X.com URLs will be properly routed to Apify")
        print("✅ Fallback to Firecrawl is working")
        print("✅ Non-Twitter URLs will use Firecrawl")
    else:
        print("❌ SOME TESTS FAILED!")
        print("Please check the test output above for details")
    
    print(f"{'='*60}")
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
