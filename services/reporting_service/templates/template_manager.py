"""
Template manager for report generation.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from shared.utils.logging import logger
from services.reporting_service.config import config


class TemplateManager:
    """Manages report templates."""
    
    def __init__(self):
        self.templates_dir = Path(config.templates_dir)
        self.ensure_default_templates()
    
    def ensure_default_templates(self):
        """Ensure all default templates exist."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure base template exists
        base_template = self.templates_dir / "base_template.html"
        if not base_template.exists():
            self._create_default_base_template()
        
        # Ensure audit report template exists
        audit_template = self.templates_dir / "audit_report.html"
        if not audit_template.exists():
            # Check if old filename exists and rename it
            old_template = self.templates_dir / "audit-report.html"
            if old_template.exists():
                old_template.rename(audit_template)
                logger.info(f"Renamed template: audit-report.html -> audit_report.html")
            else:
                self._create_default_audit_template()
        
        # Ensure CSS exists
        css_file = self.templates_dir / "style.css"
        if not css_file.exists():
            self._create_default_css()
        
        # Ensure watermark image exists
        watermark_dir = self.templates_dir / "watermarks"
        watermark_dir.mkdir(exist_ok=True)
        watermark_file = watermark_dir / "confidential.png"
        if not watermark_file.exists():
            self._create_default_watermark()
    
    def _create_default_base_template(self):
        """Create default base template."""
        # This is already in html_generator.py
        # We'll use a simplified version
        from services.reporting_service.generators.html_generator import HTMLGenerator
        html_gen = HTMLGenerator()
        # Base template is created in HTMLGenerator.__init__
    
    def _create_default_audit_template(self):
        """Create default audit template."""
        # This is already in html_generator.py
        from services.reporting_service.generators.html_generator import HTMLGenerator
        html_gen = HTMLGenerator()
        # Audit template is created in HTMLGenerator._create_default_audit_template()
    
    def _create_default_css(self):
        """Create default CSS."""
        # This is already in html_generator.py
        from services.reporting_service.generators.html_generator import HTMLGenerator
        html_gen = HTMLGenerator()
        # CSS is created in HTMLGenerator._create_default_css()
    
    def _create_default_watermark(self):
        """Create default watermark image."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            
            # Create a simple watermark image
            width, height = 400, 200
            image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)
            
            # Try to use a font
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except:
                font = ImageFont.load_default()
            
            # Draw watermark text
            text = "CONFIDENTIAL"
            text_width, text_height = draw.textsize(text, font=font)
            
            # Position text at an angle
            draw.text(
                ((width - text_width) / 2, (height - text_height) / 2),
                text,
                fill=(255, 0, 0, 128),  # Red with transparency
                font=font
            )
            
            # Save the image
            watermark_path = self.templates_dir / "watermarks" / "confidential.png"
            image.save(str(watermark_path), 'PNG')
            
            logger.info(f"Created default watermark: {watermark_path}")
        
        except ImportError:
            logger.warning("PIL not installed, skipping watermark image creation")
        except Exception as e:
            logger.error(f"Failed to create watermark image: {str(e)}")
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """List all available templates."""
        templates = []
        
        for template_file in self.templates_dir.glob("*.html"):
            template_info = {
                'name': template_file.stem,
                'filename': template_file.name,
                'path': str(template_file),
                'size': template_file.stat().st_size,
                'modified': template_file.stat().st_mtime
            }
            templates.append(template_info)
        
        return templates
    
    def get_template(self, template_name: str) -> Optional[str]:
        """Get template content."""
        template_path = self.templates_dir / f"{template_name}.html"
        
        if template_path.exists():
            return template_path.read_text(encoding='utf-8')
        
        return None
    
    def create_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new template.
        
        Args:
            template_data: Template data with 'name' and 'content'
        
        Returns:
            Creation result
        """
        try:
            template_name = template_data.get('name')
            template_content = template_data.get('content')
            
            if not template_name or not template_content:
                raise ValueError("Template name and content are required")
            
            # Validate template name
            if not template_name.replace('_', '').isalnum():
                raise ValueError("Template name can only contain letters, numbers, and underscores")
            
            template_path = self.templates_dir / f"{template_name}.html"
            
            if template_path.exists():
                raise ValueError(f"Template '{template_name}' already exists")
            
            # Save template
            template_path.write_text(template_content, encoding='utf-8')
            
            logger.info(f"Created new template: {template_name}")
            
            return {
                'success': True,
                'template_name': template_name,
                'path': str(template_path),
                'size': len(template_content)
            }
        
        except Exception as e:
            logger.error(f"Failed to create template: {str(e)}")
            raise
    
    def update_template(self, template_name: str, template_content: str) -> Dict[str, Any]:
        """Update an existing template."""
        try:
            template_path = self.templates_dir / f"{template_name}.html"
            
            if not template_path.exists():
                raise ValueError(f"Template '{template_name}' does not exist")
            
            # Backup old template
            backup_path = template_path.with_suffix('.html.bak')
            if template_path.exists():
                template_path.rename(backup_path)
            
            # Save new template
            template_path.write_text(template_content, encoding='utf-8')
            
            logger.info(f"Updated template: {template_name}")
            
            return {
                'success': True,
                'template_name': template_name,
                'backup_created': backup_path.exists()
            }
        
        except Exception as e:
            logger.error(f"Failed to update template: {str(e)}")
            raise
    
    def delete_template(self, template_name: str) -> Dict[str, Any]:
        """Delete a template."""
        try:
            template_path = self.templates_dir / f"{template_name}.html"
            
            if not template_path.exists():
                raise ValueError(f"Template '{template_name}' does not exist")
            
            # Backup before deletion
            backup_path = template_path.with_suffix('.html.bak')
            if template_path.exists():
                template_path.rename(backup_path)
            
            logger.info(f"Deleted template: {template_name}")
            
            return {
                'success': True,
                'template_name': template_name,
                'backup_path': str(backup_path)
            }
        
        except Exception as e:
            logger.error(f"Failed to delete template: {str(e)}")
            raise


# Global template manager instance
template_manager = TemplateManager()