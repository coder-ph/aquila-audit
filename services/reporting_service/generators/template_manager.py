"""
Template manager for report generation.
"""
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from shared.utils.logging import logger
from services.reporting_service.config import config


class TemplateManager:
    """Manages report templates and styling."""
    
    def __init__(self):
        self.templates_dir = Path(config.templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Load template configurations
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Any]:
        """Load available templates."""
        templates = {}
        
        # Check for template definitions
        templates_file = self.templates_dir / "templates.json"
        if templates_file.exists():
            try:
                with open(templates_file, 'r') as f:
                    templates = json.load(f)
            except Exception as e:
                logger.error(f"Error loading templates: {str(e)}")
        
        # Ensure default template exists
        if 'default' not in templates:
            templates['default'] = {
                'name': 'Default Template',
                'description': 'Standard audit report template',
                'styles': {
                    'primary_color': '#2C3E50',
                    'secondary_color': '#3498DB',
                    'accent_color': '#E74C3C',
                    'font_family': 'Inter, sans-serif',
                    'header_background': 'linear-gradient(135deg, #2C3E50, #3498DB)'
                },
                'sections': [
                    'cover',
                    'toc',
                    'executive_summary',
                    'findings',
                    'recommendations',
                    'appendix'
                ]
            }
        
        return templates
    
    def ensure_default_templates(self):
        """Ensure all default templates and assets exist."""
        # Create templates directory if it doesn't exist
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Create assets directory
        assets_dir = Path(config.assets_dir)
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        # Save template definitions
        templates_file = self.templates_dir / "templates.json"
        with open(templates_file, 'w') as f:
            json.dump(self.templates, f, indent=2)
        
        # Create sample logo if it doesn't exist
        logo_path = Path(config.company_logo_path)
        if not logo_path.exists():
            self._create_sample_logo(logo_path)
        
        logger.info("Default templates ensured")
    
    def _create_sample_logo(self, logo_path: Path):
        """Create a sample logo for testing."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import tempfile
            
            # Create a simple PDF logo
            c = canvas.Canvas(str(logo_path), pagesize=(2*inch, 1*inch))
            
            # Draw logo background
            c.setFillColor(colors.HexColor('#2C3E50'))
            c.rect(0.1*inch, 0.1*inch, 1.8*inch, 0.8*inch, fill=1, stroke=0)
            
            # Draw logo text
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(0.3*inch, 0.4*inch, "AQUILA")
            c.setFont("Helvetica", 10)
            c.drawString(0.3*inch, 0.2*inch, "AUDIT")
            
            c.save()
            
        except Exception as e:
            logger.error(f"Error creating sample logo: {str(e)}")
    
    def get_template(self, template_name: str = 'default') -> Optional[Dict[str, Any]]:
        """Get a specific template configuration."""
        return self.templates.get(template_name)
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """List all available templates."""
        return [
            {
                'name': name,
                'display_name': template.get('name', name),
                'description': template.get('description', ''),
                'sections': template.get('sections', [])
            }
            for name, template in self.templates.items()
        ]
    
    def create_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new template."""
        template_name = template_data.get('name')
        if not template_name:
            raise ValueError("Template name is required")
        
        # Ensure template name is valid
        template_name = template_name.lower().replace(' ', '_')
        
        if template_name in self.templates:
            raise ValueError(f"Template '{template_name}' already exists")
        
        # Add template
        self.templates[template_name] = template_data
        
        # Save templates
        templates_file = self.templates_dir / "templates.json"
        with open(templates_file, 'w') as f:
            json.dump(self.templates, f, indent=2)
        
        logger.info(f"Template created: {template_name}")
        
        return {
            'success': True,
            'template_name': template_name,
            'message': f"Template '{template_name}' created successfully"
        }
    
    def update_template(self, template_name: str, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing template."""
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Update template
        self.templates[template_name].update(template_data)
        
        # Save templates
        templates_file = self.templates_dir / "templates.json"
        with open(templates_file, 'w') as f:
            json.dump(self.templates, f, indent=2)
        
        logger.info(f"Template updated: {template_name}")
        
        return {
            'success': True,
            'template_name': template_name,
            'message': f"Template '{template_name}' updated successfully"
        }
    
    def delete_template(self, template_name: str) -> Dict[str, Any]:
        """Delete a template."""
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Don't allow deletion of default template
        if template_name == 'default':
            raise ValueError("Cannot delete default template")
        
        # Remove template
        del self.templates[template_name]
        
        # Save templates
        templates_file = self.templates_dir / "templates.json"
        with open(templates_file, 'w') as f:
            json.dump(self.templates, f, indent=2)
        
        logger.info(f"Template deleted: {template_name}")
        
        return {
            'success': True,
            'template_name': template_name,
            'message': f"Template '{template_name}' deleted successfully"
        }


# Global template manager instance
template_manager = TemplateManager()