"""
Prompt templates for AI explanations.
"""
from typing import Dict, List, Any, Optional
import json
from datetime import datetime
from string import Template

from shared.utils.logging import logger


class ExplanationPrompts:
    """Prompt templates for generating AI explanations."""
    
    def __init__(self):
        self.templates = {
            "explain_anomaly": Template("""
You are an expert compliance analyst. Explain this anomaly finding to an auditor.

ANOMALY DETAILS:
- Severity: $severity
- Description: $description
- Rule: $rule_name
- Rule Type: $rule_type

CONTEXT DATA:
$context_data

ANOMALY SCORES:
- Anomaly Score: $anomaly_score
- Confidence: $confidence
- Probability: $probability

ADDITIONAL CONTEXT:
$additional_context

Please provide:
1. A clear explanation of why this was flagged as an anomaly
2. The potential risk or compliance issue
3. Recommended next steps for investigation
4. Any false positive indicators to consider

Keep the explanation professional, concise, and actionable. Use bullet points where appropriate.
            """),
            
            "explain_rule_violation": Template("""
You are a regulatory compliance expert. Explain this rule violation finding.

RULE VIOLATION DETAILS:
- Rule: $rule_name
- Rule Description: $rule_description
- Rule Expression: $rule_expression
- Severity: $severity
- Violation Type: $violation_type

VIOLATION DATA:
$violation_data

CONTEXT:
$context

Please provide:
1. Explanation of the violated rule in simple terms
2. Why this specific data triggered the violation
3. Regulatory implications (if any)
4. Recommended corrective actions
5. Prevention measures for future

Format the response for a compliance report. Be specific about the violation.
            """),
            
            "summarize_findings": Template("""
You are an audit report writer. Summarize these audit findings for executive review.

AUDIT SUMMARY:
- Total Findings: $total_findings
- Critical: $critical_count
- High: $high_count
- Medium: $medium_count
- Low: $low_count

FINDINGS BREAKDOWN:
$findings_breakdown

CONTEXT:
- Audit Scope: $audit_scope
- Time Period: $time_period
- Data Source: $data_source

Please provide:
1. Executive summary (2-3 sentences)
2. Key risk areas identified
3. Most critical findings
4. Overall risk assessment
5. Immediate action items
6. Long-term recommendations

Write in professional business language suitable for C-level executives.
            """),
            
            "suggest_remediation": Template("""
You are a risk remediation specialist. Suggest actions to address these findings.

FINDING DETAILS:
- Type: $finding_type
- Severity: $severity
- Description: $description
- Affected Area: $affected_area

CONTEXT:
- Business Impact: $business_impact
- Regulatory Requirements: $regulatory_requirements
- Current Controls: $current_controls

Please provide:
1. Immediate remediation actions (within 24 hours)
2. Short-term fixes (within 7 days)
3. Long-term preventive measures
4. Control enhancements needed
5. Monitoring requirements post-remediation
6. Estimated effort and resources

Prioritize actions based on risk and business impact.
            """),
            
            "translate_technical": Template("""
You are a technical translator. Explain this technical finding in business terms.

TECHNICAL FINDING:
$technical_finding

BUSINESS CONTEXT:
- Department: $department
- Process: $process
- Business Impact: $business_impact

Please translate this finding by:
1. Explaining what happened in simple business language
2. Describing the business impact (financial, operational, reputational)
3. Connecting to business processes affected
4. Explaining why non-technical stakeholders should care
5. Suggesting business-focused next steps

Avoid technical jargon. Focus on business outcomes and risks.
            """)
        }
    
    def get_prompt(
        self,
        prompt_type: str,
        variables: Dict[str, Any],
        system_prompt: str = None
    ) -> List[Dict[str, str]]:
        """
        Get formatted prompt for given type and variables.
        
        Args:
            prompt_type: Type of prompt
            variables: Variables to substitute
            system_prompt: Custom system prompt
        
        Returns:
            List of messages for OpenAI API
        """
        if prompt_type not in self.templates:
            raise ValueError(f"Unknown prompt type: {prompt_type}")
        
        # Format variables for string substitution
        formatted_vars = {}
        for key, value in variables.items():
            if isinstance(value, (dict, list)):
                formatted_vars[key] = json.dumps(value, indent=2, default=str)
            else:
                formatted_vars[key] = str(value)
        
        # Get template and substitute variables
        template = self.templates[prompt_type]
        user_prompt = template.safe_substitute(formatted_vars)
        
        # Create messages
        messages = []
        
        # System message
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": "You are a helpful AI assistant specialized in audit, compliance, and risk analysis."})
        
        # User message
        messages.append({"role": "user", "content": user_prompt})
        
        return messages
    
    def create_custom_prompt(
        self,
        template: str,
        variables: Dict[str, Any],
        system_prompt: str = None
    ) -> List[Dict[str, str]]:
        """
        Create prompt from custom template.
        
        Args:
            template: Template string
            variables: Variables to substitute
            system_prompt: Custom system prompt
        
        Returns:
            List of messages
        """
        # Format variables
        formatted_vars = {}
        for key, value in variables.items():
            if isinstance(value, (dict, list)):
                formatted_vars[key] = json.dumps(value, indent=2, default=str)
            else:
                formatted_vars[key] = str(value)
        
        # Substitute variables
        user_prompt = Template(template).safe_substitute(formatted_vars)
        
        # Create messages
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": user_prompt})
        
        return messages
    
    def estimate_tokens(self, prompt_type: str, variables: Dict[str, Any]) -> int:
        """
        Estimate tokens for a prompt.
        
        Args:
            prompt_type: Type of prompt
            variables: Variables
        
        Returns:
            Estimated token count
        """
        messages = self.get_prompt(prompt_type, variables)
        
        # Simple estimation: 4 characters ≈ 1 token
        total_chars = sum(len(msg["content"]) for msg in messages)
        return total_chars // 4
    
    def get_available_prompts(self) -> Dict[str, str]:
        """Get list of available prompt types with descriptions."""
        descriptions = {
            "explain_anomaly": "Explain why a data point was flagged as anomalous",
            "explain_rule_violation": "Explain a rule violation in compliance terms",
            "summarize_findings": "Summarize audit findings for executive review",
            "suggest_remediation": "Suggest remediation actions for findings",
            "translate_technical": "Translate technical findings to business language"
        }
        
        return descriptions


# Global prompts instance
explanation_prompts = ExplanationPrompts()