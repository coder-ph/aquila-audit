"""
Budget management for LLM API usage.
"""
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from shared.utils.logging import logger
from services.llm_service.config import config


class BudgetManager:
    """Manages budgets for LLM API usage."""
    
    def __init__(self):
        self.budgets: Dict[str, Dict[str, Any]] = {}
        self.usage: Dict[str, List[Dict[str, Any]]] = {}
        self.budgets_file = Path("data/budgets.json")
        self.usage_file = Path("data/llm_usage.json")
        
        # Ensure data directory exists
        self.budgets_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_budgets(self):
        """Load budgets from disk."""
        try:
            if self.budgets_file.exists():
                with open(self.budgets_file, 'r') as f:
                    self.budgets = json.load(f)
                logger.info(f"Loaded {len(self.budgets)} budgets")
        except Exception as e:
            logger.error(f"Error loading budgets: {str(e)}")
            self.budgets = {}
    
    def save_budgets(self):
        """Save budgets to disk."""
        try:
            with open(self.budgets_file, 'w') as f:
                json.dump(self.budgets, f, indent=2)
            logger.info("Budgets saved to disk")
        except Exception as e:
            logger.error(f"Error saving budgets: {str(e)}")
    
    def load_usage(self):
        """Load usage data from disk."""
        try:
            if self.usage_file.exists():
                with open(self.usage_file, 'r') as f:
                    self.usage = json.load(f)
                logger.info(f"Loaded usage data for {len(self.usage)} tenants")
        except Exception as e:
            logger.error(f"Error loading usage: {str(e)}")
            self.usage = {}
    
    def save_usage(self):
        """Save usage data to disk."""
        try:
            with open(self.usage_file, 'w') as f:
                json.dump(self.usage, f, indent=2)
            logger.info("Usage data saved to disk")
        except Exception as e:
            logger.error(f"Error saving usage: {str(e)}")
    
    def get_or_create_budget(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get or create budget for tenant.
        
        Args:
            tenant_id: Tenant ID
        
        Returns:
            Budget configuration
        """
        if tenant_id not in self.budgets:
            self.budgets[tenant_id] = {
                "monthly_budget": config.default_monthly_budget,
                "current_month": datetime.utcnow().strftime("%Y-%m"),
                "spent_this_month": 0.0,
                "total_spent": 0.0,
                "warnings_sent": [],
                "limits_enforced": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            self.save_budgets()
        
        return self.budgets[tenant_id]
    
    def update_budget(
        self,
        tenant_id: str,
        amount: float,
        description: str = "",
        user_id: str = None,
        model: str = None
    ) -> Tuple[bool, str]:
        """
        Update budget with new expense.
        
        Args:
            tenant_id: Tenant ID
            amount: Amount to add (USD)
            description: Expense description
            user_id: User ID who made the request
            model: Model used
        
        Returns:
            Tuple of (success, message)
        """
        budget = self.get_or_create_budget(tenant_id)
        
        # Check if month has changed
        current_month = datetime.utcnow().strftime("%Y-%m")
        if budget["current_month"] != current_month:
            # Reset monthly spending
            budget["spent_this_month"] = 0.0
            budget["current_month"] = current_month
            budget["warnings_sent"] = []
        
        # Update spending
        budget["spent_this_month"] += amount
        budget["total_spent"] += amount
        budget["updated_at"] = datetime.utcnow().isoformat()
        
        # Initialize usage tracking if needed
        if tenant_id not in self.usage:
            self.usage[tenant_id] = []
        
        # Record usage
        usage_record = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "amount": amount,
            "description": description,
            "model": model,
            "month": current_month
        }
        
        self.usage[tenant_id].append(usage_record)
        
        # Check budget thresholds
        monthly_budget = budget["monthly_budget"]
        spent = budget["spent_this_month"]
        percentage = (spent / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        messages = []
        
        # Check warning threshold
        if percentage >= config.cost_warning_threshold * 100:
            warning_msg = f"Budget warning: {percentage:.1f}% of monthly budget used"
            if warning_msg not in budget["warnings_sent"]:
                messages.append(warning_msg)
                budget["warnings_sent"].append(warning_msg)
                logger.warning(warning_msg, tenant_id=tenant_id)
        
        # Check limit threshold
        if percentage >= config.cost_limit_threshold * 100 and budget["limits_enforced"]:
            limit_msg = f"Budget limit reached: {percentage:.1f}% of monthly budget used"
            messages.append(limit_msg)
            logger.warning(limit_msg, tenant_id=tenant_id)
        
        # Save updates
        self.save_budgets()
        self.save_usage()
        
        success_msg = f"Updated budget: ${amount:.6f} spent, {percentage:.1f}% of budget used"
        return True, success_msg
    
    def can_make_request(
        self,
        tenant_id: str,
        estimated_cost: float
    ) -> Tuple[bool, str]:
        """
        Check if request can be made within budget.
        
        Args:
            tenant_id: Tenant ID
            estimated_cost: Estimated cost of request
        
        Returns:
            Tuple of (can_proceed, message)
        """
        budget = self.get_or_create_budget(tenant_id)
        
        # Check if month has changed
        current_month = datetime.utcnow().strftime("%Y-%m")
        if budget["current_month"] != current_month:
            return True, "New month, budget reset"
        
        # Check if limits are enforced
        if not budget["limits_enforced"]:
            return True, "Budget limits not enforced"
        
        # Calculate projected spending
        monthly_budget = budget["monthly_budget"]
        spent = budget["spent_this_month"]
        projected = spent + estimated_cost
        projected_percentage = (projected / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        # Check against limit threshold
        if projected_percentage >= config.cost_limit_threshold * 100:
            message = f"Request would exceed budget limit: ${projected:.2f} (${monthly_budget:.2f} budget)"
            return False, message
        
        return True, "Within budget"
    
    def get_budget_summary(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get budget summary for tenant.
        
        Args:
            tenant_id: Tenant ID
        
        Returns:
            Budget summary
        """
        budget = self.get_or_create_budget(tenant_id)
        
        monthly_budget = budget["monthly_budget"]
        spent = budget["spent_this_month"]
        total_spent = budget["total_spent"]
        percentage = (spent / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        # Calculate daily average
        today = datetime.utcnow()
        month_start = today.replace(day=1)
        days_passed = (today - month_start).days + 1
        daily_average = spent / days_passed if days_passed > 0 else 0
        
        # Project month end
        days_in_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1)).day
        projected_end = (spent / days_passed) * days_in_month if days_passed > 0 else 0
        projected_percentage = (projected_end / monthly_budget) * 100 if monthly_budget > 0 else 0
        
        # Get recent usage
        recent_usage = []
        if tenant_id in self.usage:
            recent_usage = self.usage[tenant_id][-10:]  # Last 10 records
        
        return {
            "tenant_id": tenant_id,
            "monthly_budget": monthly_budget,
            "spent_this_month": spent,
            "total_spent": total_spent,
            "percentage_used": percentage,
            "daily_average": daily_average,
            "projected_end_of_month": projected_end,
            "projected_percentage": projected_percentage,
            "days_passed": days_passed,
            "days_in_month": days_in_month,
            "budget_status": self._get_budget_status(percentage),
            "recent_usage": recent_usage,
            "limits_enforced": budget["limits_enforced"],
            "current_month": budget["current_month"]
        }
    
    def _get_budget_status(self, percentage: float) -> str:
        """Get budget status based on percentage used."""
        if percentage >= config.cost_limit_threshold * 100:
            return "EXCEEDED"
        elif percentage >= config.cost_warning_threshold * 100:
            return "WARNING"
        else:
            return "HEALTHY"
    
    def set_budget(
        self,
        tenant_id: str,
        monthly_budget: float,
        limits_enforced: bool = None
    ) -> Dict[str, Any]:
        """
        Set budget for tenant.
        
        Args:
            tenant_id: Tenant ID
            monthly_budget: Monthly budget in USD
            limits_enforced: Whether to enforce limits
        
        Returns:
            Updated budget
        """
        budget = self.get_or_create_budget(tenant_id)
        
        budget["monthly_budget"] = monthly_budget
        if limits_enforced is not None:
            budget["limits_enforced"] = limits_enforced
        budget["updated_at"] = datetime.utcnow().isoformat()
        
        self.save_budgets()
        
        logger.info(f"Set budget for tenant {tenant_id}: ${monthly_budget}/month")
        
        return budget
    
    def get_usage_report(
        self,
        tenant_id: str,
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]:
        """
        Get usage report for tenant.
        
        Args:
            tenant_id: Tenant ID
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
        
        Returns:
            Usage report
        """
        if tenant_id not in self.usage:
            return {
                "tenant_id": tenant_id,
                "total_usage": 0,
                "total_cost": 0.0,
                "usage_by_model": {},
                "usage_by_user": {},
                "daily_usage": [],
                "period": f"{start_date} to {end_date}" if start_date and end_date else "all time"
            }
        
        # Filter usage by date
        usage_records = self.usage[tenant_id]
        
        if start_date or end_date:
            filtered = []
            for record in usage_records:
                record_date = datetime.fromisoformat(record["timestamp"].replace('Z', '+00:00'))
                
                if start_date:
                    start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    if record_date < start:
                        continue
                
                if end_date:
                    end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if record_date > end:
                        continue
                
                filtered.append(record)
            usage_records = filtered
        
        # Calculate totals
        total_cost = sum(record["amount"] for record in usage_records)
        
        # Group by model
        usage_by_model = {}
        for record in usage_records:
            model = record.get("model", "unknown")
            if model not in usage_by_model:
                usage_by_model[model] = {"count": 0, "cost": 0.0}
            usage_by_model[model]["count"] += 1
            usage_by_model[model]["cost"] += record["amount"]
        
        # Group by user
        usage_by_user = {}
        for record in usage_records:
            user_id = record.get("user_id", "anonymous")
            if user_id not in usage_by_user:
                usage_by_user[user_id] = {"count": 0, "cost": 0.0}
            usage_by_user[user_id]["count"] += 1
            usage_by_user[user_id]["cost"] += record["amount"]
        
        # Daily usage
        daily_usage = {}
        for record in usage_records:
            date = record["timestamp"][:10]  # YYYY-MM-DD
            if date not in daily_usage:
                daily_usage[date] = {"count": 0, "cost": 0.0}
            daily_usage[date]["count"] += 1
            daily_usage[date]["cost"] += record["amount"]
        
        # Convert to list sorted by date
        daily_usage_list = [
            {"date": date, "count": data["count"], "cost": data["cost"]}
            for date, data in sorted(daily_usage.items())
        ]
        
        return {
            "tenant_id": tenant_id,
            "total_usage": len(usage_records),
            "total_cost": total_cost,
            "usage_by_model": usage_by_model,
            "usage_by_user": usage_by_user,
            "daily_usage": daily_usage_list,
            "period": f"{start_date} to {end_date}" if start_date and end_date else "all time",
            "report_generated": datetime.utcnow().isoformat()
        }


# Global budget manager instance
budget_manager = BudgetManager()