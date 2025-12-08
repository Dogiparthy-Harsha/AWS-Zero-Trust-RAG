import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path so we can import app and ingest_bedrock
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules to test
# Note: app.py has global client initialization, so we might need to patch boto3 before import if strict isolation is needed.
# For this level of testing, we will patch the specific functions/clients where they are used.
import app
from ingest_bedrock import scrub_pii

class TestFunctionalRequirements(unittest.TestCase):

    # --- TEST 1: RBAC Enforcement ---
    def test_rbac_role_derivation(self):
        """
        Verify that user roles are correctly derived from their Employee ID.
        This ensures Interns are tagged as Interns.
        """
        print("\n🔎 TEST 1: Checking RBAC Role Derivation...")
        # Test Intern
        self.assertEqual(app.derive_role("in12345"), "Intern", "ID starting with 'in' should be Intern")
        # Test HR
        self.assertEqual(app.derive_role("hr999"), "HR Manager", "ID starting with 'hr' should be HR Manager")
        # Test CFO
        self.assertEqual(app.derive_role("ex001"), "CFO", "ID starting with 'ex' should be CFO")
        # Test Invalid
        self.assertIsNone(app.derive_role("unknown"), "Unknown prefix should return None")
        print("✅ RBAC Check Passed: Roles assigned correctly.")

    # --- TEST 2: PII Redaction Transparency ---
    def test_pii_redaction_custom_regex(self):
        """
        Verify that the custom Presidio regex correctly captures the specific phone format.
        """
        print("\n🔎 TEST 2: Verifying PII Redaction Logic...")
        sensitive_text = "Call me at +1-555-123-4567 regarding the merger."
        expected_redaction = "Call me at <REDACTED> regarding the merger."
        
        cleaned_text = scrub_pii(sensitive_text)
        
        self.assertIn("<REDACTED>", cleaned_text, "Phone number should be replaced with <REDACTED>")
        self.assertNotIn("+1-555-123-4567", cleaned_text, "Original phone number must not persist")
        self.assertEqual(cleaned_text, expected_redaction)
        print(f"✅ PII Check Passed: '{sensitive_text}' -> '{cleaned_text}'")

    # --- TEST 3: Secure Cache Isolation ---
    def test_cache_key_isolation(self):
        """
        Verify that an Intern and a CFO asking the same question generate DIFFERENT cache keys.
        This proves mathematically that an Intern cannot access the CFO's cached answer.
        """
        print("\n🔎 TEST 3: Checking Secure Cache Isolation...")
        query = "what is the budget for Project Zeus?"
        
        key_intern = app.generate_cache_key("Intern", query)
        key_cfo = app.generate_cache_key("CFO", query)
        
        # Keys must be non-empty strings
        self.assertTrue(key_intern)
        self.assertTrue(key_cfo)
        
        # Keys must NOT match
        self.assertNotEqual(key_intern, key_cfo, "Security Breach: Intern and CFO share the same cache key!")
        print("✅ Cache Security Passed: Intern and CFO have unique cache keys.")

    # --- TEST 4: Access Request Integration ---
    @patch('app.sns_client')
    def test_access_request_publishing(self, mock_sns):
        """
        Verify that 'send_access_request' correctly calls the AWS SNS Publish API.
        """
        print("\n🔎 TEST 4: Testing SNS Access Request Integration...")
        username = "intern_john"
        emp_id = "in999"
        query = "Show me the merger files"
        
        # Run the function
        success = app.send_access_request(username, emp_id, query)
        
        # Assertions
        self.assertTrue(success, "Function should return True on success")
        
        # Verify SNS was called exactly once
        mock_sns.publish.assert_called_once()
        
        # Verify arguments passed to SNS
        args, kwargs = mock_sns.publish.call_args
        self.assertIn(username, kwargs['Message'], "Message body should contain username")
        self.assertIn(query, kwargs['Message'], "Message body should contain the denied query")
        self.assertEqual(kwargs['TopicArn'], app.SNS_TOPIC_ARN, "Should publish to the correct ARN")
        print("✅ SNS Check Passed: Access request triggered successfully.")

    # --- TEST 5: Chat History Persistence ---
    @patch('app.user_table')
    def test_chat_history_persistence(self, mock_table):
        """
        Verify that 'save_chat_history' attempts to write to DynamoDB.
        """
        print("\n🔎 TEST 5: Verifying Chat History Persistence...")
        username = "test_user"
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        
        app.save_chat_history(username, messages)
        
        # Verify DynamoDB update_item was called
        mock_table.update_item.assert_called_once()
        
        # Check call arguments
        args, kwargs = mock_table.update_item.call_args
        self.assertEqual(kwargs['Key']['username'], username, "Should update the correct user")
        self.assertEqual(kwargs['ExpressionAttributeValues'][':h'], messages, "Should save the exact message history")
        print("✅ DB Check Passed: Chat history saved to DynamoDB.")

if __name__ == '__main__':
    unittest.main()
