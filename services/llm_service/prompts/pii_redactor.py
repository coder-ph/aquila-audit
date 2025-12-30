"""
PII (Personally Identifiable Information) redaction for prompts.
"""
import re
from typing import Dict, List, Any, Optional, Tuple
import json
from datetime import datetime

from shared.utils.logging import logger
from services.llm_service.config import config


class PIIRedactor:
    """Redacts PII from text before sending to LLM."""
    
    def __init__(self):
        self.enabled = config.pii_redaction_enabled
        self.entities = config.pii_entities
        
        # Regex patterns for different PII types
        self.patterns = {
            "EMAIL_ADDRESS": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "PHONE_NUMBER": r'\b(?:\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
            "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
            "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
            "IP_ADDRESS": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        }
        
        # Custom patterns for additional PII
        self.custom_patterns = {
            "PERSON": r'\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s?[A-Z][a-z]+\s[A-Z][a-z]+\b',
            "LOCATION": r'\b\d+\s+[A-Z][a-z]+\s+(?:St|Ave|Rd|Blvd|Ln|Dr)\.?\b',
        }
        
        # Redaction replacements
        self.replacements = {
            "EMAIL_ADDRESS": "[EMAIL_REDACTED]",
            "PHONE_NUMBER": "[PHONE_REDACTED]",
            "CREDIT_CARD": "[CC_REDACTED]",
            "SSN": "[SSN_REDACTED]",
            "IP_ADDRESS": "[IP_REDACTED]",
            "PERSON": "[NAME_REDACTED]",
            "LOCATION": "[ADDRESS_REDACTED]"
        }
        
    def redact_text(self, text: str, entity_types: List[str] = None) -> Tuple[str, Dict[str, List[str]]]:
        """
        Redact PII from text.
        
        Args:
            text: Text to redact
            entity_types: Specific entity types to redact (all if None)
        
        Returns:
            Tuple of (redacted_text, detected_entities)
        """
        if not self.enabled or not text:
            return text, {}
        
        if entity_types is None:
            entity_types = self.entities
        
        redacted_text = text
        detected_entities = {}
        
        # Check each entity type
        for entity in entity_types:
            if entity in self.patterns:
                pattern = self.patterns[entity]
                replacement = self.replacements.get(entity, f"[{entity}_REDACTED]")
                
                # Find all matches
                matches = re.findall(pattern, redacted_text, re.IGNORECASE)
                if matches:
                    detected_entities[entity] = list(set(matches))
                
                # Replace with redaction
                redacted_text = re.sub(pattern, replacement, redacted_text, flags=re.IGNORECASE)
            
            elif entity in self.custom_patterns:
                pattern = self.custom_patterns[entity]
                replacement = self.replacements.get(entity, f"[{entity}_REDACTED]")
                
                # Find all matches
                matches = re.findall(pattern, redacted_text)
                if matches:
                    detected_entities[entity] = list(set(matches))
                
                # Replace with redaction
                redacted_text = re.sub(pattern, replacement, redacted_text)
        
        # Log redaction if entities were detected
        if detected_entities:
            logger.info(f"Redacted PII from text: {list(detected_entities.keys())}")
        
        return redacted_text, detected_entities
    
    def redact_json(self, data: Any, entity_types: List[str] = None) -> Tuple[Any, Dict[str, List[str]]]:
        """
        Redact PII from JSON data.
        
        Args:
            data: JSON data (dict, list, or primitive)
            entity_types: Entity types to redact
        
        Returns:
            Tuple of (redacted_data, detected_entities)
        """
        if not self.enabled or data is None:
            return data, {}
        
        if entity_types is None:
            entity_types = self.entities
        
        all_detected = {}
        
        def process_value(value):
            nonlocal all_detected
            
            if isinstance(value, str):
                redacted, detected = self.redact_text(value, entity_types)
                if detected:
                    for entity, matches in detected.items():
                        if entity not in all_detected:
                            all_detected[entity] = []
                        all_detected[entity].extend(matches)
                return redacted
            elif isinstance(value, dict):
                return {k: process_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [process_value(item) for item in value]
            else:
                return value
        
        redacted_data = process_value(data)
        
        # Deduplicate detected entities
        for entity in all_detected:
            all_detected[entity] = list(set(all_detected[entity]))
        
        return redacted_data, all_detected
    
    def redact_prompt(
        self,
        messages: List[Dict[str, str]],
        entity_types: List[str] = None
    ) -> Tuple[List[Dict[str, str]], Dict[str, List[str]]]:
        """
        Redact PII from prompt messages.
        
        Args:
            messages: List of message dictionaries
            entity_types: Entity types to redact
        
        Returns:
            Tuple of (redacted_messages, detected_entities)
        """
        if not self.enabled:
            return messages, {}
        
        redacted_messages = []
        all_detected = {}
        
        for message in messages:
            content = message.get("content", "")
            role = message.get("role", "user")
            
            if content:
                redacted_content, detected = self.redact_text(content, entity_types)
                
                # Merge detected entities
                for entity, matches in detected.items():
                    if entity not in all_detected:
                        all_detected[entity] = []
                    all_detected[entity].extend(matches)
                
                redacted_messages.append({
                    "role": role,
                    "content": redacted_content
                })
            else:
                redacted_messages.append(message)
        
        # Deduplicate detected entities
        for entity in all_detected:
            all_detected[entity] = list(set(all_detected[entity]))
        
        return redacted_messages, all_detected
    
    def mask_sensitive_data(
        self,
        data: Dict[str, Any],
        sensitive_fields: List[str] = None
    ) -> Dict[str, Any]:
        """
        Mask sensitive data fields.
        
        Args:
            data: Data dictionary
            sensitive_fields: Fields to mask
        
        Returns:
            Masked data
        """
        if sensitive_fields is None:
            sensitive_fields = ["password", "secret", "token", "key", "auth"]
        
        def mask_value(value):
            if isinstance(value, str) and len(value) > 0:
                return "***" + value[-4:] if len(value) > 4 else "***"
            return "***"
        
        def process_dict(d):
            result = {}
            for key, value in d.items():
                key_lower = key.lower()
                is_sensitive = any(sensitive in key_lower for sensitive in sensitive_fields)
                
                if is_sensitive:
                    result[key] = mask_value(value)
                elif isinstance(value, dict):
                    result[key] = process_dict(value)
                elif isinstance(value, list):
                    result[key] = [process_dict(item) if isinstance(item, dict) else 
                                  (mask_value(item) if is_sensitive else item) for item in value]
                else:
                    result[key] = value
            return result
        
        return process_dict(data)
    
    def get_redaction_report(self, detected_entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Generate redaction report.
        
        Args:
            detected_entities: Detected entities
        
        Returns:
            Redaction report
        """
        total_entities = sum(len(matches) for matches in detected_entities.values())
        
        return {
            "total_entities_redacted": total_entities,
            "entity_types": list(detected_entities.keys()),
            "entities_by_type": {
                entity: {
                    "count": len(matches),
                    "samples": matches[:3]  # First 3 samples
                }
                for entity, matches in detected_entities.items()
            },
            "timestamp": datetime.utcnow().isoformat()
        }


# Global PII redactor instance
pii_redactor = PIIRedactor()