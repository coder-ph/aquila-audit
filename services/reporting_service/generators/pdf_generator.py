"""
PDF report generator using ReportLab.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, Flowable, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from typing import Dict, List, Any, Optional, Tuple
import os
from datetime import datetime
from pathlib import Path
import tempfile
import json

from shared.utils.logging import logger
from services.reporting_service.config import config


class PDFGenerator:
    """Generates PDF audit reports."""
    
    def __init__(self):

        # Colors
        self.colors = {
            'primary': colors.HexColor('#2C3E50'),
            'secondary': colors.HexColor('#3498DB'),
            'accent': colors.HexColor('#E74C3C'),
            'success': colors.HexColor('#27AE60'),
            'warning': colors.HexColor('#F39C12'),
            'light_gray': colors.HexColor('#ECF0F1'),
            'dark_gray': colors.HexColor('#7F8C8D')
        }
        self.page_size = getattr(config, 'pdf_page_size', 'A4').upper()
        self.page_sizes = {
            'A4': A4,
            'LETTER': letter
        }
        self.page_size_obj = self.page_sizes.get(self.page_size, A4)
        
        # Register fonts
        self._register_fonts()
        
        # Create styles
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        
        
    
    def _register_fonts(self):
        """Register custom fonts."""
        try:
            # Register default fonts
            pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica'))
            pdfmetrics.registerFont(TTFont('Helvetica-Bold', 'Helvetica-Bold'))
            pdfmetrics.registerFontFamily(
                'Helvetica',
                normal='Helvetica',
                bold='Helvetica-Bold'
            )
        except:
            # Use default fonts if custom fonts not available
            pass
    
    def _create_custom_styles(self):
        """Create custom paragraph styles."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=self.colors['primary'],
            spaceAfter=30,
            alignment=1  # Center
        ))
        
        # Heading 1
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=self.colors['primary'],
            spaceBefore=20,
            spaceAfter=10
        ))
        
        # Heading 2
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=self.colors['secondary'],
            spaceBefore=15,
            spaceAfter=8
        ))
        
        # Normal text
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6
        ))
        
        # Small text
        self.styles.add(ParagraphStyle(
            name='CustomSmall',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.colors['dark_gray']
        ))
        
        # Code/inline text
        self.styles.add(ParagraphStyle(
            name='CustomCode',
            parent=self.styles['Code'],
            fontSize=9,
            fontName='Courier',
            textColor=colors.darkblue,
            backColor=self.colors['light_gray'],
            borderPadding=3
        ))
    
    def generate_report(
        self,
        report_data: Dict[str, Any],
        output_path: str,
        include_watermark: bool = True,
        include_signature: bool = True
    ) -> Dict[str, Any]:
        """
        Generate PDF report.
        
        Args:
            report_data: Report data
            output_path: Output file path
            include_watermark: Whether to include watermark
            include_signature: Whether to include digital signature
        
        Returns:
            Generation metadata
        """
        start_time = datetime.now()
        
        try:
            # Create document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=self.page_size_obj,
                rightMargin=config.pdf_margin_right,
                leftMargin=config.pdf_margin_left,
                topMargin=config.pdf_margin_top,
                bottomMargin=config.pdf_margin_bottom
            )
            
            # Build story (content)
            story = []
            
            # Add cover page
            story.extend(self._create_cover_page(report_data))
            story.append(PageBreak())
            
            # Add table of contents
            story.extend(self._create_table_of_contents(report_data))
            story.append(PageBreak())
            
            # Add executive summary
            story.extend(self._create_executive_summary(report_data))
            story.append(PageBreak())
            
            # Add findings
            story.extend(self._create_findings_section(report_data))
            
            # Add recommendations
            if 'recommendations' in report_data:
                story.append(PageBreak())
                story.extend(self._create_recommendations_section(report_data))
            
            # Add appendix
            if 'appendix' in report_data:
                story.append(PageBreak())
                story.extend(self._create_appendix_section(report_data))
            
            # Build document
            doc.build(
                story,
                onFirstPage=self._add_header_footer,
                onLaterPages=self._add_header_footer
            )
            
            # Add watermark if requested
            if include_watermark and config.enable_watermark:
                self._add_watermark(output_path)
            
            # Add digital signature if requested
            if include_signature and config.enable_digital_signatures:
                self._add_digital_signature(output_path, report_data)
            
            # Calculate metadata
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            metadata = {
                'success': True,
                'output_path': output_path,
                'file_size': file_size,
                'generation_time': duration,
                'page_count': self._count_pages(output_path),
                'format': 'pdf',
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"PDF report generated: {output_path} ({file_size} bytes)")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            raise
    
    def _create_cover_page(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create cover page."""
        elements = []
        
        # Title
        title = report_data.get('title', 'Audit Report')
        elements.append(Paragraph(title, self.styles['CustomTitle']))
        elements.append(Spacer(1, 40))
        
        # Subtitle
        subtitle = report_data.get('subtitle', 'Compliance and Anomaly Analysis')
        elements.append(Paragraph(subtitle, self.styles['CustomHeading2']))
        elements.append(Spacer(1, 60))
        
        # Report metadata table
        metadata = [
            ['Report ID:', report_data.get('report_id', 'N/A')],
            ['Generated:', report_data.get('generated_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))],
            ['Period:', report_data.get('period', 'N/A')],
            ['Scope:', report_data.get('scope', 'N/A')],
            ['Generated By:', report_data.get('generated_by', 'Aquila Audit System')],
        ]
        
        # Add tenant info if available
        if 'tenant' in report_data:
            metadata.append(['Tenant:', report_data['tenant'].get('name', 'N/A')])
        
        metadata_table = Table(metadata, colWidths=[100, 300])
        metadata_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), self.colors['primary']),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        elements.append(metadata_table)
        elements.append(Spacer(1, 40))
        
        # Confidential notice
        if report_data.get('confidential', True):
            notice = Paragraph(
                '<b>CONFIDENTIAL</b><br/>'
                'This report contains sensitive information. '
                'Distribution is restricted to authorized personnel only.',
                self.styles['CustomNormal']
            )
            elements.append(notice)
        
        # Company info
        company_info = f"""
        <br/><br/>
        <b>{config.company_name}</b><br/>
        {config.company_address}<br/>
        {config.company_website}
        """
        elements.append(Paragraph(company_info, self.styles['CustomSmall']))
        
        return elements
    
    def _create_table_of_contents(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create table of contents."""
        elements = []
        
        elements.append(Paragraph('Table of Contents', self.styles['CustomHeading1']))
        elements.append(Spacer(1, 20))
        
        # Define TOC entries
        toc_entries = [
            ('Executive Summary', 1),
            ('Findings Summary', 2),
            ('Detailed Findings', 3),
        ]
        
        if 'recommendations' in report_data:
            toc_entries.append(('Recommendations', 4))
        
        if 'appendix' in report_data:
            toc_entries.append(('Appendix', 5))
        
        # Create TOC table
        toc_data = []
        for title, page in toc_entries:
            toc_data.append([title, f'...... {page}'])
        
        toc_table = Table(toc_data, colWidths=[400, 50])
        toc_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        elements.append(toc_table)
        
        return elements
    
    def _create_executive_summary(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create executive summary section."""
        elements = []
        
        elements.append(Paragraph('Executive Summary', self.styles['CustomHeading1']))
        elements.append(Spacer(1, 15))
        
        # Summary text
        if 'executive_summary' in report_data:
            summary = report_data['executive_summary']
            elements.append(Paragraph(summary, self.styles['CustomNormal']))
            elements.append(Spacer(1, 20))
        
        # Key metrics
        metrics = report_data.get('metrics', {})
        if metrics:
            elements.append(Paragraph('Key Metrics', self.styles['CustomHeading2']))
            elements.append(Spacer(1, 10))
            
            metrics_data = [
                ['Total Findings:', str(metrics.get('total_findings', 0))],
                ['Critical Findings:', str(metrics.get('critical', 0))],
                ['High Findings:', str(metrics.get('high', 0))],
                ['Medium Findings:', str(metrics.get('medium', 0))],
                ['Low Findings:', str(metrics.get('low', 0))],
            ]
            
            # Add risk score if available
            if 'risk_score' in metrics:
                metrics_data.append(['Overall Risk Score:', f"{metrics['risk_score']}/10"])
            
            metrics_table = Table(metrics_data, colWidths=[150, 100])
            metrics_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, -1), self.colors['light_gray']),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('PADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(metrics_table)
            elements.append(Spacer(1, 20))
        
        # Top findings
        top_findings = report_data.get('top_findings', [])[:5]
        if top_findings:
            elements.append(Paragraph('Top Findings', self.styles['CustomHeading2']))
            elements.append(Spacer(1, 10))
            
            for i, finding in enumerate(top_findings, 1):
                severity = finding.get('severity', 'Medium').upper()
                severity_color = self._get_severity_color(severity)
                
                finding_text = f"""
                <b>{i}. {finding.get('title', 'Finding')}</b><br/>
                <font color="{severity_color}">Severity: {severity}</font><br/>
                {finding.get('description', '')}
                """
                
                elements.append(Paragraph(finding_text, self.styles['CustomNormal']))
                elements.append(Spacer(1, 8))
        
        return elements
    
    def _create_findings_section(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create findings section."""
        elements = []
        
        elements.append(Paragraph('Detailed Findings', self.styles['CustomHeading1']))
        elements.append(Spacer(1, 15))
        
        findings = report_data.get('findings', [])
        
        if not findings:
            elements.append(Paragraph('No findings to report.', self.styles['CustomNormal']))
            return elements
        
        # Group findings by severity
        severity_groups = {'CRITICAL': [], 'HIGH': [], 'MEDIUM': [], 'LOW': []}
        
        for finding in findings:
            severity = finding.get('severity', 'MEDIUM').upper()
            if severity in severity_groups:
                severity_groups[severity].append(finding)
        
        # Process by severity order
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            group_findings = severity_groups[severity]
            
            if not group_findings:
                continue
            
            elements.append(Paragraph(
                f'{severITY.title()} Findings ({len(group_findings)})',
                self.styles['CustomHeading2']
            ))
            elements.append(Spacer(1, 10))
            
            for i, finding in enumerate(group_findings, 1):
                elements.extend(self._create_finding_detail(finding, i))
                elements.append(Spacer(1, 15))
        
        return elements
    
    def _create_finding_detail(self, finding: Dict[str, Any], index: int) -> List[Flowable]:
        """Create detailed finding entry."""
        elements = []
        
        severity = finding.get('severity', 'MEDIUM').upper()
        severity_color = self._get_severity_color(severity)
        
        # Finding header
        header_text = f"""
        <b>{index}. {finding.get('title', 'Finding')}</b><br/>
        <font color="{severity_color}">Severity: {severity}</font> | 
        Rule: {finding.get('rule_name', 'N/A')} |
        ID: {finding.get('id', 'N/A')}
        """
        elements.append(Paragraph(header_text, self.styles['CustomNormal']))
        elements.append(Spacer(1, 5))
        
        # Description
        if 'description' in finding:
            elements.append(Paragraph(finding['description'], self.styles['CustomNormal']))
            elements.append(Spacer(1, 8))
        
        # Context data
        if 'context' in finding:
            elements.append(Paragraph('<b>Context:</b>', self.styles['CustomNormal']))
            context_text = json.dumps(finding['context'], indent=2, default=str)
            elements.append(Paragraph(f'<code>{context_text}</code>', self.styles['CustomCode']))
            elements.append(Spacer(1, 8))
        
        # AI Explanation
        if 'ai_explanation' in finding and config.include_ai_explanations:
            elements.append(Paragraph('<b>AI Explanation:</b>', self.styles['CustomNormal']))
            elements.append(Paragraph(finding['ai_explanation'], self.styles['CustomNormal']))
            elements.append(Spacer(1, 8))
        
        # Recommendations
        if 'recommendations' in finding:
            elements.append(Paragraph('<b>Recommendations:</b>', self.styles['CustomNormal']))
            for rec in finding['recommendations']:
                elements.append(Paragraph(f'• {rec}', self.styles['CustomNormal']))
        
        return elements
    
    def _create_recommendations_section(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create recommendations section."""
        elements = []
        
        elements.append(Paragraph('Recommendations', self.styles['CustomHeading1']))
        elements.append(Spacer(1, 15))
        
        recommendations = report_data.get('recommendations', [])
        
        for i, rec in enumerate(recommendations, 1):
            rec_title = rec.get('title', f'Recommendation {i}')
            rec_priority = rec.get('priority', 'Medium').upper()
            priority_color = self._get_priority_color(rec_priority)
            
            header_text = f"""
            <b>{i}. {rec_title}</b><br/>
            <font color="{priority_color}">Priority: {rec_priority}</font> | 
            Timeline: {rec.get('timeline', '30 days')}
            """
            elements.append(Paragraph(header_text, self.styles['CustomNormal']))
            elements.append(Spacer(1, 5))
            
            if 'description' in rec:
                elements.append(Paragraph(rec['description'], self.styles['CustomNormal']))
                elements.append(Spacer(1, 5))
            
            if 'actions' in rec:
                elements.append(Paragraph('<b>Actions:</b>', self.styles['CustomNormal']))
                for action in rec['actions']:
                    elements.append(Paragraph(f'• {action}', self.styles['CustomNormal']))
            
            elements.append(Spacer(1, 15))
        
        return elements
    
    def _create_appendix_section(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create appendix section."""
        elements = []
        
        elements.append(Paragraph('Appendix', self.styles['CustomHeading1']))
        elements.append(Spacer(1, 15))
        
        appendix = report_data.get('appendix', {})
        
        for section_title, section_content in appendix.items():
            elements.append(Paragraph(section_title, self.styles['CustomHeading2']))
            elements.append(Spacer(1, 10))
            
            if isinstance(section_content, str):
                elements.append(Paragraph(section_content, self.styles['CustomNormal']))
            elif isinstance(section_content, list):
                for item in section_content:
                    elements.append(Paragraph(f'• {item}', self.styles['CustomNormal']))
            elif isinstance(section_content, dict):
                content_text = json.dumps(section_content, indent=2, default=str)
                elements.append(Paragraph(f'<code>{content_text}</code>', self.styles['CustomCode']))
            
            elements.append(Spacer(1, 15))
        
        return elements
    
    def _add_header_footer(self, canvas_obj, doc):
        """Add header and footer to each page."""
        # Save the current state
        canvas_obj.saveState()
        
        # Header
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.setFillColor(self.colors['dark_gray'])
        
        # Left header: Report title
        canvas_obj.drawString(
            doc.leftMargin,
            doc.height + doc.topMargin - 15,
            doc.title if hasattr(doc, 'title') else 'Audit Report'
        )
        
        # Right header: Page number
        page_num = canvas_obj.getPageNumber()
        canvas_obj.drawRightString(
            doc.width + doc.leftMargin,
            doc.height + doc.topMargin - 15,
            f'Page {page_num}'
        )
        
        # Footer
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.setFillColor(self.colors['dark_gray'])
        
        # Left footer: Company name
        canvas_obj.drawString(
            doc.leftMargin,
            15,
            config.company_name
        )
        
        # Center footer: Confidential notice
        if hasattr(doc, 'confidential') and doc.confidential:
            canvas_obj.drawCentredString(
                doc.width / 2 + doc.leftMargin,
                15,
                'CONFIDENTIAL'
            )
        
        # Right footer: Generation date
        gen_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        canvas_obj.drawRightString(
            doc.width + doc.leftMargin,
            15,
            f'Generated: {gen_date}'
        )
        
        # Restore state
        canvas_obj.restoreState()
    
    def _add_watermark(self, pdf_path: str):
        """Add watermark to PDF."""
        try:
            from PyPDF2 import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            import io
            
            # Create watermark PDF
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=self.page_size_obj)
            
            # Set transparency
            can.setFillAlpha(0.1)
            can.setFont('Helvetica-Bold', 60)
            can.setFillColor(colors.grey)
            
            # Rotate and position watermark
            can.saveState()
            can.translate(self.page_size_obj[0] / 2, self.page_size_obj[1] / 2)
            can.rotate(45)
            
            # Draw watermark text
            watermark_text = config.watermark_text
            can.drawCentredString(0, 0, watermark_text)
            can.restoreState()
            
            can.save()
            
            # Move to beginning
            packet.seek(0)
            
            # Read existing PDF
            existing_pdf = PdfReader(open(pdf_path, "rb"))
            watermark_pdf = PdfReader(packet)
            
            # Create output PDF
            output = PdfWriter()
            
            # Add watermark to each page
            for i in range(len(existing_pdf.pages)):
                page = existing_pdf.pages[i]
                watermark_page = watermark_pdf.pages[0]
                
                # Merge watermark with page
                page.merge_page(watermark_page)
                output.add_page(page)
            
            # Write output
            with open(pdf_path, "wb") as output_stream:
                output.write(output_stream)
                
            logger.debug(f"Watermark added to: {pdf_path}")
            
        except ImportError:
            logger.warning("PyPDF2 not installed, skipping watermark")
        except Exception as e:
            logger.error(f"Error adding watermark: {str(e)}")
    
    def _add_digital_signature(self, pdf_path: str, report_data: Dict[str, Any]):
        """Add digital signature to PDF."""
        try:
            from services.reporting_service.security.signature import DigitalSigner
            
            signer = DigitalSigner()
            if signer.can_sign():
                signature_data = {
                    'report_id': report_data.get('report_id', ''),
                    'generated_by': report_data.get('generated_by', 'Aquila Audit'),
                    'generated_at': report_data.get('generated_date', datetime.now().isoformat()),
                    'tenant_id': report_data.get('tenant', {}).get('id', ''),
                    'hash': '...'  # Will be calculated by signer
                }
                
                signed_pdf = signer.sign_pdf(pdf_path, signature_data)
                if signed_pdf:
                    # Replace original with signed version
                    with open(pdf_path, 'wb') as f:
                        f.write(signed_pdf)
                    
                    logger.info(f"Digital signature added to: {pdf_path}")
            
        except Exception as e:
            logger.error(f"Error adding digital signature: {str(e)}")
    
    def _get_severity_color(self, severity: str) -> str:
        """Get color for severity level."""
        severity_colors = {
            'CRITICAL': '#E74C3C',  # Red
            'HIGH': '#E67E22',      # Orange
            'MEDIUM': '#F1C40F',    # Yellow
            'LOW': '#2ECC71'        # Green
        }
        return severity_colors.get(severity.upper(), '#7F8C8D')  # Default gray
    
    def _get_priority_color(self, priority: str) -> str:
        """Get color for priority level."""
        priority_colors = {
            'HIGH': '#E74C3C',      # Red
            'MEDIUM': '#F1C40F',    # Yellow
            'LOW': '#2ECC71'        # Green
        }
        return priority_colors.get(priority.upper(), '#7F8C8D')  # Default gray
    
    def _count_pages(self, pdf_path: str) -> int:
        """Count pages in PDF."""
        try:
            from PyPDF2 import PdfReader
            with open(pdf_path, 'rb') as f:
                pdf = PdfReader(f)
                return len(pdf.pages)
        except:
            return 0


# Global PDF generator instance
pdf_generator = PDFGenerator()