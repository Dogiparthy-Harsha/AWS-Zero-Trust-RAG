import boto3
import json
import os
import time
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern # <--- Added PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# --- AWS CONFIGURATION ---
KB_ID = "RZPCGWVTQX" 
BUCKET_NAME = "rag-source-harsha-2025"
CACHE_TABLE_NAME = "rag_cache"
REGION = "us-east-1"

# --- LOCAL DATA SOURCES ---
# List of text files to read, redact, and ingest
FILES_TO_INGEST = [
    "policy_public.txt",
    "hr_sensitive_salaries.txt",
    "finance_secret_merger.txt"
]

# --- CLIENTS ---
s3 = boto3.client('s3', region_name=REGION)
bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION) # <--- NEW CLIENT
cache_table = dynamodb.Table(CACHE_TABLE_NAME)

# --- CUSTOM PRIVACY RECOGNIZERS ---
# The default Presidio model may miss specific phone formats (e.g., +1-555-xxx-xxxx).
# We register a high-confidence Regex pattern to ensure 100% detection of these numbers.
phone_pattern = Pattern(name="us_phone_dashed", regex=r"\+1-\d{3}-\d{3}-\d{4}", score=1.0)
phone_recognizer = PatternRecognizer(supported_entity="PHONE_NUMBER", patterns=[phone_pattern])

analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(phone_recognizer)
anonymizer = AnonymizerEngine()

# --- HELPER: CLEAR CACHE ---
def clear_cache():
    print(f"🧹 Clearing Cache Table '{CACHE_TABLE_NAME}'...")
    try:
        # Scan and delete is inefficient for massive tables, but perfect for this project
        scan = cache_table.scan()
        with cache_table.batch_writer() as batch:
            for each in scan['Items']:
                batch.delete_item(
                    Key={
                        'cache_key': each['cache_key']
                    }
                )
        print("✅ Cache cleared! Old answers removed.")
    except Exception as e:
        print(f"⚠️ Warning: Could not clear cache (Table might not exist yet): {e}")

# --- HELPER: REDACTION ---
def scrub_pii(text):
    """
    Uses Microsoft Presidio to detect and redact sensitive PII from text.
    
    Args:
        text (str): The raw text content to be sanitized.
        
    Returns:
        str: The sanitized text with sensitive entities replaced by <REDACTED>.
    """
    results = analyzer.analyze(text=text, entities=["EMAIL_ADDRESS", "PHONE_NUMBER"], language='en')
    return anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED>"})}
    ).text

def get_access_level(filename):
    """
    Determines the document classification based on the filename.
    
    Args:
        filename (str): The name of the file being processed.
        
    Returns:
        str: 'hr', 'finance', or 'public' based on keyword matching.
    """
    if "hr" in filename: return "hr"
    if "finance" in filename: return "finance"
    return "public"

# --- MAIN WORKFLOW ---
def main():
    print(f"🚀 Starting Ingestion to KB: {KB_ID}...")
    
    # 1. Clear old cache so users don't see stale data
    clear_cache()
    
    # 2. Process & Upload
    for fname in FILES_TO_INGEST:
        print(f"   Processing {fname}...")
        
        try:
            with open(fname, "r") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"❌ Error: File {fname} not found. Skipping.")
            continue

        clean_text = scrub_pii(content)
        
        # Metadata Sidecar
        metadata = {"metadataAttributes": {"access_level": get_access_level(fname)}}
        
        # Upload Text
        s3.put_object(Body=clean_text, Bucket=BUCKET_NAME, Key=fname)
        # Upload Metadata
        s3.put_object(Body=json.dumps(metadata), Bucket=BUCKET_NAME, Key=fname + ".metadata.json")

    # 3. Trigger Sync
    print("🔄 Triggering Bedrock Sync...")
    ds_list = bedrock_agent.list_data_sources(knowledgeBaseId=KB_ID)
    ds_id = ds_list['dataSourceSummaries'][0]['dataSourceId']
    
    try:
        job = bedrock_agent.start_ingestion_job(knowledgeBaseId=KB_ID, dataSourceId=ds_id)
        print(f"✅ Sync Job ID: {job['ingestionJob']['ingestionJobId']}")
        print("⏳ Wait 1-2 minutes for AWS to index the data.")
    except bedrock_agent.exceptions.ConflictException:
        print("⚠️  Ingestion job already running. Please wait for the current job to complete.")

if __name__ == "__main__":
    main()