"""
Bulk processing for rule evaluation.
"""
import pandas as pd
from typing import Dict, List, Any, Optional
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from datetime import datetime
import json

from shared.utils.logging import logger
from shared.models.rule_models import Rule
from shared.models.schemas import FindingSeverity

from .rule_evaluator import BulkRuleEvaluator
from .jsonata_engine import jsonata_engine


class BulkProcessor:
    """Processes large datasets with rule evaluation."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.bulk_evaluator = BulkRuleEvaluator(max_workers=max_workers)
    
    def process_dataframe(
        self,
        rules: List[Rule],
        df: pd.DataFrame,
        file_id: UUID,
        batch_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Process pandas DataFrame with rules.
        
        Args:
            rules: List of rules to evaluate
            df: Pandas DataFrame
            file_id: File ID
            batch_size: Batch size for processing
        
        Returns:
            List of findings
        """
        # Convert DataFrame to list of dictionaries
        data = df.to_dict(orient='records')
        
        # Process with bulk evaluator
        findings = self.bulk_evaluator.evaluate_rules_against_data(
            rules=rules,
            data=data,
            file_id=file_id,
            batch_size=batch_size
        )
        
        return findings
    
    def process_file(
        self,
        rules: List[Rule],
        file_path: str,
        file_id: UUID,
        file_type: str = "csv"
    ) -> List[Dict[str, Any]]:
        """
        Process file directly with rules.
        
        Args:
            rules: List of rules
            file_path: Path to file
            file_id: File ID
            file_type: File type (csv, excel, json)
        
        Returns:
            List of findings
        """
        try:
            # Read file based on type
            if file_type == "csv":
                df = pd.read_csv(file_path)
            elif file_type in ["xlsx", "xls"]:
                df = pd.read_excel(file_path)
            elif file_type == "json":
                with open(file_path, 'r') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                else:
                    df = pd.DataFrame([data])
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
            
            # Process DataFrame
            findings = self.process_dataframe(rules, df, file_id)
            
            logger.info(f"Processed file {file_path}: {len(findings)} findings")
            return findings
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            raise
    
    def parallel_process(
        self,
        rules: List[Rule],
        data_chunks: List[List[Dict[str, Any]]],
        file_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Process data chunks in parallel.
        
        Args:
            rules: List of rules
            data_chunks: List of data chunks
            file_id: File ID
        
        Returns:
            Combined findings from all chunks
        """
        all_findings = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks for each chunk
            future_to_chunk = {
                executor.submit(
                    self.bulk_evaluator.evaluate_rules_against_data,
                    rules,
                    chunk,
                    file_id
                ): chunk_idx
                for chunk_idx, chunk in enumerate(data_chunks)
            }
            
            # Collect results
            for future in as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_findings = future.result()
                    all_findings.extend(chunk_findings)
                    logger.debug(f"Processed chunk {chunk_idx}: {len(chunk_findings)} findings")
                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_idx}: {str(e)}")
        
        return all_findings
    
    def categorize_findings(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Categorize findings by severity and rule.
        
        Args:
            findings: List of findings
        
        Returns:
            Categorized findings
        """
        categorized = {
            "by_severity": {
                "critical": [],
                "high": [],
                "medium": [],
                "low": []
            },
            "by_rule": {},
            "summary": {
                "total": len(findings),
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            }
        }
        
        for finding in findings:
            severity = finding.get("severity", "medium").lower()
            
            # Add to severity category
            if severity in categorized["by_severity"]:
                categorized["by_severity"][severity].append(finding)
                categorized["summary"][severity] += 1
            
            # Add to rule category
            rule_id = finding.get("rule_id")
            if rule_id:
                rule_id_str = str(rule_id)
                if rule_id_str not in categorized["by_rule"]:
                    categorized["by_rule"][rule_id_str] = []
                categorized["by_rule"][rule_id_str].append(finding)
        
        return categorized
    
    def generate_summary_report(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate summary report from findings.
        
        Args:
            findings: List of findings
        
        Returns:
            Summary report
        """
        categorized = self.categorize_findings(findings)
        
        report = {
            "total_findings": len(findings),
            "severity_distribution": categorized["summary"],
            "unique_rules": len(categorized["by_rule"]),
            "timestamp": datetime.utcnow().isoformat(),
            "has_critical_findings": categorized["summary"]["critical"] > 0,
            "has_high_findings": categorized["summary"]["high"] > 0,
            "needs_attention": categorized["summary"]["critical"] > 0 or categorized["summary"]["high"] > 0
        }
        
        return report


# Global bulk processor instance
bulk_processor = BulkProcessor()