from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Text, Boolean, ForeignKey, Enum as SQLEnum, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import json

from shared.models.base import TenantBaseModel
from shared.models.schemas import RuleType, FindingSeverity


class Rule(TenantBaseModel):
    """Rule model for audit rules."""
    
    __tablename__ = "rules"
    
    # Rule information
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(
        SQLEnum(RuleType),
        default=RuleType.VALIDATION,
        nullable=False
    )
    
    # Rule configuration
    rule_expression = Column(Text, nullable=False)  # JSONata expression
    rule_config = Column(JSONB, nullable=True)  # Additional configuration
    
    # Severity and status
    severity = Column(
        SQLEnum(FindingSeverity),
        default=FindingSeverity.MEDIUM,
        nullable=False
    )
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Categories and tags
    category = Column(String(100), nullable=True)
    tags = Column(JSONB, nullable=True)  # Array of tags as JSON
    
    # Creator information
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="rules")
    findings = relationship("Finding", back_populates="rule")
    rule_sets = relationship("RuleSet", secondary="ruleset_rules", back_populates="rules")
    
    # Indexes
    __table_args__ = (
        Index('ix_rules_is_active', 'is_active'),
        Index('ix_rules_rule_type', 'rule_type'),
        Index('ix_rules_severity', 'severity'),
        Index('ix_rules_category', 'category'),
    )
    
    def __repr__(self):
        return f"<Rule {self.name} ({self.rule_type})>"
    
    @property
    def tag_list(self) -> list:
        """Get tags as list."""
        if self.tags:
            if isinstance(self.tags, list):
                return self.tags
            try:
                return json.loads(self.tags)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def evaluate(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Evaluate rule against data.
        
        Args:
            data: Data to evaluate
        
        Returns:
            Tuple of (is_violation, error_message)
        """
        # This is a placeholder - actual evaluation will be in rule_engine
        # For now, return a simple evaluation
        try:
            # Simple pattern matching for demonstration
            if "error" in str(data).lower():
                return True, "Found 'error' in data"
            return False, None
        except Exception as e:
            return False, f"Evaluation error: {str(e)}"


class RuleSet(TenantBaseModel):
    """Collection of rules."""
    
    __tablename__ = "rule_sets"
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Configuration
    config = Column(JSONB, nullable=True)
    
    # Relationships
    rules = relationship("Rule", secondary="ruleset_rules", back_populates="rule_sets")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    def __repr__(self):
        return f"<RuleSet {self.name}>"


class RuleSetRule(TenantBaseModel):
    """RuleSet-Rule association model."""
    
    __tablename__ = "ruleset_rules"
    
    rule_set_id = Column(UUID(as_uuid=True), ForeignKey("rule_sets.id"), primary_key=True)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id"), primary_key=True)
    
    # Order in rule set
    rule_order = Column(Integer, default=0, nullable=False)
    
    # Relationships
    rule_set = relationship("RuleSet", backref="rule_associations")
    rule = relationship("Rule", backref="ruleset_associations")


class RuleTemplate(TenantBaseModel):
    """Template for creating rules."""
    
    __tablename__ = "rule_templates"
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(SQLEnum(RuleType), nullable=False)
    
    # Template configuration
    template_expression = Column(Text, nullable=False)
    parameters = Column(JSONB, nullable=True)  # Template parameters
    example_data = Column(JSONB, nullable=True)  # Example data for testing
    
    # Categories
    category = Column(String(100), nullable=True)
    tags = Column(JSONB, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<RuleTemplate {self.name}>"