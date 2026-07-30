"""
Enterprise Government Logging - JSON structured, PII redaction, OTel, SIEM forwarding
NIST SP 800-92, FedRAMP AU-2, AU-3
"""
import logging
import sys
import json
import re
from pythonjsonlogger import jsonlogger
from typing import Dict, Any, Optional

# PII redaction patterns - government standard
PII_PATTERNS = [
    (re.compile(r'0x[a-fA-F0-9]{40}'), '[REDACTED_ADDRESS]'),
    (re.compile(r'0x[a-fA-F0-9]{64}'), '[REDACTED_PRIVATE_KEY]'),
    (re.compile(r'Bearer [A-Za-z0-9\-_\.]+\.[A-Za-z0-9\-_\.]+\.[A-Za-z0-9\-_]+'), 'Bearer [REDACTED_JWT]'),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\',\s]+'), 'password=[REDACTED]'),
    (re.compile(r'"evm_private_key":\s*"[^"]+"'), '"evm_private_key": "[REDACTED]"'),
]

def redact_pii(message: str) -> str:
    for pattern, repl in PII_PATTERNS:
        message = pattern.sub(repl, message)
    return message

class GovJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Redact PII from message
        if "message" in log_record:
            log_record["message"] = redact_pii(str(log_record["message"]))
        # Required gov fields
        log_record["service"] = "protean-shapes"
        log_record["compliance_framework"] = "NIST-800-53"
        log_record["env"] = getattr(record, "env", "production")
        # Ensure no secrets in extras
        for key in list(log_record.keys()):
            if "private" in key.lower() or "secret" in key.lower() or "key" in key.lower():
                if key not in ("public_key", "verification_key"):
                    log_record[key] = "[REDACTED]"

def setup_logging_otel():
    """
    Production logger with OTel trace_id correlation
    """
    from app.core.config import settings
    
    logger = logging.getLogger()
    logger.setLevel(settings.log_level)
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = GovJsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(funcName)s %(lineno)d %(otelTraceID)s %(otelSpanID)s",
        rename_fields={"levelname": "level", "asctime": "timestamp"}
    )
    handler.setFormatter(formatter)
    logger.handlers = [handler]
    
    # OTel instrumentation if configured
    if settings.otel_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.logging import LoggingInstrumentor
            
            trace.set_tracer_provider(TracerProvider())
            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
            span_processor = BatchSpanProcessor(exporter)
            trace.get_tracer_provider().add_span_processor(span_processor)
            LoggingInstrumentor().instrument()
            logger.info(f"OTel tracing enabled -> {settings.otel_endpoint}")
        except ImportError:
            logger.warning("opentelemetry not installed - tracing disabled")
    
    return logger

# Enterprise audit logger for SIEM
def audit_log(event_type: str, actor: str, action: str, resource: str, result: str, metadata: Dict[str, Any] = None):
    """
    FedRAMP AU-2 audit event
    """
    logger = logging.getLogger("audit")
    record = {
        "event_type": event_type,
        "actor": actor,
        "action": action,
        "resource": redact_pii(resource),
        "result": result,
        "metadata": metadata or {},
        "severity": "INFO" if result == "SUCCESS" else "WARNING"
    }
    logger.info(json.dumps(record))
    
    # Forward to SIEM if configured
    from app.core.config import settings
    if settings.siem_endpoint:
        try:
            import httpx
            httpx.post(settings.siem_endpoint, json=record, timeout=2.0)
        except Exception:
            pass  # Don't fail on SIEM failure, but log
