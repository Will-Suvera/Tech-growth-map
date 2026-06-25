"""Unit tests for the pure partner-assembly logic in hubspot_partners.

No live HTTP — only assemble_partners (the part that filters / cleans /
dedupes already-fetched HubSpot data) is exercised.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from hubspot_partners import assemble_partners  # noqa: E402


class TestAssemblePartners(unittest.TestCase):
    def _run(self, contacts):
        return assemble_partners(
            {"A12345": 100},
            {100: list(contacts.keys())},
            contacts,
        )

    def test_any_partner_title_counts(self):
        contacts = {
            1: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "GP Partner"},
            2: {"firstname": "B", "lastname": "Two", "email": "b@nhs.net", "jobtitle": "Senior Partner"},
            3: {"firstname": "C", "lastname": "Three", "email": "c@nhs.net", "jobtitle": "GP Partner/Principal"},
            4: {"firstname": "D", "lastname": "Four", "email": "d@nhs.net", "jobtitle": "Salaried GP Partner"},
        }
        res = self._run(contacts)["A12345"]
        self.assertEqual({p["email"] for p in res},
                         {"a@nhs.net", "b@nhs.net", "c@nhs.net", "d@nhs.net"})

    def test_non_partners_excluded(self):
        contacts = {
            1: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "Practice Manager"},
            2: {"firstname": "B", "lastname": "Two", "email": "b@nhs.net", "jobtitle": "Practice Nurse"},
        }
        self.assertEqual(assemble_partners({"A12345": 100}, {100: [1, 2]}, contacts), {})

    def test_dash_name_falls_back_to_email_local_part(self):
        contacts = {1: {"firstname": "-", "lastname": "-", "email": "simon.tricker@nhs.net", "jobtitle": "GP Partner"}}
        res = self._run(contacts)["A12345"]
        self.assertEqual(res, [{"name": "simon.tricker", "email": "simon.tricker@nhs.net"}])

    def test_case_insensitive_title_match(self):
        contacts = {1: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "gp partner"}}
        self.assertEqual(len(self._run(contacts)["A12345"]), 1)

    def test_dedupes_identical_contacts(self):
        contacts = {
            1: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "GP Partner"},
            2: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "Senior Partner"},
        }
        self.assertEqual(len(self._run(contacts)["A12345"]), 1)

    def test_practice_with_no_partners_absent_from_result(self):
        contacts = {1: {"firstname": "A", "lastname": "One", "email": "a@nhs.net", "jobtitle": "Receptionist"}}
        res = assemble_partners({"A12345": 100}, {100: [1]}, contacts)
        self.assertNotIn("A12345", res)

    def test_missing_company_contacts_handled(self):
        # ODS resolved to a company that has no association entry at all.
        self.assertEqual(assemble_partners({"A12345": 100}, {}, {}), {})


if __name__ == "__main__":
    unittest.main()
