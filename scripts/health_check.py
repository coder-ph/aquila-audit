#!/usr/bin/env python3
"""
Health check script for Aquila Audit services.
"""
import requests
import time
import sys
from typing import Dict, List, Tuple

HEALTH_ENDPOINTS = [
    ("API Gateway", "http://localhost:8000/health"),
    ("Admin Service", "http://localhost:8001/health"),
]

SERVICE_PORTS = [
    ("PostgreSQL", 5432),
    ("Redis", 6379),
    ("RabbitMQ", 5672),
]


def check_port(host: str, port: int) -> bool:
    """Check if a port is open."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_http_endpoint(name: str, url: str) -> Tuple[bool, str]:
    """Check HTTP endpoint health."""
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True, "✅ Healthy"
        else:
            return False, f"❌ HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "❌ Connection refused"
    except requests.exceptions.Timeout:
        return False, "❌ Timeout"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"


def main():
    """Run health checks."""
    print("🔍 Aquila Audit Health Check")
    print("=" * 50)
    
    all_healthy = True
    
    # Check service ports
    print("\n📡 Infrastructure Services:")
    for service_name, port in SERVICE_PORTS:
        is_healthy = check_port("localhost", port)
        status = "✅ Running" if is_healthy else "❌ Not running"
        print(f"  {service_name}: {status}")
        if not is_healthy:
            all_healthy = False
    
    # Check HTTP endpoints
    print("\n🌐 HTTP Services:")
    for service_name, url in HEALTH_ENDPOINTS:
        is_healthy, message = check_http_endpoint(service_name, url)
        print(f"  {service_name}: {message}")
        if not is_healthy:
            all_healthy = False
    
    # Check RabbitMQ management
    print("\n🐰 RabbitMQ Management:")
    try:
        response = requests.get("http://localhost:15672", timeout=5)
        if response.status_code == 200:
            print("  Management UI: ✅ Accessible")
        else:
            print(f"  Management UI: ❌ HTTP {response.status_code}")
            all_healthy = False
    except Exception as e:
        print(f"  Management UI: ❌ {str(e)}")
        all_healthy = False
    
    print("\n" + "=" * 50)
    
    if all_healthy:
        print("🎉 All services are healthy!")
        return 0
    else:
        print("⚠️  Some services are not healthy. Check the logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())