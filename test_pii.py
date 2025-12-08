from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

text = "10. PAYROLL CONTACT: For direct deposit updates, contact Mary Jane at mary.jane@goliath.com or +1-415-103-4567."

analyzer = AnalyzerEngine()
results = analyzer.analyze(text=text, entities=["PHONE_NUMBER"], language='en')

print(f"Found {len(results)} phone numbers")
for res in results:
    print(res)
