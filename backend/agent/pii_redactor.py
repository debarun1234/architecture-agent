"""
Local PII Redaction Engine
Wraps Microsoft Presidio to safely redact sensitive information locally.
"""
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class PIIRedactor:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PIIRedactor, cls).__new__(cls)
            cls._instance.analyzer = AnalyzerEngine()
            cls._instance.anonymizer = AnonymizerEngine()
            
            # Entities we want to aggressively scrub
            cls._instance.entities = [
                "PERSON",
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "CREDIT_CARD",
                "CRYPTO",
                "IP_ADDRESS",
                "US_SSN",
                "US_BANK_NUMBER"
            ]
        return cls._instance

    def redact(self, text: str) -> str:
        """
        Takes raw string text containing potential PII and returns
        a completely anonymized string where PII is replaced by tags (e.g. <PERSON>). 
        """
        if not text:
            return text
            
        results = self.analyzer.analyze(
            text=text,
            language='en',
            entities=self.entities,
            return_decision_process=False
        )
        
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        
        return anonymized_result.text
