# 🏦 Cloud-Native Zero Trust RAG

A secure, role-based Retrieval-Augmented Generation (RAG) system built for **Goliath National Bank**. This application demonstrates how to build an enterprise-grade internal search tool using **AWS Bedrock**, **DynamoDB**, and **Streamlit**, with a strong focus on **Zero Trust security principles** and **PII protection**.

---

## 🏗️ Architecture

The system follows a cloud-native architecture leveraging AWS managed services for scalability and security.

![Architecture Diagram](architecture.jpg)

### Key Components
1.  **Ingestion Layer**: A Python script (`ingest_bedrock.py`) that reads local documents, scrubs PII using **Microsoft Presidio**, and uploads redacted content to **Amazon S3**.
2.  **Vector Store**: **Amazon Bedrock Knowledge Base** utilizes Titan Embeddings and OpenSearch Serverless to index the redacted data.
3.  **Application Layer**: A **Streamlit** web app (`app.py`) that serves as the user interface.
4.  **State & Caching**: **Amazon DynamoDB** handles user authentication (RBAC), chat history persistence, and a "Speed Layer" cache for frequent queries.
5.  **Access Control**: Zero Trust filters are applied at the database level, ensuring Interns cannot retrieve Executive-level documents.
6.  **Alerting**: **Amazon SNS** notifies HR when a user attempts to access unauthorized data.

---

## 🗺️ Diagrams

### Sequence Diagram
Describes the flow of data from login to query retrieval, caching, and generation.
![Sequence Diagram](sequence.png)

### Use Case Diagram
Outlines the primary interactions for Users (Employees) and HR Admins.
![Use Case Diagram](use_case.png)

---

## 🚀 Setup Instructions

### 1. Prerequisites
*   **AWS Account** with permissions for Bedrock, S3, DynamoDB, and SNS.
*   **Python 3.9+** installed.
*   **AWS CLI** configured with `aws configure`.

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone <your-repo-url>
cd AWS-RAG-Project
pip install -r requirements.txt
```

### 3. AWS Resource Configuration
You need to set up the following resources in AWS `us-east-1` (N. Virginia):

1.  **S3 Bucket**: Create a bucket (e.g., `rag-source-[your_name]-2025`).
2.  **Bedrock Knowledge Base**: Create a Knowledge Base pointing to the S3 bucket. Note the `KB_ID`.
3.  **DynamoDB Tables**:
    *   `rag_users`: Partition Key = `username` (String).
    *   `rag_cache`: Partition Key = `cache_key` (String).
4.  **SNS Topic**: Create a Standard topic for alerts (e.g., `RagAccessRequests`). Subcribe your email to it.

### 4. Code Configuration
Update the configuration constants in `app.py` and `ingest_bedrock.py`:

**`app.py`**
```python
KB_ID = "YOUR_KB_ID"
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:1223334566:RagAccessRequests"
USER_TABLE_NAME = "rag_users"
CACHE_TABLE_NAME = "rag_cache"
```

**`ingest_bedrock.py`**
```python
KB_ID = "YOUR_KB_ID"
BUCKET_NAME = "your-s3-bucket-name"
FILES_TO_INGEST = ["policy_public.txt", "hr_sensitive_salaries.txt", "finance_secret_merger.txt"]
```

### 5. Ingestion (ETL Pipeline)
This script allows you to "hydrate" your Knowledge Base. It will automatically:
*   Read the local `.txt` files.
*   **Redact PII** (replace phone numbers like `+1-555...` and emails).
*   Upload to S3.
*   Trigger a Bedrock Sync Job.

```bash
python3 ingest_bedrock.py
```
*Wait for the script to say "✅ Sync Job ID: ... COMPLETE".*

### 6. Run the Application
Start the Streamlit portal:
```bash
streamlit run app.py
```

---

## 🔐 Security Features
*   **Least Privilege**: Role-based metadata filters (`access_level`) enforce data segregation.
*   **Data Masking**: `Microsoft Presidio` removes sensitive PII before it ever hits the cloud vector store.
*   **Audit Trail**: All chat history and access requests are logged.


