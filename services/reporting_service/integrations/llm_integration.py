"""
LLM integration for AI explanations in reports.
"""
from typing import Dict, Any, List, Optional
from uuid import UUID

from shared.utils.logging import logger
from shared.utils.config import settings
from services.llm_service.clients.openai_client import llm_client
from services.llm_service.clients.fallback_client import fallback_client
from services.llm_service.prompts.explanation_prompts import (
    get_finding_explanation_prompt,
    get_executive_summary_prompt,
    get_recommendation_prompt
)


class LLMIntegration:
    """Handles LLM integration for report explanations."""
    
    def __init__(self):
        self.use_fallback = False
        self.llm_cache = {}  # Simple in-memory cache
    
    def get_finding_explanation(
        self,
        finding: Dict[str, Any],
        context: Optional[str] = None,
        use_cache: bool = True
    ) -> str:
        """
        Get AI explanation for a finding.
        
        Args:
            finding: Finding data
            context: Additional context
            use_cache: Whether to use cached explanations
        
        Returns:
            AI explanation
        """
        cache_key = self._get_cache_key(finding, 'explanation')
        
        if use_cache and cache_key in self.llm_cache:
            return self.llm_cache[cache_key]
        
        try:
            prompt = get_finding_explanation_prompt(finding, context)
            
            explanation = self._call_llm_with_fallback(
                prompt=prompt,
                context=f"Finding explanation for {finding.get('id', 'unknown')}",
                max_tokens=300
            )
            
            if use_cache:
                self.llm_cache[cache_key] = explanation
            
            return explanation
        
        except Exception as e:
            logger.error(f"Failed to get finding explanation: {str(e)}")
            return self._get_default_explanation(finding)
    
    def get_executive_summary(
        self,
        findings: List[Dict[str, Any]],
        report_metadata: Dict[str, Any]
    ) -> str:
        """
        Get AI-generated executive summary.
        
        Args:
            findings: List of findings
            report_metadata: Report metadata
        
        Returns:
            Executive summary
        """
        try:
            prompt = get_executive_summary_prompt(findings, report_metadata)
            
            summary = self._call_llm_with_fallback(
                prompt=prompt,
                context=f"Executive summary for report",
                max_tokens=500
            )
            
            return summary
        
        except Exception as e:
            logger.error(f"Failed to get executive summary: {str(e)}")
            return self._get_default_summary(findings, report_metadata)
    
    def get_recommendations(
        self,
        findings: List[Dict[str, Any]],
        priority: str = "high"
    ) -> List[Dict[str, Any]]:
        """
        Get AI-generated recommendations.
        
        Args:
            findings: List of findings
            priority: Priority filter
        
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Filter findings by priority if specified
        filtered_findings = findings
        if priority != "all":
            filtered_findings = [f for f in findings if f.get('severity') == priority]
        
        for finding in filtered_findings:
            try:
                prompt = get_recommendation_prompt(finding)
                
                recommendation_text = self._call_llm_with_fallback(
                    prompt=prompt,
                    context=f"Recommendation for finding {finding.get('id')}",
                    max_tokens=200
                )
                
                recommendation = {
                    'finding_id': finding.get('id'),
                    'title': finding.get('title'),
                    'severity': finding.get('severity'),
                    'recommendation': recommendation_text,
                    'priority': finding.get('severity', 'medium'),
                    'estimated_effort': self._estimate_effort(finding)
                }
                
                recommendations.append(recommendation)
            
            except Exception as e:
                logger.error(f"Failed to get recommendation for finding {finding.get('id')}: {str(e)}")
                # Add default recommendation
                recommendations.append({
                    'finding_id': finding.get('id'),
                    'title': finding.get('title'),
                    'severity': finding.get('severity'),
                    'recommendation': f"Review and address the {finding.get('category', 'security')} finding.",
                    'priority': finding.get('severity', 'medium'),
                    'estimated_effort': 'medium'
                })
        
        return recommendations
    
    def enhance_report_with_ai(
        self,
        report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enhance report data with AI-generated content.
        
        Args:
            report_data: Original report data
        
        Returns:
            Enhanced report data
        """
        enhanced_data = report_data.copy()
        
        # Add executive summary if not present
        if 'executive_summary' not in enhanced_data:
            findings = enhanced_data.get('findings', [])
            metadata = enhanced_data.get('report_metadata', {})
            
            try:
                enhanced_data['executive_summary'] = self.get_executive_summary(
                    findings, metadata
                )
            except Exception as e:
                logger.error(f"Failed to add executive summary: {str(e)}")
                enhanced_data['executive_summary'] = self._get_default_summary(findings, metadata)
        
        # Add AI explanations to findings
        findings = enhanced_data.get('findings', [])
        for finding in findings:
            if 'ai_explanation' not in finding:
                try:
                    finding['ai_explanation'] = self.get_finding_explanation(finding)
                except Exception as e:
                    logger.error(f"Failed to add AI explanation to finding {finding.get('id')}: {str(e)}")
                    finding['ai_explanation'] = self._get_default_explanation(finding)
        
        # Add AI recommendations
        if 'ai_recommendations' not in enhanced_data:
            try:
                enhanced_data['ai_recommendations'] = self.get_recommendations(
                    findings, priority="high"
                )
            except Exception as e:
                logger.error(f"Failed to add AI recommendations: {str(e)}")
                enhanced_data['ai_recommendations'] = []
        
        # Add risk assessment if not present
        if 'risk_assessment' not in enhanced_data:
            enhanced_data['risk_assessment'] = self._assess_risk(findings)
        
        return enhanced_data
    
    def _call_llm_with_fallback(
        self,
        prompt: str,
        context: str,
        max_tokens: int
    ) -> str:
        """
        Call LLM with fallback mechanism.
        
        Args:
            prompt: Prompt text
            context: Context for the call
            max_tokens: Maximum tokens in response
        
        Returns:
            LLM response
        """
        try:
            if not self.use_fallback:
                return llm_client.generate_explanation(
                    prompt=prompt,
                    context=context,
                    max_tokens=max_tokens
                )
            else:
                return fallback_client.generate_explanation(
                    prompt=prompt,
                    context=context,
                    max_tokens=max_tokens
                )
        
        except Exception as primary_error:
            logger.warning(f"Primary LLM failed, trying fallback: {str(primary_error)}")
            
            try:
                self.use_fallback = True
                return fallback_client.generate_explanation(
                    prompt=prompt,
                    context=context,
                    max_tokens=max_tokens
                )
            
            except Exception as fallback_error:
                logger.error(f"Both LLM and fallback failed: {str(fallback_error)}")
                raise
    
    def _get_cache_key(self, finding: Dict[str, Any], content_type: str) -> str:
        """Generate cache key for a finding."""
        finding_id = finding.get('id', 'unknown')
        title_hash = hash(finding.get('title', ''))
        severity = finding.get('severity', 'unknown')
        
        return f"{content_type}_{finding_id}_{title_hash}_{severity}"
    
    def _get_default_explanation(self, finding: Dict[str, Any]) -> str:
        """Get default explanation when LLM fails."""
        severity = finding.get('severity', 'medium').capitalize()
        category = finding.get('category', 'security').replace('_', ' ').title()
        
        return (
            f"This is a {severity.lower()} severity finding in the {category.lower()} category. "
            f"It indicates a potential issue that should be reviewed. "
            f"Please refer to the finding details for more information."
        )
    
    def _get_default_summary(
        self,
        findings: List[Dict[str, Any]],
        metadata: Dict[str, Any]
    ) -> str:
        """Get default summary when LLM fails."""
        total_findings = len(findings)
        high_severity = len([f for f in findings if f.get('severity') == 'high'])
        medium_severity = len([f for f in findings if f.get('severity') == 'medium'])
        
        return (
            f"This audit report contains {total_findings} findings, including "
            f"{high_severity} high severity and {medium_severity} medium severity findings. "
            f"Review the detailed findings and recommendations for remediation steps."
        )
    
    def _estimate_effort(self, finding: Dict[str, Any]) -> str:
        """Estimate remediation effort."""
        severity = finding.get('severity', 'medium')
        category = finding.get('category', 'security')
        
        if severity == 'high':
            return 'high'
        elif severity == 'medium':
            return 'medium'
        else:
            return 'low'
    
    def _assess_risk(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess overall risk based on findings."""
        high_count = len([f for f in findings if f.get('severity') == 'high'])
        medium_count = len([f for f in findings if f.get('severity') == 'medium'])
        low_count = len([f for f in findings if f.get('severity') == 'low'])
        
        total = len(findings)
        
        # Calculate risk score (0-100)
        if total == 0:
            risk_score = 0
        else:
            risk_score = min(100, (high_count * 10 + medium_count * 5 + low_count * 2))
        
        # Determine risk level
        if risk_score >= 70:
            risk_level = 'Critical'
        elif risk_score >= 40:
            risk_level = 'High'
        elif risk_score >= 20:
            risk_level = 'Medium'
        elif risk_score >= 5:
            risk_level = 'Low'
        else:
            risk_level = 'Very Low'
        
        return {
            'risk_score': risk_score,
            'risk_level': risk_level,
            'finding_counts': {
                'high': high_count,
                'medium': medium_count,
                'low': low_count,
                'total': total
            },
            'assessment': f"The overall risk level is {risk_level.lower()} with a score of {risk_score}/100."
        }


# Global LLM integration instance
llm_integration = LLMIntegration()