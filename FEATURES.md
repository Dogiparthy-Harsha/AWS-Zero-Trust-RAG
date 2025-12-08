# 🛡️ Feature Documentation: Zero Trust RAG

This document outlines the core security protocols and advanced usability features responsible for making this RAG (Retrieval-Augmented Generation) system enterprise-grade.

---

## 🔐 Core Security Features

### 1. Zero Trust Access Control (RBAC)
Unlike standard RAG apps that allow anyone to query any document, this system enforces **Role-Based Access Control** at the retrieval level.
*   **Mechanism**: Every document in S3 is tagged with an `access_level` attribute (`public`, `hr`, `finance`).
*   **Enforcement**: When a user queries Bedrock, a metadata filter is rigidly applied based on their session role.
    *   *Interns* can only retrieve `public` docs.
    *   *CFOs* can retrieve `finance`, `hr`, and `public` docs.
*   **Result**: It is mathematically impossible for an Intern to retrieve "Project Zeus" documents, even via prompt injection.

### 2. PII Data Masking (Presidio)
To prevent sensitive data leaks (DL), all documents undergo a sanitization process before they ever reach the cloud vector store.
*   **Technology**: Microsoft Presidio + Custom Regex Pattern Matchers.
*   **Target**: Scans for emails and phone numbers (e.g., `+1-555-xxx-xxxx`).
*   **Action**: Replaces sensitive entities with `<REDACTED>` tags.
*   **Benefit**: Even if the LLM hallucinates, it cannot reveal private contact info because it simply doesn't have it.

### 3. Secure "Speed Layer" Caching
We implemented a high-performance cache using **Amazon DynamoDB** to reduce latency and Bedrock costs.
*   **Security Isolation**: The cache key is not just the user's question. It is a composite hash of `SHA256(Role + Question)`.
*   **Prevention**: This prevents **Cache Poisoning** attacks where a low-level user asks a question previously asked by an executive and inadvertently retrieves the executive's cached answer.

### 4. DynamoDB Audit Trail
All interactions are persisted for compliance.
*   **Chat History**: Every conversation turn is logged to the `rag_users` DynamoDB table.
*   **Accountability**: User actions are traceable to their specific Employee ID, ensuring non-repudiation.

---

## 🚀 Additional Features

### 1. "Break-Glass" Access Request System
When a user is blocked from viewing data due to their security clearance, the system doesn't just stop—it enables a secure workflow to request permission.
*   **Trigger**: If the LLM responds with "I don't have enough information" or "Access Denied", a warning banner appears.
*   **Action**: A **"Request Access"** button becomes available.
*   **Backend**: Clicking this triggers an **Amazon SNS** event, instantly emailing the HR Administrator with the User's ID and the specific query they attempted.

### 2. Transparent Verified Sources
Trust is critical in enterprise AI. The system explicitly proves where it got its information.
*   **UI Integration**: Before displaying the AI's answer, the app renders a **"Verified Sources"** section.
*   **Detail**: Users can expand these dropdowns to see the exact S3 URI (e.g., `s3://.../policy_public.txt`) and the raw text snippet used by the model.

### 3. Automated Cache Invalidation
To prevent "Stale Data" vulnerabilities, the system self-heals during data updates.
*   **Workflow**: Whenever the `ingest_bedrock.py` script is run to upload new documents, it automatically triggers a `clear_cache()` function.
*   **Impact**: The `rag_cache` table is wiped clean. This ensures that users never receive outdated answers (e.g., old salary info) derived from previous document versions.

### 4. Self-Healing Authentication
The application includes a robust session management system.
*   **State Persistence**: Login state is managed via `st.session_state`, ensuring the user remains logged in even if the Streamlit app re-renders during interaction.

