"""Concurrent-edit tests for the doctor/nurse shared patient record.

The app's concurrency model:
- Doctor and nurse each own their own field (diagnosis vs instructions);
  edits bump that field's version counter and append to its history.
- `seen` tracks, per role, the last version that role has looked at — the
  "unseen change" dot is how the other role discovers concurrent edits.

These tests cover: independent fields never overwrite each other, version
counters/histories behave, identical/empty edits are ignored, and the
cross-role stale-change detection works end to end.
"""
import copy
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import app as app_module
import data as data_module
from app import app, build_unseen

# Pristine snapshot taken at import time — setUp restores the live patient
# dicts from this so every test starts from the same baseline.
BASELINE = copy.deepcopy(data_module.patients)

TEXT_FIELDS = ("patient_story", "ai_suggestion",
               "doctor_diagnosis", "nurse_instructions")


class TestConcurrentEdits(unittest.TestCase):
    def setUp(self):
        # restore the original texts, then re-seed versions/histories/seen
        for p, base in zip(data_module.patients, BASELINE):
            p.update({k: base[k] for k in TEXT_FIELDS})
        app_module.reset_state()
        self.app = app.test_client()
        self.app.testing = True

    def _patient(self, patient_id):
        return next(p for p in data_module.patients if p["id"] == patient_id)

    def test_doctor_and_nurse_pages_load(self):
        """Test that both doctor and nurse pages load successfully"""
        with self.app as c:
            # Login as doctor
            c.get('/login?role=doctor')
            resp = c.get('/doctor')
            self.assertEqual(resp.status_code, 200)

            # Login as nurse
            c.get('/login?role=nurse')
            resp = c.get('/nurse')
            self.assertEqual(resp.status_code, 200)

    def test_different_fields_do_not_overwrite_each_other(self):
        """Doctor edits the diagnosis while the nurse edits instructions on
        the SAME patient: both changes persist, neither clobbers the other,
        and each field's version/history only reflects its own editor."""
        with self.app as c:
            c.get('/login?role=doctor')
            c.post('/doctor', data={'patient_id': '1',
                                    'diagnosis': 'Migraine, adjust medication'})
            c.get('/login?role=nurse')
            c.post('/nurse', data={'patient_id': '1',
                                   'instruction': 'Rest and hydrate, recheck tomorrow'})

        p = self._patient(1)
        self.assertEqual(p['doctor_diagnosis'], 'Migraine, adjust medication')
        self.assertEqual(p['nurse_instructions'], 'Rest and hydrate, recheck tomorrow')
        # each field's version was bumped by exactly its own edit
        self.assertEqual(p['doctor_diagnosis_version'], 2)
        self.assertEqual(p['nurse_instructions_version'], 2)
        # histories stay role-separated
        self.assertEqual([h['author'] for h in p['doctor_diagnosis_history']],
                         ['System', 'Doctor'])
        self.assertEqual([h['author'] for h in p['nurse_instructions_history']],
                         ['System', 'Nurse'])

    def test_editing_increments_version_and_appends_history(self):
        """Each distinct edit bumps the version and appends a labelled
        history entry; earlier entries are never destroyed."""
        with self.app as c:
            c.get('/login?role=doctor')
            c.post('/doctor', data={'patient_id': '1',
                                    'diagnosis': 'First edit'})
            c.post('/doctor', data={'patient_id': '1',
                                    'diagnosis': 'Second edit'})

        p = self._patient(1)
        self.assertEqual(p['doctor_diagnosis_version'], 3)
        self.assertEqual(len(p['doctor_diagnosis_history']), 3)
        self.assertEqual([h['text'] for h in p['doctor_diagnosis_history']],
                         [BASELINE[0]['doctor_diagnosis'], 'First edit', 'Second edit'])
        self.assertEqual([h['author'] for h in p['doctor_diagnosis_history']],
                         ['System', 'Doctor', 'Doctor'])

    def test_identical_edit_creates_no_new_version(self):
        """Re-submitting the current text is a no-op (no version bump, no
        history entry) — the guard `new_text != current` in app.py."""
        with self.app as c:
            c.get('/login?role=doctor')
            current = self._patient(1)['doctor_diagnosis']
            c.post('/doctor', data={'patient_id': '1', 'diagnosis': current})

        p = self._patient(1)
        self.assertEqual(p['doctor_diagnosis_version'], 1)
        self.assertEqual(len(p['doctor_diagnosis_history']), 1)

    def test_empty_edit_is_ignored(self):
        """Whitespace-only submissions are dropped."""
        with self.app as c:
            c.get('/login?role=doctor')
            c.post('/doctor', data={'patient_id': '1', 'diagnosis': '   '})

        p = self._patient(1)
        self.assertEqual(p['doctor_diagnosis_version'], 1)
        self.assertEqual(len(p['doctor_diagnosis_history']), 1)

    def test_stale_change_detection_between_roles(self):
        """The cross-role coordination mechanism: when the nurse edits the
        instructions, the doctor's dashboard flags that field as unseen
        until the doctor actually opens its history."""
        with self.app as c:
            # doctor catches up on both fields
            c.get('/login?role=doctor')
            c.get('/history/1/diagnosis')
            c.get('/history/1/instructions')
            self.assertFalse(build_unseen('doctor')[1]['instructions'])

            # nurse makes a concurrent edit while the doctor is away
            c.get('/login?role=nurse')
            c.post('/nurse', data={'patient_id': '1',
                                   'instruction': 'Blood test rescheduled to Friday'})

            unseen = build_unseen('doctor')
            self.assertTrue(unseen[1]['instructions'],
                            "doctor should see the nurse's new edit as unseen")
            self.assertFalse(unseen[1]['diagnosis'],
                             "diagnosis was untouched, so it must not be flagged")

            # doctor opens the history -> the flag clears
            c.get('/login?role=doctor')
            c.get('/history/1/instructions')
            self.assertFalse(build_unseen('doctor')[1]['instructions'])

    def test_same_patient_concurrent_edits_are_independent(self):
        """Both roles editing one patient at the same time: final state
        contains the doctor's diagnosis AND the nurse's instructions."""
        with self.app as c:
            c.get('/login?role=doctor')
            c.post('/doctor', data={'patient_id': '1',
                                    'diagnosis': 'CT clear, continue observation'})
            c.get('/login?role=nurse')
            c.post('/nurse', data={'patient_id': '1',
                                   'instruction': 'Schedule follow-up in one week'})

        p = self._patient(1)
        self.assertEqual(p['doctor_diagnosis'], 'CT clear, continue observation')
        self.assertEqual(p['nurse_instructions'], 'Schedule follow-up in one week')
        self.assertEqual(p['doctor_diagnosis_version'], 2)
        self.assertEqual(p['nurse_instructions_version'], 2)


if __name__ == '__main__':
    unittest.main()
