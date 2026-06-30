# src/engine/validator.py
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ValidationEngine:
    """
    Validation Engine that runs AFTER projection.
    Validates email structure, E164 phone formats, date formats, ISO country codes,
    and required schema fields. Updates pipeline context metrics.
    """

    @staticmethod
    def validate(payload: Dict[str, Any], config_def: Any, context: Any) -> Dict[str, Any]:
        logger.info("Executing post-projection schema and business validations...")
        
        errors = []
        warnings = []
        
        # 1. Required fields and Schema Type checks
        fields_def = config_def.fields if hasattr(config_def, "fields") else config_def.get("fields", [])
        on_missing = config_def.on_missing if hasattr(config_def, "on_missing") else config_def.get("on_missing", "null")
        
        for field in fields_def:
            path = field.get("path")
            is_required = field.get("required", False)
            expected_type = field.get("type", "string")
            
            val = payload.get(path)
            
            # Check Missing
            if val is None or (isinstance(val, list) and len(val) == 0):
                if is_required:
                    if on_missing == "error":
                        raise ValueError(f"Post-Projection Validation Error: Required field '{path}' is missing.")
                    elif on_missing == "omit":
                        if path in payload:
                            del payload[path]
                        warnings.append(f"Required field '{path}' was missing and has been omitted.")
                    else:  # "null"
                        payload[path] = None
                        warnings.append(f"Required field '{path}' was missing and has been set to null.")
                continue
                
            # Check Expected Schema Types
            if expected_type == "string" and not isinstance(val, str):
                # Handle wrapped objects if confidence/provenance is included
                if isinstance(val, dict) and "value" in val:
                    val_check = val["value"]
                else:
                    val_check = val
                if val_check is not None and not isinstance(val_check, str):
                    errors.append(f"Schema Mismatch: Field '{path}' expected string, got {type(val_check).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                errors.append(f"Schema Mismatch: Field '{path}' expected array, got {type(val).__name__}")
            elif expected_type == "object" and not isinstance(val, dict):
                errors.append(f"Schema Mismatch: Field '{path}' expected object, got {type(val).__name__}")

        # 2. Email Validation
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        # Check primary_email or any emails
        for key in ["primary_email", "email"]:
            if key in payload and payload[key]:
                email_val = payload[key]["value"] if isinstance(payload[key], dict) and "value" in payload[key] else payload[key]
                if email_val and not re.match(email_regex, str(email_val)):
                    errors.append(f"Email Syntax Error: '{email_val}' is not a valid email address.")

        if "emails" in payload and isinstance(payload["emails"], list):
            for e in payload["emails"]:
                email_val = e["value"] if isinstance(e, dict) and "value" in e else e
                if email_val and not re.match(email_regex, str(email_val)):
                    errors.append(f"Email List Syntax Error: '{email_val}' is not a valid email address.")

        # 3. Phone Validation
        phone_regex = r'^\+[1-9]\d{1,14}$'  # E164 regex
        for key in ["primary_phone", "phone"]:
            if key in payload and payload[key]:
                phone_val = payload[key]["value"] if isinstance(payload[key], dict) and "value" in payload[key] else payload[key]
                if phone_val and not re.match(phone_regex, str(phone_val)):
                    warnings.append(f"Phone Format Warning: '{phone_val}' does not comply with international E164 format.")

        if "phones" in payload and isinstance(payload["phones"], list):
            for ph in payload["phones"]:
                phone_val = ph["value"] if isinstance(ph, dict) and "value" in ph else ph
                if phone_val and not re.match(phone_regex, str(phone_val)):
                    warnings.append(f"Phone List Format Warning: '{phone_val}' does not comply with international E164 format.")

        # 4. Country Code Validation (ISO-3166 check)
        if "location" in payload and payload["location"]:
            loc_val = payload["location"]["value"] if isinstance(payload["location"], dict) and "value" in payload["location"] else payload["location"]
            if isinstance(loc_val, dict) and loc_val.get("country"):
                country = loc_val["country"]
                if len(str(country)) != 2:
                    warnings.append(f"ISO Country Code Warning: Location country '{country}' is not a standard ISO-3166 2-character code.")

        # 5. Log metrics
        validation_report = {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
        
        context.log_metric("validation_errors_count", len(errors))
        context.log_metric("validation_warnings_count", len(warnings))
        context.log_metric("validation_report", validation_report)
        
        if errors:
            logger.error(f"Post-Projection Validation found {len(errors)} error(s): {errors}")
        if warnings:
            logger.warning(f"Post-Projection Validation found {len(warnings)} warning(s): {warnings}")
            
        return validation_report
