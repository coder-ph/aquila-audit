import json
import jsonata
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime

from shared.utils.logging import logger
from shared.models.rule_models import Rule
from shared.models.schemas import FindingSeverity


class RuleEvaluator:
    """Evaluates rules against data using JSONata expressions."""
    
    def __init__(self):
        self.cache = {}
    
    def evaluate_rule(
        self,
        rule: Rule,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Evaluate a single rule against data.
        
        Args:
            rule: Rule to evaluate
            data: Data to evaluate against
            context: Additional context
        
        Returns:
            Tuple of (is_violation, error_message, violation_data)
        """
        try:
            # Prepare evaluation context
            eval_context = {
                "data": data,
                "context": context or {},
                "rule": {
                    "id": str(rule.id),
                    "name": rule.name,
                    "type": rule.rule_type,
                    "severity": rule.severity
                }
            }
            
            # Apply JSONata expression
            expression = jsonata.Expression(rule.rule_expression)
            result = expression.evaluate(eval_context)
            
            # Interpret result
            if result is None or result is False:
                return False, None, None
            elif result is True:
                # Simple boolean match
                violation_data = {
                    "rule_id": str(rule.id),
                    "rule_name": rule.name,
                    "matched": True,
                    "context": context
                }
                return True, f"Rule '{rule.name}' matched", violation_data
            elif isinstance(result, dict) and result.get("match", False):
                # Complex match with details
                violation_data = {
                    "rule_id": str(rule.id),
                    "rule_name": rule.name,
                    "matched": True,
                    "details": result.get("details"),
                    "context": context
                }
                message = result.get("message", f"Rule '{rule.name}' matched")
                return True, message, violation_data
            elif isinstance(result, list) and len(result) > 0:
                # Multiple matches
                violation_data = {
                    "rule_id": str(rule.id),
                    "rule_name": rule.name,
                    "matched": True,
                    "matches": result,
                    "match_count": len(result),
                    "context": context
                }
                return True, f"Rule '{rule.name}' matched {len(result)} times", violation_data
            else:
                # No match
                return False, None, None
                
        except jsonata.JSONataError as e:
            logger.error(f"JSONata evaluation error for rule {rule.id}: {str(e)}")
            return False, f"Rule evaluation error: {str(e)}", None
        except Exception as e:
            logger.error(f"Unexpected error evaluating rule {rule.id}: {str(e)}")
            return False, f"Unexpected error: {str(e)}", None
    
    def evaluate_batch(
        self,
        rule: Rule,
        data_batch: List[Dict[str, Any]],
        batch_context: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Dict[str, Any], bool, Optional[str], Optional[Dict[str, Any]]]]:
        """
        Evaluate rule against a batch of data.
        
        Args:
            rule: Rule to evaluate
            data_batch: List of data records
            batch_context: Additional context for the batch
        
        Returns:
            List of (data_record, is_violation, error_message, violation_data)
        """
        results = []
        
        for i, data in enumerate(data_batch):
            # Add row/record context
            context = {
                **(batch_context or {}),
                "row_index": i,
                "batch_size": len(data_batch),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            is_violation, error_message, violation_data = self.evaluate_rule(
                rule, data, context
            )
            
            results.append((data, is_violation, error_message, violation_data))
        
        return results
    
    def create_finding_from_violation(
        self,
        rule: Rule,
        data: Dict[str, Any],
        violation_data: Dict[str, Any],
        file_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a finding dictionary from rule violation.
        
        Args:
            rule: Rule that was violated
            data: Original data that triggered violation
            violation_data: Violation details from evaluation
            file_id: File ID where data came from
            context: Additional context
        
        Returns:
            Finding dictionary ready for database insertion
        """
        # Create finding description
        if "message" in violation_data:
            description = violation_data["message"]
        elif "details" in violation_data:
            description = f"Rule '{rule.name}' violation: {violation_data['details']}"
        else:
            description = f"Rule '{rule.name}' violation detected"
        
        # Create finding
        finding = {
            "rule_id": rule.id,
            "file_id": file_id,
            "severity": rule.severity,
            "description": description,
            "raw_data": data,
            "context": {
                **(context or {}),
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "violation_data": violation_data
            },
            "status": "open"
        }
        
        # Add location if available
        if context and "row_index" in context:
            finding["location"] = {
                "row": context["row_index"],
                "batch_index": context.get("batch_index", 0)
            }
        
        return finding


class BulkRuleEvaluator:
    """Evaluates multiple rules against data in bulk."""
    
    def __init__(self, max_workers: int = 4):
        self.rule_evaluator = RuleEvaluator()
        self.max_workers = max_workers
    
    def evaluate_rules_against_data(
        self,
        rules: List[Rule],
        data: List[Dict[str, Any]],
        file_id: UUID,
        batch_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Evaluate multiple rules against data.
        
        Args:
            rules: List of rules to evaluate
            data: List of data records
            file_id: File ID where data came from
            batch_size: Size of data batches
        
        Returns:
            List of findings
        """
        all_findings = []
        
        # Filter active rules
        active_rules = [rule for rule in rules if rule.is_active]
        
        if not active_rules:
            logger.warning("No active rules to evaluate")
            return []
        
        logger.info(f"Evaluating {len(active_rules)} active rules against {len(data)} records")
        
        # Process data in batches
        for batch_index in range(0, len(data), batch_size):
            batch = data[batch_index:batch_index + batch_size]
            batch_context = {
                "batch_index": batch_index // batch_size,
                "total_batches": (len(data) + batch_size - 1) // batch_size
            }
            
            # Evaluate each rule against the batch
            for rule in active_rules:
                batch_results = self.rule_evaluator.evaluate_batch(
                    rule, batch, batch_context
                )
                
                # Create findings from violations
                for data_record, is_violation, error_message, violation_data in batch_results:
                    if is_violation and violation_data:
                        # Add row context
                        row_context = {
                            **batch_context,
                            "row_index": batch_results.index((data_record, is_violation, error_message, violation_data))
                        }
                        
                        finding = self.rule_evaluator.create_finding_from_violation(
                            rule=rule,
                            data=data_record,
                            violation_data=violation_data,
                            file_id=file_id,
                            context=row_context
                        )
                        
                        all_findings.append(finding)
            
            logger.debug(f"Processed batch {batch_index//batch_size + 1}/{(len(data) + batch_size - 1)//batch_size}")
        
        logger.info(f"Generated {len(all_findings)} findings from {len(data)} records")
        
        return all_findings
    
    def evaluate_single_record(
        self,
        rules: List[Rule],
        data: Dict[str, Any],
        file_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate multiple rules against a single data record.
        
        Args:
            rules: List of rules to evaluate
            data: Single data record
            file_id: File ID where data came from
            context: Additional context
        
        Returns:
            List of findings
        """
        findings = []
        
        for rule in rules:
            if not rule.is_active:
                continue
            
            is_violation, error_message, violation_data = self.rule_evaluator.evaluate_rule(
                rule, data, context
            )
            
            if is_violation and violation_data:
                finding = self.rule_evaluator.create_finding_from_violation(
                    rule=rule,
                    data=data,
                    violation_data=violation_data,
                    file_id=file_id,
                    context=context
                )
                
                findings.append(finding)
        
        return findings


# Global evaluator instance
rule_evaluator = RuleEvaluator()
bulk_evaluator = BulkRuleEvaluator()