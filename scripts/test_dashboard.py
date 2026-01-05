#!/usr/bin/env python3
"""
Test script for Week 11 Dashboard features
"""

import requests
import json
import time
from datetime import datetime, timedelta
from shared.utils.logging import logger


class DashboardTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.headers = {
            "Authorization": "Bearer admin-secret-token-change-in-production",
            "Content-Type": "application/json"
        }
    
    def test_health_endpoint(self):
        """Test dashboard health endpoint"""
        print("\n=== Testing Dashboard Health ===")
        try:
            response = requests.get(f"{self.base_url}/admin/v1/health", headers=self.headers)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_dashboard_summary(self):
        """Test dashboard summary endpoint"""
        print("\n=== Testing Dashboard Summary ===")
        try:
            response = requests.get(
                f"{self.base_url}/admin/v1/dashboard/summary",
                headers=self.headers
            )
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Total Tenants: {data.get('total_tenants')}")
                print(f"Active Users: {data.get('active_users')}")
                print(f"Total Files: {data.get('total_files')}")
                print(f"Total Reports: {data.get('total_reports')}")
                print(f"API Usage: {data.get('api_usage', {}).get('total_calls')}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_usage_statistics(self):
        """Test usage statistics endpoint"""
        print("\n=== Testing Usage Statistics ===")
        try:
            # Test with date range
            params = {
                "start_date": (datetime.now() - timedelta(days=7)).isoformat(),
                "end_date": datetime.now().isoformat(),
                "granularity": "day"
            }
            
            response = requests.get(
                f"{self.base_url}/admin/v1/dashboard/usage",
                headers=self.headers,
                params=params
            )
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Time Range: {data.get('time_range')}")
                print(f"Data Points: {len(data.get('data', []))}")
                print(f"Total API Calls: {data.get('total_usage', {}).get('api_calls')}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_billing_overview(self):
        """Test billing overview endpoint"""
        print("\n=== Testing Billing Overview ===")
        try:
            response = requests.get(
                f"{self.base_url}/admin/v1/dashboard/billing",
                headers=self.headers
            )
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Total Revenue: ${data.get('total_revenue', 0):.2f}")
                print(f"Active Subscriptions: {data.get('active_subscriptions')}")
                print(f"Pending Invoices: {data.get('pending_invoices')}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_system_health(self):
        """Test system health endpoint"""
        print("\n=== Testing System Health ===")
        try:
            response = requests.get(
                f"{self.base_url}/admin/v1/dashboard/health",
                headers=self.headers
            )
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                services = data.get('services', {})
                
                print("Service Status:")
                for service, status in services.items():
                    print(f"  {service}: {status.get('status')}")
                
                return all(
                    s.get('status') == 'healthy' 
                    for s in services.values() 
                    if s.get('status')
                )
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_export_functionality(self):
        """Test dashboard export functionality"""
        print("\n=== Testing Export Functionality ===")
        try:
            # Test JSON export
            params = {
                "format": "json",
                "data_type": "summary"
            }
            
            response = requests.get(
                f"{self.base_url}/admin/v1/dashboard/export",
                headers=self.headers,
                params=params
            )
            
            if response.status_code == 200:
                print("JSON export successful")
                
                # Test CSV export
                params["format"] = "csv"
                response = requests.get(
                    f"{self.base_url}/admin/v1/dashboard/export",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    print("CSV export successful")
                    return True
                else:
                    print(f"CSV export failed: {response.text}")
                    return False
            else:
                print(f"JSON export failed: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def test_billing_service(self):
        """Test billing service endpoints"""
        print("\n=== Testing Billing Service ===")
        try:
            billing_url = "http://localhost:8006"
            
            # Test billing health
            response = requests.get(f"{billing_url}/billing/health")
            print(f"Billing Health Status: {response.status_code}")
            
            if response.status_code == 200:
                # Test usage tracking
                usage_data = {
                    "tenant_id": "test_tenant",
                    "service": "api_gateway",
                    "metric": "api_calls",
                    "value": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
                response = requests.post(
                    f"{billing_url}/billing/usage",
                    json=usage_data,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code in [200, 201]:
                    print("Usage tracking test passed")
                    return True
                else:
                    print(f"Usage tracking failed: {response.text}")
                    return False
            else:
                print(f"Billing service not healthy: {response.text}")
                return False
        except Exception as e:
            print(f"Error connecting to billing service: {e}")
            return False
    
    def run_all_tests(self):
        """Run all dashboard tests"""
        print("=" * 60)
        print("Running Week 11 Dashboard Tests")
        print("=" * 60)
        
        tests = [
            ("Health Endpoint", self.test_health_endpoint),
            ("Dashboard Summary", self.test_dashboard_summary),
            ("Usage Statistics", self.test_usage_statistics),
            ("Billing Overview", self.test_billing_overview),
            ("System Health", self.test_system_health),
            ("Export Functionality", self.test_export_functionality),
            ("Billing Service", self.test_billing_service)
        ]
        
        results = []
        for test_name, test_func in tests:
            print(f"\nRunning: {test_name}")
            try:
                success = test_func()
                results.append((test_name, success))
                status = "✓ PASS" if success else "✗ FAIL"
                print(f"Result: {status}")
            except Exception as e:
                results.append((test_name, False))
                print(f"Error: {e}")
                print("Result: ✗ FAIL")
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for test_name, success in results:
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"{status} - {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        return passed == total


def main():
    """Main test function"""
    tester = DashboardTester()
    
    # Wait for services to start
    print("Waiting for services to start...")
    time.sleep(5)
    
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed! Week 11 features are working correctly.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())