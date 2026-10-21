from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GovernanceContractTests(unittest.TestCase):
    def test_admin_enrollment_requires_hashed_token(self):
        source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("admin_enrollment_tokens", source)
        self.assertIn("hashlib.sha256(token.encode()).hexdigest()", source)
        self.assertIn("secrets.compare_digest", source)
        self.assertIn("expires_at", source)

    def test_audit_aggregates_service_events(self):
        source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        for table in ("audit_logs", "published_reports", "refresh_runs", "alert_events"):
            self.assertIn(f"table('{table}')", source)

    def test_groups_materialize_workspace_membership(self):
        source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("workspace_group_member_links", source)
        self.assertIn("workspace_direct_members", source)
        self.assertIn("_apply_effective_membership", source)

    def test_secrets_are_not_embedded_in_distributable_sources(self):
        env_example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        self.assertIn("YOUR_SUPABASE_SERVICE_ROLE_KEY", env_example)
        self.assertIn("YOUR_BREVO_API_KEY", env_example)
        self.assertNotIn("xkey" + "sib-", env_example)


if __name__ == "__main__":
    unittest.main()
