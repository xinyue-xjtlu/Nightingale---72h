# Nightingale — Shared Patient Record (Flask Demo)

A lightweight, role-based web app where a doctor and a nurse share one
patient record: the doctor owns the **diagnosis**, the nurse owns the
**care instructions**, and the patient gets a read-only view of their own
story plus both clinical fields. Every edit is versioned, logged in a
per-field history, and flagged to the other role as an "unseen change".

Built for the Nightingale 72-Hour Build. **All patient data is synthetic.**

---

## Features

- **Three roles, one record** — patient (read-only), doctor (diagnosis
  editor), nurse (instructions editor).
- **Field-level ownership** — the doctor can never overwrite the nurse's
  instructions and vice versa; concurrent edits on different fields are
  fully independent.
- **Version counters + edit history** — every distinct edit bumps the
  field's version and appends `{text, time, author}` to its history; the
  full history is viewable per field.
- **Unseen-change indicators** — each role's dashboard shows a dot on any
  field the *other* role has edited since they last viewed its history;
  opening the history clears it.
- **Simulated AI suggestion** — each patient carries an `ai_suggestion`
  field shown alongside the clinical record.
- **Server-side RBAC** — role checks live in the route handlers, not in
  the templates (details below).

## Project structure

```
nightingale/
├── app.py              # Flask app: routes, edit logic, versioning, seen-state
├── data.py             # patient data source (synthetic), imported by app.py
├── ATTRIBUTION.txt     # third-party libraries and licenses
├── templates/
│   ├── login.html      # role picker (patient / doctor / nurse)
│   ├── patient_select.html
│   ├── patient.html    # patient's read-only record view
│   ├── doctor.html     # doctor dashboard (diagnosis editor)
│   ├── nurse.html      # nurse dashboard (instructions editor)
│   └── history.html    # per-field edit history
└── test/
    ├── test_rbac_scope.py        # 9 role-permission tests
    └── test_concurrent_edits.py  # 7 concurrent-edit tests
```

## Quickstart

```bash
# requires Python 3.8+ and Flask
pip install flask          # if not already installed

cd nightingale
python3 app.py
# open http://127.0.0.1:5000
```

No accounts are needed — pick a role on the login page:

| Role | Sees | Can edit |
|---|---|---|
| Doctor | all patients, AI suggestions + edit history | diagnosis |
| Nurse | all patients, AI suggestions + edit history | instructions |
| Patient | own record only (story, diagnosis, instructions) | nothing |

## How RBAC is enforced

Server-side, on every request, in the route handlers:

1. Login (`/login?role=<role>`) stores the role in the Flask session
   cookie.
2. Every protected route re-checks `session.get('role')` before rendering;
   a wrong (or missing) role gets a `302` redirect back to login — never
   the protected page.
3. Write routes (`POST /doctor`, `POST /nurse`) additionally verify the
   role again before touching any field, and only ever mutate the field
   their role owns (`FIELD_KEYS` / field ownership in `app.py`).

The templates contain no permission logic — hiding a button client-side
would not protect anything; every check is verified by
`test/test_rbac_scope.py` (patient cannot reach doctor/nurse pages, doctor
cannot reach nurse pages, etc.).

## Concurrency model

- **Different fields never clash**: the doctor editing `diagnosis` and the
  nurse editing `instructions` on the same patient at the same time are
  stored independently — each field has its own version counter and
  history.
- **Same field is last-write-wins**: a re-submission of identical text is
  ignored (no version bump, no history entry); whitespace-only edits are
  dropped.
- **Stale edits become visible, not silent**: `seen` tracks, per role, the
  last version of each field that role has looked at. If the nurse edits
  the instructions, the doctor's dashboard flags that field until the
  doctor opens its history page.

Covered by `test/test_concurrent_edits.py` (7 tests), including the
cross-role unseen-change flow.

## Data & privacy

- **Synthetic data only** — Tom and Tina are fictional.
- **No real LLM calls**: the `ai_suggestion` field is static, pre-simulated
  text stored in `data.py`. Because no patient data ever leaves the
  machine, no PHI redaction step is required in the current data flow.
  (If a real LLM were ever wired in, a redaction pipeline for names/NRICs/
  phones would have to sit in front of it — see Known limitations.)
- Session state is signed server-side via Flask's `secret_key`.

## Tests

```bash
cd nightingale
python3 -m unittest discover -s test -v
```

- `test_rbac_scope.py` — role permission matrix: each role can reach its
  own pages and is redirected away from everything else.
- `test_concurrent_edits.py` — field independence, version bumps and
  history appends, identical/empty edits ignored, and the cross-role
  unseen-change detection flow.

Tests reset the app's in-memory state (`app.reset_state()`) in `setUp`,
so they are independent of each other and of the running server.

## Known limitations

- In-memory data: patients, versions and histories live in Python lists —
  they reset whenever the server restarts. A database (SQLite) is the
  obvious next step.
- The `secret_key` is a hardcoded dev value; production would load it from
  the environment.
- `app.run(debug=True)` is dev-only; production would serve via a WSGI
  server with TLS in front.
- Same-field concurrent edits are last-write-wins without an explicit
  conflict prompt.
- Any patient account can open any patient's page; per-patient ownership
  binding would be added in a real deployment.
- No real AI/LLM integration yet — connecting one requires adding a PHI
  redaction pipeline first.

## Attribution

See `ATTRIBUTION.txt` for third-party libraries (Flask, BSD-3-Clause) and
their licenses.
