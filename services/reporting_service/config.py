from typing import List
from pydantic_settings import BaseSettings


class ReportingServiceConfig(BaseSettings):
    """Reporting Service configuration."""
    
    # Service settings
    api_title: str = "Aquila Reporting Service"
    api_description: str = "Report generation for Aquila Audit platform"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8005
    debug: bool = False
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/reports"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # Storage paths
    reports_dir: str = "data/reports/tenants"
    templates_dir: str = "services/reporting_service/templates"
    assets_dir: str = "services/reporting_service/assets"
    
    # Report settings
    default_report_format: str = "pdf"  # pdf, excel, html
    include_ai_explanations: bool = True
    max_findings_per_report: int = 1000
    
    # PDF settings
    pdf_page_size: str = "A4"
    pdf_margin_top: int = 50
    pdf_margin_bottom: int = 50
    pdf_margin_left: int = 50
    pdf_margin_right: int = 50
    
    # Excel settings
    excel_max_rows_per_sheet: int = 1000000
    excel_include_charts: bool = True
    
    # Security settings
    enable_digital_signatures: bool = True
    signature_certificate_path: str = "data/certificates/signature.pem"
    signature_private_key_path: str = "data/certificates/private.key"
    
    # Watermark settings
    enable_watermark: bool = True
    watermark_text: str = "CONFIDENTIAL - AUDIT REPORT"
    
    # Retention settings
    report_retention_days: int = 365
    auto_cleanup_enabled: bool = True
    cleanup_schedule: str = "0 2 * * *"  # Daily at 2 AM
    
    # Template settings
    default_template: str = "default"
    company_name: str = "Aquila Audit"
    company_logo_path: str = "assets/logo.png"
    company_address: str = "123 Audit Street, Compliance City"
    company_website: str = "https://aquila-audit.com"
    
    class Config:
        env_file = ".env"
        env_prefix = "REPORTING_SERVICE_"


# Global config instance
config = ReportingServiceConfig()