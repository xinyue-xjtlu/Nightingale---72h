import unittest
import sys
import os

sys.path.insert(0, '/Users/chenxinyue/Desktop/nightingale')
from app import app

class TestRBACScope(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_patient_cannot_access_doctor_page(self):
        """Patient cannot access doctor page"""
        with self.app as c:
            c.get('/login?role=patient')
            resp = c.get('/doctor')
            self.assertEqual(resp.status_code, 302)  # Redirect to login

    def test_patient_cannot_access_nurse_page(self):
        """Patient cannot access nurse page"""
        with self.app as c:
            c.get('/login?role=patient')
            resp = c.get('/nurse')
            self.assertEqual(resp.status_code, 302)  # Redirect to login

    def test_doctor_can_access_doctor_page(self):
        """Doctor can access doctor page"""
        with self.app as c:
            c.get('/login?role=doctor')
            resp = c.get('/doctor')
            self.assertEqual(resp.status_code, 200)

    def test_doctor_cannot_access_patient_page(self):
        """Doctor cannot access patient page"""
        with self.app as c:
            c.get('/login?role=doctor')
            resp = c.get('/patient')
            self.assertEqual(resp.status_code, 302)

    def test_nurse_can_access_nurse_page(self):
        """Nurse can access nurse page"""
        with self.app as c:
            c.get('/login?role=nurse')
            resp = c.get('/nurse')
            self.assertEqual(resp.status_code, 200)

    def test_nurse_cannot_access_doctor_page(self):
        """Nurse cannot access doctor page"""
        with self.app as c:
            c.get('/login?role=nurse')
            resp = c.get('/doctor')
            self.assertEqual(resp.status_code, 302)

    def test_nurse_cannot_access_patient_page(self):
        """Nurse cannot access patient page"""
        with self.app as c:
            c.get('/login?role=nurse')
            resp = c.get('/patient')
            self.assertEqual(resp.status_code, 302)

    def test_doctor_cannot_access_nurse_page(self):
        """Doctor cannot access nurse page"""
        with self.app as c:
            c.get('/login?role=doctor')
            resp = c.get('/nurse')
            self.assertEqual(resp.status_code, 302)

    def test_patient_cannot_access_patient_select(self):
        """Patient can access patient select page"""
        with self.app as c:
            c.get('/login?role=patient')
            resp = c.get('/patient')
            self.assertEqual(resp.status_code, 200)

if __name__ == '__main__':
    unittest.main()
