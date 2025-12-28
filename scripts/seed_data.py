#!/usr/bin/env python3
"""
Seed initial data for development.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from uuid import UUID
import json

from shared.database.base import Base, SessionLocal
from shared.models.user_models import User, Tenant, UserRole, UserTenant
from shared.auth.password import get_password_hash
from shared.utils.logging import logger
from shared.utils.config import settings


def seed_database():
    """Seed initial database data."""
    logger.info("Seeding initial database data...")
    
    engine = create_engine(str(settings.database_url))
    Base.metadata.create_all(bind=engine)
    
    with SessionLocal() as db:
        # Create super admin user
        super_admin_email = "admin@aquila.com"
        super_admin = db.query(User).filter(User.email == super_admin_email).first()
        
        if not super_admin:
            super_admin = User(
                email=super_admin_email,
                hashed_password=get_password_hash("AdminPass123!"),
                full_name="Super Administrator",
                company="Aquila Audit",
                is_active=True,
                is_verified=True,
                is_superuser=True
            )
            db.add(super_admin)
            db.commit()
            db.refresh(super_admin)
            logger.info(f"Created super admin user: {super_admin_email}")
        
        # Create default tenant
        default_tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        
        if not default_tenant:
            default_tenant = Tenant(
                name="Default Tenant",
                slug="default",
                description="Default tenant for development",
                config={
                    "max_file_size": 100 * 1024 * 1024,  # 100MB
                    "allowed_file_types": [".csv", ".xlsx", ".xls", ".json"],
                    "auto_process": True
                },
                billing_tier="enterprise",
                is_active=True
            )
            db.add(default_tenant)
            db.commit()
            db.refresh(default_tenant)
            logger.info(f"Created default tenant: {default_tenant.name}")
        
        # Add super admin to default tenant
        user_tenant = db.query(UserTenant).filter(
            UserTenant.user_id == super_admin.id,
            UserTenant.tenant_id == default_tenant.id
        ).first()
        
        if not user_tenant:
            user_tenant = UserTenant(
                user_id=super_admin.id,
                tenant_id=default_tenant.id,
                role="admin"
            )
            db.add(user_tenant)
            db.commit()
            logger.info(f"Added super admin to default tenant")
        
        # Create admin role
        admin_role = db.query(UserRole).filter(
            UserRole.user_id == super_admin.id,
            UserRole.tenant_id == default_tenant.id,
            UserRole.role == "tenant_admin"
        ).first()
        
        if not admin_role:
            admin_role = UserRole(
                user_id=super_admin.id,
                tenant_id=default_tenant.id,
                role="tenant_admin",
                permissions=json.dumps([
                    "user:read", "user:write", "user:delete",
                    "file:upload", "file:read", "file:delete",
                    "rule:read", "rule:write", "rule:delete",
                    "report:generate", "report:read", "report:delete"
                ])
            )
            db.add(admin_role)
            db.commit()
            logger.info(f"Created admin role for super admin")
        
        # Create test user
        test_user_email = "user@example.com"
        test_user = db.query(User).filter(User.email == test_user_email).first()
        
        if not test_user:
            test_user = User(
                email=test_user_email,
                hashed_password=get_password_hash("UserPass123!"),
                full_name="Test User",
                company="Test Company",
                is_active=True,
                is_verified=True,
                is_superuser=False
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            logger.info(f"Created test user: {test_user_email}")
            
            # Add test user to default tenant
            user_tenant = UserTenant(
                user_id=test_user.id,
                tenant_id=default_tenant.id,
                role="auditor"
            )
            db.add(user_tenant)
            db.commit()
            
            # Create user role
            user_role = UserRole(
                user_id=test_user.id,
                tenant_id=default_tenant.id,
                role="auditor",
                permissions=json.dumps([
                    "file:upload", "file:read",
                    "rule:read",
                    "report:generate", "report:read"
                ])
            )
            db.add(user_role)
            db.commit()
            logger.info(f"Added test user to default tenant with auditor role")
        
        logger.info("Database seeding completed successfully!")
        
        # Print credentials for development
        print("\n" + "="*50)
        print("DEVELOPMENT CREDENTIALS")
        print("="*50)
        print(f"Super Admin:")
        print(f"  Email:    {super_admin_email}")
        print(f"  Password: AdminPass123!")
        print(f"\nTest User:")
        print(f"  Email:    {test_user_email}")
        print(f"  Password: UserPass123!")
        print(f"\nDefault Tenant ID: {default_tenant.id}")
        print("="*50 + "\n")


if __name__ == "__main__":
    try:
        seed_database()
    except Exception as e:
        logger.error(f"Failed to seed database: {str(e)}")
        sys.exit(1)