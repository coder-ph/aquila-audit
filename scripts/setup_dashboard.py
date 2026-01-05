#!/usr/bin/env python3
"""
Dashboard setup script for Week 11
"""

import json
from pathlib import Path
from shared.database.session import SessionLocal
from shared.utils.logging import logger


def setup_dashboard_directories():
    """Create necessary directories for dashboard data"""
    directories = [
        "data/dashboards/cache",
        "data/dashboards/exports",
        "data/dashboards/snapshots",
        "data/billing/reports",
        "data/monitoring/metrics"
    ]
    
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {dir_path}")


def create_dashboard_config():
    """Create default dashboard configuration"""
    config = {
        "dashboard": {
            "refresh_interval": 30,  # seconds
            "cache_ttl": 300,  # seconds
            "max_data_points": 1000,
            "export_formats": ["json", "csv", "pdf"]
        },
        "charts": {
            "usage_over_time": {
                "type": "line",
                "colors": ["#3498db", "#2ecc71", "#e74c3c"],
                "time_range": "7d"
            },
            "tenant_distribution": {
                "type": "pie",
                "colors": ["#3498db", "#9b59b6", "#2ecc71", "#e74c3c", "#f1c40f"]
            },
            "cost_breakdown": {
                "type": "bar",
                "stacked": True,
                "time_range": "30d"
            }
        },
        "widgets": {
            "summary_stats": {
                "enabled": True,
                "metrics": ["active_tenants", "total_revenue", "api_usage", "storage_used"]
            },
            "recent_activity": {
                "enabled": True,
                "limit": 10
            },
            "system_health": {
                "enabled": True,
                "services": ["api_gateway", "admin_service", "billing_service", "reporting_service"]
            }
        }
    }
    
    config_path = Path("data/dashboards/config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"Dashboard config created: {config_path}")


def setup_database_views():
    """Create database views for dashboard queries"""
    db = SessionLocal()
    try:
        # Create view for tenant usage summary
        db.execute("""
        CREATE OR REPLACE VIEW tenant_usage_summary AS
        SELECT 
            t.id as tenant_id,
            t.name as tenant_name,
            COUNT(DISTINCT u.id) as total_users,
            COUNT(DISTINCT f.id) as total_files,
            COUNT(DISTINCT r.id) as total_reports,
            COALESCE(SUM(ur.api_calls), 0) as total_api_calls,
            COALESCE(SUM(ur.storage_bytes), 0) as total_storage_bytes
        FROM tenants t
        LEFT JOIN users u ON t.id = u.tenant_id
        LEFT JOIN audit_files f ON t.id = f.tenant_id
        LEFT JOIN audit_reports r ON t.id = r.tenant_id
        LEFT JOIN usage_records ur ON t.id = ur.tenant_id
        GROUP BY t.id, t.name
        """)
        
        # Create view for billing overview
        db.execute("""
        CREATE OR REPLACE VIEW billing_overview AS
        SELECT 
            s.tenant_id,
            s.plan_type,
            s.monthly_price,
            s.status as subscription_status,
            bc.start_date,
            bc.end_date,
            bc.total_amount,
            bc.paid_amount,
            bc.status as billing_status,
            COALESCE(SUM(ur.api_calls), 0) as current_usage_api_calls,
            COALESCE(SUM(ur.storage_bytes), 0) as current_usage_storage
        FROM subscriptions s
        JOIN billing_cycles bc ON s.id = bc.subscription_id
        LEFT JOIN usage_records ur ON s.tenant_id = ur.tenant_id 
            AND ur.timestamp >= bc.start_date 
            AND ur.timestamp <= bc.end_date
        WHERE bc.status = 'active'
        GROUP BY s.tenant_id, s.plan_type, s.monthly_price, s.status, 
                 bc.start_date, bc.end_date, bc.total_amount, bc.paid_amount, bc.status
        """)
        
        db.commit()
        logger.info("Database views created for dashboard")
    except Exception as e:
        logger.error(f"Error creating database views: {e}")
        db.rollback()
    finally:
        db.close()


def main():
    """Main setup function"""
    logger.info("Starting dashboard setup...")
    
    try:
        setup_dashboard_directories()
        create_dashboard_config()
        setup_database_views()
        
        logger.info("Dashboard setup completed successfully!")
        
        print("\nDashboard setup complete!")
        print("Access the dashboard at: http://localhost:8001/admin/dashboard")
        print("\nAvailable endpoints:")
        print("  GET /admin/dashboard/summary - System summary")
        print("  GET /admin/dashboard/usage - Usage statistics")
        print("  GET /admin/dashboard/billing - Billing overview")
        print("  GET /admin/dashboard/health - System health")
        
    except Exception as e:
        logger.error(f"Dashboard setup failed: {e}")
        raise


if __name__ == "__main__":
    main()