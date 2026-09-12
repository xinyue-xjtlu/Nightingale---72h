"""RBAC tests for the three-site architecture.

Three sites (one per role) run from one process and share one patient
record. Each site:
- serves ONLY its own pages (other roles' pages are 404 on this site),
- still shows all three role cards at login, but claiming a role that is
  not the site's role is rejected and no session is created,
- uses its own session cookie, so all three roles can be signed in at the
  same time in three browser tabs,
- enforces patient identity binding (a patient can only open the record
  they claimed).
"""
import copy
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import app as app_module
import data as data_module
from app import doctor_app, nurse_app, patient_app

BASELINE = copy.deepcopy(data_module.patients)

TEXT_FIELDS = ("patient_story", "ai_suggestion",
               "doctor_diagnosis", "nurse_instructions")


def claim(client, role):
    """Claim the site's own role from its login page."""
    resp = client.get(f'/login?claim={role}')
    assert resp.status_code == 302, f'claiming {role} should redirect'
    return resp


class TestRBACScope(unittest.TestCase):
    def setUp(self):
        for p, base in zip(data_module.patients, BASELINE):
            p.update({k: base[k] for k in TEXT_FIELDS})
        app_module.reset_state()
        self.patient_client = patient_app.test_client()
        self.doctor_client = doctor_app.test_client()
        self.nurse_client = nurse_app.test_client()
        for c in (self.patient_client, self.doctor_client, self.nurse_client):
            c.testing = True

    def test_each_site_serves_only_its_own_pages(self):
        """Other roles' pages simply do not exist on this site (404)."""
        with self.patient_client as c:
            self.assertEqual(c.get('/doctor').status_code, 404)
            self.assertEqual(c.get('/nurse').status_code, 404)
            self.assertEqual(c.get('/history/1/diagnosis').status_code, 404)
        with self.doctor_client as c:
            self.assertEqual(c.get('/nurse').status_code, 404)
            self.assertEqual(c.get('/patient').status_code, 404)
            self.assertEqual(c.get('/patient/1').status_code, 404)
        with self.nurse_client as c:
            self.assertEqual(c.get('/doctor').status_code, 404)
            self.assertEqual(c.get('/patient/1').status_code, 404)

    def test_wrong_claim_is_rejected_on_every_site(self):
        """Each site shows all three cards, but only its own role works."""
        with self.patient_client as c:
            resp = c.get('/login?claim=doctor')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'not allowed', resp.data)
            resp = c.get('/login?claim=nurse')
            self.assertIn(b'not allowed', resp.data)
            # no session was created -> own pages still bounce to /
            self.assertEqual(c.get('/patient').status_code, 302)
        with self.doctor_client as c:
            resp = c.get('/login?claim=patient')
            self.assertIn(b'not allowed', resp.data)
            resp = c.get('/login?claim=nurse')
            self.assertIn(b'not allowed', resp.data)
            self.assertEqual(c.get('/doctor').status_code, 302)
        with self.nurse_client as c:
            resp = c.get('/login?claim=doctor')
            self.assertIn(b'not allowed', resp.data)
            self.assertEqual(c.get('/nurse').status_code, 302)

    def test_unauthenticated_requests_bounce_to_login(self):
        with self.patient_client as c:
            for path in ('/patient', '/patient/1', '/patient_claim/1'):
                self.assertEqual(c.get(path).status_code, 302, path)
        with self.doctor_client as c:
            self.assertEqual(c.get('/doctor').status_code, 302)
            self.assertEqual(c.get('/history/1/diagnosis').status_code, 302)
        with self.nurse_client as c:
            self.assertEqual(c.get('/nurse').status_code, 302)

    def test_patient_claims_identity_then_opens_own_record(self):
        with self.patient_client as c:
            claim(c, 'patient')
            resp = c.get('/patient')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Tom', resp.data)
            resp = c.get('/patient_claim/1')  # claim Tom
            self.assertEqual(resp.status_code, 302)
            resp = c.get('/patient/1')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'poor sleep', resp.data)  # Tom's own story

    def test_patient_cannot_open_another_patients_record(self):
        with self.patient_client as c:
            claim(c, 'patient')
            c.get('/patient_claim/2')  # claim Tina
            resp = c.get('/patient/1')  # try Tom
            self.assertEqual(resp.status_code, 302)
            self.assertNotIn(b'Tom', resp.data)  # nothing leaked
            resp = c.get('/patient/2')  # own record fine
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Tina', resp.data)

    def test_doctor_site_flow(self):
        with self.doctor_client as c:
            claim(c, 'doctor')
            resp = c.get('/doctor')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Tom', resp.data)
            self.assertIn(b'Tina', resp.data)

    def test_nurse_site_flow(self):
        with self.nurse_client as c:
            claim(c, 'nurse')
            resp = c.get('/nurse')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Tom', resp.data)

    def test_unauthenticated_write_is_rejected_and_state_unchanged(self):
        with self.doctor_client as c:
            resp = c.post('/doctor', data={'patient_id': '1',
                                           'diagnosis': 'Sneaky edit'})
            self.assertEqual(resp.status_code, 302)
        with self.nurse_client as c:
            resp = c.post('/nurse', data={'patient_id': '1',
                                          'instruction': 'Sneaky edit'})
            self.assertEqual(resp.status_code, 302)
        p = next(p for p in data_module.patients if p['id'] == 1)
        self.assertEqual(p['doctor_diagnosis_version'], 1)
        self.assertEqual(p['nurse_instructions_version'], 1)
        self.assertEqual(p['doctor_diagnosis'], BASELINE[0]['doctor_diagnosis'])

    def test_three_roles_signed_in_simultaneously(self):
        """Three tabs, three cookies, three roles at once — no clash."""
        pc, dc, nc = self.patient_client, self.doctor_client, self.nurse_client
        claim(pc, 'patient')
        pc.get('/patient_claim/1')
        claim(dc, 'doctor')
        claim(nc, 'nurse')
        self.assertEqual(pc.get('/patient/1').status_code, 200)
        self.assertEqual(dc.get('/doctor').status_code, 200)
        self.assertEqual(nc.get('/nurse').status_code, 200)

    def test_logout_clears_role(self):
        with self.doctor_client as c:
            claim(c, 'doctor')
            self.assertEqual(c.get('/doctor').status_code, 200)
            c.get('/logout')
            self.assertEqual(c.get('/doctor').status_code, 302)


if __name__ == '__main__':
    unittest.main()
