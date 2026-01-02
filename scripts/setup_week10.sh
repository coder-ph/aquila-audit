#!/bin/bash

# Setup script for Week 10: Enhanced Report Generation and Storage

echo "Setting up Week 10: Enhanced Report Generation and Storage..."

# Create required directories
echo "Creating required directories..."
mkdir -p services/reporting_service/storage
mkdir -p services/reporting_service/templates/watermarks
mkdir -p data/reports/exports

# Fix template file names
echo "Fixing template file names..."
if [ -f "services/reporting_service/templates/audit-report.html" ]; then
    mv "services/reporting_service/templates/audit-report.html" "services/reporting_service/templates/audit_report.html"
    echo "Renamed audit-report.html to audit_report.html"
fi

# Install Week 10 dependencies
echo "Installing Week 10 dependencies..."
pip install -r requirements-week10.txt

# Run database migrations for new tables
echo "Running database migrations..."
alembic revision --autogenerate -m "Add report metadata tables"
alembic upgrade head

# Create test watermarks
echo "Creating watermark assets..."
python -c "
from PIL import Image, ImageDraw, ImageFont
import os

# Create confidential watermark
watermark_dir = 'services/reporting_service/templates/watermarks'
os.makedirs(watermark_dir, exist_ok=True)

# Create a simple watermark
img = Image.new('RGBA', (400, 200), (255, 255, 255, 0))
draw = ImageDraw.Draw(img)

# Try to use a font
try:
    font = ImageFont.truetype('arial.ttf', 24)
except:
    font = ImageFont.load_default()

# Draw text
text = 'CONFIDENTIAL'
draw.text((100, 80), text, fill=(255, 0, 0, 128), font=font)

# Save
img.save(f'{watermark_dir}/confidential.png')
print(f'Created watermark: {watermark_dir}/confidential.png')

# Create draft watermark
img = Image.new('RGBA', (400, 200), (255, 255, 255, 0))
draw = ImageDraw.Draw(img)
text = 'DRAFT'
draw.text((150, 80), text, fill=(255, 165, 0, 128), font=font)
img.save(f'{watermark_dir}/draft.png')
print(f'Created watermark: {watermark_dir}/draft.png')
"

# Create test reports for demonstration
echo "Creating test reports..."
python -c "
import uuid
from datetime import datetime
from pathlib import Path
from services.reporting_service.generators.report_generator import report_generator

# Create test report data
test_data = {
    'report_id': str(uuid.uuid4()),
    'title': 'Week 10 Test Report',
    'subtitle': 'Enhanced Storage and Compression Features',
    'generated_by': 'System Administrator',
    'generated_date': datetime.now().isoformat(),
    'period': 'Q4 2024',
    'scope': 'Full System Audit',
    'confidential': True,
    'metrics': {
        'total_findings': 25,
        'critical': 3,
        'high': 7,
        'medium': 10,
        'low': 5,
        'risk_score': 7.5
    },
    'findings': [
        {
            'id': 'F-001',
            'title': 'Test Finding 1',
            'description': 'This is a test finding for Week 10 features.',
            'severity': 'high',
            'category': 'security',
            'rule_name': 'Test Rule 1',
            'recommendations': ['Implement fix', 'Review configuration']
        },
        {
            'id': 'F-002',
            'title': 'Test Finding 2',
            'description': 'Another test finding.',
            'severity': 'medium',
            'category': 'compliance',
            'rule_name': 'Test Rule 2'
        }
    ],
    'executive_summary': 'This is a test report demonstrating Week 10 features including enhanced storage, compression, and digital signatures.',
    'top_findings': [
        {
            'id': 'F-001',
            'title': 'Test Finding 1',
            'description': 'High severity finding',
            'severity': 'high',
            'rule_name': 'Test Rule 1'
        }
    ]
}

# Generate test reports in all formats
print('Generating test reports...')
tenant_id = 'test-tenant-week10'
test_dir = Path('data/reports') / 'tenants' / tenant_id
test_dir.mkdir(parents=True, exist_ok=True)

formats = ['pdf', 'excel', 'html']
for fmt in formats:
    try:
        result = report_generator.generate_report(
            report_data=test_data,
            output_format=fmt,
            tenant_id=tenant_id,
            track_metadata=True
        )
        print(f'✓ {fmt.upper()} report generated: {result[\"filename\"]}')
    except Exception as e:
        print(f'✗ Failed to generate {fmt} report: {str(e)}')
"

# Test compression features
echo "Testing compression features..."
python -c "
from services.reporting_service.security.signature.digital_signer import digital_signer
from pathlib import Path

# Find a test PDF to compress
test_pdf = list(Path('data/reports/tenants/test-tenant-week10').glob('*.pdf'))
if test_pdf:
    pdf_path = str(test_pdf[0])
    print(f'Testing compression on: {pdf_path}')
    
    # Compress
    compress_result = digital_signer.compress_report(pdf_path, compression_level=6)
    if compress_result['compressed']:
        print(f'✓ Compression successful: {compress_result[\"compression_ratio\"]} saved')
        
        # Decompress
        decompress_result = digital_signer.decompress_report(compress_result['compressed_path'])
        if decompress_result['decompressed']:
            print(f'✓ Decompression successful')
    else:
        print(f'✗ Compression failed: {compress_result.get(\"error\", \"Unknown error\")}')
else:
    print('No test PDF found for compression test')
"

# Create startup script for Week 10 services
echo "Creating startup script..."
cat > scripts/start_week10.sh << 'EOF'
#!/bin/bash

echo "Starting Week 10 Reporting Services..."

# Start the reporting service with enhanced features
echo "Starting Reporting Service..."
cd services/reporting_service
python main.py &

# Start a background task for report compression
echo "Starting background compression monitor..."
python -c "
import time
from datetime import datetime
from services.reporting_service.storage.bulk_operations import bulk_report_operations
import uuid

print('Background compression monitor started')
while True:
    try:
        # Check every hour for reports to compress
        time.sleep(3600)
        
        # Get storage analysis for all tenants
        # In production, this would iterate through actual tenants
        print(f'[{datetime.now()}] Checking for compression opportunities...')
        
        # Example: Check test tenant
        test_tenant = uuid.UUID('11111111-1111-1111-1111-111111111111')
        analysis = bulk_report_operations.get_storage_analysis(test_tenant)
        
        if 'recommendations' in analysis:
            for rec in analysis['recommendations']:
                if rec['type'] == 'compression':
                    print(f'  Found compression opportunity: {rec[\"message\"]}')
        
    except Exception as e:
        print(f'Error in compression monitor: {str(e)}')
" &

echo "Week 10 services started!"
echo ""
echo "Available features:"
echo "1. Enhanced PDF/Excel/HTML report generation"
echo "2. Digital signatures and verification"
echo "3. Report compression and decompression"
echo "4. Bulk report operations"
echo "5. Storage analysis and recommendations"
echo "6. Database metadata tracking"
EOF

chmod +x scripts/start_week10.sh

echo "Week 10 setup completed!"
echo ""
echo "To start Week 10 features:"
echo "  ./scripts/start_week10.sh"
echo ""
echo "New API endpoints available:"
echo "  GET    /api/v1/reports/storage/usage        - Storage usage statistics"
echo "  GET    /api/v1/reports/storage/analysis     - Storage analysis"
echo "  POST   /api/v1/reports/storage/export       - Export multiple reports"
echo "  DELETE /api/v1/reports/storage/bulk-delete  - Delete multiple reports"
echo "  POST   /api/v1/reports/storage/compress     - Compress reports"
echo "  POST   /api/v1/reports/storage/sign/{id}    - Digitally sign report"
echo "  GET    /api/v1/reports/storage/verify/{id}  - Verify digital signature"