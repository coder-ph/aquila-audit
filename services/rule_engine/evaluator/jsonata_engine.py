"""
JSONata expression engine for rule evaluation.
"""
import jsonata
import json
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID
import re



class JSONataEngine:
    """Enhanced JSONata expression engine with custom functions."""
    
    def __init__(self):
        self.custom_functions = self._register_custom_functions()
    
    def _register_custom_functions(self) -> Dict[str, Any]:
        """Register custom JSONata functions."""
        
        def regex_match(pattern: str, text: str) -> bool:
            """Check if text matches regex pattern."""
            try:
                return bool(re.match(pattern, text))
            except:
                return False
        
        def contains_any(text: str, substrings: List[str]) -> bool:
            """Check if text contains any of the substrings."""
            if not isinstance(text, str):
                return False
            return any(sub in text for sub in substrings)
        
        def contains_all(text: str, substrings: List[str]) -> bool:
            """Check if text contains all of the substrings."""
            if not isinstance(text, str):
                return False
            return all(sub in text for sub in substrings)
        
        def is_email(text: str) -> bool:
            """Check if text is a valid email."""
            if not isinstance(text, str):
                return False
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return bool(re.match(email_regex, text))
        
        def is_phone(text: str) -> bool:
            """Check if text is a valid phone number."""
            if not isinstance(text, str):
                return False
            # Simple phone regex
            phone_regex = r'^[\d\s\-\+\(\)]{10,20}$'
            return bool(re.match(phone_regex, text))
        
        def is_credit_card(text: str) -> bool:
            """Check if text is a credit card number."""
            if not isinstance(text, str):
                return False
            # Remove spaces and dashes
            cleaned = re.sub(r'[\s\-]', '', text)
            # Check if it's all digits and proper length
            if not cleaned.isdigit() or len(cleaned) < 13 or len(cleaned) > 19:
                return False
            # Luhn algorithm check
            return self._luhn_check(cleaned)
        
        def _luhn_check(number: str) -> bool:
            """Luhn algorithm for credit card validation."""
            def digits_of(n):
                return [int(d) for d in str(n)]
            
            digits = digits_of(number)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10 == 0
        
        def is_ssn(text: str) -> bool:
            """Check if text is a Social Security Number."""
            if not isinstance(text, str):
                return False
            ssn_regex = r'^\d{3}-\d{2}-\d{4}$'
            return bool(re.match(ssn_regex, text))
        
        def is_date(text: str, format: Optional[str] = None) -> bool:
            """Check if text is a valid date."""
            try:
                from datetime import datetime
                if format:
                    datetime.strptime(text, format)
                else:
                    # Try common formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y.%m.%d']:
                        try:
                            datetime.strptime(text, fmt)
                            return True
                        except:
                            continue
                    return False
                return True
            except:
                return False
        
        def is_number_in_range(num: float, min_val: float, max_val: float) -> bool:
            """Check if number is in range."""
            try:
                return min_val <= float(num) <= max_val
            except:
                return False
        
        def string_length(text: str) -> int:
            """Get string length."""
            if not isinstance(text, str):
                return 0
            return len(text)
        
        return {
            "$regexMatch": regex_match,
            "$containsAny": contains_any,
            "$containsAll": contains_all,
            "$isEmail": is_email,
            "$isPhone": is_phone,
            "$isCreditCard": is_credit_card,
            "$isSSN": is_ssn,
            "$isDate": is_date,
            "$inRange": is_number_in_range,
            "$strLength": string_length
        }
    
    def compile_expression(self, expression: str) -> jsonata.Expression:
        """
        Compile JSONata expression with custom functions.
        
        Args:
            expression: JSONata expression string
        
        Returns:
            Compiled expression
        """
        expr = jsonata.Expression(expression)
        
        # Register custom functions
        for name, func in self.custom_functions.items():
            expr.register_function(name, func)
        
        return expr
    
    def validate_expression(self, expression: str) -> Tuple[bool, Optional[str]]:
        """
        Validate JSONata expression.
        
        Args:
            expression: JSONata expression to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.compile_expression(expression)
            return True, None
        except Exception as e:
            return False, str(e)
    
    def extract_variables(self, expression: str) -> List[str]:
        """
        Extract variable references from JSONata expression.
        
        Args:
            expression: JSONata expression
        
        Returns:
            List of variable names
        """
        # Simple extraction of $ variables
        variables = re.findall(r'\$[a-zA-Z_][a-zA-Z0-9_]*', expression)
        return list(set(variables))
    
    def create_test_context(self, rule_expression: str, sample_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create test context for rule expression.
        
        Args:
            rule_expression: Rule expression
            sample_data: Sample data
        
        Returns:
            Test context
        """
        # Extract expected variables
        variables = self.extract_variables(rule_expression)
        
        # Build context based on variables
        context = {}
        for var in variables:
            if var == "$data":
                context["data"] = sample_data
            elif var == "$context":
                context["context"] = {"test": True}
            elif var == "$row":
                context["row"] = sample_data
            elif var == "$file":
                context["file"] = {"name": "test.csv", "size": 1000}
        
        return context
    
    def test_expression(
        self,
        expression: str,
        test_data: Dict[str, Any],
        expected_result: Any = None
    ) -> Dict[str, Any]:
        """
        Test JSONata expression with test data.
        
        Args:
            expression: JSONata expression
            test_data: Test data
            expected_result: Expected result (optional)
        
        Returns:
            Test results
        """
        try:
            expr = self.compile_expression(expression)
            context = self.create_test_context(expression, test_data)
            result = expr.evaluate(context)
            
            test_result = {
                "success": True,
                "result": result,
                "context_used": context
            }
            
            if expected_result is not None:
                test_result["expected"] = expected_result
                test_result["matches_expected"] = result == expected_result
            
            return test_result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "context_used": self.create_test_context(expression, test_data)
            }


# Global JSONata engine instance
jsonata_engine = JSONataEngine()