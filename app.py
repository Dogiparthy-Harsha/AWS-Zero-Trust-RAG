import streamlit as st
import boto3
import json
import time
import hashlib
import os

# --- AWS CONFIGURATION ---
KB_ID = "RZPCGWVTQX" 
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:375756730751:RagAccessRequests"
USER_TABLE_NAME = "rag_users"
CACHE_TABLE_NAME = "rag_cache"
REGION = "us-east-1"

# --- AWS CLIENTS ---
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION)
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

user_table = dynamodb.Table(USER_TABLE_NAME)
cache_table = dynamodb.Table(CACHE_TABLE_NAME)

# --- CACHING FUNCTIONS ---
def generate_cache_key(role, query):
    """
    Generates a secure, deterministic hash for caching.
    The key includes the User Role to enforce security boundaries (data isolation).
    """
    raw_key = f"{role}::{query.lower().strip()}"
    return hashlib.sha256(raw_key.encode()).hexdigest()

def check_cache(role, query):
    """
    Checking the DynamoDB 'rag_cache' table for a previous answer.
    The key is a composite of Role + Query to enforce role-based access even in the cache.
    """
    key = generate_cache_key(role, query)
    try:
        response = cache_table.get_item(Key={'cache_key': key})
        if 'Item' in response:
            return response['Item']
    except Exception as e:
        print(f"Cache Miss/Error: {e}")
    return None

def save_to_cache(role, query, answer, sources):
    """
    Persists the LLM response to DynamoDB for future speedups.
    Includes a Time-To-Live (TTL) of 24 hours to prevent stale data.
    """
    key = generate_cache_key(role, query)
    try:
        ttl = int(time.time()) + 86400 
        cache_table.put_item(
            Item={
                'cache_key': key,
                'question': query,
                'role': role,
                'answer': answer,
                'sources': sources,
                'ttl': ttl
            }
        )
    except Exception as e:
        print(f"Cache Write Error: {e}")

# --- USER MANAGEMENT FUNCTIONS ---
def derive_role(employee_id):
    """
    Heuristic to determine role based on Employee ID prefix.
    In a real app, this would be an LDAP or AD lookup.
    """
    prefix = employee_id[:2].lower()
    if prefix == "in": return "Intern"
    elif prefix == "hr": return "HR Manager"
    elif prefix == "ex": return "CFO"
    return None
def hash_password(password):
    """Converts a plain text password into a secure SHA-256 hash."""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, employee_id):
    role = derive_role(employee_id)
    if not role: return False, "Invalid ID format."
    
    if 'Item' in user_table.get_item(Key={'username': username}):
        return False, "Username taken."
    
    secure_password = hash_password(password)
        
    user_table.put_item(Item={
        'username': username,
        'password': secure_password,
        'employee_id': employee_id,
        'role': role,
        'history': []
    })
    return True, f"Account created! Role: {role}"

def check_credentials(username, password):
    """
    Validates user login against DynamoDB.
    Returns: (Role, ChatHistory, EmployeeID) or (None, [], None)
    """
    try:
        response = user_table.get_item(Key={'username': username})
        if 'Item' in response:
            user = response['Item']
            input_hash = hash_password(password)
            if user['password'] == input_hash:
                return user['role'], user.get('history', []), user.get('employee_id', 'Unknown')
    except Exception as e:
        st.error(f"DB Error: {e}")
    return None, [], None

def save_chat_history(username, messages):
    user_table.update_item(
        Key={'username': username},
        UpdateExpression="set history = :h",
        ExpressionAttributeValues={':h': messages}
    )

def send_access_request(username, emp_id, query):
    message = f"User: {username}\nID: {emp_id}\nQuery: {query}\n\nAction: Review Clearance."
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=f"RAG Access Request: {username}"
        )
        return True
    except Exception as e:
        st.error(f"SNS Error: {e}")
        return False

def logout():
    st.session_state.clear()
    st.rerun()

# --- APP ENTRY POLL ---
def main():
    st.set_page_config(page_title="Goliath National Bank", page_icon="🏦")

    # --- APP LOGIC ---
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # 1. AUTHENTICATION
    if not st.session_state['logged_in']:
        st.title("🏦 Goliath Bank Portal")
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            with st.form("login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    role, hist, eid = check_credentials(u, p)
                    if role:
                        st.session_state['logged_in'] = True
                        st.session_state['user_role'] = role
                        st.session_state['username'] = u
                        st.session_state['employee_id'] = eid
                        st.session_state['messages'] = hist
                        st.session_state['last_denial'] = None
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")

        with tab2:
            with st.form("signup"):
                nu = st.text_input("New Username")
                np = st.text_input("New Password", type="password")
                nid = st.text_input("Employee ID (in..., hr..., ex...)")
                if st.form_submit_button("Register"):
                    s, m = create_user(nu, np, nid)
                    if s: st.success(m)
                    else: st.error(m)

    # 2. MAIN APP
    else:
        with st.sidebar:
            st.write(f"👤 **{st.session_state['username']}**")
            st.caption(f"ID: {st.session_state['employee_id']}")
            st.info(f"🔑 **{st.session_state['user_role']}**")
            if st.button("Logout"): logout()

        st.title("☁️ Zero Trust RAG")

        role = st.session_state['user_role']
        # Security Filters
        if role == "Intern": search_filter = {"equals": { "key": "access_level", "value": "public" }}
        elif role == "HR Manager": search_filter = {"in": { "key": "access_level", "value": ["public", "hr"] }}
        else: search_filter = {"in": { "key": "access_level", "value": ["public", "hr", "finance"] }}

        # Display History
        for msg in st.session_state['messages']:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Chat Input
        if prompt := st.chat_input("Ask a question..."):
            st.chat_message("user").write(prompt)
            st.session_state['messages'].append({"role": "user", "content": prompt})
            st.session_state['last_denial'] = None # Reset state

            # --- STEP A: CHECK CACHE ---
            cached_data = check_cache(role, prompt)
            
            if cached_data:
                answer = cached_data['answer']
                st.chat_message("assistant").write(answer)
                st.success("⚡️ Answer retrieved from Cache (0ms latency)")
                
                if cached_data['sources']:
                    st.subheader("🔍 Verified Sources (Cached)")
                    for src in cached_data['sources']:
                        with st.expander(f"Source: {src}"):
                            st.write("(Content from cache record)")

                st.session_state['messages'].append({"role": "assistant", "content": answer})
                save_chat_history(st.session_state['username'], st.session_state['messages'])

            else:
                try:
                    # 1. Retrieve
                    response = bedrock_agent_runtime.retrieve(
                        knowledgeBaseId=KB_ID,
                        retrievalQuery={'text': prompt},
                        retrievalConfiguration={
                            'vectorSearchConfiguration': {
                                'numberOfResults': 3,
                                'filter': search_filter
                            }
                        }
                    )
                    
                    results = response['retrievalResults']
                    context_str = ""
                    source_uris = [] 
                    access_denied = False

                    if not results:
                        access_denied = True
                        answer = "🔒 **Access Denied**: No documents found matching your security clearance."
                    else:
                        st.subheader("🔍 Verified Sources")
                        for res in results:
                            text = res['content']['text']
                            uri = res['location']['s3Location']['uri']
                            source_uris.append(uri)
                            with st.expander(f"Source: {uri}"):
                                st.code(text)
                            context_str += text + "\n"
                        
                        # 2. Generate
                        claude_prompt = f"""Human: You are an internal corporate assistant. 
                        The user is an authorized employee ({role}).
                        Answer using the data below.
                        <context>{context_str}</context>
                        Question: {prompt}
                        Assistant:"""

                        model_response = bedrock_runtime.invoke_model(
                            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                            body=json.dumps({
                                "anthropic_version": "bedrock-2023-05-31",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": claude_prompt}]
                            })
                        )
                        answer = json.loads(model_response['body'].read())['content'][0]['text']
                        
                        if ("cannot" in answer.lower() or 
                            "proprietary" in answer.lower() or 
                            "<redacted>" in answer.lower() or
                            "not have" in answer.lower() or
                            "no information" in answer.lower() or
                            "context" in answer.lower() or
                            "apologize" in answer.lower()):
                            access_denied = True
                        else:
                            save_to_cache(role, prompt, answer, source_uris)

                    st.chat_message("assistant").write(answer)
                    st.session_state['messages'].append({"role": "assistant", "content": answer})
                    save_chat_history(st.session_state['username'], st.session_state['messages'])

                    if access_denied:
                        st.session_state['last_denial'] = {"query": prompt}

                except Exception as e:
                    st.error(f"AWS Error: {e}")

        # --- PERSISTENT REQUEST BUTTON ---
        if st.session_state.get('last_denial'):
            st.warning("⚠️ Information blocked due to clearance.")
            if st.button("Request Access to this Data", key="req_btn"):
                sent = send_access_request(
                    st.session_state['username'], 
                    st.session_state['employee_id'], 
                    st.session_state['last_denial']['query']
                )
                if sent:
                    st.success("✅ Request sent to HR!")
                    st.session_state['last_denial'] = None
                    time.sleep(2)
                    st.rerun()

if __name__ == "__main__":
    main()